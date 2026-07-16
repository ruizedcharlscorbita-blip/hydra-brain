"""
dag.py — Hydra Brain v0.6.0
===========================

Directed Acyclic Graph (DAG) task structure, execution statuses, and dependency resolution.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(kw_only=True)
class TaskNode:
    """
    Represents a single step or task of work in the planner execution DAG.
    """
    id: str
    name: str
    description: str
    capability: str
    depends_on: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_specialist: Optional[str] = None
    result: Optional[Any] = None


@dataclass(kw_only=True)
class TaskGraph:
    """
    Directed Acyclic Graph tracking dependencies and execution state of all TaskNodes.
    """
    nodes: Dict[str, TaskNode] = field(default_factory=dict)

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.id] = node

    def get_ready_nodes(self) -> List[TaskNode]:
        """
        Returns all nodes in PENDING status whose dependencies are all in SUCCESS status.
        """
        ready = []
        for node in self.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps_ok = True
            for dep_id in node.depends_on:
                dep_node = self.nodes.get(dep_id)
                if not dep_node or dep_node.status != TaskStatus.SUCCESS:
                    deps_ok = False
                    break
            if deps_ok:
                ready.append(node)
        return ready

    def get_terminal_nodes(self) -> List[TaskNode]:
        """
        Returns nodes that no other nodes depend on.
        """
        all_deps = set()
        for node in self.nodes.values():
            all_deps.update(node.depends_on)
        return [node for node in self.nodes.values() if node.id not in all_deps]

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the graph state for observability traces.
        """
        return {
            "nodes": {
                nid: {
                    "id": n.id,
                    "name": n.name,
                    "description": n.description,
                    "capability": n.capability,
                    "depends_on": n.depends_on,
                    "status": n.status.value,
                    "assigned_specialist": n.assigned_specialist,
                    "result": n.result.to_dict() if n.result and hasattr(n.result, "to_dict") else n.result
                } for nid, n in self.nodes.items()
            }
        }
