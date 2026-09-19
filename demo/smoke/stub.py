"""Canned responses for Thiran AI, enabling complete state machine testing
with no API key, no network, and zero tokens.
Optimized for minimal LLM calls with unified Intervention and strategy shifting.
"""
from __future__ import annotations

import json
from typing import Any, Type
from pydantic import BaseModel

# ------------------------------------------------------------------- Session 1 Canned Data

DIAGNOSTIC_V1 = """{
  "prior_score": 1,
  "concepts_detected": ["recursion", "base_case"],
  "challenge_question": "Write a recursive function countdown(n) that prints from n to 1."
}"""

COGNITIVE_V1 = """{
  "misconceptions": [
    {
      "concept": "base_case",
      "description": "Missing stopping condition causes infinite recursion.",
      "evidence": "countdown(n - 1)",
      "attempt_count": 1,
      "confidence": "medium",
      "past_interventions": [],
      "resolved": false
    }
  ],
  "mental_model_summary": "Treats recursion as unbounded iteration without termination.",
  "confidence_level": "medium"
}"""

INTERVENTION_V1 = """{
  "explanation": "Recursion requires a base case to stop calling itself. Think of it like a bouncer at a door halting entry when full.",
  "teaching_strategy_used": "conceptual_analogy",
  "problem_statement": "What stops countdown(n) when n reaches 0? Add the base case.",
  "buggy_code_or_prompt": "def countdown(n):\\n    countdown(n - 1)",
  "target_misconception": "base_case"
}"""

GATE_BLOCK = """{
  "status": "BLOCK",
  "score": 2,
  "feedback": "Missing base case guard when n <= 0.",
  "unresolved_evidence": "countdown(n - 1)"
}"""

INTERVENTION_V2 = """{
  "explanation": "Trace countdown(0): without 'if n <= 0: return', it calls countdown(-1). Insert the guard clause as the first statement.",
  "teaching_strategy_used": "execution_trace_guard",
  "problem_statement": "Add 'if n <= 0: return' as the first line of countdown(n).",
  "buggy_code_or_prompt": "def countdown(n):\\n    # add guard here\\n    print(n)\\n    countdown(n - 1)",
  "target_misconception": "base_case"
}"""

GATE_PASS = """{
  "status": "PASS",
  "score": 4,
  "feedback": "Base case correctly halts recursion safely.",
  "unresolved_evidence": null
}"""

# ------------------------------------------------------------------- Session 2 Canned Data

DIAGNOSTIC_S2 = """{
  "prior_score": 4,
  "concepts_detected": ["base_case", "return_values"],
  "challenge_question": "Write a recursive function factorial(n) returning n! using base case n <= 1: return 1."
}"""

COGNITIVE_S2 = """{
  "misconceptions": [
    {
      "concept": "return_values",
      "description": "Omits multiplying n with the recursive call in the return statement.",
      "evidence": "return factorial(n - 1)",
      "attempt_count": 1,
      "confidence": "medium",
      "past_interventions": [],
      "resolved": false
    }
  ],
  "mental_model_summary": "Understands stopping condition but forgets to accumulate return values across the stack.",
  "confidence_level": "medium"
}"""

INTERVENTION_S2 = """{
  "explanation": "Each stack frame must multiply n by the value returned from the smaller problem: return n * factorial(n - 1).",
  "teaching_strategy_used": "execution_trace_guard",
  "problem_statement": "In factorial(n), multiply n with the recursive call result.",
  "buggy_code_or_prompt": "def factorial(n):\\n    if n <= 1: return 1\\n    return factorial(n - 1)",
  "target_misconception": "return_values"
}"""

GATE_PASS_S2 = """{
  "status": "PASS",
  "score": 4,
  "feedback": "Correct! factorial(n) returns n * factorial(n - 1) with valid base case.",
  "unresolved_evidence": null
}"""

# Default scripted sequence: 1 block, 1 pass (proves backward loop)
DEFAULT_SCRIPT: dict[str, list[str]] = {
    "assess": [DIAGNOSTIC_V1],
    "cognitive": [COGNITIVE_V1],
    "intervention": [INTERVENTION_V1, INTERVENTION_V2],
    "gate": [GATE_BLOCK, GATE_PASS],
}

DEFAULT_ANSWERS = [
    "def countdown(n):\n    print(n)\n    countdown(n - 1)",           # diagnostic answer
    "def countdown(n):\n    countdown(n - 1)",                          # socratic answer 1 (buggy)
    "def countdown(n):\n    if n <= 0:\n        return\n    print(n)\n    countdown(n - 1)",  # socratic answer 2 (fixed)
]

DEFAULT_ANSWERS_S2 = [
    "def factorial(n):\n    if n <= 1: return 1\n    return factorial(n - 1)",
    "def factorial(n):\n    if n <= 1: return 1\n    return n * factorial(n - 1)",
]


class ThiranStub:
    """A drop-in replacement for slice.llm.complete for Thiran AI."""

    def __init__(self, script: dict[str, list[str]] | None = None) -> None:
        self.script = script or {k: list(v) for k, v in DEFAULT_SCRIPT.items()}
        self.calls: list[str] = []
        self._n: dict[str, int] = {}

    def __call__(
        self,
        *,
        settings,
        budget,
        messages,
        schema: Type[BaseModel] | None = None,
        model: str | None = None,
        step: str = "call",
        timeout: float = 120.0,
    ) -> Any:
        base = step.split(":")[0]
        i = self._n.get(base, 0)
        self._n[base] = i + 1
        self.calls.append(step)

        try:
            raw = self.script[base][i]
        except (KeyError, IndexError):
            raise AssertionError(
                f"ThiranStub has no scripted reply {i} for step {step!r}. "
                f"Recorded calls: {self.calls}."
            )

        budget.record_tokens(len(raw) // 4)
        return schema.model_validate_json(raw) if schema else raw


class CleanStub(ThiranStub):
    """Passes on the very first try (no backward loop)."""

    def __init__(self) -> None:
        super().__init__({
            "assess": [DIAGNOSTIC_V1],
            "cognitive": [COGNITIVE_V1],
            "intervention": [INTERVENTION_V1],
            "gate": [GATE_PASS],
        })


class Session2Stub(ThiranStub):
    """Simulates a returning learner in Session 2 tackling advanced recursion."""

    def __init__(self) -> None:
        super().__init__({
            "assess": [DIAGNOSTIC_S2],
            "cognitive": [COGNITIVE_S2],
            "intervention": [INTERVENTION_S2],
            "gate": [GATE_PASS_S2],
        })


class AlwaysBlocksStub(ThiranStub):
    """Fails every time, demonstrating the max_loops_exhausted bound."""

    def __init__(self) -> None:
        super().__init__({
            "assess": [DIAGNOSTIC_V1],
            "cognitive": [COGNITIVE_V1],
            "intervention": [INTERVENTION_V1, INTERVENTION_V2, INTERVENTION_V2, INTERVENTION_V2],
            "gate": [GATE_BLOCK, GATE_BLOCK, GATE_BLOCK, GATE_BLOCK],
        })


# Legacy alias for test compatibility
Stub = ThiranStub
