"""节点基类 — 所有节点的统一接口.

设计要点(依据 :file:`docs/design/01-system-architecture.md` 第 1.5 节):

- 子类必须定义 :class:`NodeContract` 类变量 ``contract``。
- :meth:`BaseNode.run` 是唯一业务入口;
  executor 通过本类访问 ``run`` / ``validate_inputs`` / ``validate_params``。
- 业务错误统一抛 :class:`HSCreditWorkflowError` (与本项目异常体系对齐);
  抛其他异常会被 executor 视为系统错误并按 ``contract.retryable`` 决定是否重试。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from hscredit_studio.schemas.node_contract import NodeContract


class BaseNode(ABC):
    """所有节点的基类.

    子类必须:

    1. 定义 ``contract`` 类变量(:class:`NodeContract` 实例)。
    2. 实现 :meth:`run` 方法。

    ``run`` 方法应当:

    - 接受上游节点的输出(``key`` 对应 ``contract.outputs`` 的 ``name``)。
    - 返回下游节点期望的输入(``key`` 对应 ``contract.outputs`` 的 ``name``)。
    - 抛出 :class:`HSCreditWorkflowError` 让 executor 统一处理;
      其余异常视为系统错误,按 ``contract.retryable`` 决定是否重试。
    """

    contract: ClassVar[NodeContract]
    """节点契约(子类必须覆盖)."""

    @abstractmethod
    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        """执行节点逻辑.

        Args:
            inputs: 上游节点的输出字典, ``key`` 是 :attr:`contract.outputs` 的 ``name``。
            params: 用户填写的参数, ``key`` 是 :attr:`contract.params` 的 ``name``。

        Returns:
            本节点输出字典, ``key`` 是 :attr:`contract.outputs` 的 ``name``。

        Raises:
            HSCreditWorkflowError: 业务错误(参数错误 / 类型错误 / hscredit 异常等),
                executor 不会重试。
            Exception: 系统错误(网络 / 磁盘 / 序列化等),
                executor 按 ``contract.retryable`` 决定是否重试。
        """
        raise NotImplementedError(f"{type(self).__name__}.run() must be implemented")

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        """校验输入完整性(按 :attr:`contract.inputs` 的 ``required`` 字段).

        子类可在 :meth:`run` 开头调用,也可在更细粒度处使用。

        支持 ``PortSchema.aliases`` 别名：若 ``inputs`` 含任一别名（含端口名本身），
        则视为该 required 端口已满足。子类在 :meth:`run` 中应同步按别名取值。
        """
        from hscredit_studio.core.exceptions import ValidationError

        for port in self.contract.inputs:
            if not port.required:
                continue
            candidates = [port.name, *port.aliases]
            if any(c in inputs for c in candidates):
                continue
            raise ValidationError(
                f"节点 {self.contract.node_type} 缺少必需输入端口 '{port.name}'（aliases: {port.aliases}）",
                details={
                    "node_type": self.contract.node_type,
                    "missing_port": port.name,
                    "aliases": port.aliases,
                    "required_ports": [p.name for p in self.contract.inputs if p.required],
                },
            )

    def validate_params(self, params: dict[str, Any]) -> None:
        """校验参数.

        校验项:

        1. ``required=True`` 但 ``params[spec.name]`` 为 ``None``。
        2. ``select`` / ``multiselect`` 的值不在 ``choices`` 范围内。
        3. 数值类型 (``int`` / ``float`` / ``range``) 超出 ``min`` / ``max``。

        注意:本方法只做基础校验;复杂业务校验应在 :meth:`run` 内进行。
        """
        from hscredit_studio.core.exceptions import ValidationError

        for spec in self.contract.params:
            value = params.get(spec.name, spec.default)
            # 必填项
            if spec.required and value is None:
                raise ValidationError(
                    f"节点 {self.contract.node_type} 缺少必需参数 '{spec.label}' ({spec.name})",
                    details={
                        "node_type": self.contract.node_type,
                        "param_name": spec.name,
                        "param_label": spec.label,
                    },
                )
            # 候选项
            if spec.choices and value is not None:
                allowed_values = [c.value for c in spec.choices]
                if value not in allowed_values:
                    raise ValidationError(
                        f"节点 {self.contract.node_type} 参数 {spec.name} 值 {value!r} "
                        f"不在允许范围内 {allowed_values}",
                        details={
                            "node_type": self.contract.node_type,
                            "param_name": spec.name,
                            "value": value,
                            "allowed_values": allowed_values,
                        },
                    )
            # 数值范围
            if spec.type in ("int", "float", "range") and value is not None:
                # bool 是 int 子类但不应进入这里; 直接放行
                if isinstance(value, bool):
                    continue
                if spec.min is not None and value < spec.min:
                    raise ValidationError(
                        f"节点 {self.contract.node_type} 参数 {spec.name} 值 {value} 小于最小值 {spec.min}",
                        details={
                            "node_type": self.contract.node_type,
                            "param_name": spec.name,
                            "value": value,
                            "min": spec.min,
                        },
                    )
                if spec.max is not None and value > spec.max:
                    raise ValidationError(
                        f"节点 {self.contract.node_type} 参数 {spec.name} 值 {value} 大于最大值 {spec.max}",
                        details={
                            "node_type": self.contract.node_type,
                            "param_name": spec.name,
                            "value": value,
                            "max": spec.max,
                        },
                    )

    def __repr__(self) -> str:
        return f"<{self.contract.node_type} node>"

    def __str__(self) -> str:
        return self.contract.name


__all__ = ["BaseNode"]