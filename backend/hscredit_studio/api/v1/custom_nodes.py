"""自定义节点 API — Phase 6 B36.

端点列表:
- GET    /api/v1/{tenant}/custom-nodes                    列表
- POST   /api/v1/{tenant}/custom-nodes                    创建 + v1
- GET    /api/v1/{tenant}/custom-nodes/{id}               详情
- PUT    /api/v1/{tenant}/custom-nodes/{id}               更新元数据
- DELETE /api/v1/{tenant}/custom-nodes/{id}               软删除
- PUT    /api/v1/{tenant}/custom-nodes/{id}/code          提交新版本
- GET    /api/v1/{tenant}/custom-nodes/{id}/versions      版本列表
- GET    /api/v1/{tenant}/custom-nodes/{id}/versions/{vid}  版本详情
- POST   /api/v1/{tenant}/custom-nodes/{id}/versions/{vid}/rollback  回滚
- GET    /api/v1/{tenant}/custom-nodes/{id}/draft         读草稿
- PUT    /api/v1/{tenant}/custom-nodes/{id}/draft         存草稿
- DELETE /api/v1/{tenant}/custom-nodes/{id}/draft         丢弃草稿
- POST   /api/v1/{tenant}/custom-nodes/{id}/lock          申请锁
- DELETE /api/v1/{tenant}/custom-nodes/{id}/lock          释放锁
- POST   /api/v1/{tenant}/custom-nodes/{id}/lock/heartbeat 心跳
- POST   /api/v1/{tenant}/custom-nodes/{id}/validate      AST 静态校验
- POST   /api/v1/{tenant}/custom-nodes/{id}/detect-contract 反推 contract
- POST   /api/v1/{tenant}/custom-nodes/{id}/test          试运行
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from hscredit_studio.api.deps import (
    CurrentUserDep,
    SessionDep,
    TenantDep,
    require_role,
)
from hscredit_studio.core.exceptions import ResourceNotFoundError, ValidationError
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import CustomNodeVersion
from hscredit_studio.schemas.custom_node import (
    CustomNodeCreateRequest,
    CustomNodeDraftRequest,
    CustomNodeDraftResponse,
    CustomNodeListItem,
    CustomNodeListResponse,
    CustomNodeLockResponse,
    CustomNodeResponse,
    CustomNodeUpdateCodeRequest,
    CustomNodeUpdateRequest,
    CustomNodeVersionListResponse,
    CustomNodeVersionResponse,
    DetectContractRequest,
    DetectContractResponse,
    TestRunRequest,
    TestRunResponse,
    ValidateRequest,
    ValidateResponse,
    ValidationIssueResponse,
)
from hscredit_studio.schemas.node_contract import NodeContract
from hscredit_studio.services import custom_nodes as svc
from hscredit_studio.services.ast_analyzer import validate_user_code
from hscredit_studio.services.contract_inference import (
    infer_from_ast,
    infer_from_runtime,
    merge_inference,
)
from hscredit_studio.services.rbac import Role

_log = get_logger(__name__)
router = APIRouter(tags=["自定义节点"])


# ===== Helpers =====


def _to_node_response(cn) -> CustomNodeResponse:
    """手动构造响应 (避免 from_attributes 对 SoftDeleteMixin 等的兼容问题)."""
    return CustomNodeResponse(
        custom_node_id=cn.custom_node_id,
        tenant_id=cn.tenant_id,
        node_type=cn.node_type,
        name=cn.name,
        category=cn.category,
        description=cn.description,
        icon=cn.icon,
        visibility=cn.visibility,
        enabled=cn.enabled,
        contract=cn.contract or {},
        current_version_number=cn.current_version_number,
        test_run_count=cn.test_run_count,
        last_test_run_at=cn.last_test_run_at,
        locked_by=cn.locked_by,
        locked_at=cn.locked_at,
        created_by=cn.created_by,
        created_at=cn.created_at,
        updated_at=cn.updated_at,
    )


def _to_list_item(cn) -> CustomNodeListItem:
    return CustomNodeListItem(
        custom_node_id=cn.custom_node_id,
        node_type=cn.node_type,
        name=cn.name,
        category=cn.category,
        visibility=cn.visibility,
        enabled=cn.enabled,
        icon=cn.icon,
        current_version_number=cn.current_version_number,
        test_run_count=cn.test_run_count,
        last_test_run_at=cn.last_test_run_at,
        updated_at=cn.updated_at,
    )


def _to_version_response(v) -> CustomNodeVersionResponse:
    return CustomNodeVersionResponse(
        version_id=v.version_id,
        custom_node_id=v.custom_node_id,
        version_number=v.version_number,
        code=v.code,
        contract=v.contract or {},
        requirements=v.requirements,
        change_summary=v.change_summary,
        created_by=v.created_by,
        created_at=v.created_at,
    )


def _user_id(user: dict) -> uuid.UUID | None:
    """从 CurrentUserDep dict 拿 user_id.

    JWT payload 的 subject 在 ``sub`` 字段 (字符串 UUID).
    """
    raw = user.get("user_id") or user.get("sub")
    if raw is None:
        return None
    return uuid.UUID(raw) if isinstance(raw, str) else raw


# ===== 端点 =====


@router.get(
    "",
    response_model=CustomNodeListResponse,
    summary="列出本租户的自定义节点",
)
async def list_custom_nodes(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    category: str | None = Query(default=None),
    visibility: str | None = Query(default=None),
    enabled_only: bool = Query(default=True),
    search: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CustomNodeListResponse:
    """列出自定义节点 (按租户隔离)."""
    items, total = await svc.list_nodes(
        session,
        tenant_id=tenant_id,
        category=category,
        visibility=visibility,
        enabled_only=enabled_only,
        search=search,
        page=page,
        page_size=page_size,
    )
    return CustomNodeListResponse(
        items=[_to_list_item(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=CustomNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建自定义节点 (+v1)",
    dependencies=[__import__("fastapi").Depends(require_role(Role.TENANT_ADMIN))],
)
async def create_custom_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    payload: CustomNodeCreateRequest,
) -> CustomNodeResponse:
    """创建自定义节点. 自动创建 v1 版本 + node_definitions 缓存."""
    cn = await svc.create_node(
        session,
        tenant_id=tenant_id,
        user_id=_user_id(user),
        node_type=payload.node_type,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        icon=payload.icon,
        visibility=payload.visibility,
        code=payload.code,
        contract=payload.contract,
        requirements=payload.requirements,
    )
    return _to_node_response(cn)


@router.get(
    "/{custom_node_id}",
    response_model=CustomNodeResponse,
    summary="自定义节点详情",
)
async def get_custom_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> CustomNodeResponse:
    cn = await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    return _to_node_response(cn)


@router.put(
    "/{custom_node_id}",
    response_model=CustomNodeResponse,
    summary="更新节点元数据",
)
async def update_custom_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    payload: CustomNodeUpdateRequest,
) -> CustomNodeResponse:
    cn = await svc.update_node_meta(
        session,
        custom_node_id=custom_node_id,
        tenant_id=tenant_id,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        icon=payload.icon,
        visibility=payload.visibility,
        enabled=payload.enabled,
    )
    return _to_node_response(cn)


@router.delete(
    "/{custom_node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除节点",
)
async def delete_custom_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> None:
    await svc.soft_delete_node(
        session, custom_node_id=custom_node_id, tenant_id=tenant_id
    )


@router.put(
    "/{custom_node_id}/code",
    response_model=CustomNodeVersionResponse,
    summary="提交新版本代码",
)
async def update_custom_node_code(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    payload: CustomNodeUpdateCodeRequest,
) -> CustomNodeVersionResponse:
    v = await svc.update_code(
        session,
        custom_node_id=custom_node_id,
        tenant_id=tenant_id,
        user_id=_user_id(user),
        code=payload.code,
        contract=payload.contract,
        change_summary=payload.change_summary,
    )
    return _to_version_response(v)


@router.get(
    "/{custom_node_id}/versions",
    response_model=CustomNodeVersionListResponse,
    summary="版本列表",
)
async def list_versions(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> CustomNodeVersionListResponse:
    cn = await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    versions = await svc.list_versions(session, custom_node_id=cn.custom_node_id, tenant_id=tenant_id)
    return CustomNodeVersionListResponse(
        items=[_to_version_response(v) for v in versions],
        total=len(versions),
    )


@router.get(
    "/{custom_node_id}/versions/{version_id}",
    response_model=CustomNodeVersionResponse,
    summary="版本详情",
)
async def get_version(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    version_id: uuid.UUID,
) -> CustomNodeVersionResponse:
    v = await svc.get_version(
        session,
        custom_node_id=custom_node_id,
        version_id=version_id,
        tenant_id=tenant_id,
    )
    return _to_version_response(v)


@router.post(
    "/{custom_node_id}/versions/{version_id}/rollback",
    response_model=CustomNodeVersionResponse,
    summary="回滚到指定版本",
)
async def rollback_version(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    version_id: uuid.UUID,
) -> CustomNodeVersionResponse:
    new_ver = await svc.rollback(
        session,
        custom_node_id=custom_node_id,
        version_id=version_id,
        tenant_id=tenant_id,
        user_id=_user_id(user),
    )
    return _to_version_response(new_ver)


# ===== 草稿 =====


@router.get(
    "/{custom_node_id}/draft",
    response_model=CustomNodeDraftResponse,
    summary="取草稿",
)
async def get_draft(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> CustomNodeDraftResponse:
    await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    draft = await svc.get_draft(session, custom_node_id=custom_node_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_DRAFT_NOT_FOUND", "message": "草稿不存在"},
        )
    return CustomNodeDraftResponse.model_validate(draft)


@router.put(
    "/{custom_node_id}/draft",
    response_model=CustomNodeDraftResponse,
    summary="保存草稿 (静默调用, 防抖自动保存)",
)
async def save_draft(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    payload: CustomNodeDraftRequest,
) -> CustomNodeDraftResponse:
    await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    draft = await svc.save_draft(
        session,
        custom_node_id=custom_node_id,
        code=payload.code,
        contract_preview=payload.contract_preview,
        validation_status=payload.validation_status,
        validation_issues=payload.validation_issues,
    )
    return CustomNodeDraftResponse.model_validate(draft)


@router.delete(
    "/{custom_node_id}/draft",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="丢弃草稿",
)
async def discard_draft(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> None:
    await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    await svc.discard_draft(session, custom_node_id=custom_node_id)


# ===== 编辑锁 =====


@router.post(
    "/{custom_node_id}/lock",
    response_model=CustomNodeLockResponse,
    summary="申请编辑锁 (进入编辑页时调用)",
)
async def acquire_lock(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> CustomNodeLockResponse:
    cn = await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    lock = await svc.acquire_lock(
        session,
        node_type=cn.node_type,
        tenant_id=tenant_id,
        user_id=_user_id(user),
    )
    return CustomNodeLockResponse.model_validate(lock)


@router.delete(
    "/{custom_node_id}/lock",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="释放编辑锁 (离开编辑页时调用)",
)
async def release_lock(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> None:
    cn = await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    await svc.release_lock(
        session,
        node_type=cn.node_type,
        tenant_id=tenant_id,
        user_id=_user_id(user),
    )


@router.post(
    "/{custom_node_id}/lock/heartbeat",
    response_model=CustomNodeLockResponse,
    summary="心跳续期 (每 2 分钟)",
)
async def heartbeat_lock(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
) -> CustomNodeLockResponse:
    cn = await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    lock = await svc.heartbeat_lock(
        session,
        node_type=cn.node_type,
        tenant_id=tenant_id,
        user_id=_user_id(user),
    )
    return CustomNodeLockResponse.model_validate(lock)


# ===== 校验 / 反推 / 试运行 =====


@router.post(
    "/{custom_node_id}/validate",
    response_model=ValidateResponse,
    summary="AST 静态校验 (不持久化, 即时返回)",
)
async def validate_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    payload: ValidateRequest,
) -> ValidateResponse:
    """快速静态校验 — 不入库, 仅返回 valid/issues/ast_preview."""
    await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    result = validate_user_code(payload.code)
    return ValidateResponse(
        valid=result.valid,
        issues=[
            ValidationIssueResponse(
                line=i.line,
                column=i.column,
                severity=i.severity,
                rule=i.rule,
                message=i.message,
            )
            for i in result.issues
        ],
        ast_preview=result.ast_preview.to_dict() if result.ast_preview else None,
    )


@router.post(
    "/{custom_node_id}/detect-contract",
    response_model=DetectContractResponse,
    summary="反推 contract (AST + 可选试运行)",
)
async def detect_contract(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    payload: DetectContractRequest,
) -> DetectContractResponse:
    """反推 contract — 静态 AST 给结构, 可选试运行给类型."""
    await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    ast_result = infer_from_ast(payload.code)
    runtime_result = None
    if payload.sample_data:
        # 简化: 不真跑试运行, 只用 sample 列名生成 placeholder
        runtime_result = infer_from_runtime({
            k: v for k, v in payload.sample_data.get("columns", {}).items() if isinstance(v, str)
        }) if isinstance(payload.sample_data.get("columns"), dict) else None
    merged = merge_inference(
        ast_result,
        runtime_result,
        node_type=ast_result.get("class_name") or "",
        name=ast_result.get("class_name") or "",
    )
    return DetectContractResponse(
        draft_contract=merged.draft_contract.to_dict(),
        ast_inferred=merged.ast_inferred,
        runtime_inferred=merged.runtime_inferred,
        warnings=merged.warnings,
    )


@router.post(
    "/{custom_node_id}/test",
    response_model=TestRunResponse,
    summary="沙箱试运行 (阶段 3 完整集成)",
)
async def test_run(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    custom_node_id: uuid.UUID,
    payload: TestRunRequest,
) -> TestRunResponse:
    """试运行 — 阶段 3 完整沙箱执行.

    流程:
    1. 静态校验 (AST) — 拦截明显错误
    2. 解析 version_id (默认 current_version)
    3. 调 UserSandbox.execute() (subprocess + RestrictedPython + setrlimit)
    4. 记录 CustomNodeTestRun (状态/日志/资源)
    5. 返回 outputs / logs / error

    风险:
    - 当前是子进程沙箱, 不是 Docker. 多租户共用宿主机, 信任度需配合 RBAC.
    """
    import time
    cn = await svc.get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)

    # 选 version (默认 current — 通过 version_number 找最新 version_id)
    version_id = payload.version_id
    if version_id is None:
        # 用 current_version_number 找最新版本的 id
        if cn.current_version_number is None:
            raise ValidationError("节点没有当前版本, 请先提交代码")
        version = await session.scalar(
            select(CustomNodeVersion).where(
                CustomNodeVersion.custom_node_id == cn.custom_node_id,
                CustomNodeVersion.version_number == cn.current_version_number,
            )
        )
        if version is None:
            raise ResourceNotFoundError("无法定位当前版本")
        version_id = version.version_id

    # 取 version 实际 code (支持回滚后用旧版本试运行)
    code = cn.code
    if payload.version_id and payload.version_id != cn.current_version_number:
        version = await session.get(CustomNodeVersion, version_id)
        if version is None or version.custom_node_id != cn.custom_node_id:
            raise ResourceNotFoundError(f"version {version_id} not found")
        code = version.code

    user_id = _user_id(user)

    # 1. AST 预校验 (快速失败)
    from hscredit_studio.services.ast_analyzer import validate_user_code
    ast_result = validate_user_code(code)
    if not ast_result.valid:
        await svc.record_test_run(
            session,
            custom_node_id=cn.custom_node_id,
            tenant_id=tenant_id,
            version_id=version_id,
            triggered_by=user_id,
            status="failed",
            log="; ".join(f"{i.rule}: {i.message}" for i in ast_result.issues),
            duration_ms=0,
        )
        return TestRunResponse(
            test_run_id=uuid.uuid4(),
            status="failed",
            duration_ms=0,
            outputs=None,
            logs=[f"{i.rule}: {i.message}" for i in ast_result.issues],
            error={"code": "E_VALIDATION_ERROR", "message": "静态校验未通过"},
        )

    # 2. 沙箱执行
    from hscredit_studio.services.user_sandbox import UserSandbox, UserSandboxTimeout, UserSandboxOOM, UserSandboxError

    # 把 sample_data (dict) 注入 sample_inputs (供 DataFrame 端口)
    final_inputs = dict(payload.sample_inputs or {})
    if payload.sample_data:
        # sample_data 一般形如 {columns: [...], rows: [...]} 或 {column_name: value}
        for key, value in payload.sample_data.items():
            if key not in final_inputs:
                final_inputs[key] = value

    # 自定义节点沙箱: 默认 60s timeout 偏长, 试运行用 30s 防止恶意死循环拖住 worker
    sb = UserSandbox(timeout_sec=30)
    started = time.monotonic()
    try:
        # UserSandbox.execute 是同步方法, 用 to_thread 避免阻塞 event loop
        outputs, usage = await asyncio.to_thread(
            sb.execute,
            code=code,
            sample_inputs=final_inputs,
            sample_params=payload.sample_params or {},
            node_type=cn.node_type,
        )
    except UserSandboxTimeout as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        await svc.record_test_run(
            session,
            custom_node_id=cn.custom_node_id,
            tenant_id=tenant_id,
            version_id=version_id,
            triggered_by=user_id,
            status="timeout",
            log=str(e),
            duration_ms=duration_ms,
        )
        return TestRunResponse(
            test_run_id=uuid.uuid4(),
            status="timeout",
            duration_ms=duration_ms,
            error={"code": "SANDBOX_TIMEOUT", "message": str(e)},
        )
    except UserSandboxOOM as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        await svc.record_test_run(
            session,
            custom_node_id=cn.custom_node_id,
            tenant_id=tenant_id,
            version_id=version_id,
            triggered_by=user_id,
            status="oom",
            log=str(e),
            duration_ms=duration_ms,
        )
        return TestRunResponse(
            test_run_id=uuid.uuid4(),
            status="oom",
            duration_ms=duration_ms,
            error={"code": "SANDBOX_OOM", "message": str(e)},
        )
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        import traceback as _tb
        _tb.print_exc(file=_sys.stderr)
        await svc.record_test_run(
            session,
            custom_node_id=cn.custom_node_id,
            tenant_id=tenant_id,
            version_id=version_id,
            triggered_by=user_id,
            status="failed",
            log=str(e),
            duration_ms=duration_ms,
        )
        return TestRunResponse(
            test_run_id=uuid.uuid4(),
            status="failed",
            duration_ms=duration_ms,
            error={"code": "E_SANDBOX_EXECUTION", "message": str(e)},
        )

    # 3. 处理 outputs (从 sandbox result dict)
    final_outputs = outputs
    final_logs: list[str] = []
    final_error: dict[str, Any] | None = None
    status = "success"
    if isinstance(outputs, dict) and "__sandbox_error__" in outputs:
        # worker 返回的错误 dict
        err = outputs["__sandbox_error__"]
        status = "failed"
        final_outputs = None
        final_error = {
            "code": err.get("code", "E_UNKNOWN"),
            "message": err.get("message", ""),
            "details": err.get("details", {}),
        }
        final_logs.append(f"[{err.get('exception_type', 'Error')}] {err.get('message', '')}")

    duration_ms = int((time.monotonic() - started) * 1000)
    await svc.record_test_run(
        session,
        custom_node_id=cn.custom_node_id,
        tenant_id=tenant_id,
        version_id=version_id,
        triggered_by=user_id,
        status=status,
        log="\n".join(final_logs) if final_logs else None,
        duration_ms=duration_ms,
    )

    try:
        resp = TestRunResponse(
            test_run_id=uuid.uuid4(),
            status=status,
            duration_ms=duration_ms,
            outputs=final_outputs,
            logs=final_logs,
            resource_usage=usage.to_dict() if usage else None,
            error=final_error,
        )
        return resp
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        raise


__all__ = ["router"]
