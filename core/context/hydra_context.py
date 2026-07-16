"""
hydra_context.py — Hydra Brain v0.6.0
======================================

State-carrying context container for a single Hydra execution run.
Allows pipeline engines to read inputs and write outputs without direct return values.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.results.execution_result import ExecutionResult
from core.results.consensus_result import ConsensusResult
from core.results.verification_result import VerificationResult
from core.results.correction_result import CorrectionResult
from core.results.confidence_result import ConfidenceScore
from core.results.trace_result import HydraTrace
from core.results.hydra_result import HydraResult
from core.pipeline.dag import TaskGraph


@dataclass(kw_only=True)
class RequestContext:
    """Inputs and settings for the request."""
    prompt: str
    constraints: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class RoutingContext:
    """Intent and capability ranking details computed by routing stages."""
    intent: Optional[str] = None
    intent_weights: Dict[str, float] = field(default_factory=dict)
    eligible_models: List[str] = field(default_factory=list)
    ranked_models: List[Tuple[float, Dict[str, Any]]] = field(default_factory=list)


@dataclass(kw_only=True)
class WorkflowContext:
    """DAG and structured tasks for agentic scheduling (Sprints 6.2–6.4)."""
    planner_output: Optional[str] = None
    task_graph: Optional[TaskGraph] = None
    scheduler_state: Dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class ExecutionContext:
    """Model outputs, consensus choices, verification, and confidence metrics."""
    results: List[ExecutionResult] = field(default_factory=list)
    consensus: Optional[ConsensusResult] = None
    verification: Optional[VerificationResult] = None
    correction: Optional[CorrectionResult] = None
    confidence: Optional[ConfidenceScore] = None


@dataclass(kw_only=True)
class HydraContext:
    """The root execution context flowing through the Hydra orchestrator."""
    request: RequestContext
    routing: RoutingContext = field(default_factory=RoutingContext)
    workflow: WorkflowContext = field(default_factory=WorkflowContext)
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    trace: Optional[HydraTrace] = None
    final_result: Optional[HydraResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
