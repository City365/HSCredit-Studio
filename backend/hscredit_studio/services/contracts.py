"""合同生成与状态管理 — Phase 4 B21.

依据 docs/ROADMAP.md Phase 4 B21:

> 增值税专票 / 普票申请流程
> 合同 PDF 模板 (电子签章占位)
> 与 B20 支付成功自动开收据

合同类型:
- service_agreement — 服务协议
- dpa — 数据处理协议 (Data Processing Agreement, PIPL 必备)
- nda — 保密协议
- quote — 报价单

合同状态机:
    draft → pending_signature → signed → archived
                          ↘ voided

签章:
- 生产对接法大大 / e签宝 (中国合规电子签)
- 当前迭代: 仅生成 PDF 占位 + 文本描述签章位置
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import Contract

_log = get_logger(__name__)


# ===== 合同类型定义 =====

CONTRACT_TEMPLATES = {
    "service_agreement": {
        "title_template": "HSCredit Studio 服务协议 — {tenant_name}",
        "validity_months": 12,
        "sections": [
            "第一条 服务范围",
            "服务范围包括评分卡建模、模型部署、用量计量等核心功能。详细功能列表以平台官网为准。",
            "第二条 服务等级",
            "本平台承诺可用性不低于 99.5%, 不含计划内维护窗口。故障响应时间: P1<30min, P2<2h, P3<24h。",
            "第三条 数据保护",
            "甲乙双方严格遵守《个人信息保护法》《数据安全法》《网络安全法》。",
            "第四条 费用与结算",
            "服务费按双方约定的订阅计划与超额用量计费, 详见各账单。",
            "第五条 知识产权",
            "本平台软件著作权归乙方所有, 甲方对其建模数据拥有完整所有权。",
            "第六条 保密条款",
            "双方对在合作中获得的对方商业秘密负有保密义务, 期限 5 年。",
            "第七条 争议解决",
            "本协议适用中华人民共和国法律, 争议由北京仲裁委员会仲裁解决。",
        ],
    },
    "dpa": {
        "title_template": "数据处理协议 (DPA) — {tenant_name}",
        "validity_months": 12,
        "sections": [
            "第一条 处理目的",
            "乙方仅为提供 HSCredit Studio 服务之目的处理甲方数据, 不作其他用途。",
            "第二条 处理类型",
            "包括评分卡特征工程、模型训练、推理、产物存储等环节中涉及的数据读写。",
            "第三条 数据主体类别",
            "甲方上传的脱敏客户数据, 乙方不知悉亦不应接触未脱敏个人数据。",
            "第四条 安全措施",
            "传输 TLS 1.3, 存储 AES-256, 访问 RBAC + 审计日志, 备份加密 + 异地容灾。",
            "第五条 跨境传输",
            "如涉及跨境, 乙方需取得甲方明示同意并完成 PIPL 评估。",
            "第六条 数据主体权利",
            "协助甲方响应查询、更正、删除、可携等 PIPL 第 44-50 条规定的权利请求。",
            "第七条 违约责任",
            "因乙方过错导致数据泄露, 乙方需承担相应法律责任并赔偿甲方损失。",
        ],
    },
    "nda": {
        "title_template": "保密协议 (NDA) — {tenant_name}",
        "validity_months": 60,
        "sections": [
            "第一条 保密信息定义",
            "包括但不限于技术方案、商业计划、客户名单、定价政策等标注或可识别为保密的信息。",
            "第二条 保密义务",
            "接收方不得向第三方披露保密信息, 仅在履行本协议目的所必需的范围内使用。",
            "第三条 保密期限",
            "自本协议签署之日起 5 年。",
            "第四条 违约责任",
            "违反本协议须赔偿守约方因此遭受的全部损失。",
        ],
    },
    "quote": {
        "title_template": "HSCredit Studio 报价单 — {tenant_name}",
        "validity_months": 3,
        "sections": [
            "第一条 报价明细",
            "基础订阅费 + 三维度超额费用详见附表。",
            "第二条 有效期",
            "本报价单有效期 3 个月, 逾期请重新申请。",
            "第三条 备注",
            "如对报价有疑问, 请联系客户经理。",
        ],
    },
}


@dataclass
class ContractCreationRequest:
    """合同创建请求 (Phase 4 B21)."""

    contract_type: str
    tenant_name: str
    tenant_id: UUID
    extra_metadata: dict[str, Any] | None = None


def generate_contract_number(contract_type: str) -> str:
    """生成合同号: CT-{type_prefix}-{YYYY}-{seq:04d}."""
    type_prefix = {
        "service_agreement": "SA",
        "dpa": "DPA",
        "nda": "NDA",
        "quote": "QT",
    }.get(contract_type, "CT")
    now = datetime.utcnow()
    year = now.year
    seq = int(now.timestamp()) % 10000  # 简化: 用时间戳末 4 位
    return f"CT-{type_prefix}-{year}-{seq:04d}"


def render_contract_text(
    contract_type: str,
    tenant_name: str,
    contract_number: str,
    issued_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
) -> str:
    """渲染合同正文 (中文模板) — Phase 4 B21."""
    template = CONTRACT_TEMPLATES.get(contract_type)
    if not template:
        raise ValueError(f"不支持的合同类型: {contract_type}")

    title = template["title_template"].format(tenant_name=tenant_name)

    content_lines = [
        "═══════════════════════════════════════════════",
        f"  {title}",
        "═══════════════════════════════════════════════",
        "",
        f"合同编号: {contract_number}",
        f"签订日期: {issued_at.strftime('%Y年%m月%d日')}",
        f"生效日期: {valid_from.strftime('%Y年%m月%d日')}",
        f"到期日期: {valid_until.strftime('%Y年%m月%d日')}",
        "",
        "───────────────────────────────────────────────",
        "甲方 (委托方):",
        f"  名称: {tenant_name}",
        "",
        "乙方 (服务方):",
        "  名称: 衡枢真信 (HSCredit) 科技有限公司",
        "",
    ]

    for idx, section in enumerate(template["sections"], start=1):  # noqa: B007
        content_lines.append(f"  {section}")
        if not section.startswith("第"):
            content_lines.append("")  # 段落内容后空行

    content_lines.extend(
        [
            "───────────────────────────────────────────────",
            "电子签章占位:",
            "  甲方 (签章): _______________ 日期: ___________",
            "  乙方 (签章): _______________ 日期: ___________",
            "",
            "  [本协议由电子合同平台签署, 与纸质合同具有同等法律效力]",
            "",
            f"  生成时间: {issued_at.isoformat()}",
            "═══════════════════════════════════════════════",
        ]
    )

    return "\n".join(content_lines)


async def generate_contract_for_tenant(
    tenant_id: UUID,
    tenant_name: str,
    contract_type: str,
    *,
    pdf_dir: str = "/tmp/contracts",
) -> Contract:
    """为租户生成合同 (Phase 4 B21 验收).

    1. 生成合同号
    2. 渲染合同正文
    3. 写 PDF 文件
    4. 落库 (status=draft)
    """
    if contract_type not in CONTRACT_TEMPLATES:
        raise ValueError(f"不支持的合同类型: {contract_type}, 可选: {list(CONTRACT_TEMPLATES)}")

    template = CONTRACT_TEMPLATES[contract_type]
    os.makedirs(pdf_dir, exist_ok=True)

    now = datetime.utcnow()
    valid_from = now
    valid_until = now + timedelta(days=template["validity_months"] * 30)

    contract_number = generate_contract_number(contract_type)
    content = render_contract_text(
        contract_type=contract_type,
        tenant_name=tenant_name,
        contract_number=contract_number,
        issued_at=now,
        valid_from=valid_from,
        valid_until=valid_until,
    )

    pdf_path = os.path.join(pdf_dir, f"{contract_number}.txt")
    with open(pdf_path, "w", encoding="utf-8") as f:
        f.write(content)

    async with session_scope() as session:
        contract = Contract(
            tenant_id=tenant_id,
            contract_number=contract_number,
            contract_type=contract_type,
            title=template["title_template"].format(tenant_name=tenant_name),
            status="draft",
            valid_from=valid_from,
            valid_until=valid_until,
            pdf_path=pdf_path,
            extra_metadata={
                "tenant_name": tenant_name,
                "sections_count": len(template["sections"]),
                "validity_months": template["validity_months"],
            },
        )
        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        _log.info(
            "contract_generated",
            contract_id=str(contract.contract_id),
            contract_number=contract_number,
            contract_type=contract_type,
            pdf_path=pdf_path,
        )

        # Phase 5 B22: 审计 - 合同生成
        try:
            from hscredit_studio.services.audit import AuditAction, ResourceType, record_event

            await record_event(
                session,
                tenant_id=tenant_id,
                user_id=None,
                action=AuditAction.CONTRACT_SIGN,  # 复用于合同生命周期
                resource_type=ResourceType.CONTRACT,
                resource_id=contract.contract_id,
                details={
                    "contract_type": contract_type,
                    "contract_number": contract_number,
                    "pdf_path": pdf_path,
                },
            )
        except Exception as e:
            _log.warning("contract_audit_failed", error=str(e)[:200])

        return contract


async def sign_contract(contract_id: UUID, tenant_id: UUID) -> Contract:
    """合同签约 — 状态 pending_signature → signed (Phase 4 B21 验收).

    真实场景对接法大大 / e签宝 webhook; 当前迭代直接标记签约。
    """
    async with session_scope() as session:
        contract = await session.scalar(
            select(Contract).where(
                Contract.contract_id == contract_id,
                Contract.tenant_id == tenant_id,
            )
        )
        if contract is None:
            raise ValueError(f"合同不存在: {contract_id}")
        if contract.status == "signed":
            return contract
        if contract.status == "voided":
            raise ValueError("合同已作废, 不能签约")

        contract.status = "signed"
        contract.signed_at = datetime.utcnow()
        await session.commit()
        await session.refresh(contract)
        _log.info(
            "contract_signed",
            contract_id=str(contract_id),
            signed_at=contract.signed_at.isoformat(),
        )

        # Phase 5 B22: 审计 - 合同签约
        try:
            from hscredit_studio.services.audit import AuditAction, ResourceType, record_event

            await record_event(
                session,
                tenant_id=tenant_id,
                user_id=None,
                action=AuditAction.CONTRACT_SIGN,
                resource_type=ResourceType.CONTRACT,
                resource_id=contract.contract_id,
                details={
                    "contract_number": contract.contract_number,
                    "contract_type": contract.contract_type,
                    "signed_at": contract.signed_at.isoformat(),
                },
            )
        except Exception as e:
            _log.warning("contract_sign_audit_failed", error=str(e)[:200])

        return contract


__all__ = [
    "CONTRACT_TEMPLATES",
    "ContractCreationRequest",
    "generate_contract_for_tenant",
    "generate_contract_number",
    "render_contract_text",
    "sign_contract",
]
