"""Phase 5 B22 审计事件分类扩展 — 单元测试.

依据 docs/ROADMAP.md Phase 5 B22:

- 新事件类型: DATA_ACCESS / DATA_EXPORT / MODEL_EXPORT / PERMISSION_CHANGE /
  CONFIG_CHANGE / AUTH_FAILURE / CONTRACT_SIGN / VAT_INVOICE_APPLY /
  BILL_GENERATE / PAYMENT_INIT
- 新资源类型: DATASET / BILL / INVOICE / CONTRACT / TENANT_CONFIG /
  ROLE / MODEL_ARTIFACT
"""
from __future__ import annotations

from hscredit_studio.services.audit import AuditAction, ResourceType


def test_audit_action_data_access_added():
    """AuditAction.DATA_ACCESS: B22 新增."""
    assert AuditAction.DATA_ACCESS == "data_access"


def test_audit_action_data_export_added():
    """AuditAction.DATA_EXPORT: B22 新增."""
    assert AuditAction.DATA_EXPORT == "data_export"


def test_audit_action_model_export_added():
    """AuditAction.MODEL_EXPORT: B22 新增."""
    assert AuditAction.MODEL_EXPORT == "model_export"


def test_audit_action_permission_change_added():
    """AuditAction.PERMISSION_CHANGE: B22 新增."""
    assert AuditAction.PERMISSION_CHANGE == "permission_change"


def test_audit_action_config_change_added():
    """AuditAction.CONFIG_CHANGE: B22 新增."""
    assert AuditAction.CONFIG_CHANGE == "config_change"


def test_audit_action_auth_failure_added():
    """AuditAction.AUTH_FAILURE: B22 新增."""
    assert AuditAction.AUTH_FAILURE == "auth_failure"


def test_audit_action_contract_sign_added():
    """AuditAction.CONTRACT_SIGN: B22 新增 (Phase 4 B21 也复用)."""
    assert AuditAction.CONTRACT_SIGN == "contract_sign"


def test_audit_action_vat_invoice_apply_added():
    """AuditAction.VAT_INVOICE_APPLY: B22 新增."""
    assert AuditAction.VAT_INVOICE_APPLY == "vat_invoice_apply"


def test_audit_action_bill_generate_added():
    """AuditAction.BILL_GENERATE: B22 新增."""
    assert AuditAction.BILL_GENERATE == "bill_generate"


def test_audit_action_payment_init_added():
    """AuditAction.PAYMENT_INIT: B22 新增."""
    assert AuditAction.PAYMENT_INIT == "payment_init"


def test_resource_type_bill_added():
    """ResourceType.BILL: B22 新增."""
    assert ResourceType.BILL == "bill"


def test_resource_type_invoice_added():
    """ResourceType.INVOICE: B22 新增."""
    assert ResourceType.INVOICE == "invoice"


def test_resource_type_contract_added():
    """ResourceType.CONTRACT: B22 新增."""
    assert ResourceType.CONTRACT == "contract"


def test_resource_type_tenant_config_added():
    """ResourceType.TENANT_CONFIG: B22 新增."""
    assert ResourceType.TENANT_CONFIG == "tenant_config"


def test_resource_type_dataset_added():
    """ResourceType.DATASET: B22 新增."""
    assert ResourceType.DATASET == "dataset"


def test_resource_type_role_added():
    """ResourceType.ROLE: B22 新增."""
    assert ResourceType.ROLE == "role"


def test_resource_type_model_artifact_added():
    """ResourceType.MODEL_ARTIFACT: B22 新增."""
    assert ResourceType.MODEL_ARTIFACT == "model_artifact"


def test_audit_action_no_duplicates():
    """AuditAction: 所有 action 值唯一."""
    actions = [
        v for k, v in vars(AuditAction).items()
        if not k.startswith("_") and isinstance(v, str)
    ]
    assert len(actions) == len(set(actions)), f"重复的 action: {actions}"


def test_resource_type_no_duplicates():
    """ResourceType: 所有 resource_type 值唯一."""
    types = [
        v for k, v in vars(ResourceType).items()
        if not k.startswith("_") and isinstance(v, str)
    ]
    assert len(types) == len(set(types)), f"重复的 type: {types}"


def test_audit_action_backward_compatibility():
    """B22 新增不影响 Phase 2 已有的 action."""
    assert AuditAction.LOGIN == "login"
    assert AuditAction.LOGIN_FAILED == "login_failed"
    assert AuditAction.WORKFLOW_RUN_SUBMIT == "workflow_run_submit"
    assert AuditAction.WORKFLOW_RUN_RETRY_NODE == "workflow_run_retry_node"


def test_resource_type_backward_compatibility():
    """B22 新增不影响 Phase 2 已有的 resource_type."""
    assert ResourceType.WORKFLOW == "workflow"
    assert ResourceType.RUN == "run"
    assert ResourceType.NODE_EXECUTION == "node_execution"
    assert ResourceType.TEMPLATE == "template"
