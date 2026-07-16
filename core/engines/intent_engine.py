"""
intent_engine.py — Hydra Brain v0.6.0
=======================================

Intent engine mapped to the HydraContext runtime structure.
Classifies user prompt intent into capability weights and dominant intent.
"""

import re
from typing import Dict, List, Tuple

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine

# Copy pattern definitions directly from core/intent.py
_INTENT_RULES: List[Tuple[str, float, List[str]]] = [
    ("coding", 0.9, [
        r"\bcode\b", r"\bprogram\b", r"\bprogramming\b",
        r"\bfunction\b", r"\bclass\b", r"\bmethod\b",
        r"\bscript\b", r"\bimplement\b", r"\bimplementation\b",
        r"\brefactor\b", r"\bdebug\b", r"\bfix.*bug\b", r"\bbug\b",
        r"\bpython\b", r"\bjavascript\b", r"\btypescript\b", r"\bjava\b",
        r"\brust\b", r"\bc\+\+\b", r"\bcpp\b", r"\bgo\b",
        r"\bsql\b", r"\bquery\b", r"\bapi\b", r"\bendpoint\b",
        r"\balgorithm\b", r"\bdata structure\b", r"\brecursion\b",
        r"\btest case\b", r"\bunit test\b", r"\bmodule\b",
        r"\bcompile\b", r"\bsyntax\b", r"\bcli\b",
    ]),
    ("reasoning", 0.85, [
        r"\breason\b", r"\bthink\b", r"\bthinking\b",
        r"\bstep.?by.?step\b", r"\bchain.?of.?thought\b",
        r"\bmath\b", r"\bmathematics\b", r"\bcalculate\b", r"\bcompute\b",
        r"\bsolve\b", r"\bprove\b", r"\bproof\b",
        r"\blogic\b", r"\blogical\b", r"\bdeduce\b",
        r"\bcompare\b", r"\bevaluate\b", r"\bjudge\b",
        r"\banalyze\b", r"\bbreak down\b", r"\bbreakdown\b",
        r"\bproblem\b", r"\bpuzzle\b", r"\boptimize\b",
        r"\bwhy\b", r"\bhow does\b", r"\bexplain.*work\b",
    ]),
    ("writing", 0.85, [
        r"\bwrite\b", r"\bwriting\b", r"\bwritten\b",
        r"\bessay\b", r"\barticle\b", r"\bblog\b", r"\bpost\b",
        r"\bstory\b", r"\bnarrative\b", r"\bfiction\b",
        r"\bcreative\b", r"\bpoem\b", r"\bpoetry\b",
        r"\bemail\b", r"\bletter\b", r"\breport\b",
        r"\bdraft\b", r"\bcompose\b", r"\bcopywrite\b",
        r"\bcontent\b", r"\bdescription\b", r"\bproduct description\b",
        r"\bcover letter\b", r"\bresume\b",
    ]),
    ("analysis", 0.8, [
        r"\bsummariz\b", r"\bsummary\b", r"\bsummarise\b",
        r"\bextract\b", r"\bextraction\b",
        r"\banalyze\b", r"\banalysis\b", r"\banalyse\b",
        r"\breview\b", r"\baudit\b",
        r"\bexplain\b", r"\bexplanation\b",
        r"\bwhat does\b", r"\bwhat is\b",
        r"\bparse\b", r"\bparsing\b",
        r"\bdocument\b", r"\btext\b", r"\bpassage\b",
        r"\bclassify\b", r"\bcategorize\b",
        r"\bdata\b", r"\bdataset\b",
        r"\binsight\b", r"\breport\b",
        r"\blong.*context\b", r"\bbook\b", r"\bchapter\b",
    ]),
    ("vision", 0.95, [
        r"\bimage\b", r"\bphoto\b", r"\bpicture\b",
        r"\bscreenshot\b", r"\bdiagram\b", r"\bchart\b",
        r"\bvisual\b", r"\bdescribe.*this\b",
        r"\bwhat.*in.*image\b", r"\bwhat.*photo\b",
        r"\bocr\b", r"\bread.*image\b",
        r"\bidentify.*image\b", r"\bvision\b",
        r"\bfigure\b", r"\billustration\b",
    ]),
    ("tool_calling", 0.8, [
        r"\bfunction call\b", r"\btool\b", r"\binvoke\b",
        r"\bfetch\b", r"\bsearch\b", r"\blookup\b",
        r"\bapi call\b", r"\buse.*tool\b",
        r"\buse.*function\b", r"\bstructured call\b",
        r"\bagent\b",
    ]),
    ("json_output", 0.85, [
        r"\bjson\b", r"\bstructured.*output\b", r"\boutput.*json\b",
        r"\bformat.*as\b", r"\bschema\b", r"\bformat.*json\b",
        r"\bparseable\b", r"\bstructured.*format\b",
        r"\bkey.*value\b", r"\barray of\b", r"\bobject.*with.*fields\b",
    ]),
    ("chat", 0.5, [
        r"\bchat\b", r"\bconversation\b", r"\btalk\b",
        r"\bhello\b", r"\bhi\b", r"\bhey\b",
        r"\btell me\b", r"\bcan you\b", r"\bplease\b",
        r"\bwhat.*think\b", r"\byour opinion\b",
        r"\broleplay\b", r"\bpretend\b", r"\bact as\b",
    ]),
]

_CHAT_FLOOR = 0.3
_WEIGHT_CAP = 1.0


class IntentEngine(BaseEngine):
    """
    Classifies a user prompt intent into a capability weight dict.
    Updates context.routing in-place.
    """

    def __init__(self) -> None:
        self._compiled: List[Tuple[str, float, List[re.Pattern]]] = []
        for cap, weight, patterns in _INTENT_RULES:
            compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
            self._compiled.append((cap, weight, compiled_patterns))

    def process(self, context: HydraContext) -> None:
        prompt = context.request.prompt
        weights = self.parse_intent(prompt)
        context.routing.intent_weights = weights
        context.routing.intent = max(weights, key=lambda k: weights[k])

    def parse_intent(self, prompt: str) -> Dict[str, float]:
        if not prompt or not isinstance(prompt, str):
            return self._empty_weights()

        weights: Dict[str, float] = self._empty_weights()
        prompt_stripped = prompt.strip()

        for cap, base_weight, compiled_patterns in self._compiled:
            matched_count = sum(
                1 for pattern in compiled_patterns
                if pattern.search(prompt_stripped)
            )
            if matched_count > 0:
                score = min(_WEIGHT_CAP, base_weight + (matched_count - 1) * 0.05)
                weights[cap] = max(weights[cap], score)

        dominant = any(v >= 0.5 for k, v in weights.items() if k != "chat")
        if not dominant and weights["chat"] < _CHAT_FLOOR:
            weights["chat"] = _CHAT_FLOOR

        return weights

    def dominant_capability(self, prompt: str) -> str:
        weights = self.parse_intent(prompt)
        return max(weights, key=lambda k: weights[k])

    @staticmethod
    def _empty_weights() -> Dict[str, float]:
        return {
            "coding": 0.0,
            "reasoning": 0.0,
            "writing": 0.0,
            "analysis": 0.0,
            "vision": 0.0,
            "chat": 0.0,
            "tool_calling": 0.0,
            "json_output": 0.0,
        }
