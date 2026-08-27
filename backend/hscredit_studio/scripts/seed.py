"""数据库种子脚本 — 1 租户 + 2 用户 + 全部节点定义 + 3 系统模板.

用法::

    # 在 backend/ 目录下：
    cd backend && python -m hscredit_studio.scripts.seed

    # 或直接：
    python backend/hscredit_studio/scripts/seed.py

环境要求:
    - ``.env`` 已配置数据库连接（``DATABASE_URL``）
    - alembic 迁移已执行（表结构存在）
    - hscredit 节点库已通过 ``import hscredit_studio.nodes`` 注册

幂等性:
    所有操作均先查存在性后再插入，可重复执行。
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

# 将 backend 加入 path（允许从项目根目录直接运行）
_backend_path = Path(__file__).resolve().parents[2]
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from sqlalchemy import select  # noqa: E402

from hscredit_studio.core.database import session_scope, set_tenant_context  # noqa: E402
from hscredit_studio.core.security import hash_password  # noqa: E402
from hscredit_studio.models import Tenant, User, TenantMember, NodeDefinition  # noqa: E402
from hscredit_studio.nodes import NodeRegistry  # noqa: E402
from hscredit_studio.services.template import ensure_system_templates  # noqa: E402


DEMO_TENANTS = [
    {
        "name": "Demo 租户",
        "slug": "demo",
        "plan": "pro",
        "users": [
            {"email": "admin@demo.com", "display_name": "Demo Admin", "password": "DemoPass123!", "role": "owner"},
            {"email": "analyst@demo.com", "display_name": "Demo Analyst", "password": "DemoPass123!", "role": "analyst"},
        ],
    },
    {
        "name": "Acme 租户",
        "slug": "acme",
        "plan": "enterprise",
        "users": [
            {"email": "admin@acme.com", "display_name": "Acme Admin", "password": "AcmePass123!", "role": "owner"},
        ],
    },
]


async def seed_users():
    """创建 demo & acme 租户与用户."""
    async with session_scope() as session:
        for t_info in DEMO_TENANTS:
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == t_info["slug"]))
            if tenant is None:
                tenant = Tenant(
                    tenant_id=uuid4(),
                    name=t_info["name"],
                    slug=t_info["slug"],
                    plan=t_info["plan"],
                    status="active",
                    settings={},
                )
                session.add(tenant)
                await session.flush()
                print(f"✓ 创建租户: {tenant.name} (id={tenant.tenant_id})")
            else:
                print(f"· 租户已存在: {tenant.slug}")

            await set_tenant_context(session, tenant.tenant_id)

            for u in t_info["users"]:
                existing = await session.scalar(select(User).where(User.email == u["email"]))
                if existing:
                    print(f"· 用户已存在: {u['email']}")
                    continue
                user = User(
                    user_id=uuid4(),
                    email=u["email"],
                    display_name=u["display_name"],
                    password_hash=hash_password(u["password"]),
                    status="active",
                    locale="zh-CN",
                    email_verified_at=datetime.utcnow(),
                )
                session.add(user)
                await session.flush()

                member = TenantMember(
                    tenant_id=tenant.tenant_id,
                    user_id=user.user_id,
                    role=u["role"],
                    status="active",
                    invited_by=None,
                )
                session.add(member)
                print(f"✓ 创建用户: {u['email']} (role={u['role']})")


async def seed_node_definitions():
    """把所有注册节点导入 node_definitions 表."""
    async with session_scope() as session:
        for node_cls in NodeRegistry.list_all():
            contract = node_cls.contract
            # contract.category 是 Literal 字符串，直接存为 str
            category_str = (
                contract.category
                if isinstance(contract.category, str)
                else getattr(contract.category, "value", str(contract.category))
            )
            existing = await session.scalar(
                select(NodeDefinition).where(NodeDefinition.node_type == contract.node_type)
            )
            if existing:
                print(f"· 节点定义已存在: {contract.node_type}")
                continue
            # contract_version: ORM 字段是 int；从语义化版本字符串取主版本号
            try:
                major_version = int(contract.version.split(".", 1)[0])
            except (ValueError, AttributeError):
                major_version = 1
            nd = NodeDefinition(
                node_type=contract.node_type,
                category=category_str,
                name=contract.name,
                description=contract.description,
                icon=contract.icon,
                contract_version=major_version,
                contract=contract.model_dump(mode="json"),
                enabled=True,
            )
            session.add(nd)
            print(f"✓ 导入节点定义: {contract.node_type}")
        await session.commit()


async def seed_templates():
    """植入系统模板."""
    async with session_scope() as session:
        await ensure_system_templates(session)
        print("✓ 系统模板已植入")


async def main():
    print("🌱 种子数据植入开始...")
    await seed_users()
    await seed_node_definitions()
    await seed_templates()
    print("\n🎉 种子数据植入完成！")
    print(f"\n登录信息:")
    for t_info in DEMO_TENANTS:
        print(f"  [租户: {t_info['slug']}]")
        for u in t_info['users']:
            print(f"    {u['role']}: {u['email']} / {u['password']}")


if __name__ == "__main__":
    asyncio.run(main())