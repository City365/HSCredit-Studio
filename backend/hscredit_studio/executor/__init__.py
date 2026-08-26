"""节点执行引擎 — DAG 解析 / 协调 / 任务调度.

按 :file:`docs/design/01-system-architecture.md` 第 1.5 节,
执行引擎拆为三层:

- :mod:`parser`    — 把前端 react-flow JSON 解析为节点执行计划,
                    做拓扑排序 / 循环检测 / 入度计算。
- :mod:`coordinator` — 协调 Run / NodeExecution 的状态推进,
                    包含初始节点入队、下游节点触发、重试 / 终态判定。
- :mod:`tasks`     — Celery 任务入口:加载节点、读缓存、调用
                    :meth:`BaseNode.run`、落盘、写缓存、转发到 coordinator。

子模块按依赖顺序加载(parser → coordinator → tasks)。
"""
from __future__ import annotations

from hscredit_studio.executor.coordinator import RunCoordinator
from hscredit_studio.executor.parser import (
    NodeExecutionPlan,
    WorkflowParser,
    get_downstream_ready_nodes,
    get_initial_nodes,
    parse_workflow_definition,
    topological_sort,
)
from hscredit_studio.executor.tasks import run_heavy_node, run_node

__all__ = [
    # parser
    "WorkflowParser",
    "NodeExecutionPlan",
    "parse_workflow_definition",
    "topological_sort",
    "get_initial_nodes",
    "get_downstream_ready_nodes",
    # coordinator
    "RunCoordinator",
    # tasks
    "run_node",
    "run_heavy_node",
]