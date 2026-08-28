"""Phase 6 B30 — 行业模板市场单元测试.

依据 docs/ROADMAP.md Phase 6 B30:

- 6 个行业模板 (银行信用卡 / 消金 / 助贷 / 现金贷 / 电商分期 / 汽车金融)
- 每个模板含: 默认参数、推荐特征、模型选型、评分公式、报告模板
- 一键实例化 (instantiate_industry_template)
- 模板市场列表 (list_industry_templates)
- 评分 (rate_industry_template)
"""
from __future__ import annotations

import pytest

from hscredit_studio.services.industry_marketplace import INDUSTRY_NAMES
from hscredit_studio.services.industry_templates import (
    ASSISTED_LOAN_TEMPLATE,
    AUTO_FINANCE_TEMPLATE,
    BANK_CREDIT_CARD_TEMPLATE,
    CASH_LOAN_TEMPLATE,
    ECOM_INSTALMENT_TEMPLATE,
    INDUSTRY_TEMPLATES,
    INTERNET_FINANCE_TEMPLATE,
)

# ===== 模板元数据完整性 =====


def test_industry_templates_count():
    """INDUSTRY_TEMPLATES 必须是 6 个."""
    assert len(INDUSTRY_TEMPLATES) == 6


def test_industry_names_unique():
    """6 个模板的 industry 唯一."""
    industries = [t["industry"] for t in INDUSTRY_TEMPLATES]
    assert len(set(industries)) == 6


def test_required_industries_present():
    """ROADMAP 要求的 6 个行业齐全."""
    expected = {"银行信用卡", "互联网消金", "助贷", "现金贷", "电商分期", "汽车金融"}
    assert expected == INDUSTRY_NAMES


# ===== 银行信用卡模板 (B30 验收模板) =====


def test_bank_credit_card_template_8_nodes():
    """银行信用卡模板 ≥ 8 个节点 (B30 验收)."""
    assert len(BANK_CREDIT_CARD_TEMPLATE["nodes"]) >= 8


def test_bank_credit_card_has_required_metadata():
    """银行信用卡模板含必备元数据 (B30 验收)."""
    t = BANK_CREDIT_CARD_TEMPLATE
    assert t["name"] == "银行信用卡评分卡"
    assert t["industry"] == "银行信用卡"
    assert t["target_column"] == "FPD"
    assert t["model_type"]
    assert t["score_formula"]
    assert t["report_template"]
    assert len(t["recommended_features"]) > 0
    assert len(t["nodes"]) > 0
    assert len(t["edges"]) > 0


def test_bank_credit_card_node_data_has_target():
    """节点 data 字段含 target 字段 (供 scorecard 链路)."""
    for node in BANK_CREDIT_CARD_TEMPLATE["nodes"]:
        if "target" in node["data"]:
            assert node["data"]["target"] == "FPD"


def test_bank_credit_card_edges_consistent():
    """边引用的节点 ID 必须在 nodes 中."""
    node_ids = {n["id"] for n in BANK_CREDIT_CARD_TEMPLATE["nodes"]}
    for edge in BANK_CREDIT_CARD_TEMPLATE["edges"]:
        assert edge["source"] in node_ids, f"edge.source 缺失节点: {edge['source']}"
        assert edge["target"] in node_ids, f"edge.target 缺失节点: {edge['target']}"


# ===== 其他 5 个模板同样验证 =====


@pytest.mark.parametrize(
    "template",
    [
        INTERNET_FINANCE_TEMPLATE,
        ASSISTED_LOAN_TEMPLATE,
        CASH_LOAN_TEMPLATE,
        ECOM_INSTALMENT_TEMPLATE,
        AUTO_FINANCE_TEMPLATE,
    ],
)
def test_each_industry_template_metadata(template):
    """每个模板必备字段齐全."""
    assert template["name"]
    assert template["industry"] in INDUSTRY_NAMES
    assert template["category"] == "评分卡"
    assert template["target_column"] == "FPD"
    assert template["model_type"]
    assert template["score_formula"]
    assert template["report_template"]
    assert template["default_dataset"]
    assert len(template["recommended_features"]) >= 3
    assert len(template["nodes"]) >= 6
    assert len(template["edges"]) >= 4

    # 边节点一致性
    node_ids = {n["id"] for n in template["nodes"]}
    for edge in template["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


@pytest.mark.parametrize(
    "template",
    [
        BANK_CREDIT_CARD_TEMPLATE,
        INTERNET_FINANCE_TEMPLATE,
        ASSISTED_LOAN_TEMPLATE,
        CASH_LOAN_TEMPLATE,
        ECOM_INSTALMENT_TEMPLATE,
        AUTO_FINANCE_TEMPLATE,
    ],
)
def test_each_template_starts_with_csv_ingest(template):
    """所有模板起点都是 csv_ingest (数据接入)."""
    first = template["nodes"][0]
    assert first["id"] == "csv_ingest"
    assert first["type"] == "csv_ingest"


@pytest.mark.parametrize(
    "template",
    [
        BANK_CREDIT_CARD_TEMPLATE,
        INTERNET_FINANCE_TEMPLATE,
        ASSISTED_LOAN_TEMPLATE,
        CASH_LOAN_TEMPLATE,
        ECOM_INSTALMENT_TEMPLATE,
        AUTO_FINANCE_TEMPLATE,
    ],
)
def test_each_template_ends_with_model_report(template):
    """所有模板终点都是 model_report."""
    last = template["nodes"][-1]
    assert last["id"] == "model_report"
    assert last["type"] == "model_report"


# ===== INDUSTRY_NAMES 集合 =====


def test_industry_names_set_complete():
    """INDUSTRY_NAMES 集合与 6 模板完全对应."""
    assert len(INDUSTRY_NAMES) == 6
    assert "银行信用卡" in INDUSTRY_NAMES
    assert "互联网消金" in INDUSTRY_NAMES
    assert "助贷" in INDUSTRY_NAMES
    assert "现金贷" in INDUSTRY_NAMES
    assert "电商分期" in INDUSTRY_NAMES
    assert "汽车金融" in INDUSTRY_NAMES


# ===== 评分公式正确性 (B30 验收) =====


def test_score_formula_format():
    """所有评分公式符合 'Score = base - pdo × ln(odds)' 模式."""
    import re

    pattern = re.compile(r"^Score\s*=\s*\d+\s*-\s*[\d.]+\s*[×x*]\s*ln\(odds\)$")
    for t in INDUSTRY_TEMPLATES:
        assert pattern.match(t["score_formula"]), (
            f"模板 {t['name']} 评分公式不符合: {t['score_formula']}"
        )


def test_default_dataset_path():
    """默认数据集路径统一为 examples/hscredit_yyp.xlsx."""
    for t in INDUSTRY_TEMPLATES:
        assert t["default_dataset"] == "examples/hscredit_yyp.xlsx"


# ===== 一键实例化 API schema 校验 =====


def test_instantiate_request_overrides_default():
    """InstantiateRequest 默认 params_overrides 为空 dict."""
    from hscredit_studio.schemas.industry_templates import IndustryTemplateInstantiateRequest

    req = IndustryTemplateInstantiateRequest()
    assert req.workflow_name is None
    assert req.params_overrides == {}


def test_rating_range_validation():
    """Rating 1-5 范围由 Pydantic Field 强制."""
    from pydantic import ValidationError

    from hscredit_studio.schemas.industry_templates import IndustryTemplateRatingCreate

    with pytest.raises(ValidationError):
        IndustryTemplateRatingCreate(rating=0)
    with pytest.raises(ValidationError):
        IndustryTemplateRatingCreate(rating=6)
    # 边界值 OK
    IndustryTemplateRatingCreate(rating=1)
    IndustryTemplateRatingCreate(rating=5)
