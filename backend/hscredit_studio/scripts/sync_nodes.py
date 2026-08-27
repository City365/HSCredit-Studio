"""同步新节点到 node_definitions 表.

新增节点 (批次 12) 需要插入到 DB node_definitions 表才能在前端显示.
"""
import asyncio
import sys
from pathlib import Path

_backend_path = Path(__file__).resolve().parents[2]
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from sqlalchemy import select  # noqa: E402

from hscredit_studio.core.database import session_scope  # noqa: E402
from hscredit_studio.models import NodeDefinition  # noqa: E402
from hscredit_studio.nodes import NodeRegistry  # noqa: E402

NEW_NODES = ["shap_explanation", "xgboost", "reject_inference"]


async def main():
    # 触发所有节点模块导入
    from hscredit_studio import nodes  # noqa: F401

    async with session_scope() as session:
        for node_type in NEW_NODES:
            cls = NodeRegistry.try_get(node_type)
            if cls is None:
                print(f"✗ {node_type}: not registered in NodeRegistry")
                continue
            contract = cls.contract
            category_str = (
                contract.category
                if isinstance(contract.category, str)
                else getattr(contract.category, "value", str(contract.category))
            )

            existing = await session.scalar(
                select(NodeDefinition).where(NodeDefinition.node_type == node_type)
            )
            if existing:
                print(f"~ {node_type}: already exists, skipping")
                continue

            nd = NodeDefinition(
                node_type=node_type,
                category=category_str,
                name=contract.name,
                description=contract.description,
                icon=contract.icon,
                contract_version=2,
                contract={
                    "node_type": contract.node_type,
                    "category": category_str,
                    "name": contract.name,
                    "description": contract.description,
                    "icon": contract.icon,
                    "inputs": [
                        {
                            "name": p.name,
                            "type": p.type,
                            "required": p.required,
                            "aliases": p.aliases,
                            "description": p.description,
                        }
                        for p in contract.inputs
                    ],
                    "outputs": [
                        {"name": p.name, "type": p.type, "description": p.description}
                        for p in contract.outputs
                    ],
                    "params": [
                        {
                            "name": p.name,
                            "type": p.type,
                            "label": p.label,
                            "default": p.default,
                            "required": p.required,
                            "choices": (
                                [{"label": c.label, "value": c.value} for c in p.choices]
                                if p.choices
                                else None
                            ),
                            "min": p.min,
                            "max": p.max,
                        }
                        for p in contract.params
                    ],
                },
                enabled=True,
            )
            session.add(nd)
            print(f"✓ {node_type}: inserted into node_definitions")
        await session.commit()

    print("\nNode registry sync complete.")


if __name__ == "__main__":
    asyncio.run(main())