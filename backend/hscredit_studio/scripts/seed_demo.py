"""演示数据填充 — 让前端页面有数据可看.

用法: python -m hscredit_studio.scripts.seed_demo
"""
from __future__ import annotations

import asyncio
import json
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models.alert import AlertRule, AlertSilence
from hscredit_studio.models.billing import Bill, Contract
from hscredit_studio.models.notification import NotificationConfig
from hscredit_studio.models.run import Run
from hscredit_studio.models.workflow import Workflow, WorkflowVersion
from hscredit_studio.models.tenant import Tenant
from hscredit_studio.models.template import Template
from hscredit_studio.models.user import User
from hscredit_studio.models.webhook import WebhookSubscription
from hscredit_studio.services.audit import AuditAction, ResourceType, record_event
from hscredit_studio.services.template import ensure_system_templates

_log = get_logger(__name__)

DEMO_TENANT_SLUG = "demo"


async def _ensure_demo_tenant(session: AsyncSession) -> str:
    """确保 demo 租户存在,返回 tenant_id."""
    stmt = select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
    t = (await session.execute(stmt)).scalar_one_or_none()
    if t:
        return str(t.tenant_id)
    t = Tenant(
        tenant_id=uuid.uuid4(),
        slug=DEMO_TENANT_SLUG,
        name="Demo 租户",
        plan="pro",
        status="active",
        is_super_admin=False,
    )
    session.add(t)
    await session.flush()
    return str(t.tenant_id)


async def _ensure_admin(session: AsyncSession, tenant_id: str) -> str:
    """确保 admin 用户存在,返回 user_id."""
    stmt = select(User).where(User.email == "admin@demo.com")
    u = (await session.execute(stmt)).scalar_one_or_none()
    if u:
        return str(u.user_id)
    u = User(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        email="admin@demo.com",
        display_name="Demo Admin",
        status="active",
        role="super_admin",
    )
    session.add(u)
    await session.flush()
    return str(u.user_id)


async def _create_workflows(session: AsyncSession, tenant_id: str, user_id: str) -> list[tuple[str, uuid.UUID]]:
    """创建 3 个示例工作流, 返回 (workflow_id, version_id) 元组列表."""
    out = []
    samples = [
        ("客户评分卡 - 银行信用卡", "credit_card_scorecard"),
        ("现金贷风险预测", "cash_loan_risk"),
        ("电商分期模型 V2", "ecommerce_instalment_v2"),
    ]
    for name, code in samples:
        wf_id = uuid.uuid4()
        ver_id = uuid.uuid4()
        wf = Workflow(
            workflow_id=wf_id,
            tenant_id=uuid.UUID(tenant_id),
            name=name,
            description=f"演示工作流: {name}",
            tags=["demo"],
            created_by=uuid.UUID(user_id),
        )
        session.add(wf)
        await session.flush()
        # 为每个 demo 工作流填充真实的节点编排 — 让前端编辑器打开有内容
        definition = _demo_workflow_definition(code)
        ver = WorkflowVersion(
            version_id=ver_id,
            workflow_id=wf_id,
            version_number=1,
            definition=definition,
            created_by=uuid.UUID(user_id),
        )
        session.add(ver)
        await session.flush()
        wf.current_version_id = ver.version_id
        out.append((str(wf_id), ver_id))
    return out


def _demo_workflow_definition(code: str) -> dict[str, object]:
    """为 3 个 demo 工作流返回真实的节点编排.

    节点类型须在 :mod:`hscredit_studio.nodes` 注册表中存在, 否则编辑器右侧参数表单
    无法显示. 这里复用系统评分卡模板里的标准节点.
    """
    if code == "credit_card_scorecard":
        return {
            "nodes": [
                {"id": "csv_in", "type": "csv_ingest", "position": {"x": 0, "y": 0},
                 "label": "CSV 接入", "data": {"node_type": "csv_ingest", "name": "CSV 接入",
                                                "category": "数据接入", "icon": "📥",
                                                "params": {"path": "/data/bank_card.csv",
                                                           "sep": ",", "encoding": "utf-8"}}},
                {"id": "ft_infer", "type": "field_type_infer", "position": {"x": 240, "y": 0},
                 "label": "字段类型推断", "data": {"node_type": "field_type_infer",
                                                  "name": "字段类型推断", "category": "EDA",
                                                  "icon": "🔍",
                                                  "params": {"target": "FPD"}}},
                {"id": "miss", "type": "missing_rate", "position": {"x": 480, "y": 0},
                 "label": "缺失率", "data": {"node_type": "missing_rate", "name": "缺失率",
                                             "category": "EDA", "icon": "🕳️",
                                             "params": {"threshold": 0.3}}},
                {"id": "iv", "type": "iv_analysis", "position": {"x": 720, "y": 0},
                 "label": "IV 分析", "data": {"node_type": "iv_analysis", "name": "IV 分析",
                                              "category": "特征工程", "icon": "📊",
                                              "params": {"target": "FPD"}}},
                {"id": "bin_age", "type": "optimal_binning_chi", "position": {"x": 960, "y": -120},
                 "label": "分箱-年龄", "data": {"node_type": "optimal_binning_chi",
                                                "name": "分箱-年龄", "category": "特征工程",
                                                "icon": "📦",
                                                "params": {"feature": "年龄", "max_bins": 6}}},
                {"id": "bin_inc", "type": "optimal_binning_chi", "position": {"x": 960, "y": 0},
                 "label": "分箱-收入", "data": {"node_type": "optimal_binning_chi",
                                                "name": "分箱-收入", "category": "特征工程",
                                                "icon": "📦",
                                                "params": {"feature": "年收入", "max_bins": 6}}},
                {"id": "bin_credit", "type": "optimal_binning_chi", "position": {"x": 960, "y": 120},
                 "label": "分箱-征信", "data": {"node_type": "optimal_binning_chi",
                                                "name": "分箱-征信", "category": "特征工程",
                                                "icon": "📦",
                                                "params": {"feature": "央行征信分", "max_bins": 8}}},
                {"id": "woe", "type": "woe_encoder", "position": {"x": 1200, "y": 0},
                 "label": "WOE 编码", "data": {"node_type": "woe_encoder", "name": "WOE 编码",
                                               "category": "特征工程", "icon": "🔄",
                                               "params": {"target": "FPD"}}},
                {"id": "lr", "type": "logistic_regression", "position": {"x": 1440, "y": 0},
                 "label": "逻辑回归", "data": {"node_type": "logistic_regression",
                                               "name": "逻辑回归", "category": "模型训练",
                                               "icon": "📈",
                                               "params": {"target": "FPD", "C": 1.0,
                                                          "max_iter": 200}}},
                {"id": "sc", "type": "score_card", "position": {"x": 1680, "y": 0},
                 "label": "标准评分卡", "data": {"node_type": "score_card", "name": "标准评分卡",
                                                 "category": "评分卡与规则", "icon": "💳",
                                                 "params": {"target": "FPD", "base_score": 750,
                                                            "pdo": 35.77, "rate": 50}}},
                {"id": "rep", "type": "model_report", "position": {"x": 1920, "y": 0},
                 "label": "模型报告", "data": {"node_type": "model_report", "name": "模型报告",
                                               "category": "报告与部署", "icon": "📑",
                                               "params": {"target": "FPD",
                                                          "output_path": "/tmp/bank_card.xlsx"}}},
            ],
            "edges": [
                {"source": "csv_in", "target": "ft_infer"},
                {"source": "ft_infer", "target": "miss"},
                {"source": "ft_infer", "target": "iv"},
                {"source": "iv", "target": "bin_age"},
                {"source": "iv", "target": "bin_inc"},
                {"source": "iv", "target": "bin_credit"},
                {"source": "bin_age", "target": "woe"},
                {"source": "bin_inc", "target": "woe"},
                {"source": "bin_credit", "target": "woe"},
                {"source": "woe", "target": "lr"},
                {"source": "lr", "target": "sc"},
                {"source": "sc", "target": "rep"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 0.6},
        }
    if code == "cash_loan_risk":
        return {
            "nodes": [
                {"id": "src", "type": "csv_ingest", "position": {"x": 0, "y": 0},
                 "label": "CSV 接入", "data": {"node_type": "csv_ingest", "name": "CSV 接入",
                                                "category": "数据接入", "icon": "📥",
                                                "params": {"path": "/data/cash_loan.csv"}}},
                {"id": "ft", "type": "field_type_infer", "position": {"x": 240, "y": 0},
                 "label": "字段类型", "data": {"node_type": "field_type_infer",
                                               "name": "字段类型", "category": "EDA",
                                               "icon": "🔍",
                                               "params": {"target": "FPD30"}}},
                {"id": "miss", "type": "missing_rate", "position": {"x": 480, "y": 0},
                 "label": "缺失率", "data": {"node_type": "missing_rate", "name": "缺失率",
                                             "category": "EDA", "icon": "🕳️",
                                             "params": {"threshold": 0.25}}},
                {"id": "iv", "type": "iv_analysis", "position": {"x": 720, "y": 0},
                 "label": "IV 分析", "data": {"node_type": "iv_analysis", "name": "IV 分析",
                                              "category": "特征工程", "icon": "📊",
                                              "params": {"target": "FPD30"}}},
                {"id": "woe", "type": "woe_encoder", "position": {"x": 960, "y": 0},
                 "label": "WOE 编码", "data": {"node_type": "woe_encoder", "name": "WOE 编码",
                                               "category": "特征工程", "icon": "🔄",
                                               "params": {"target": "FPD30"}}},
                {"id": "sel", "type": "iv_selector", "position": {"x": 1200, "y": 0},
                 "label": "IV 筛选", "data": {"node_type": "iv_selector", "name": "IV 筛选",
                                              "category": "特征筛选", "icon": "🎯",
                                              "params": {"target": "FPD30", "threshold": 0.02}}},
                {"id": "lr", "type": "logistic_regression", "position": {"x": 1440, "y": 0},
                 "label": "逻辑回归", "data": {"node_type": "logistic_regression",
                                               "name": "逻辑回归", "category": "模型训练",
                                               "icon": "📈",
                                               "params": {"target": "FPD30", "C": 0.5,
                                                          "max_iter": 300}}},
                {"id": "sc", "type": "score_card", "position": {"x": 1680, "y": 0},
                 "label": "评分卡", "data": {"node_type": "score_card", "name": "评分卡",
                                             "category": "评分卡与规则", "icon": "💳",
                                             "params": {"target": "FPD30", "base_score": 650,
                                                        "pdo": 28.85, "rate": 50}}},
            ],
            "edges": [
                {"source": "src", "target": "ft"},
                {"source": "ft", "target": "miss"},
                {"source": "ft", "target": "iv"},
                {"source": "iv", "target": "woe"},
                {"source": "woe", "target": "sel"},
                {"source": "sel", "target": "lr"},
                {"source": "lr", "target": "sc"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 0.7},
        }
    # ecommerce_instalment_v2
    return {
        "nodes": [
            {"id": "csv", "type": "csv_ingest", "position": {"x": 0, "y": 0},
             "label": "CSV 接入", "data": {"node_type": "csv_ingest", "name": "CSV 接入",
                                            "category": "数据接入", "icon": "📥",
                                            "params": {"path": "/data/ecommerce.csv"}}},
            {"id": "ft", "type": "field_type_infer", "position": {"x": 240, "y": 0},
             "label": "字段类型", "data": {"node_type": "field_type_infer",
                                           "name": "字段类型", "category": "EDA",
                                           "icon": "🔍", "params": {"target": "default_30d"}}},
            {"id": "iv", "type": "iv_analysis", "position": {"x": 480, "y": 0},
             "label": "IV 分析", "data": {"node_type": "iv_analysis", "name": "IV 分析",
                                          "category": "特征工程", "icon": "📊",
                                          "params": {"target": "default_30d"}}},
            {"id": "woe", "type": "woe_encoder", "position": {"x": 720, "y": 0},
             "label": "WOE 编码", "data": {"node_type": "woe_encoder", "name": "WOE 编码",
                                           "category": "特征工程", "icon": "🔄",
                                           "params": {"target": "default_30d"}}},
            {"id": "xgb", "type": "xgboost_train", "position": {"x": 960, "y": 0},
             "label": "XGBoost", "data": {"node_type": "xgboost_train", "name": "XGBoost",
                                          "category": "模型训练", "icon": "🌲",
                                          "params": {"target": "default_30d", "n_estimators": 200,
                                                     "max_depth": 5, "lr": 0.05}}},
            {"id": "rep", "type": "model_report", "position": {"x": 1200, "y": 0},
             "label": "模型报告", "data": {"node_type": "model_report", "name": "模型报告",
                                           "category": "报告与部署", "icon": "📑",
                                           "params": {"target": "default_30d",
                                                      "output_path": "/tmp/ecom_v2.xlsx"}}},
        ],
        "edges": [
            {"source": "csv", "target": "ft"},
            {"source": "ft", "target": "iv"},
            {"source": "iv", "target": "woe"},
            {"source": "woe", "target": "xgb"},
            {"source": "xgb", "target": "rep"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 0.7},
    }


async def _create_runs(
    session: AsyncSession,
    tenant_id: str,
    user_id: str,
    workflow_versions: list[tuple[str, uuid.UUID]],
) -> None:
    """创建 10 个示例 Run (混合状态)."""
    statuses = ["success", "success", "failed", "running", "success", "pending", "cancelled", "success", "failed", "success"]
    for i, status in enumerate(statuses):
        wf_id, ver_id = workflow_versions[i % len(workflow_versions)]
        submitted_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=i * 3)
        started_at = submitted_at + timedelta(seconds=5)
        finished_at = None
        if status in ("success", "failed", "cancelled"):
            finished_at = started_at + timedelta(seconds=random.randint(30, 600))
        run = Run(
            run_id=uuid.uuid4(),
            workflow_id=uuid.UUID(wf_id),
            workflow_version_id=ver_id,
            workflow_version_number=1,
            tenant_id=uuid.UUID(tenant_id),
            run_number=1000 + i,
            status=status,
            submitted_by=uuid.UUID(user_id),
            submitted_at=submitted_at,
            started_at=started_at,
            finished_at=finished_at,
            duration_sec=int((finished_at - started_at).total_seconds()) if finished_at else 0,
        )
        session.add(run)


async def _create_templates(session: AsyncSession, tenant_id: str, user_id: str) -> None:
    """创建 3 个自定义模板."""
    samples = [
        ("信用卡风险评估模板", "credit_risk", ["banking", "credit"]),
        ("现金贷申请模板", "cash_loan", ["lending"]),
        ("小微企业贷模板", "sme_loan", ["sme", "lending"]),
    ]
    for name, code, tags in samples:
        t = Template(
            template_id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            name=name,
            category=code,
            description=f"演示模板: {name}",
            tags=tags,
            visibility="tenant",
            review_status="approved",
            created_by=uuid.UUID(user_id),
        )
        session.add(t)


async def _create_bills(session: AsyncSession, tenant_id: str) -> None:
    """创建 4 个账单 (近 4 个月)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    for i in range(4):
        period = (now - timedelta(days=30 * i)).strftime("%Y-%m")
        bill = Bill(
            bill_id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            billing_period=period,
            plan="pro",
            status="paid" if i > 0 else "pending",
            base_fee=199.0,
            overage_runs_fee=random.uniform(0, 50),
            overage_duration_fee=random.uniform(0, 30),
            overage_storage_fee=random.uniform(0, 20),
            total_amount=199.0 + random.uniform(0, 100),
            currency="CNY",
            due_date=now + timedelta(days=30 * (1 - i)),
            paid_at=now - timedelta(days=30 * i) if i > 0 else None,
            payment_channel="wechat" if i > 0 else None,
        )
        session.add(bill)


async def _create_contracts(session: AsyncSession, tenant_id: str) -> None:
    """创建 2 个合同."""
    now = datetime.now(UTC).replace(tzinfo=None)
    for i, (ctype, status) in enumerate([("service", "signed"), ("sla", "pending")]):
        c = Contract(
            contract_id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            contract_number=f"HT-2026-{i:04d}",
            contract_type=ctype,
            title=f"{'服务' if ctype == 'service' else 'SLA'} 合同 HT-2026-{i:04d}",
            status=status,
            valid_from=now,
            valid_until=now + timedelta(days=365),
            signed_at=now - timedelta(days=30) if status == "signed" else None,
        )
        session.add(c)


async def _create_alerts(session: AsyncSession, tenant_id: str) -> None:
    """创建 3 个告警规则."""
    samples = [
        ("BackendHighErrorRate", "rate(http_requests_total{status=~'5..'}[5m]) > 0.05", "5m", "critical"),
        ("HighCPUUsage", "cpu_usage_percent > 80", "10m", "warning"),
        ("QueueBacklog", "celery_queue_length > 1000", "2m", "warning"),
    ]
    for name, promql, dur, sev in samples:
        rule = AlertRule(
            rule_id=uuid.uuid4(),
            name=name,
            group="hsc-credit",
            summary=name,
            description=f"Demo rule for {name}",
            promql=promql,
            for_duration=dur,
            severity=sev,
            enabled=True,
        )
        session.add(rule)


async def _create_notification_configs(session: AsyncSession, tenant_id: str) -> None:
    """创建 2 个通知配置."""
    samples = [
        ("email", "ops@demo.com", ["alert.fired", "run.failed"]),
        ("wecom", "https://oapi.dingtalk.com/robot/send?access_token=demo", ["alert.critical"]),
    ]
    for channel, recipient, events in samples:
        cfg = NotificationConfig(
            config_id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            channel=channel,
            template_key=events[0],
            recipient=recipient,
            config={"events": events},
            enabled=True,
        )
        session.add(cfg)


async def _create_webhook_subs(session: AsyncSession, tenant_id: str) -> None:
    """创建 1 个 Webhook 订阅."""
    sub = WebhookSubscription(
        subscription_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        url="https://httpbin.org/post/hscredit-demo",
        secret="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        events=["run.completed", "alert.fired"],
        active=True,
        description="E2E 演示订阅",
    )
    session.add(sub)


async def _seed_audit_events(session: AsyncSession, tenant_id: str, user_id: str) -> None:
    """生成 20 个审计事件."""
    actions = [
        (AuditAction.LOGIN, ResourceType.USER),
        (AuditAction.WORKFLOW_CREATE, ResourceType.WORKFLOW),
        (AuditAction.WORKFLOW_RUN_SUBMIT, ResourceType.RUN),
        (AuditAction.BILL_GENERATE, ResourceType.BILL),
        (AuditAction.DATA_EXPORT, ResourceType.BILL),
    ]
    for i in range(20):
        action, res_type = random.choice(actions)
        await record_event(
            session,
            tenant_id=uuid.UUID(tenant_id),
            user_id=uuid.UUID(user_id),
            action=action,
            resource_type=res_type,
            resource_id=uuid.uuid4(),
            details={"demo": True, "index": i},
        )


async def main() -> int:
    """执行全部演示数据填充."""
    print("=" * 60)
    print("填充演示数据 (Phase 7 B33-B35 前端可视化)")
    print("=" * 60)
    async with session_scope() as session:
        tenant_id = await _ensure_demo_tenant(session)
        user_id = await _ensure_admin(session, tenant_id)
        print(f"  租户: {tenant_id[:8]}... 用户: {user_id[:8]}...")

        # 1) 行业模板 (B30) — 跳过: ensure_system_templates 有 NOT NULL tenant_id bug
        # 直接调用 industry API 即可获取 6 个内置模板
        print("  ⏭  行业模板 (B30) — 通过 /industry-templates API 获取")

        # 2) Workflows + Runs
        wf_versions = await _create_workflows(session, tenant_id, user_id)
        print(f"  ✓ Workflows — {len(wf_versions)} 个")

        # 3) Runs
        await _create_runs(session, tenant_id, user_id, wf_versions)
        print("  ✓ Runs — 10 个 (混合状态)")

        # 4) Templates (B30)
        await _create_templates(session, tenant_id, user_id)
        print("  ✓ 自定义模板 — 3 个")

        # 5) Bills (B20)
        await _create_bills(session, tenant_id)
        print("  ✓ Bills — 4 个 (近 4 月)")

        # 6) Contracts (B21)
        await _create_contracts(session, tenant_id)
        print("  ✓ Contracts — 2 个")

        # 7) Alerts (B27)
        await _create_alerts(session, tenant_id)
        print("  ✓ Alert Rules — 3 个")

        # 8) Notifications (B23)
        await _create_notification_configs(session, tenant_id)
        print("  ✓ Notification Configs — 2 个")

        # 9) Webhooks (B35)
        await _create_webhook_subs(session, tenant_id)
        print("  ✓ Webhook Subscriptions — 1 个")

        # 10) Audit events
        await _seed_audit_events(session, tenant_id, user_id)
        print("  ✓ Audit Events — 20 个")

        await session.commit()

    print("=" * 60)
    print("✅ 全部演示数据填充完成")
    print("刷新浏览器即可看到所有页面有数据")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))