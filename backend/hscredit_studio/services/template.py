"""模板服务 — 模板 CRUD + 实例化 + 评分.

设计要点（见 :file:`docs/design/05-templates.md` 与 ``14-api-specification.md`` 第 14.7.4 节）：

- 模板分两类：

  - **系统模板**（平台官方）：``tenant_id IS NULL``，``visibility="public"``，
    所有租户可见，由 :func:`ensure_system_templates` 在迁移/启动时植入。
  - **租户模板**：``tenant_id`` 指向具体租户，仅本租户可见。

- 列表查询同时返回系统模板与当前租户模板（``OR`` 条件），
  排除 ``deleted_at IS NOT NULL`` 行。

- 实例化 = 从模板最新版本构造 :class:`WorkflowDefinition` → 创建
  :class:`Workflow` + 初始 ``WorkflowVersion``。支持 ``params_overrides``
  按 node_id 覆盖节点 ``data`` 字段。

- 评分：对同一用户对同一模板限唯一评分（unique 约束兜底），
  评分后重算 ``Template.rating_avg`` / ``rating_count``。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.exceptions import (
    FeatureNotFoundError,
    ValidationError,
)
from hscredit_studio.models import (
    Template,
    TemplateRating,
    TemplateVersion,
    Workflow,
    WorkflowVersion,
)
from hscredit_studio.schemas.workflow import WorkflowDefinition

# ===== 评分边界（与 ORM CheckConstraint "rating >= 1 AND rating <= 5" 对齐） =====


class TemplateRatingAllowedValues:
    """模板评分合法范围常量."""

    min = 1
    max = 5

    @classmethod
    def contains(cls, value: int) -> bool:
        return cls.min <= value <= cls.max


# ===== 系统模板定义（按 05 第 5.1-5.3 节落地） =====


# 评分卡模板 v1 — 12 节点编排（精简版，参见 docs/design/05-templates.md 5.1）
SCORECARD_TEMPLATE_V1: dict[str, Any] = {
    "name": "标准评分卡建模",
    "category": "评分卡",
    "description": (
        "12 节点标准评分卡全流程：CSV 接入 → 字段类型推断 → 缺失率分析 → "
        "IV 分析 → 卡方分箱 × N → WOE 编码 → IV 筛选 → VIF 筛选 → "
        "逻辑回归 → 标准评分卡 → 模型报告"
    ),
    "icon": "💳",
    "tags": ["评分卡", "标准模板", "入门"],
    "nodes": [
        # 数据接入层
        {
            "id": "csv_ingest",
            "type": "csv_ingest",
            "position": {"x": 0, "y": 0},
            "data": {"path": "/data/train.csv", "sep": ",", "encoding": "utf-8"},
        },
        {
            "id": "field_type_infer",
            "type": "field_type_infer",
            "position": {"x": 240, "y": 0},
            "data": {},
        },
        {
            "id": "missing_rate",
            "type": "missing_rate",
            "position": {"x": 480, "y": 0},
            "data": {"threshold": 0.5},
        },
        {
            "id": "iv_analysis",
            "type": "iv_analysis",
            "position": {"x": 720, "y": 0},
            "data": {"target": "FPD", "max_n_bins": 5},
        },
        # 分箱层（MVP 展示 3 个示例特征）
        {
            "id": "bin_age",
            "type": "optimal_binning_chi",
            "position": {"x": 960, "y": -120},
            "data": {"feature": "age", "target": "FPD", "max_n_bins": 5},
        },
        {
            "id": "bin_income",
            "type": "optimal_binning_chi",
            "position": {"x": 960, "y": 0},
            "data": {"feature": "income", "target": "FPD", "max_n_bins": 5},
        },
        {
            "id": "bin_history",
            "type": "optimal_binning_chi",
            "position": {"x": 960, "y": 120},
            "data": {"feature": "credit_history", "target": "FPD", "max_n_bins": 5},
        },
        # WOE 编码
        {
            "id": "woe_encoder",
            "type": "woe_encoder",
            "position": {"x": 1200, "y": 0},
            "data": {
                "features": ["age_bin", "income_bin", "credit_history_bin"],
                "target": "FPD",
            },
        },
        # 筛选层
        {
            "id": "iv_selector",
            "type": "iv_selector",
            "position": {"x": 1440, "y": 0},
            "data": {"target": "FPD", "threshold": 0.02},
        },
        {
            "id": "vif_selector",
            "type": "vif_selector",
            "position": {"x": 1680, "y": 0},
            "data": {"target": "FPD"},
        },
        # 模型
        {
            "id": "logistic_regression",
            "type": "logistic_regression",
            "position": {"x": 1920, "y": 0},
            "data": {
                "target": "FPD",
                "features": [],
                "eval_metric": ["auc", "ks"],
            },
        },
        {
            "id": "score_card",
            "type": "score_card",
            "position": {"x": 2160, "y": 0},
            "data": {
                "target": "FPD",
                "features": [],
                "pdo": 60,
                "rate": 2,
                "base_score": 750,
            },
        },
        # 报告
        {
            "id": "model_report",
            "type": "model_report",
            "position": {"x": 2400, "y": 0},
            "data": {
                "target": "FPD",
                "features": [],
                "output_path": "/tmp/scorecard_report.xlsx",
            },
        },
    ],
    "edges": [
        # 数据流
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "field_type_infer", "target": "missing_rate"},
        {"source": "field_type_infer", "target": "iv_analysis"},
        # 分箱节点需要原始 DataFrame，故直连 csv_ingest（而非 iv_analysis，后者只用于 EDA 报告）
        {"source": "csv_ingest", "target": "bin_age"},
        {"source": "csv_ingest", "target": "bin_income"},
        {"source": "csv_ingest", "target": "bin_history"},
        # 分箱 → WOE
        {"source": "bin_age", "target": "woe_encoder"},
        {"source": "bin_income", "target": "woe_encoder"},
        {"source": "bin_history", "target": "woe_encoder"},
        # WOE → 筛选 → 模型
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "vif_selector"},
        {"source": "vif_selector", "target": "logistic_regression"},
        {"source": "logistic_regression", "target": "score_card"},
        # 模型 → 报告
        {"source": "score_card", "target": "model_report"},
    ],
}


# 规则挖掘模板 v1 — 4 节点精简版（完整版参见 05 第 5.2 节）
RULE_MINING_TEMPLATE_V1: dict[str, Any] = {
    "name": "规则策略挖掘",
    "category": "规则",
    "description": "基于决策树的规则挖掘流程（CART 分箱 → IV 筛选 → 逻辑回归）",
    "icon": "⛏️",
    "tags": ["规则", "决策树"],
    "nodes": [
        {
            "id": "csv_ingest",
            "type": "csv_ingest",
            "position": {"x": 0, "y": 0},
            "data": {"path": "/data/samples.csv"},
        },
        {
            "id": "binning",
            "type": "optimal_binning_cart",
            "position": {"x": 240, "y": 0},
            "data": {"feature": "all", "target": "FPD"},
        },
        {
            "id": "selector",
            "type": "iv_selector",
            "position": {"x": 480, "y": 0},
            "data": {"target": "FPD", "threshold": 0.05},
        },
        {
            "id": "model",
            "type": "logistic_regression",
            "position": {"x": 720, "y": 0},
            "data": {"target": "FPD"},
        },
    ],
    "edges": [
        {"source": "csv_ingest", "target": "binning"},
        {"source": "binning", "target": "selector"},
        {"source": "selector", "target": "model"},
    ],
}


# 监控模板 v1 — 3 节点精简版（完整版参见 05 第 5.3 节）
MONITOR_TEMPLATE_V1: dict[str, Any] = {
    "name": "模型监控",
    "category": "监控",
    "description": "PSI/CSI 监控与告警配置（基础版）",
    "icon": "📡",
    "tags": ["监控", "PSI"],
    "nodes": [
        {
            "id": "csv_ingest",
            "type": "csv_ingest",
            "position": {"x": 0, "y": 0},
            "data": {"path": "/data/inference.csv"},
        },
        {
            "id": "score_card",
            "type": "score_card",
            "position": {"x": 240, "y": 0},
            "data": {"target": "FPD"},
        },
        {
            "id": "excel_export",
            "type": "excel_export",
            "position": {"x": 480, "y": 0},
            "data": {"output_path": "/tmp/monitor.xlsx"},
        },
    ],
    "edges": [
        {"source": "csv_ingest", "target": "score_card"},
        {"source": "score_card", "target": "excel_export"},
    ],
}


SYSTEM_TEMPLATES: list[dict[str, Any]] = [
    SCORECARD_TEMPLATE_V1,
    RULE_MINING_TEMPLATE_V1,
    MONITOR_TEMPLATE_V1,
]


# ===== 列表 =====


async def list_templates(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    category: str | None = None,
) -> tuple[list[Template], int]:
    """分页列出模板 — 系统模板 + 当前租户模板.

    Parameters
    ----------
    session:
        数据库会话。
    tenant_id:
        当前租户 UUID。
    page / page_size:
        分页参数。
    search:
        模糊匹配 ``name`` / ``description``。
    category:
        按模板分类过滤（评分卡 / 规则 / 监控）。

    Returns
    -------
    (items, total)
        当前页模板列表 + 总记录数。

    Notes
    -----
    按 ``use_count`` desc + ``created_at`` desc 排序，让高频模板优先展示。
    """
    base = select(Template).where(
        or_(Template.tenant_id == tenant_id, Template.tenant_id.is_(None)),
        Template.deleted_at.is_(None),
    )
    count_q = (
        select(func.count())
        .select_from(Template)
        .where(
            or_(Template.tenant_id == tenant_id, Template.tenant_id.is_(None)),
            Template.deleted_at.is_(None),
        )
    )
    if category:
        base = base.where(Template.category == category)
        count_q = count_q.where(Template.category == category)
    if search:
        search_filter = or_(
            Template.name.ilike(f"%{search}%"),
            Template.description.ilike(f"%{search}%"),
        )
        base = base.where(search_filter)
        count_q = count_q.where(search_filter)

    base = (
        base.order_by(Template.use_count.desc(), Template.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await session.scalars(base)).all()
    total = (await session.scalar(count_q)) or 0
    return list(items), total


# ===== 详情 =====


async def get_template(
    session: AsyncSession,
    tenant_id: UUID,
    template_id: UUID,
) -> Template:
    """获取模板详情.

    Raises
    ------
    FeatureNotFoundError
        模板不存在 / 已软删除 / 属于其他租户（系统模板 ``tenant_id IS NULL`` 总是允许）。
    """
    t = await session.get(Template, template_id)
    if t is None or t.deleted_at is not None:
        raise FeatureNotFoundError(f"模板 {template_id} 不存在")
    if t.tenant_id is not None and t.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"模板 {template_id} 不属于当前租户")
    return t


async def get_latest_version(
    session: AsyncSession,
    template_id: UUID,
) -> TemplateVersion:
    """获取模板的最新版本（按 version_number desc 排序）.

    Raises
    ------
    FeatureNotFoundError
        模板没有任何版本记录。
    """
    v = await session.scalar(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.version_number.desc())
        .limit(1)
    )
    if v is None:
        raise FeatureNotFoundError("模板版本不存在")
    return v


# ===== 实例化 =====


async def instantiate_template(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    template_id: UUID,
    workflow_name: str | None = None,
    params_overrides: dict[str, dict[str, Any]] | None = None,
) -> Workflow:
    """从模板实例化一个新工作流.

    Parameters
    ----------
    session:
        数据库会话。
    tenant_id / user_id:
        新工作流的归属。
    template_id:
        模板 ID（系统模板 / 租户模板均可）。
    workflow_name:
        新工作流名（不指定使用 ``"{模板名}_{时间戳}"`` 形式）。
    params_overrides:
        节点参数覆盖字典 ``{node_id: {param_name: value}}``，
        用于在加载模板时调整特定节点的参数（例如指定 CSV 路径）。

    Returns
    -------
    Workflow
        新建的 :class:`Workflow` ORM 对象（已 commit，可直接使用 ``workflow_id``）。

    Raises
    ------
    FeatureNotFoundError
        模板不存在 / 已删除 / 跨租户访问。
    """
    tmpl = await get_template(session, tenant_id, template_id)
    version = await get_latest_version(session, template_id)

    # 从 JSONB 读出节点 / 边 / 默认参数（version.nodes 实际为 list[dict]）
    nodes = version.nodes or []
    edges = version.edges or []
    default_params = version.default_params or {}

    # 应用节点参数覆盖：default_params → 当前节点 data → 用户 overrides
    if params_overrides:
        nodes = [
            {
                **n,
                "data": {
                    **default_params.get(n["id"], n.get("data", {}) or {}),
                    **params_overrides.get(n["id"], {}),
                },
            }
            for n in nodes
        ]

    definition_dict: dict[str, Any] = {
        "nodes": nodes,
        "edges": edges,
        "metadata": {"from_template": tmpl.name},
    }

    # 创建工作流 + 初始版本 v1（与 workflow.create_workflow 等价）
    wf = Workflow(
        tenant_id=tenant_id,
        name=workflow_name or f"{tmpl.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        description=f"从模板「{tmpl.name}」实例化",
        tags=tmpl.tags or [],
        created_by=user_id,
        current_version_id=None,
    )
    session.add(wf)
    await session.flush()

    v1 = WorkflowVersion(
        workflow_id=wf.workflow_id,
        version_number=1,
        definition=definition_dict,
        change_summary=f"实例化自模板 v{version.version_number}",
        created_by=user_id,
    )
    session.add(v1)
    await session.flush()
    wf.current_version_id = v1.version_id

    # 更新模板使用次数
    tmpl.use_count = (tmpl.use_count or 0) + 1
    await session.commit()
    return wf


# ===== 评分 =====


async def rate_template(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    template_id: UUID,
    rating: int,
    comment: str | None = None,
) -> TemplateRating:
    """为模板评分 — 同一用户对同一模板限唯一评分（更新或新增）.

    评分后重算 ``Template.rating_avg`` 与 ``rating_count`` 字段。
    """
    if not TemplateRatingAllowedValues.contains(rating):
        raise ValidationError(
            f"评分必须在 {TemplateRatingAllowedValues.min}-" f"{TemplateRatingAllowedValues.max} 之间"
        )

    # 先校验模板存在并属于当前租户 / 系统
    await get_template(session, tenant_id, template_id)

    existing = await session.scalar(
        select(TemplateRating).where(
            TemplateRating.template_id == template_id,
            TemplateRating.user_id == user_id,
        )
    )
    if existing is not None:
        existing.rating = rating
        existing.comment = comment
        rating_obj = existing
    else:
        rating_obj = TemplateRating(
            tenant_id=tenant_id,
            template_id=template_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
        )
        session.add(rating_obj)

    await session.flush()

    # 重算聚合（统计所有未删除评分行的均值与计数）
    tmpl = await session.get(Template, template_id)
    if tmpl is not None:
        avg = await session.scalar(
            select(func.avg(TemplateRating.rating)).where(TemplateRating.template_id == template_id)
        )
        count = await session.scalar(
            select(func.count(TemplateRating.rating_id)).where(TemplateRating.template_id == template_id)
        )
        tmpl.rating_avg = float(avg) if avg is not None else 0.0
        tmpl.rating_count = count or 0

    await session.commit()
    return rating_obj


# ===== 系统模板植入 =====


async def ensure_system_templates(session: AsyncSession) -> None:
    """确保系统模板已植入 — ``tenant_id IS NULL`` + ``visibility='public'``.

    通常在 alembic 迁移或首次启动时调用。**幂等**：通过 ``(tenant_id IS NULL) AND name``
    判定存在性，避免重复插入。

    Notes
    -----
    - 模板 ``icon`` 字段已写入（``💳`` / ``⛏️`` / ``📡``）。
    - 默认参数 ``default_params={}``（系统模板的节点 ``data`` 已包含默认值）。
    """
    for tmpl_def in SYSTEM_TEMPLATES:
        existing = await session.scalar(
            select(Template).where(
                Template.tenant_id.is_(None),
                Template.name == tmpl_def["name"],
            )
        )
        if existing is not None:
            continue

        tmpl = Template(
            tenant_id=None,
            category=tmpl_def["category"],
            name=tmpl_def["name"],
            description=tmpl_def["description"],
            visibility="public",
            use_count=0,
            rating_avg=0.0,
            rating_count=0,
            icon=tmpl_def.get("icon"),
            tags=tmpl_def["tags"],
            created_by=None,
        )
        session.add(tmpl)
        await session.flush()

        v1 = TemplateVersion(
            template_id=tmpl.template_id,
            version_number=1,
            nodes=tmpl_def["nodes"],
            edges=tmpl_def["edges"],
            default_params={},
            readme_md=f"# {tmpl_def['name']}\n\n{tmpl_def['description']}\n",
        )
        session.add(v1)

    await session.commit()


# 显式 re-export WorkflowDefinition 以便 API 层直接引用
__all__ = [
    "MONITOR_TEMPLATE_V1",
    "RULE_MINING_TEMPLATE_V1",
    "SCORECARD_TEMPLATE_V1",
    "SYSTEM_TEMPLATES",
    "TemplateRatingAllowedValues",
    "WorkflowDefinition",
    "ensure_system_templates",
    "get_latest_version",
    "get_template",
    "instantiate_template",
    "list_templates",
    "rate_template",
]
