"""workflow 后端统一异常体系.

设计要点：
- 单一基类 :class:`HSCreditWorkflowError`，便于调用方 ``except``。
- 每个异常携带 ``code``（机器可读错误码）和 ``http_status``（HTTP 状态码），
  供 FastAPI exception handler 渲染为统一 JSON 响应。
- ``InputTypeError`` 同时作为 ``ValidationError`` 子类（覆盖类型不匹配场景）。
- ``NotFittedError`` 同时作为 ``StateError`` 子类（HSCredit 库命名兼容）。
- 提供便捷抛出函数 ``raise_not_fitted`` / ``raise_feature_not_found`` /
  ``raise_state_error``，与 hscredit 库命名保持一致。
"""

from __future__ import annotations

from typing import Any


class HSCreditWorkflowError(Exception):
    """所有 workflow 自定义异常的基类.

    Attributes
    ----------
    code:
        机器可读错误码（如 ``"E_VALIDATION_INPUT"``）。
    http_status:
        HTTP 响应状态码（默认 500）。
    """

    code: str = "E_INTERNAL"
    http_status: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """渲染为统一错误响应结构.

        Returns
        -------
        dict
            ``{"code": ..., "message": ...[, "details": ...]}``
            无 details 时省略 "details" 键。
        """
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ===== 校验类（400） =====


class ValidationError(HSCreditWorkflowError):
    """参数或数据校验失败（通用基类）."""

    code = "E_VALIDATION_INPUT"
    http_status = 400


class InputValidationError(ValidationError):
    """输入数据校验失败."""

    code = "E_VALIDATION_INPUT"
    http_status = 400


class InputTypeError(ValidationError):
    """输入类型不符合要求."""

    code = "E_TYPE_MISMATCH"
    http_status = 400


# ===== 资源缺失类（404） =====


class FeatureNotFoundError(HSCreditWorkflowError):
    """特征或字段不存在."""

    code = "E_FEATURE_NOT_FOUND"
    http_status = 404


class NodeNotFoundError(HSCreditWorkflowError):
    """节点不存在或已删除."""

    code = "E_NODE_NOT_FOUND"
    http_status = 404


# ===== 状态/状态机类（409） =====


class StateError(HSCreditWorkflowError):
    """对象状态不符合预期（例如状态机非法转移）."""

    code = "E_STATE_INVALID"
    http_status = 409


class NotFittedError(StateError):
    """对象尚未完成 fit/初始化（例如未训练即预测）.

    与 hscredit 库的 :class:`hscredit.exceptions.NotFittedError` 命名兼容。
    """

    code = "E_NOT_FITTED"
    http_status = 409


# ===== 工作流解析与执行 =====


class WorkflowParseError(HSCreditWorkflowError):
    """工作流定义解析失败（JSON/YAML 格式、节点引用、循环依赖等）."""

    code = "E_WORKFLOW_PARSE"
    http_status = 400


class NodeExecutionError(HSCreditWorkflowError):
    """节点执行期间抛出的异常（被统一捕获后包装）."""

    code = "E_NODE_EXECUTION"
    http_status = 500


# ===== 外部依赖/序列化 =====


class DependencyError(HSCreditWorkflowError):
    """缺少或不可用外部依赖（数据库、对象存储、SMTP 等）."""

    code = "E_DEPENDENCY_UNAVAILABLE"
    http_status = 503


class SerializationError(HSCreditWorkflowError):
    """序列化或反序列化失败（如 JSON/Parquet/PMML）."""

    code = "E_SERIALIZATION"
    http_status = 500


# ===== 鉴权类（401/403） =====


class AuthenticationError(HSCreditWorkflowError):
    """未提供或无效的访问凭据."""

    code = "E_AUTH_REQUIRED"
    http_status = 401


class TenantForbiddenError(HSCreditWorkflowError):
    """无权访问指定租户（跨租户越权）."""

    code = "E_TENANT_FORBIDDEN"
    http_status = 403


# ===== 便捷抛出函数 =====


def raise_not_fitted(node_type: str | None = None) -> None:
    """抛出 :class:`NotFittedError` 的辅助函数.

    Parameters
    ----------
    node_type:
        节点类型名（如 ``"OptimalBinning"``），用于错误信息。
        为 None 时使用通用文案。
    """
    if node_type:
        raise NotFittedError(
            f"{node_type} 尚未拟合，请先调用 fit 方法",
            details={"node_type": node_type},
        )
    raise NotFittedError("组件尚未拟合，请先调用 fit 方法")


def raise_feature_not_found(feature_name: str, owner_name: str = "特征") -> None:
    """抛出 :class:`FeatureNotFoundError` 的辅助函数.

    Parameters
    ----------
    feature_name:
        缺失的特征名。
    owner_name:
        上下文（如 ``"工作流"``、``"评分卡"``），中文。
    """
    raise FeatureNotFoundError(
        f"{owner_name} '{feature_name}' 未找到",
        details={"feature_name": feature_name, "owner": owner_name},
    )


def raise_state_error(message: str, **details: Any) -> None:
    """抛出 :class:`StateError` 的辅助函数.

    Parameters
    ----------
    message:
        中文错误描述。
    **details:
        附加上下文，会合并到 ``details`` 字段。
    """
    raise StateError(message, details=details or None)


__all__ = [
    "AuthenticationError",
    "DependencyError",
    "FeatureNotFoundError",
    "HSCreditWorkflowError",
    "InputTypeError",
    "InputValidationError",
    "NodeExecutionError",
    "NodeNotFoundError",
    "NotFittedError",
    "SerializationError",
    "StateError",
    "TenantForbiddenError",
    "ValidationError",
    "WorkflowParseError",
    "raise_feature_not_found",
    "raise_not_fitted",
    "raise_state_error",
]
