"""回填 3 个 demo 工作流的 definition — 让编辑器有内容.

仅在 demo 租户且 name 匹配时执行. 不影响其他工作流.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# 把 backend 加到 sys.path
backend_dir = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, update

from hscredit_studio.core.database import async_session_maker
from hscredit_studio.models.workflow import Workflow, WorkflowVersion


def _demo_workflow_definition(code: str) -> dict[str, object]:
    """复用 seed_demo 中的实现."""
    from hscredit_studio.scripts.seed_demo import _demo_workflow_definition as _impl
    return _impl(code)


async def main() -> None:
    demo_names = {
        "客户评分卡 - 银行信用卡": "credit_card_scorecard",
        "现金贷风险预测": "cash_loan_risk",
        "电商分期模型 V2": "ecommerce_instalment_v2",
    }
    async with async_session_maker() as session:
        # 找到 demo 租户下的所有 demo 工作流
        stmt = select(Workflow).where(
            Workflow.name.in_(list(demo_names.keys())),
            Workflow.deleted_at.is_(None),
        )
        rows = (await session.scalars(stmt)).all()
        print(f"找到 {len(rows)} 个 demo 工作流")
        updated = 0
        for wf in rows:
            code = demo_names[wf.name]
            new_def = _demo_workflow_definition(code)
            # 找当前 HEAD 版本
            v_stmt = select(WorkflowVersion).where(
                WorkflowVersion.version_id == wf.current_version_id
            )
            head = (await session.scalars(v_stmt)).first()
            if not head:
                print(f"  ⚠ {wf.name}: 无 HEAD 版本, 跳过")
                continue
            head.definition = new_def
            print(f"  ✓ {wf.name} ({code}): nodes={len(new_def['nodes'])}, edges={len(new_def['edges'])}")
            updated += 1
        await session.commit()
        print(f"\n已更新 {updated} 个工作流的 definition")


if __name__ == "__main__":
    asyncio.run(main())
