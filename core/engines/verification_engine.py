"""
verification_engine.py — Hydra Brain v0.6.0
============================================

Verification engine mapped to the HydraContext runtime structure.
Asserts that model outputs satisfy constraints (length, keywords, json, etc.).
"""

import json
import re
from typing import Any, List, Optional

from core.context.hydra_context import HydraContext
from core.engines.base import BaseEngine
from core.results.execution_result import ExecutionResult
from core.results.verification_result import CheckResult, VerificationResult


class NonEmptyConstraint:
    """Response must contain non-whitespace text."""
    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        if not text or not text.strip():
            return CheckResult(name, False, "Response is empty or only whitespace.")
        return CheckResult(name, True, "Response is non-empty.")


class MinLengthConstraint:
    """Response must meet a minimum character length."""
    def __init__(self, min_chars: int):
        self.min_chars = min_chars

    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        val = text or ""
        length = len(val)
        if length < self.min_chars:
            return CheckResult(name, False, f"Length {length} is less than minimum {self.min_chars}.")
        return CheckResult(name, True, f"Length {length} meets minimum of {self.min_chars}.")


class MaxLengthConstraint:
    """Response must not exceed a maximum character length."""
    def __init__(self, max_chars: int):
        self.max_chars = max_chars

    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        val = text or ""
        length = len(val)
        if length > self.max_chars:
            return CheckResult(name, False, f"Length {length} exceeds maximum {self.max_chars}.")
        return CheckResult(name, True, f"Length {length} is within maximum of {self.max_chars}.")


class ContainsKeywordConstraint:
    """Response must contain at least one of the specified keywords (case-insensitive)."""
    def __init__(self, keywords: List[str]):
        self.keywords = [k.lower() for k in keywords]

    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        val = (text or "").lower()
        matched = [k for k in self.keywords if k in val]
        if not matched:
            return CheckResult(name, False, f"None of the required keywords matched: {self.keywords}.")
        return CheckResult(name, True, f"Matched keywords: {matched}.")


class ForbiddenKeywordConstraint:
    """Response must not contain any of the forbidden keywords (case-insensitive)."""
    def __init__(self, keywords: List[str]):
        self.keywords = [k.lower() for k in keywords]

    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        val = (text or "").lower()
        matched = [k for k in self.keywords if k in val]
        if matched:
            return CheckResult(name, False, f"Response contains forbidden keywords: {matched}.")
        return CheckResult(name, True, "No forbidden keywords found.")


class JsonFormatConstraint:
    """Response must be valid JSON or contain a valid JSON markdown block."""
    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        val = (text or "").strip()
        if not val:
            return CheckResult(name, False, "Response is empty.")

        try:
            json.loads(val)
            return CheckResult(name, True, "Response is valid JSON.")
        except json.JSONDecodeError:
            pass

        match = re.search(r"```json\s*(.*?)\s*```", val, re.DOTALL | re.IGNORECASE)
        if match:
            inner_content = match.group(1)
            try:
                json.loads(inner_content)
                return CheckResult(name, True, "Response contains valid JSON markdown block.")
            except json.JSONDecodeError as e:
                return CheckResult(name, False, f"Fenced json block is invalid: {str(e)}")

        return CheckResult(name, False, "Response does not contain valid JSON.")


class CodeBlockConstraint:
    """Response must contain at least one fenced code block (e.g. ```python ... ```)."""
    def __call__(self, text: Optional[str]) -> CheckResult:
        name = self.__class__.__name__
        val = text or ""
        match = re.search(r"```\w*\s*.*?\s*```", val, re.DOTALL)
        if not match:
            return CheckResult(name, False, "Response contains no fenced code blocks.")
        return CheckResult(name, True, "Response contains a fenced code block.")


class VerificationEngine(BaseEngine):
    """
    Evaluates one or more constraints against the selected execution winner.
    Updates context.execution.verification in-place.
    """

    def __init__(self, constraints: Optional[List[Any]] = None):
        self.constraints = constraints

    def process(self, context: HydraContext) -> None:
        winner = context.execution.consensus.winner
        # If constraints are not initialized on initialization, read them from context.request
        active_constraints = self.constraints if self.constraints is not None else context.request.constraints
        context.execution.verification = self.verify(winner, active_constraints)

    def verify(self, result: ExecutionResult, constraints: Optional[List[Any]] = None) -> VerificationResult:
        active = constraints if constraints is not None else (self.constraints or [])
        if not active:
            return VerificationResult(
                passed=True,
                checks=[],
                score=1.0,
                model_id=result.model_id
            )

        checks: List[CheckResult] = []
        text = result.response

        for constraint in active:
            try:
                check_res = constraint(text)
                checks.append(check_res)
            except Exception as e:
                checks.append(CheckResult(
                    constraint_name=constraint.__class__.__name__,
                    passed=False,
                    reason=f"Error executing constraint: {str(e)}"
                ))

        passed_count = sum(1 for c in checks if c.passed)
        total_count = len(checks)
        score = passed_count / total_count if total_count > 0 else 1.0
        passed = (passed_count == total_count)

        return VerificationResult(
            passed=passed,
            checks=checks,
            score=score,
            model_id=result.model_id
        )
