"""DAG 解析与拓扑排序.

依据 :file:`docs/design/01-system-architecture.md` 第 1.5 节,
parser 的职责:

1. 把 ``WorkflowDefinition`` (react-flow 序列化) 转为 ``NodeExecutionPlan``。
2. 检查节点 ID 唯一性 + 边的引用合法性。
3. 用 Kahn 算法做拓扑排序;无环 DAG 必然能排好,排不出就抛错。
4. 用 DFS 三色染色定位循环依赖路径,给出可读错误。

性能:本模块所有算法都是 ``O(V+E)``,
对 MVP 模板 (单 run 内 < 100 个节点) 完全够用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hscredit_studio.core.exceptions import WorkflowParseError
from hscredit_studio.schemas.workflow import WorkflowDefinition


@dataclass
class NodeExecutionPlan:
    """单个节点的执行计划.

    Attributes:
        node_id: 工作流内节点 ID(react-flow ``NodeDef.id``)。
        node_type: 节点类型(注册表 key,如 ``optimal_binning_chi``)。
        params: 用户填写的参数快照。
        upstream_node_ids: 上游节点 ID 列表。
        downstream_node_ids: 下游节点 ID 列表。
        is_initial: 是否入度为 0(执行起点)。
    """

    node_id: str
    node_type: str
    params: dict[str, Any]
    upstream_node_ids: list[str] = field(default_factory=list)
    downstream_node_ids: list[str] = field(default_factory=list)
    is_initial: bool = False


class WorkflowParser:
    """工作流定义解析器 — 拓扑排序 + 循环检测 + 入度计算.

    入口::

        plans = WorkflowParser.parse(definition)

    既支持 dict 也支持 Pydantic ``WorkflowDefinition`` 输入;
    内部统一走 :func:`parse_workflow_definition`。
    """

    @staticmethod
    def parse(definition: dict[str, Any] | WorkflowDefinition) -> dict[str, NodeExecutionPlan]:
        """解析工作流定义,返回按 ``node_id`` 索引的执行计划."""
        if isinstance(definition, dict):
            definition = WorkflowDefinition(**definition)
        return parse_workflow_definition(definition)


def parse_workflow_definition(definition: WorkflowDefinition) -> dict[str, NodeExecutionPlan]:
    """解析 Pydantic :class:`WorkflowDefinition` → 节点执行计划.

    Raises:
        WorkflowParseError: 节点 ID 重复、边引用不存在节点、检测到循环依赖。
    """
    # 1. 节点 ID 唯一性
    node_ids = [n.id for n in definition.nodes]
    duplicates = sorted({nid for nid in node_ids if node_ids.count(nid) > 1})
    if duplicates:
        raise WorkflowParseError(
            f"节点 ID 重复: {duplicates}",
            details={"duplicates": duplicates},
        )

    # 2. 边引用合法性
    for edge in definition.edges:
        if edge.source not in node_ids:
            raise WorkflowParseError(
                f"边的源节点 '{edge.source}' 不存在",
                details={
                    "missing_source": edge.source,
                    "edge_id": edge.id,
                    "defined_nodes": node_ids,
                },
            )
        if edge.target not in node_ids:
            raise WorkflowParseError(
                f"边的目标节点 '{edge.target}' 不存在",
                details={
                    "missing_target": edge.target,
                    "edge_id": edge.id,
                    "defined_nodes": node_ids,
                },
            )

    # 3. 构建计划
    plans: dict[str, NodeExecutionPlan] = {
        n.id: NodeExecutionPlan(
            node_id=n.id,
            node_type=n.type,
            params=n.data or {},
        )
        for n in definition.nodes
    }

    for e in definition.edges:
        plans[e.source].downstream_node_ids.append(e.target)
        plans[e.target].upstream_node_ids.append(e.source)

    # 4. 标记初始节点
    for plan in plans.values():
        plan.is_initial = len(plan.upstream_node_ids) == 0

    # 5. 循环检测(DFS 三色染色)
    _detect_cycle(plans)

    # 6. 拓扑排序验证(无环 DAG 必然能拓扑排序)
    topological_sort(plans)

    return plans


def topological_sort(plans: dict[str, NodeExecutionPlan]) -> list[str]:
    """Kahn 算法拓扑排序 — 返回按执行顺序的 ``node_id`` 列表.

    Raises:
        WorkflowParseError: 工作流包含循环依赖(理论上 ``_detect_cycle`` 已经拦过)。
    """
    in_degree: dict[str, int] = {nid: len(p.upstream_node_ids) for nid, p in plans.items()}
    queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        nid = queue.pop(0)
        result.append(nid)
        for downstream_id in plans[nid].downstream_node_ids:
            in_degree[downstream_id] -= 1
            if in_degree[downstream_id] == 0:
                queue.append(downstream_id)

    if len(result) != len(plans):
        # _detect_cycle 已经定位循环路径,这里作为兜底
        raise WorkflowParseError("工作流包含循环依赖")
    return result


def _detect_cycle(plans: dict[str, NodeExecutionPlan]) -> None:
    """DFS 三色染色检测循环.

    WHITE: 未访问;GRAY: 正在访问(在递归栈上);BLACK: 访问完成。
    出现 GRAY → GRAY 的边意味着后向边,即循环。
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(plans, WHITE)

    def dfs(nid: str) -> None:
        color[nid] = GRAY
        for downstream in plans[nid].downstream_node_ids:
            if color[downstream] == GRAY:
                # 发现循环
                cycle_path = _trace_cycle(plans, nid, downstream)
                raise WorkflowParseError(
                    f"检测到循环依赖: {' -> '.join(cycle_path)}",
                    details={"cycle": cycle_path},
                )
            if color[downstream] == WHITE:
                dfs(downstream)
        color[nid] = BLACK

    for nid in plans:
        if color[nid] == WHITE:
            dfs(nid)


def _trace_cycle(
    plans: dict[str, NodeExecutionPlan],
    from_id: str,
    to_id: str,
) -> list[str]:
    """回溯循环路径.

    简化实现:返回 ``[to_id, ..., from_id, to_id]``,其中 ``...`` 是从
    ``from_id`` 出发沿 ``downstream_node_ids`` BFS 找到的若干中间节点。
    生产环境若需要更精确的路径可改用 parent 指针追踪。
    """
    # 从 to_id 回溯到 from_id 的最短路径(简化:展示起点 + 中间 + 终点)
    seen: list[str] = []
    cursor = from_id
    for _ in range(min(3, len(plans))):
        downstream = plans[cursor].downstream_node_ids
        if not downstream:
            break
        cursor = downstream[0]
        seen.append(cursor)
    return [to_id, *seen, from_id, to_id]


def get_initial_nodes(plans: dict[str, NodeExecutionPlan]) -> list[str]:
    """获取入度为 0 的节点(执行起点)."""
    return [nid for nid, p in plans.items() if p.is_initial]


def get_downstream_ready_nodes(
    plans: dict[str, NodeExecutionPlan],
    completed: set[str],
) -> list[str]:
    """获取所有上游已完成的节点(可入队执行).

    Args:
        plans: 全部节点执行计划。
        completed: 已完成节点 ID 集合。

    Returns:
        满足"所有上游都在 ``completed`` 中"且未完成的节点 ID 列表。
        顺序按 ``node_id`` 排序,保证可重现。
    """
    ready: list[str] = []
    for nid, plan in plans.items():
        if nid in completed:
            continue
        if all(up in completed for up in plan.upstream_node_ids):
            ready.append(nid)
    return sorted(ready)


__all__ = [
    "NodeExecutionPlan",
    "WorkflowParser",
    "get_downstream_ready_nodes",
    "get_initial_nodes",
    "parse_workflow_definition",
    "topological_sort",
]
