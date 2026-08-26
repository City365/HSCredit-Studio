"""节点契约 schema — 节点注册表对外暴露的核心数据结构.

依据 ``docs/design/03-node-catalog.md`` 第 3.2 节的契约定义生成 Pydantic 模型，
供前端 FormBuilder / Editor 与后端 NodeRegistry 共享类型。

设计要点
--------

- :class:`NodeContract` 是节点元数据的"事实来源"（source of truth）；
  ORM ``node_definitions.contract`` 字段存储其 ``model_dump()`` 结果。
- :class:`PortSchema.type` 与 :class:`ParamSpec.type` 使用 ``Literal`` 而非
  Enum，便于 ORM JSONB 直接存储字符串值。
- :class:`ParamSpec` 的 ``depends_on`` 字段用于前端条件渲染（如选择
  ``method="chest"`` 后才显示 ``chi_threshold``）。
- :class:`CacheConfig.ttl_seconds`` 使用 ``int``（秒）而非 ``timedelta``，
  便于跨语言序列化（前端 JS / 数据库）。
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ===== 枚举（字符串字面量，与 ORM / JSON 序列化对齐） =====

PortType = Literal[
    "DataFrame",
    "Series",
    "BinnerArtifact",
    "EncoderArtifact",
    "SelectorArtifact",
    "ModelArtifact",
    "ScorecardArtifact",
    "RuleArtifact",
    "Excel",
    "Parquet",
    "PNG",
    "JSON",
    "PMML",
    "SQL",
    "Python",
    "Any",
]
"""节点端口数据类型.

扩展：``Any`` 表示任意类型（灵活端口，未严格校验）。
"""

ParamType = Literal[
    "str",
    "int",
    "float",
    "bool",
    "select",
    "multiselect",
    "range",
    "list",
    "dict",
    "json",
    "file",
]
"""节点参数类型.

- ``range`` — 数值区间滑块（min/max/step）
- ``json`` — JSON 编辑器（任意嵌套结构）
- ``file`` — 文件选择（前端触发上传/选择）
"""

NodeCategory = Literal[
    "数据接入",
    "EDA",
    "特征工程",
    "特征筛选",
    "模型训练",
    "评分卡与规则",
    "报告与部署",
]
"""节点 7 类分类（与 03 第 3.1 节对齐）."""

CacheStrategy = Literal["by_inputs_hash", "by_params_hash", "none"]
"""缓存策略.

- ``by_inputs_hash`` — 按输入数据哈希缓存（默认；适合数据驱动节点）
- ``by_params_hash`` — 按参数哈希缓存（适合无输入节点）
- ``none`` — 不缓存
"""


# ===== 端口 =====


class PortSchema(BaseModel):
    """节点输入 / 输出端口.

    Attributes
    ----------
    name:
        端口名（在同一节点内唯一）。
    type:
        端口数据类型（用于连接校验）。
    required:
        是否必填（默认 True）。
    description:
        端口说明（中文，鼠标悬停展示）。
    multi:
        是否支持多连接（即同一端口可接收多条上游边）。
    """

    name: str = Field(..., min_length=1, max_length=64, description="端口名")
    type: PortType = Field(..., description="端口数据类型")
    required: bool = Field(default=True, description="是否必填")
    aliases: list[str] = Field(
        default_factory=list,
        description="端口别名列表（任一别名在 inputs 中存在即视为该端口已满足）",
    )
    description: str = Field(default="", max_length=500, description="端口说明")
    multi: bool = Field(default=False, description="是否支持多连接")


# ===== 参数 =====


class ParamChoice(BaseModel):
    """``select`` / ``multiselect`` 的候选项.

    Attributes
    ----------
    label:
        显示文本（中文）。
    value:
        实际值（任意 JSON 可序列化类型）。
    """

    label: str = Field(..., min_length=1, description="显示文本")
    value: Any = Field(..., description="实际值")


class ParamSpec(BaseModel):
    """节点参数规格（前端按此渲染表单）.

    Attributes
    ----------
    name:
        参数名（Python 标识符，用于 params dict 的 key）。
    type:
        参数类型（决定前端渲染的控件）。
    label:
        中文标签。
    description:
        帮助提示（鼠标悬停）。
    default:
        默认值（可为 None）。
    required:
        是否必填。
    choices:
        ``select`` / ``multiselect`` 的候选项。
    min:
        ``range`` / ``int`` / ``float`` 的下界。
    max:
        ``range`` / ``int`` / ``float`` 的上界。
    step:
        ``range`` 的步长。
    advanced:
        是否折叠到"高级参数"分组。
    depends_on:
        依赖的其他参数名列表（前端用于条件渲染）。
    placeholder:
        输入框占位符。
    help_url:
        帮助文档链接。
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="参数名（Python 标识符）",
    )
    type: ParamType = Field(..., description="参数类型")
    label: str = Field(..., min_length=1, max_length=128, description="中文标签")
    description: str = Field(default="", max_length=500, description="帮助提示")
    default: Any = Field(default=None, description="默认值")
    required: bool = Field(default=False, description="是否必填")
    choices: list[ParamChoice] | None = Field(default=None, description="select 候选项")
    min: float | None = Field(default=None, description="数值下界")
    max: float | None = Field(default=None, description="数值上界")
    step: float | None = Field(default=None, gt=0, description="滑块步长")
    advanced: bool = Field(default=False, description="是否折叠到高级参数")
    depends_on: list[str] = Field(default_factory=list, description="依赖的其他参数名")
    placeholder: str | None = Field(default=None, max_length=128, description="占位符")
    help_url: str | None = Field(default=None, max_length=512, description="帮助文档 URL")

    @model_validator(mode="after")
    def _validate_constraints(self) -> "ParamSpec":
        """交叉校验：``select`` 类型必须有 ``choices``；数值范围合法等。"""
        if self.type in ("select", "multiselect"):
            if not self.choices:
                raise ValueError("select / multiselect 类型必须提供 choices")
        # range/int/float 必须有 min/max
        if self.type in ("range", "int", "float"):
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError(f"参数 '{self.name}' 的 min ({self.min}) 不能大于 max ({self.max})")
        # step 仅对 range 有意义
        if self.step is not None and self.type != "range":
            # 静默忽略；前端会按 type 渲染
            pass
        return self


# ===== 缓存 =====


class CacheConfig(BaseModel):
    """缓存策略配置.

    Attributes
    ----------
    strategy:
        缓存键生成策略。
    ttl_seconds:
        缓存过期秒数（NULL 表示永不过期）。
    trusted_required:
        反序列化产物时是否需要 ``trusted=true``（防止 pickle 反序列化攻击）。
    """

    strategy: CacheStrategy = Field(
        default="by_inputs_hash",
        description="缓存策略",
    )
    ttl_seconds: int | None = Field(
        default=None,
        ge=0,
        description="缓存过期秒数（NULL = 永不过期）",
    )
    trusted_required: bool = Field(
        default=False,
        description="反序列化产物是否需 trusted=true",
    )


# ===== 节点契约 =====


class NodeContract(BaseModel):
    """节点完整契约.

    Attributes
    ----------
    node_type:
        注册表唯一 key（小写字母数字下划线）。
    category:
        节点分类。
    name:
        中文显示名。
    description:
        节点说明（业务视角，中文）。
    icon:
        UI 显示图标（emoji 或图标名）。
    inputs:
        输入端口列表。
    outputs:
        输出端口列表。
    params:
        参数列表。
    cache:
        缓存策略。
    retryable:
        失败是否自动重试。
    max_retries:
        最大重试次数（0-5）。
    timeout_sec:
        单节点超时秒数（1-86400）。
    estimated_duration_sec:
        预估运行时长（用于 UI 进度条）。
    tags:
        标签数组（搜索/过滤用）。
    version:
        契约版本（语义化版本字符串）。
    """

    node_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="节点类型唯一标识（小写字母数字下划线）",
    )
    category: NodeCategory = Field(..., description="节点分类")
    name: str = Field(..., min_length=1, max_length=128, description="中文显示名")
    description: str = Field(default="", max_length=2000, description="节点说明")
    icon: str = Field(default="📦", max_length=32, description="UI 图标（emoji）")

    inputs: list[PortSchema] = Field(default_factory=list, description="输入端口列表")
    outputs: list[PortSchema] = Field(default_factory=list, description="输出端口列表")
    params: list[ParamSpec] = Field(default_factory=list, description="参数列表")

    cache: CacheConfig = Field(default_factory=CacheConfig, description="缓存策略")
    retryable: bool = Field(default=False, description="是否自动重试")
    max_retries: int = Field(default=0, ge=0, le=5, description="最大重试次数")
    timeout_sec: int = Field(default=300, ge=1, le=86400, description="超时秒数")
    estimated_duration_sec: int = Field(default=30, ge=1, description="预估时长（秒）")

    tags: list[str] = Field(default_factory=list, description="标签数组")
    version: str = Field(default="1.0.0", description="契约版本（语义化版本）")

    @field_validator("node_type")
    @classmethod
    def _validate_node_type(cls, v: str) -> str:
        """确保 ``node_type`` 全部为小写字母 / 数字 / 下划线（pattern 已覆盖）。"""
        if not v[0].isalpha():
            raise ValueError("node_type 必须以字母开头")
        return v

    @model_validator(mode="after")
    def _validate_param_uniqueness(self) -> "NodeContract":
        """确保 ``params`` 中 ``name`` 唯一。"""
        names = [p.name for p in self.params]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"params 中存在重复参数名: {sorted(duplicates)}")
        return self


# ===== 节点定义响应（用于前端节点库） =====


class NodeDefinitionResponse(BaseModel):
    """单个节点定义的响应.

    Attributes
    ----------
    node_type:
        节点类型。
    category:
        节点分类。
    name:
        中文显示名。
    description:
        描述。
    icon:
        图标。
    contract_version:
        契约 schema 版本号（整数；与 ORM ``contract_version`` 字段对应）。
    contract:
        完整契约。
    enabled:
        是否在 UI 中启用。
    is_custom:
        是否租户自定义节点。
    """

    node_type: str = Field(..., description="节点类型")
    category: NodeCategory = Field(..., description="节点分类")
    name: str = Field(..., description="中文显示名")
    description: str = Field(..., description="描述")
    icon: str = Field(..., description="图标")
    contract_version: str = Field(..., description="契约版本")
    contract: NodeContract = Field(..., description="完整契约")
    enabled: bool = Field(..., description="是否启用")
    is_custom: bool = Field(default=False, description="是否自定义节点")


class NodeDefinitionListResponse(BaseModel):
    """节点定义列表响应.

    Attributes
    ----------
    definitions:
        节点定义列表。
    """

    definitions: list[NodeDefinitionResponse] = Field(
        default_factory=list,
        description="节点定义列表",
    )


# ===== 节点测试运行（自定义节点沙箱） =====


class NodeTestRequest(BaseModel):
    """节点测试运行请求.

    Attributes
    ----------
    contract:
        待测试的自定义节点契约。
    inputs:
        输入数据（key=端口名，value=数据）。
    params:
        参数（key=参数名，value=值）。
    sample_data:
        样本数据 CSV/JSON 字符串（用于数据接入类节点的冒烟测试）。
    """

    contract: NodeContract = Field(..., description="自定义节点契约")
    inputs: dict[str, Any] = Field(default_factory=dict, description="输入数据")
    params: dict[str, Any] = Field(default_factory=dict, description="参数")
    sample_data: dict[str, Any] | None = Field(default=None, description="样本数据")


class NodeTestResponse(BaseModel):
    """节点测试运行响应.

    Attributes
    ----------
    status:
        测试结果状态（``success`` / ``failed``）。
    outputs:
        输出数据（key=端口名）。
    logs:
        沙箱执行日志。
    duration_ms:
        执行时长（毫秒）。
    error:
        失败错误信息。
    """

    status: Literal["success", "failed"] = Field(..., description="测试结果")
    outputs: dict[str, Any] = Field(default_factory=dict, description="输出数据")
    logs: list[str] = Field(default_factory=list, description="执行日志")
    duration_ms: int = Field(..., ge=0, description="执行时长（毫秒）")
    error: str | None = Field(default=None, description="失败错误信息")


__all__ = [
    "PortType",
    "ParamType",
    "NodeCategory",
    "CacheStrategy",
    "PortSchema",
    "ParamChoice",
    "ParamSpec",
    "CacheConfig",
    "NodeContract",
    "NodeDefinitionResponse",
    "NodeDefinitionListResponse",
    "NodeTestRequest",
    "NodeTestResponse",
]