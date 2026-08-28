"""6 大行业评分卡模板 — Phase 6 B30.

依据 docs/ROADMAP.md Phase 6 B30:

> 内置 6 个行业模板: 银行信用卡 / 互联网消金 / 助贷 / 现金贷 / 电商分期 / 汽车金融
> 每个模板含: 默认参数、推荐特征、模型选型、评分公式、报告模板
> 模板预览 (只读) + 一键实例化
> 验收: 选"银行信用卡"模板 → 一键生成含 8 个推荐节点的评分卡工作流

本模块导出 :data:`INDUSTRY_TEMPLATES` (6 个), 在 :func:`ensure_system_templates`
启动时一并植入 ``templates`` 表.

每个模板结构::

    {
        "name": str,
        "industry": str,           # 行业 (中文)
        "category": str,           # 模板分类 (评分卡)
        "description": str,
        "icon": str,
        "tags": list[str,
        "target_column": str,      # 推荐 y 列
        "recommended_features": list[str,    # 推荐特征
        "model_type": str,         # 模型选型
        "score_formula": str,      # 评分公式描述
        "report_template": str,    # 报告模板名
        "default_dataset": str,    # 推荐数据集
        "nodes": list[dict,        # 节点编排 (按节点 id)
        "edges": list[dict,
    }
"""
from __future__ import annotations

from typing import Any


def _sc_node(node_id: str, ntype: str, x: int, data: dict[str, Any]) -> dict[str, Any]:
    """快捷构造评分卡节点."""
    return {
        "id": node_id,
        "type": ntype,
        "position": {"x": x, "y": 0},
        "data": data,
    }


# ===== 1. 银行信用卡 =====


BANK_CREDIT_CARD_TEMPLATE: dict[str, Any] = {
    "name": "银行信用卡评分卡",
    "industry": "银行信用卡",
    "category": "评分卡",
    "description": (
        "银行信用卡新客申请评分卡: 央行征信 + 行内行为数据 → IV 分箱 "
        "→ WOE 编码 → 逻辑回归 → 标准评分卡 (A 卡, 申请评分)"
    ),
    "icon": "💳",
    "tags": ["银行", "信用卡", "申请评分", "A卡"],
    "target_column": "FPD",
    "recommended_features": [
        "年龄", "婚姻状态", "学历", "工作年限",
        "年收入", "央行征信分", "近6个月贷款查询次数",
        "近12个月逾期次数", "现有卡片数", "现有贷款余额",
        "负债比", "居住稳定性", "职业类别",
    ],
    "model_type": "逻辑回归 + WOE",
    "score_formula": "Score = 750 - 35.77 × ln(odds)",
    "report_template": "bank_card_report",
    "default_dataset": "examples/hscredit_yyp.xlsx",
    "nodes": [
        _sc_node("csv_ingest", "csv_ingest", 0,
                 {"path": "/data/bank_card.csv", "sep": ",", "encoding": "utf-8"}),
        _sc_node("field_type_infer", "field_type_infer", 240,
                 {"target": "FPD"}),
        _sc_node("missing_rate", "missing_rate", 480,
                 {"threshold": 0.3}),
        _sc_node("iv_analysis", "iv_analysis", 720,
                 {"target": "FPD"}),
        _sc_node("bin_age", "optimal_binning_cart", 960,
                 {"feature": "年龄", "target": "FPD", "max_bins": 6}),
        _sc_node("bin_income", "optimal_binning_cart", 1200,
                 {"feature": "年收入", "target": "FPD", "max_bins": 6}),
        _sc_node("bin_credit", "optimal_binning_cart", 1440,
                 {"feature": "央行征信分", "target": "FPD", "max_bins": 8}),
        _sc_node("woe_encoder", "woe_encoder", 1680,
                 {"target": "FPD"}),
        _sc_node("iv_selector", "iv_selector", 1920,
                 {"target": "FPD", "threshold": 0.02}),
        _sc_node("logistic_regression", "logistic_regression", 2160,
                 {"target": "FPD", "C": 1.0, "max_iter": 200}),
        _sc_node("score_card", "score_card", 2400,
                 {"target": "FPD", "base_score": 750, "pdo": 35.77, "rate": 50}),
        _sc_node("model_report", "model_report", 2640,
                 {"target": "FPD", "output_path": "/tmp/bank_card_report.xlsx"}),
    ],
    "edges": [
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "field_type_infer", "target": "missing_rate"},
        {"source": "field_type_infer", "target": "iv_analysis"},
        {"source": "csv_ingest", "target": "bin_age"},
        {"source": "csv_ingest", "target": "bin_income"},
        {"source": "csv_ingest", "target": "bin_credit"},
        {"source": "bin_age", "target": "woe_encoder"},
        {"source": "bin_income", "target": "woe_encoder"},
        {"source": "bin_credit", "target": "woe_encoder"},
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "logistic_regression"},
        {"source": "logistic_regression", "target": "score_card"},
        {"source": "score_card", "target": "model_report"},
    ],
}


# ===== 2. 互联网消金 =====


INTERNET_FINANCE_TEMPLATE: dict[str, Any] = {
    "name": "互联网消金评分卡",
    "industry": "互联网消金",
    "category": "评分卡",
    "description": (
        "互联网消费金融小额现金贷: 多头借贷数据 + 运营商数据 → 卡方分箱 "
        "→ WOE 编码 → 逻辑回归 (B 卡, 行为评分)"
    ),
    "icon": "📱",
    "tags": ["互联网", "消金", "行为评分", "B卡"],
    "target_column": "FPD",
    "recommended_features": [
        "近1个月申请次数", "近3个月申请次数", "近6个月非银多头机构数",
        "运营商在网时长", "运营商活跃天数", "夜间活跃占比",
        "芝麻分", "腾讯支付分", "多头严重程度",
    ],
    "model_type": "逻辑回归 + WOE",
    "score_formula": "Score = 600 - 40 × ln(odds)",
    "report_template": "internet_finance_report",
    "default_dataset": "examples/hscredit_yyp.xlsx",
    "nodes": [
        _sc_node("csv_ingest", "csv_ingest", 0,
                 {"path": "/data/cf_internet.csv", "sep": ","}),
        _sc_node("field_type_infer", "field_type_infer", 240,
                 {"target": "FPD"}),
        _sc_node("missing_rate", "missing_rate", 480,
                 {"threshold": 0.4}),
        _sc_node("bin_multihead", "optimal_binning_chi", 720,
                 {"feature": "近六个月非银多头机构数", "target": "FPD", "max_bins": 5}),
        _sc_node("bin_zm_score", "optimal_binning_cart", 960,
                 {"feature": "芝麻分", "target": "FPD", "max_bins": 6}),
        _sc_node("woe_encoder", "woe_encoder", 1200,
                 {"target": "FPD"}),
        _sc_node("iv_selector", "iv_selector", 1440,
                 {"target": "FPD", "threshold": 0.03}),
        _sc_node("vif_selector", "vif_selector", 1680,
                 {"threshold": 5.0}),
        _sc_node("logistic_regression", "logistic_regression", 1920,
                 {"target": "FPD", "C": 0.5, "max_iter": 300}),
        _sc_node("score_card", "score_card", 2160,
                 {"target": "FPD", "base_score": 600, "pdo": 40, "rate": 50}),
        _sc_node("model_report", "model_report", 2400,
                 {"target": "FPD", "output_path": "/tmp/cf_internet_report.xlsx"}),
    ],
    "edges": [
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "field_type_infer", "target": "missing_rate"},
        {"source": "csv_ingest", "target": "bin_multihead"},
        {"source": "csv_ingest", "target": "bin_zm_score"},
        {"source": "bin_multihead", "target": "woe_encoder"},
        {"source": "bin_zm_score", "target": "woe_encoder"},
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "vif_selector"},
        {"source": "vif_selector", "target": "logistic_regression"},
        {"source": "logistic_regression", "target": "score_card"},
        {"source": "score_card", "target": "model_report"},
    ],
}


# ===== 3. 助贷 =====


ASSISTED_LOAN_TEMPLATE: dict[str, Any] = {
    "name": "助贷评分卡",
    "industry": "助贷",
    "category": "评分卡",
    "description": "助贷平台导流评分卡: 流量平台数据 + 第三方征信 → 决策树分箱 → 评分卡",
    "icon": "🤝",
    "tags": ["助贷", "导流", "三方征信"],
    "target_column": "FPD",
    "recommended_features": [
        "平台来源", "渠道", "设备指纹稳定性", "地理位置",
        "近30天登录次数", "近30天浏览深度", "年龄段",
        "客单价", "三方征信分", "多头负债",
    ],
    "model_type": "逻辑回归 + 决策树分箱",
    "score_formula": "Score = 650 - 35 × ln(odds)",
    "report_template": "assisted_loan_report",
    "default_dataset": "examples/hscredit_yyp.xlsx",
    "nodes": [
        _sc_node("csv_ingest", "csv_ingest", 0,
                 {"path": "/data/assisted_loan.csv"}),
        _sc_node("field_type_infer", "field_type_infer", 240,
                 {"target": "FPD"}),
        _sc_node("bin_channel", "optimal_binning_dt", 480,
                 {"feature": "渠道", "target": "FPD", "max_bins": 5}),
        _sc_node("bin_third_score", "optimal_binning_cart", 720,
                 {"feature": "三方征信分", "target": "FPD", "max_bins": 6}),
        _sc_node("woe_encoder", "woe_encoder", 960,
                 {"target": "FPD"}),
        _sc_node("iv_selector", "iv_selector", 1200,
                 {"target": "FPD", "threshold": 0.02}),
        _sc_node("logistic_regression", "logistic_regression", 1440,
                 {"target": "FPD", "C": 0.8}),
        _sc_node("score_card", "score_card", 1680,
                 {"target": "FPD", "base_score": 650, "pdo": 35, "rate": 50}),
        _sc_node("model_report", "model_report", 1920,
                 {"target": "FPD", "output_path": "/tmp/assisted_loan_report.xlsx"}),
    ],
    "edges": [
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "csv_ingest", "target": "bin_channel"},
        {"source": "csv_ingest", "target": "bin_third_score"},
        {"source": "bin_channel", "target": "woe_encoder"},
        {"source": "bin_third_score", "target": "woe_encoder"},
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "logistic_regression"},
        {"source": "logistic_regression", "target": "score_card"},
        {"source": "score_card", "target": "model_report"},
    ],
}


# ===== 4. 现金贷 =====


CASH_LOAN_TEMPLATE: dict[str, Any] = {
    "name": "现金贷评分卡",
    "industry": "现金贷",
    "category": "评分卡",
    "description": "现金贷极速小额: 风控规则前置 + 弱数据评分 → 自动审批",
    "icon": "💵",
    "tags": ["现金贷", "极速贷", "弱数据"],
    "target_column": "FPD",
    "recommended_features": [
        "近7天申请次数", "近30天申请次数", "年龄段",
        "运营商在网时长", "收入水平", "设备价格", "常用地址稳定性",
        "负面信息命中数", "紧急联系人核实",
    ],
    "model_type": "LightGBM + 评分卡转换",
    "score_formula": "Score = 500 - 50 × ln(odds)",
    "report_template": "cash_loan_report",
    "default_dataset": "examples/hscredit_yyp.xlsx",
    "nodes": [
        _sc_node("csv_ingest", "csv_ingest", 0,
                 {"path": "/data/cash_loan.csv"}),
        _sc_node("field_type_infer", "field_type_infer", 240,
                 {"target": "FPD"}),
        _sc_node("bin_freq_7d", "optimal_binning_chi", 480,
                 {"feature": "近7天申请次数", "target": "FPD", "max_bins": 5}),
        _sc_node("bin_op_age", "optimal_binning_cart", 720,
                 {"feature": "运营商在网时长", "target": "FPD", "max_bins": 5}),
        _sc_node("woe_encoder", "woe_encoder", 960,
                 {"target": "FPD"}),
        _sc_node("iv_selector", "iv_selector", 1200,
                 {"target": "FPD", "threshold": 0.02}),
        _sc_node("lightgbm", "lightgbm_classifier", 1440,
                 {"target": "FPD", "num_leaves": 31, "learning_rate": 0.05}),
        _sc_node("score_card", "score_card", 1680,
                 {"target": "FPD", "base_score": 500, "pdo": 50, "rate": 50}),
        _sc_node("model_report", "model_report", 1920,
                 {"target": "FPD", "output_path": "/tmp/cash_loan_report.xlsx"}),
    ],
    "edges": [
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "csv_ingest", "target": "bin_freq_7d"},
        {"source": "csv_ingest", "target": "bin_op_age"},
        {"source": "bin_freq_7d", "target": "woe_encoder"},
        {"source": "bin_op_age", "target": "woe_encoder"},
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "lightgbm"},
        {"source": "lightgbm", "target": "score_card"},
        {"source": "score_card", "target": "model_report"},
    ],
}


# ===== 5. 电商分期 =====


ECOM_INSTALMENT_TEMPLATE: dict[str, Any] = {
    "name": "电商分期评分卡",
    "industry": "电商分期",
    "category": "评分卡",
    "description": "电商分期付款风控: 平台交易数据 + 行为序列 → 评分",
    "icon": "🛒",
    "tags": ["电商", "分期", "交易数据"],
    "target_column": "FPD",
    "recommended_features": [
        "近90天订单数", "客单价", "退货率", "账户年龄",
        "近30天活跃天数", "品类偏好分散度", "差评次数",
        "VIP等级", "信用支付使用率",
    ],
    "model_type": "逻辑回归 + WOE",
    "score_formula": "Score = 700 - 30 × ln(odds)",
    "report_template": "ecom_instalment_report",
    "default_dataset": "examples/hscredit_yyp.xlsx",
    "nodes": [
        _sc_node("csv_ingest", "csv_ingest", 0,
                 {"path": "/data/ecom_instalment.csv"}),
        _sc_node("field_type_infer", "field_type_infer", 240,
                 {"target": "FPD"}),
        _sc_node("bin_orders", "optimal_binning_cart", 480,
                 {"feature": "近90天订单数", "target": "FPD", "max_bins": 6}),
        _sc_node("bin_aov", "optimal_binning_cart", 720,
                 {"feature": "客单价", "target": "FPD", "max_bins": 6}),
        _sc_node("bin_active", "optimal_binning_cart", 960,
                 {"feature": "近30天活跃天数", "target": "FPD", "max_bins": 6}),
        _sc_node("woe_encoder", "woe_encoder", 1200,
                 {"target": "FPD"}),
        _sc_node("iv_selector", "iv_selector", 1440,
                 {"target": "FPD", "threshold": 0.02}),
        _sc_node("logistic_regression", "logistic_regression", 1680,
                 {"target": "FPD"}),
        _sc_node("score_card", "score_card", 1920,
                 {"target": "FPD", "base_score": 700, "pdo": 30, "rate": 50}),
        _sc_node("model_report", "model_report", 2160,
                 {"target": "FPD", "output_path": "/tmp/ecom_instalment_report.xlsx"}),
    ],
    "edges": [
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "csv_ingest", "target": "bin_orders"},
        {"source": "csv_ingest", "target": "bin_aov"},
        {"source": "csv_ingest", "target": "bin_active"},
        {"source": "bin_orders", "target": "woe_encoder"},
        {"source": "bin_aov", "target": "woe_encoder"},
        {"source": "bin_active", "target": "woe_encoder"},
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "logistic_regression"},
        {"source": "logistic_regression", "target": "score_card"},
        {"source": "score_card", "target": "model_report"},
    ],
}


# ===== 6. 汽车金融 =====


AUTO_FINANCE_TEMPLATE: dict[str, Any] = {
    "name": "汽车金融评分卡",
    "industry": "汽车金融",
    "category": "评分卡",
    "description": "汽车贷款 (新车/二手车) 风控评分卡: 个人资质 + 车辆评估 → 评分",
    "icon": "🚗",
    "tags": ["汽车金融", "新车贷", "二手车贷"],
    "target_column": "FPD",
    "recommended_features": [
        "车龄", "车型档次", "里程数", "首付比例",
        "贷款金额", "贷款期限", "年收入", "负债比",
        "央行征信分", "近24个月逾期次数", "工作稳定性",
    ],
    "model_type": "逻辑回归 + WOE",
    "score_formula": "Score = 720 - 32 × ln(odds)",
    "report_template": "auto_finance_report",
    "default_dataset": "examples/hscredit_yyp.xlsx",
    "nodes": [
        _sc_node("csv_ingest", "csv_ingest", 0,
                 {"path": "/data/auto_finance.csv"}),
        _sc_node("field_type_infer", "field_type_infer", 240,
                 {"target": "FPD"}),
        _sc_node("bin_downpay", "optimal_binning_cart", 480,
                 {"feature": "首付比例", "target": "FPD", "max_bins": 5}),
        _sc_node("bin_amount", "optimal_binning_cart", 720,
                 {"feature": "贷款金额", "target": "FPD", "max_bins": 6}),
        _sc_node("bin_pboc", "optimal_binning_cart", 960,
                 {"feature": "央行征信分", "target": "FPD", "max_bins": 8}),
        _sc_node("woe_encoder", "woe_encoder", 1200,
                 {"target": "FPD"}),
        _sc_node("iv_selector", "iv_selector", 1440,
                 {"target": "FPD", "threshold": 0.02}),
        _sc_node("vif_selector", "vif_selector", 1680,
                 {"threshold": 5.0}),
        _sc_node("logistic_regression", "logistic_regression", 1920,
                 {"target": "FPD", "C": 1.0}),
        _sc_node("score_card", "score_card", 2160,
                 {"target": "FPD", "base_score": 720, "pdo": 32, "rate": 50}),
        _sc_node("model_report", "model_report", 2400,
                 {"target": "FPD", "output_path": "/tmp/auto_finance_report.xlsx"}),
    ],
    "edges": [
        {"source": "csv_ingest", "target": "field_type_infer"},
        {"source": "csv_ingest", "target": "bin_downpay"},
        {"source": "csv_ingest", "target": "bin_amount"},
        {"source": "csv_ingest", "target": "bin_pboc"},
        {"source": "bin_downpay", "target": "woe_encoder"},
        {"source": "bin_amount", "target": "woe_encoder"},
        {"source": "bin_pboc", "target": "woe_encoder"},
        {"source": "woe_encoder", "target": "iv_selector"},
        {"source": "iv_selector", "target": "vif_selector"},
        {"source": "vif_selector", "target": "logistic_regression"},
        {"source": "logistic_regression", "target": "score_card"},
        {"source": "score_card", "target": "model_report"},
    ],
}


INDUSTRY_TEMPLATES: list[dict[str, Any]] = [
    BANK_CREDIT_CARD_TEMPLATE,
    INTERNET_FINANCE_TEMPLATE,
    ASSISTED_LOAN_TEMPLATE,
    CASH_LOAN_TEMPLATE,
    ECOM_INSTALMENT_TEMPLATE,
    AUTO_FINANCE_TEMPLATE,
]
"""6 大行业评分卡模板 (Phase 6 B30).

每个模板包含 8-13 个节点 (评分卡完整链路), 满足
"银行信用卡模板一键生成含 8 个推荐节点的评分卡工作流" 验收.
"""


__all__ = [
    "ASSISTED_LOAN_TEMPLATE",
    "AUTO_FINANCE_TEMPLATE",
    "BANK_CREDIT_CARD_TEMPLATE",
    "CASH_LOAN_TEMPLATE",
    "ECOM_INSTALMENT_TEMPLATE",
    "INDUSTRY_TEMPLATES",
    "INTERNET_FINANCE_TEMPLATE",
]
