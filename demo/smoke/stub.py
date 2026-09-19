"""Canned responses for Thiran AI, enabling complete state machine testing
with no API key, no network, and zero tokens across multiple DSA concepts.
Optimized for minimal LLM calls with unified Intervention and strategy shifting.
Supports:
- Recursion (countdown, factorial)
- Two Pointers (pair sum sorted)
- Binary Search (boundary updates)
"""
from __future__ import annotations

import json
from typing import Any, Type
from pydantic import BaseModel

# ------------------------------------------------------------------- Recursion Session 1 Canned Data

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
  "mental_model_summary": "Treats recursion as unbounded iteration.",
  "confidence_level": "medium"
}"""

INTERVENTION_V1 = """{
  "mistake_diagnosis": "Missing stopping condition causes infinite recursion.",
  "core_dsa_concept": "Recursion breaks problems down until a base case terminates calls.",
  "simple_example": "countdown(0): 'if n <= 0: return' halts recursion.",
  "explanation": "Needs a base case to halt self-calls.",
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
  "mistake_diagnosis": "Recursive call executes before checking if n <= 0.",
  "core_dsa_concept": "Guard clause must execute before any recursive call.",
  "simple_example": "countdown(0): guard halts before -1 call.",
  "explanation": "Trace countdown(0): guard halts it before recursive call.",
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

# ------------------------------------------------------------------- Recursion Session 2 Canned Data

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
  "mistake_diagnosis": "Omits multiplying n with the recursive call in the return statement.",
  "core_dsa_concept": "Accumulating recursive results requires multiplying n by the returned value from n - 1.",
  "simple_example": "factorial(3) = 3 * factorial(2) = 3 * 2 = 6.",
  "explanation": "Each frame must multiply n by the value returned: return n * factorial(n - 1).",
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

# ------------------------------------------------------------------- Two Pointers Canned Data

DIAGNOSTIC_TP = """{
  "prior_score": 1,
  "concepts_detected": ["two_pointers", "opposite_ends"],
  "challenge_question": "Write pair_sum_sorted(nums, target) returning True if two numbers sum to target."
}"""

COGNITIVE_TP = """{
  "misconceptions": [
    {
      "concept": "pointer_movement",
      "description": "Uses nested loops O(N^2) instead of linear opposite-end pointer convergence.",
      "evidence": "for i in range(len(nums)): for j in range(i+1, len(nums)):",
      "attempt_count": 1,
      "confidence": "medium",
      "past_interventions": [],
      "resolved": false
    }
  ],
  "mental_model_summary": "Fails to exploit sorted order to eliminate elements from ends.",
  "confidence_level": "medium"
}"""

INTERVENTION_TP1 = """{
  "mistake_diagnosis": "Nested loops take O(N^2) time because they ignore the array's sorted order.",
  "core_dsa_concept": "Start left=0, right=len-1. If sum < target move left rightward; if sum > target move right leftward.",
  "simple_example": "nums=[1,3,5], target=4: 1+5=6>4 -> right--; 1+3=4==target -> True.",
  "explanation": "Opposite-end pointers narrow down the target sum in a single linear pass.",
  "teaching_strategy_used": "conceptual_analogy",
  "problem_statement": "Initialize left=0 and right=len(nums)-1 in a while loop left < right.",
  "buggy_code_or_prompt": "def pair_sum_sorted(nums, target):\\n    left, right = 0, len(nums) - 1",
  "target_misconception": "pointer_movement"
}"""

GATE_BLOCK_TP = """{
  "status": "BLOCK",
  "score": 2,
  "feedback": "Pointers do not advance inside while loop, causing an infinite loop.",
  "unresolved_evidence": "while left < right: s = nums[left] + nums[right]"
}"""

INTERVENTION_TP2 = """{
  "mistake_diagnosis": "The loop calculates sum but never updates left or right to shrink the search interval.",
  "core_dsa_concept": "Each iteration must adjust pointers: left += 1 if sum < target, right -= 1 if sum > target.",
  "simple_example": "s < target: left += 1; s > target: right -= 1; s == target: return True.",
  "explanation": "Guaranteed convergence: advance left or decrement right after each comparison.",
  "teaching_strategy_used": "execution_trace_guard",
  "problem_statement": "Update pointers: if s < target left += 1, elif s > target right -= 1.",
  "buggy_code_or_prompt": "while left < right:\\n    s = nums[left] + nums[right]\\n    # update pointers",
  "target_misconception": "pointer_movement"
}"""

GATE_PASS_TP = """{
  "status": "PASS",
  "score": 4,
  "feedback": "Two-pointer convergence implemented with correct boundary updates in O(N).",
  "unresolved_evidence": null
}"""

# ------------------------------------------------------------------- Binary Search Canned Data

DIAGNOSTIC_BS = """{
  "prior_score": 1,
  "concepts_detected": ["binary_search", "boundary_update"],
  "challenge_question": "Write binary_search(nums, target) returning index of target, or -1."
}"""

COGNITIVE_BS = """{
  "misconceptions": [
    {
      "concept": "boundary_update",
      "description": "Sets low = mid or high = mid, causing infinite loop when 2 elements remain.",
      "evidence": "low = mid",
      "attempt_count": 1,
      "confidence": "medium",
      "past_interventions": [],
      "resolved": false
    }
  ],
  "mental_model_summary": "Does not exclude the checked mid element from the next interval.",
  "confidence_level": "medium"
}"""

INTERVENTION_BS = """{
  "mistake_diagnosis": "Setting low = mid leaves mid in the search space, causing an infinite loop.",
  "core_dsa_concept": "Because nums[mid] is not target, strictly exclude it: low = mid + 1 or high = mid - 1.",
  "simple_example": "nums=[1, 5], target=5: mid=0; low must become mid + 1 = 1 to examine index 1.",
  "explanation": "Binary search halves the search space by strictly excluding mid at every step.",
  "teaching_strategy_used": "execution_trace_guard",
  "problem_statement": "Update search bounds to strictly exclude mid: low = mid + 1 and high = mid - 1.",
  "buggy_code_or_prompt": "if nums[mid] < target:\\n    # update low\\nelse:\\n    # update high",
  "target_misconception": "boundary_update"
}"""

GATE_PASS_BS = """{
  "status": "PASS",
  "score": 4,
  "feedback": "Binary search correctly excludes mid with proper low <= high termination.",
  "unresolved_evidence": null
}"""

# ------------------------------------------------------------------- Scripts & Default Answers

DEFAULT_SCRIPT: dict[str, list[str]] = {
    "assess": [DIAGNOSTIC_V1],
    "cognitive": [COGNITIVE_V1],
    "intervention": [INTERVENTION_V1, INTERVENTION_V2],
    "gate": [GATE_BLOCK, GATE_PASS],
}

TWO_POINTERS_SCRIPT: dict[str, list[str]] = {
    "assess": [DIAGNOSTIC_TP],
    "cognitive": [COGNITIVE_TP],
    "intervention": [INTERVENTION_TP1, INTERVENTION_TP2],
    "gate": [GATE_BLOCK, GATE_PASS],
}

BINARY_SEARCH_SCRIPT: dict[str, list[str]] = {
    "assess": [DIAGNOSTIC_BS],
    "cognitive": [COGNITIVE_BS],
    "intervention": [INTERVENTION_BS],
    "gate": [GATE_PASS_BS],
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

DEFAULT_ANSWERS_TP = [
    "def pair_sum_sorted(nums, target):\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] + nums[j] == target: return True\n    return False",
    "def pair_sum_sorted(nums, target):\n    left, right = 0, len(nums) - 1\n    while left < right:\n        s = nums[left] + nums[right]\n        if s == target: return True",
    "def pair_sum_sorted(nums, target):\n    left, right = 0, len(nums) - 1\n    while left < right:\n        s = nums[left] + nums[right]\n        if s == target: return True\n        elif s < target: left += 1\n        else: right -= 1\n    return False",
]

DEFAULT_ANSWERS_BS = [
    "def binary_search(nums, target):\n    low, high = 0, len(nums) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if nums[mid] == target: return mid\n        elif nums[mid] < target: low = mid\n        else: high = mid\n    return -1",
    "def binary_search(nums, target):\n    low, high = 0, len(nums) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if nums[mid] == target: return mid\n        elif nums[mid] < target: low = mid + 1\n        else: high = mid - 1\n    return -1",
]


class ThiranStub:
    """A drop-in replacement for slice.llm.complete for Thiran AI."""

    def __init__(self, script: dict[str, list[str]] | None = None, topic: str = "recursion") -> None:
        if script is not None:
            self.script = script
        elif topic == "two_pointers":
            self.script = {k: list(v) for k, v in TWO_POINTERS_SCRIPT.items()}
        elif topic == "binary_search":
            self.script = {k: list(v) for k, v in BINARY_SEARCH_SCRIPT.items()}
        else:
            self.script = {k: list(v) for k, v in DEFAULT_SCRIPT.items()}
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

    def __init__(self, topic: str = "recursion") -> None:
        if topic == "two_pointers":
            script = {
                "assess": [DIAGNOSTIC_TP],
                "cognitive": [COGNITIVE_TP],
                "intervention": [INTERVENTION_TP1],
                "gate": [GATE_PASS_TP],
            }
        elif topic == "binary_search":
            script = {
                "assess": [DIAGNOSTIC_BS],
                "cognitive": [COGNITIVE_BS],
                "intervention": [INTERVENTION_BS],
                "gate": [GATE_PASS_BS],
            }
        else:
            script = {
                "assess": [DIAGNOSTIC_V1],
                "cognitive": [COGNITIVE_V1],
                "intervention": [INTERVENTION_V1],
                "gate": [GATE_PASS],
            }
        super().__init__(script)


class Session2Stub(ThiranStub):
    """Simulates a returning learner in Session 2 tackling advanced recursion."""

    def __init__(self) -> None:
        super().__init__({
            "assess": [DIAGNOSTIC_S2],
            "cognitive": [COGNITIVE_S2],
            "intervention": [INTERVENTION_S2],
            "gate": [GATE_PASS_S2],
        })


class TwoPointersStub(ThiranStub):
    """Simulates learning two pointers with 1 backward loop then pass."""

    def __init__(self) -> None:
        super().__init__(topic="two_pointers")


class BinarySearchStub(ThiranStub):
    """Simulates learning binary search with clean pass."""

    def __init__(self) -> None:
        super().__init__(topic="binary_search")


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
