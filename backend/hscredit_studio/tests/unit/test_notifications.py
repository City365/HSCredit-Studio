"""Phase 5 B23 通知服务 — 单元测试.

依据 docs/ROADMAP.md Phase 5 B23:

- 5 预置模板 (bill_generated / quota_near_limit / quota_exceeded /
  contract_signed / alert_cpu_high)
- 3 通道: slack / wecom / email
- render_template 变量替换
- 统一入口 send_notification 返回每通道结果
- dry_run 模式不真正发送
"""
from __future__ import annotations

import pytest

from hscredit_studio.services.notification import (
    TEMPLATES,
    EmailNotifier,
    NotificationChannel,
    NotificationTemplate,
    SlackNotifier,
    WeComNotifier,
    render_template,
    send_notification,
)


def test_notification_channel_enum():
    """NotificationChannel: 3 个枚举值."""
    assert NotificationChannel.SLACK == "slack"
    assert NotificationChannel.WECOM == "wecom"
    assert NotificationChannel.EMAIL == "email"


def test_templates_5_keys():
    """TEMPLATES: 预置 5 种模板."""
    expected = {
        "bill_generated",
        "quota_near_limit",
        "quota_exceeded",
        "contract_signed",
        "alert_cpu_high",
    }
    assert set(TEMPLATES.keys()) == expected


def test_template_has_required_fields():
    """每个模板都有 title / body / default_channels."""
    for t in TEMPLATES.values():
        assert isinstance(t, NotificationTemplate)
        assert t.title_template
        assert t.body_template
        assert len(t.default_channels) > 0


def test_render_template_basic():
    """render_template: 变量替换正确."""
    t = TEMPLATES["bill_generated"]
    title, body = render_template(
        t,
        {
            "billing_period": "2026-08",
            "tenant_name": "测试租户",
            "plan": "pro",
            "total_amount": 199.0,
            "due_date": "2026-09-26",
            "bill_id": "abc123",
        },
    )
    assert "2026-08" in title
    assert "测试租户" in body
    assert "199.00" in body


def test_render_template_missing_var():
    """render_template: 缺变量保留原始模板字符串 (不抛错)."""
    t = TEMPLATES["bill_generated"]
    title, _body = render_template(t, {})  # 缺所有变量
    # 不抛错, 保留原始模板
    assert "{" in title or "{billing_period}" in title


def test_render_template_format_spec():
    """render_template: 支持格式化规范 (:.2f / :.0%)."""
    t = TEMPLATES["quota_near_limit"]
    _title, body = render_template(
        t,
        {
            "tenant_name": "x",
            "ratio": 0.85,
            "dimension": "runs",
            "used": 170,
            "limit": 200,
        },
    )
    # 0.85 → 85% (via :.0%)
    assert "85%" in body


@pytest.mark.asyncio
async def test_slack_notifier_no_webhook_url():
    """SlackNotifier: 无 webhook URL 返回 failure."""
    notifier = SlackNotifier(webhook_url="")
    r = await notifier.send("title", "body")
    assert r.success is False
    assert "未配置" in r.error


@pytest.mark.asyncio
async def test_wecom_notifier_no_webhook_url():
    """WeComNotifier: 无 webhook URL 返回 failure."""
    notifier = WeComNotifier(webhook_url="")
    r = await notifier.send("title", "body")
    assert r.success is False
    assert "未配置" in r.error


@pytest.mark.asyncio
async def test_email_notifier_mock_file():
    """EmailNotifier: 无 SMTP 时写本地 .eml 文件 (mock)."""
    notifier = EmailNotifier(host=None)  # 无 host → 走 mock 文件
    r = await notifier.send("测试邮件", "正文内容", recipient="test@example.com")
    assert r.success is True
    assert r.dry_run is True


@pytest.mark.asyncio
async def test_email_notifier_dry_run():
    """EmailNotifier: dry_run=True 不真正发送 (有 host 也仅记录日志)."""
    notifier = EmailNotifier(host="smtp.example.com")
    r = await notifier.send("title", "body", recipient="test@example.com", dry_run=True)
    assert r.success is True
    assert r.dry_run is True


@pytest.mark.asyncio
async def test_send_notification_unknown_template():
    """send_notification: 未知模板返回 failure."""
    results = await send_notification(
        template_key="nonexistent_template",
        variables={},
        channels=[NotificationChannel.EMAIL],
    )
    assert len(results) == 1
    assert results[0].success is False
    assert "模板不存在" in results[0].error


@pytest.mark.asyncio
async def test_send_notification_dry_run_default_channels():
    """send_notification: dry_run 用模板默认 channels (contract_signed 仅 email)."""
    results = await send_notification(
        template_key="contract_signed",
        variables={
            "contract_number": "CT-NDA-2026-001",
            "contract_type": "nda",
            "valid_from": "2026-08-27",
            "valid_until": "2031-08-27",
            "contract_id": "test-id",
        },
        dry_run=True,
    )
    # contract_signed 默认 [email], 应该返回 1 个结果
    assert len(results) == 1
    assert results[0].channel == NotificationChannel.EMAIL
    assert results[0].success is True
    assert results[0].dry_run is True


@pytest.mark.asyncio
async def test_send_notification_override_channels():
    """send_notification: 指定 channels 覆盖模板默认."""
    results = await send_notification(
        template_key="contract_signed",  # 默认 [email]
        variables={
            "contract_number": "CT-NDA-2026-001",
            "contract_type": "nda",
            "valid_from": "2026-08-27",
            "valid_until": "2031-08-27",
            "contract_id": "test-id",
        },
        channels=[NotificationChannel.WECOM],  # 覆盖为 wecom
        dry_run=True,
    )
    assert len(results) == 1
    assert results[0].channel == NotificationChannel.WECOM
