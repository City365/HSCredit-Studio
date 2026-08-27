"""单元测试 — DAG 解析器."""

import pytest

from hscredit_studio.core.exceptions import WorkflowParseError
from hscredit_studio.executor.parser import (
    get_downstream_ready_nodes,
    get_initial_nodes,
    parse_workflow_definition,
    topological_sort,
)
from hscredit_studio.schemas.workflow import (
    EdgeDef,
    NodeDef,
    NodePosition,
    WorkflowDefinition,
)


def _make_def(nodes, edges):
    return WorkflowDefinition(
        nodes=[NodeDef(id=n["id"], type=n["type"], position=NodePosition(**n["position"]), data={}) for n in nodes],
        edges=[EdgeDef(source=e["source"], target=e["target"]) for e in edges],
    )


def test_simple_linear_workflow():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "field_type_infer", "position": {"x": 100, "y": 0}},
        ],
        [{"source": "a", "target": "b"}],
    )
    plans = parse_workflow_definition(defn)
    assert len(plans) == 2
    assert plans["a"].is_initial is True
    assert plans["b"].is_initial is False
    assert plans["a"].downstream_node_ids == ["b"]
    assert plans["b"].upstream_node_ids == ["a"]


def test_diamond_workflow():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "missing_rate", "position": {"x": 100, "y": 0}},
            {"id": "c", "type": "iv_analysis", "position": {"x": 100, "y": 100}},
            {"id": "d", "type": "woe_encoder", "position": {"x": 200, "y": 50}},
        ],
        [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ],
    )
    plans = parse_workflow_definition(defn)
    assert plans["a"].is_initial is True
    assert plans["b"].is_initial is False
    assert plans["d"].is_initial is False
    initial_ids = get_initial_nodes(plans)
    assert initial_ids == ["a"]


def test_cycle_detection():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "missing_rate", "position": {"x": 100, "y": 0}},
        ],
        [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    )
    with pytest.raises(WorkflowParseError, match="循环"):
        parse_workflow_definition(defn)


def test_duplicate_node_id():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "a", "type": "missing_rate", "position": {"x": 100, "y": 0}},
        ],
        [],
    )
    with pytest.raises(WorkflowParseError, match="重复"):
        parse_workflow_definition(defn)


def test_edge_to_nonexistent_node():
    defn = _make_def(
        [{"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}}],
        [{"source": "a", "target": "ghost"}],
    )
    with pytest.raises(WorkflowParseError, match="不存在"):
        parse_workflow_definition(defn)


def test_edge_from_nonexistent_node():
    defn = _make_def(
        [{"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}}],
        [{"source": "ghost", "target": "a"}],
    )
    with pytest.raises(WorkflowParseError, match="不存在"):
        parse_workflow_definition(defn)


def test_topological_sort():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "missing_rate", "position": {"x": 100, "y": 0}},
            {"id": "c", "type": "iv_analysis", "position": {"x": 100, "y": 100}},
        ],
        [{"source": "a", "target": "b"}, {"source": "a", "target": "c"}],
    )
    plans = parse_workflow_definition(defn)
    topo = topological_sort(plans)
    assert topo[0] == "a"
    assert set(topo[1:]) == {"b", "c"}


def test_get_downstream_ready_nodes():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "missing_rate", "position": {"x": 100, "y": 0}},
            {"id": "c", "type": "iv_analysis", "position": {"x": 100, "y": 100}},
            {"id": "d", "type": "woe_encoder", "position": {"x": 200, "y": 50}},
        ],
        [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ],
    )
    plans = parse_workflow_definition(defn)
    ready = get_downstream_ready_nodes(plans, completed={"a", "b", "c"})
    assert ready == ["d"]


def test_get_downstream_ready_empty_when_none_completed():
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "missing_rate", "position": {"x": 100, "y": 0}},
        ],
        [{"source": "a", "target": "b"}],
    )
    plans = parse_workflow_definition(defn)
    ready = get_downstream_ready_nodes(plans, completed=set())
    # 初始无完成节点 → 只有无上游的根节点 a ready, 下游 b 等待 a 完成
    assert "a" in ready
    assert "b" not in ready


def test_topological_sort_linear_chain():
    """线性链 a->b->c 的拓扑排序唯一."""
    defn = _make_def(
        [
            {"id": "a", "type": "csv_ingest", "position": {"x": 0, "y": 0}},
            {"id": "b", "type": "missing_rate", "position": {"x": 100, "y": 0}},
            {"id": "c", "type": "iv_analysis", "position": {"x": 200, "y": 0}},
        ],
        [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    )
    plans = parse_workflow_definition(defn)
    topo = topological_sort(plans)
    assert topo == ["a", "b", "c"]


def test_get_initial_nodes_empty_for_disconnected():
    """完全空工作流."""
    defn = _make_def([], [])
    plans = parse_workflow_definition(defn)
    assert get_initial_nodes(plans) == []
