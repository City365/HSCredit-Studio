"""单元测试 — 异常体系."""
import pytest
from hscredit_studio.core.exceptions import (
    HSCreditWorkflowError, ValidationError, InputValidationError,
    AuthenticationError, TenantForbiddenError, FeatureNotFoundError,
    NodeNotFoundError, StateError, NotFittedError, WorkflowParseError,
    NodeExecutionError, DependencyError, SerializationError,
    raise_not_fitted, raise_feature_not_found,
)


def test_base_exception_to_dict():
    e = HSCreditWorkflowError("test error", details={"foo": "bar"})
    d = e.to_dict()
    assert d["code"] == "E_INTERNAL"
    assert d["message"] == "test error"
    assert d["details"] == {"foo": "bar"}


def test_validation_error_inheritance():
    e = ValidationError("invalid input")
    assert isinstance(e, HSCreditWorkflowError)
    assert e.code == "E_VALIDATION_INPUT"
    assert e.http_status == 400


def test_authentication_error():
    e = AuthenticationError("auth failed")
    assert e.code == "E_AUTH_REQUIRED"
    assert e.http_status == 401


def test_tenant_forbidden_error():
    e = TenantForbiddenError("wrong tenant")
    assert e.code == "E_TENANT_FORBIDDEN"
    assert e.http_status == 403


def test_state_error():
    e = StateError("invalid state")
    assert e.code == "E_STATE_INVALID"
    assert e.http_status == 409


def test_not_fitted_error():
    e = NotFittedError("not fitted")
    assert isinstance(e, StateError)
    assert e.code == "E_NOT_FITTED"


def test_workflow_parse_error():
    e = WorkflowParseError("cycle detected")
    assert e.code == "E_WORKFLOW_PARSE"
    assert e.http_status == 400


def test_dependency_error():
    e = DependencyError("db unavailable")
    assert e.code == "E_DEPENDENCY_UNAVAILABLE"
    assert e.http_status == 503


def test_serialization_error():
    e = SerializationError("cannot serialize")
    assert e.code == "E_SERIALIZATION"
    assert e.http_status == 500


def test_raise_not_fitted_helper():
    with pytest.raises(NotFittedError) as exc_info:
        raise_not_fitted("csv_ingest")
    assert "csv_ingest" in str(exc_info.value)


def test_raise_feature_not_found_helper():
    with pytest.raises(FeatureNotFoundError) as exc_info:
        raise_feature_not_found("user_id")
    assert "user_id" in str(exc_info.value)


def test_exception_with_no_details():
    e = ValidationError("simple error")
    d = e.to_dict()
    assert d["code"] == "E_VALIDATION_INPUT"
    assert d["message"] == "simple error"
    assert "details" not in d


def test_node_not_found_error():
    e = NodeNotFoundError("node missing")
    assert e.code == "E_NODE_NOT_FOUND"
    assert e.http_status == 404


def test_node_execution_error():
    e = NodeExecutionError("node failed")
    assert e.code == "E_NODE_EXECUTION"
    assert e.http_status == 500


def test_input_validation_error_inheritance():
    """InputValidationError 应继承自 ValidationError."""
    e = InputValidationError("bad input")
    assert isinstance(e, ValidationError)
    assert isinstance(e, HSCreditWorkflowError)
    assert e.code == "E_VALIDATION_INPUT"