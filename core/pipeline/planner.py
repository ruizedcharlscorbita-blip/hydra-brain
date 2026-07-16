"""
planner.py — Hydra Brain v0.6.0
================================

Planner engine that translates user prompts into structural execution TaskGraphs.
"""

from typing import List, Optional

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.pipeline.dag import TaskNode, TaskGraph


class PlannerEngine(BaseEngine):
    """
    Analyzes prompts and compiles them into a structured execution TaskGraph.
    """

    def process(self, context: HydraContext) -> None:
        prompt = context.request.prompt
        graph = TaskGraph()

        # Split on sequential connectors: "then", "and then", or punctuation clauses
        raw_parts = [p.strip() for p in prompt.split(" then ") if p.strip()]
        if len(raw_parts) <= 1:
            # Try splitting on commas if they look like task sequencing
            comma_parts = [p.strip() for p in prompt.split(",") if p.strip()]
            if len(comma_parts) > 1 and any(any(kw in p.lower() for kw in ["code", "write", "research", "compare", "summarize"]) for p in comma_parts):
                raw_parts = comma_parts
            else:
                raw_parts = [prompt]

        prev_id: Optional[str] = None
        for idx, part in enumerate(raw_parts):
            node_id = f"task_{idx + 1}"
            cap = self._detect_capability(part)

            node = TaskNode(
                id=node_id,
                name=f"Task {idx + 1}",
                description=part,
                capability=cap,
                depends_on=[prev_id] if prev_id else []
            )
            graph.add_node(node)
            prev_id = node_id

        context.workflow.task_graph = graph
        context.workflow.planner_output = f"Compiled into {len(graph.nodes)} sequential tasks."

    def _detect_capability(self, text: str) -> str:
        """
        Maps a text segment to the most likely capability.
        """
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["code", "python", "script", "function", "debug", "develop", "program"]):
            return "coding"
        if any(kw in text_lower for kw in ["research", "compare", "analyze", "analysis", "benchmark"]):
            return "analysis"
        if any(kw in text_lower for kw in ["write", "summarize", "summary", "draft", "essay", "post"]):
            return "writing"
        if any(kw in text_lower for kw in ["solve", "math", "reason", "logic", "calculate"]):
            return "reasoning"
        if any(kw in text_lower for kw in ["image", "picture", "photo", "draw", "visual"]):
            return "vision"
        if any(kw in text_lower for kw in ["json", "schema", "structured output"]):
            return "json_output"
        return "chat"
