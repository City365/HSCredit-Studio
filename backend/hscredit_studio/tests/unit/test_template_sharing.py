"""Phase 6 B31 — 自定义模板共享单元测试.

依据 docs/ROADMAP.md Phase 6 B31:

- 从 Workflow 发布为租户模板 (publish_workflow_as_template)
- 跨租户共享申请 (request_cross_tenant_share)
- 审核状态机 (review_template + TEMPLATE_REVIEW_TRANSITIONS)
- 审核日志 (TemplateReviewLog)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hscredit_studio.services.template_sharing import (
    TEMPLATE_REVIEW_TRANSITIONS,
    publish_workflow_as_template,
    request_cross_tenant_share,
    review_template,
)

# ===== 审核状态机 =====


def test_review_state_machine_legal_transitions():
    """TEMPLATE_REVIEW_TRANSITIONS 状态机定义合理."""
    assert "pending" in TEMPLATE_REVIEW_TRANSITIONS["draft"]
    assert "approved" in TEMPLATE_REVIEW_TRANSITIONS["pending"]
    assert "rejected" in TEMPLATE_REVIEW_TRANSITIONS["pending"]
    assert "draft" in TEMPLATE_REVIEW_TRANSITIONS["rejected"]


def test_review_state_machine_no_skip():
    """draft 不能直接 → approved (须经 pending)."""
    assert "approved" not in TEMPLATE_REVIEW_TRANSITIONS["draft"]


def test_review_state_machine_approved_can_reapply():
    """approved → pending 允许重新申请."""
    assert "pending" in TEMPLATE_REVIEW_TRANSITIONS["approved"]


# ===== request_cross_tenant_share 输入校验 =====


@pytest.mark.asyncio
async def test_request_share_empty_tenants_raises(monkeypatch):
    """target_tenants 空列表抛 ValidationError."""
    from hscredit_studio.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="target_tenants"):
        await request_cross_tenant_share(
            session=MagicMock(),
            template_id=uuid4(),
            requester_id=uuid4(),
            target_tenants=[],
            reason=None,
        )


# ===== publish_workflow 输入校验 =====


@pytest.mark.asyncio
async def test_publish_invalid_visibility_raises(monkeypatch):
    """publish 非法 visibility 抛 ValidationError."""
    from hscredit_studio.core.exceptions import ValidationError

    # 构造一个足够 mock 的 session
    session = MagicMock()
    with pytest.raises(ValidationError, match="非法 visibility"):
        await publish_workflow_as_template(
            session=session,
            tenant_id=uuid4(),
            user_id=uuid4(),
            workflow_id=uuid4(),
            template_name="x",
            description=None,
            tags=[],
            visibility="invalid",
        )


# ===== review_template 输入校验 =====


@pytest.mark.asyncio
async def test_review_nonexistent_template_raises(monkeypatch):
    """review 不存在的模板抛 FeatureNotFoundError."""
    from hscredit_studio.core.exceptions import FeatureNotFoundError

    tid = uuid4()
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    with pytest.raises(FeatureNotFoundError, match="不存在"):
        await review_template(
            session=session,
            template_id=tid,
            reviewer_id=uuid4(),
            approve=True,
        )


@pytest.mark.asyncio
async def test_review_non_pending_template_raises(monkeypatch):
    """review draft 状态模板 (非 pending) 抛 ValidationError."""
    from hscredit_studio.core.exceptions import ValidationError

    tid = uuid4()
    template = MagicMock()
    template.deleted_at = None
    template.review_status = "draft"
    session = MagicMock()
    session.get = AsyncMock(return_value=template)

    with pytest.raises(ValidationError, match="不允许审核"):
        await review_template(
            session=session,
            template_id=tid,
            reviewer_id=uuid4(),
            approve=True,
        )


# ===== 服务层模块导入 =====


def test_template_sharing_module_imports():
    """验证 module 可被导入."""
    from hscredit_studio.services import template_sharing

    assert hasattr(template_sharing, "publish_workflow_as_template")
    assert hasattr(template_sharing, "request_cross_tenant_share")
    assert hasattr(template_sharing, "review_template")
    assert hasattr(template_sharing, "TEMPLATE_REVIEW_TRANSITIONS")


# ===== Schemas 校验 =====


def test_publish_workflow_request_validation():
    """PublishWorkflowRequest 模板名必填 1-255."""
    from pydantic import ValidationError

    from hscredit_studio.schemas.template_sharing import PublishWorkflowRequest

    with pytest.raises(ValidationError):
        PublishWorkflowRequest(template_name="")
    with pytest.raises(ValidationError):
        PublishWorkflowRequest(template_name="x" * 256)
    # OK
    PublishWorkflowRequest(template_name="x")
    PublishWorkflowRequest(template_name="x", visibility="public", tags=["a", "b"])


def test_review_decision_request_validation():
    """ReviewDecisionRequest approve 必填, rejection_reason 可选."""
    from hscredit_studio.schemas.template_sharing import ReviewDecisionRequest

    r = ReviewDecisionRequest(approve=True, comment="OK")
    assert r.approve is True
    assert r.granted_tenants == []


def test_cross_tenant_share_request_min():
    """CrossTenantShareRequest target_tenants 至少 1 个."""
    from pydantic import ValidationError

    from hscredit_studio.schemas.template_sharing import CrossTenantShareRequest

    with pytest.raises(ValidationError):
        CrossTenantShareRequest(target_tenants=[])
    # OK
    CrossTenantShareRequest(target_tenants=[uuid4()], reason="test")
