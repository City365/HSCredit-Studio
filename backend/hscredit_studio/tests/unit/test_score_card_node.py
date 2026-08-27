"""ScoreCard + RoundScoreCard 节点 smoke test (mocked)."""

from unittest.mock import MagicMock

import pytest

from hscredit_studio.core.exceptions import ValidationError
from hscredit_studio.nodes.scorecard_rule.round_score_card import RoundScoreCardNode
from hscredit_studio.nodes.scorecard_rule.score_card import ScoreCardNode


def test_score_card_node_contract():
    node = ScoreCardNode()
    assert node.contract.node_type == "score_card"
    assert node.contract.category.value == "评分卡与规则"
    assert any(p.name == "pdo" for p in node.contract.params)
    assert any(p.name == "base_score" for p in node.contract.params)


def test_round_score_card_node_contract():
    node = RoundScoreCardNode()
    assert node.contract.node_type == "round_score_card"
    assert node.contract.category.value == "评分卡与规则"


def test_round_score_card_missing_input_raises():
    """未传 score_card 应抛 FeatureNotFoundError."""
    node = RoundScoreCardNode()
    from hscredit_studio.core.exceptions import FeatureNotFoundError

    with pytest.raises(FeatureNotFoundError):
        node.run(inputs={}, params={"decimal": 0})


def test_round_score_card_rejects_non_scorecard_object():
    """传入没有 scorecard_points 方法的对象应抛 DependencyError."""
    node = RoundScoreCardNode()
    from hscredit_studio.core.exceptions import DependencyError

    bogus = MagicMock(spec=[])  # 没有任何方法
    with pytest.raises(DependencyError):
        node.run(inputs={"score_card": bogus}, params={"decimal": 0})


def test_score_card_node_validates_features_param():
    """features 必须是非空列表."""
    node = ScoreCardNode()

    # features 为 None 应抛错
    with pytest.raises(ValidationError):
        # 触发 validate_params 即可
        node.validate_params({"target": "FPD", "features": None})


def test_score_card_node_required_params():
    node = ScoreCardNode()
    # target 和 features 都是 required
    required = {p.name for p in node.contract.params if p.required}
    assert "target" in required
    assert "features" in required


def test_round_score_card_rounds_scores():
    """圆整节点对传入的 score_points 做整数化."""
    import pandas as pd

    node = RoundScoreCardNode()

    # 真实 DataFrame（便于 copy/astype/round/clip）
    df = pd.DataFrame(
        {
            "变量名": ["x1", "x2", "x3"],
            "分箱": ["bin1", "bin2", "bin3"],
            "分箱WOE值": [0.1, -0.2, 0.0],
            "分数": [100.4, 200.6, 300.2],
        }
    )

    mock_sc = MagicMock()
    mock_sc.scorecard_points.return_value = df

    result = node.run(inputs={"score_card": mock_sc}, params={"decimal": 0})
    assert "score_points" in result
    assert "score_card_rounded" in result
    # 圆整后所有分数都是 int
    assert all(isinstance(v, int) for v in result["score_points"]["分数"].tolist())


def test_round_score_card_clamps_to_min_max():
    """min_score / max_score 应截断分数."""
    import pandas as pd

    node = RoundScoreCardNode()

    df = pd.DataFrame(
        {
            "变量名": ["x1"],
            "分箱": ["bin1"],
            "分箱WOE值": [0.1],
            "分数": [999.0],
        }
    )
    mock_sc = MagicMock()
    mock_sc.scorecard_points.return_value = df

    result = node.run(
        inputs={"score_card": mock_sc},
        params={"decimal": 0, "min_score": 0, "max_score": 500},
    )
    assert result["score_points"]["分数"].iloc[0] == 500  # 被上限截断
