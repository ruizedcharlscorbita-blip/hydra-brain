"""
confidence_engine.py — Hydra Brain v0.6.0
==========================================

Confidence engine mapped to the HydraContext runtime structure.
Computes a composite confidence score combining routing, consensus, and verification.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.results.consensus_result import ConsensusResult
from core.results.verification_result import VerificationResult
from core.results.confidence_result import ConfidenceScore

logger = logging.getLogger("hydra")

POLICY_CONFIG_PATH = os.path.join("config", "router_policy.json")

_DEFAULT_CONFIDENCE_WEIGHTS = {
    "consensus": 0.40,
    "verification": 0.40,
    "routing": 0.20
}


class ConfidenceScorer:
    """
    Evaluates system confidence in a selected output.
    """
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights if weights is not None else self._load_weights()

    def _load_weights(self) -> Dict[str, float]:
        if not os.path.exists(POLICY_CONFIG_PATH):
            return _DEFAULT_CONFIDENCE_WEIGHTS
        try:
            with open(POLICY_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("confidence_weights", _DEFAULT_CONFIDENCE_WEIGHTS)
        except Exception as e:
            logger.warning(f"ConfidenceScorer: failed to load config/router_policy.json: {e}")
            return _DEFAULT_CONFIDENCE_WEIGHTS

    def score(
        self,
        consensus: ConsensusResult,
        verification: VerificationResult,
    ) -> ConfidenceScore:
        w_con = float(self.weights.get("consensus", _DEFAULT_CONFIDENCE_WEIGHTS["consensus"]))
        w_ver = float(self.weights.get("verification", _DEFAULT_CONFIDENCE_WEIGHTS["verification"]))
        w_rtg = float(self.weights.get("routing", _DEFAULT_CONFIDENCE_WEIGHTS["routing"]))

        total_w = w_con + w_ver + w_rtg
        if total_w > 0:
            w_con /= total_w
            w_ver /= total_w
            w_rtg /= total_w

        c_val = float(consensus.consensus_score)
        v_val = float(verification.score)
        r_val = float(consensus.winner.routing_score)

        comp_con = w_con * c_val
        comp_ver = w_ver * v_val
        comp_rtg = w_rtg * r_val

        final_score = comp_con + comp_ver + comp_rtg
        final_score = max(0.0, min(1.0, final_score))

        if final_score >= 0.80:
            label = "HIGH"
        elif final_score >= 0.60:
            label = "MEDIUM"
        elif final_score >= 0.40:
            label = "LOW"
        else:
            label = "UNCERTAIN"

        logger.info(
            f"ConfidenceScorer: final_score={final_score:.4f} ({label}) "
            f"[consensus={c_val:.2f}, verification={v_val:.2f}, routing={r_val:.2f}]"
        )

        return ConfidenceScore(
            final_score=final_score,
            consensus_component=comp_con,
            verification_component=comp_ver,
            routing_component=comp_rtg,
            label=label
        )


class ConfidenceEngine(BaseEngine):
    """
    Evaluates confidence scorer.
    Updates context.execution.confidence in-place.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.scorer = ConfidenceScorer(weights)

    def process(self, context: HydraContext) -> None:
        consensus = context.execution.consensus
        verification = context.execution.verification
        context.execution.confidence = self.scorer.score(consensus, verification)
