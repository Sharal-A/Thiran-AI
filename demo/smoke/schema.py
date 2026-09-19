"""The records Thiran passes between steps.

Nothing crosses a step boundary as prose. A schema fails loudly at the boundary
where you can still see it - and slice/llm.py gets one repair pass out of it.
Supports any DSA concept (recursion, two pointers, binary search, sliding window, etc.).
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class Misconception(BaseModel):
    """One diagnosed misconception, tracked across attempts until resolved."""

    concept: str = Field(description="The underlying concept, e.g. 'base_case', 'pointer_movement'")
    description: str = Field(description="Specific mental model failure")
    evidence: str = Field(description="Verbatim quote or code from learner's answer")
    attempt_count: int = Field(default=1, description="How many attempts learner has made")
    confidence: Literal["low", "medium", "high"] = Field(default="medium", description="Learner confidence")
    past_interventions: list[str] = Field(default_factory=list, description="List of past pedagogical strategies attempted")
    resolved: bool = Field(default=False, description="Whether this misconception has been resolved")


class LearnerProfile(BaseModel):
    """Persistent learner state across sessions, stored in SQLite learners table."""

    learner_id: str
    name: str
    domain: str = "computer_science"
    knowledge_state: dict[str, int] = Field(default_factory=dict, description="Concept to score 0-4")
    confidence_state: dict[str, str] = Field(default_factory=dict, description="Concept to 'learning' | 'confident' | 'revisiting'")
    consecutive_correct: dict[str, int] = Field(default_factory=dict, description="Concept to consecutive correct streak count")
    misconceptions: list[Misconception] = Field(default_factory=list)
    session_count: int = 0
    last_topic: str | None = None


class DiagnosticChallenge(BaseModel):
    """What the Assessment Agent produces (combines diagnostic evaluation & challenge)."""

    prior_score: int = Field(ge=0, le=4, description="Estimated prior competency score 0-4")
    concepts_detected: list[str] = Field(default_factory=list, description="Relevant subconcepts detected")
    challenge_question: str = Field(description="Opening diagnostic problem posed to the learner")


class CognitiveAnalysis(BaseModel):
    """What the Cognitive Agent produces after analyzing learner's diagnostic answer."""

    misconceptions: list[Misconception] = Field(default_factory=list)
    mental_model_summary: str = Field(description="Summary of learner's mental model and reasoning flaws")
    confidence_level: Literal["low", "medium", "high"] = "medium"


class Intervention(BaseModel):
    """Unified teaching and Socratic debugging intervention produced in a single model call.
    Sequence: explain mistake -> teach core DSA concept -> simple toy example -> targeted practice.
    """

    mistake_diagnosis: str = Field(description="1 sentence explaining the specific mistake in student's code")
    core_dsa_concept: str = Field(description="1-2 sentences teaching the core DSA algorithmic invariant / principle")
    simple_example: str = Field(description="1-2 lines demonstrating the pattern on a minimal toy trace")
    explanation: str = Field(default="", description="Concise summary explanation")
    teaching_strategy_used: str = Field(description="Strategy applied: e.g. 'conceptual_analogy', 'execution_trace_guard', 'fill_in_scaffold'")
    problem_statement: str = Field(description="1-sentence Socratic challenge directing learner to fix the flaw")
    buggy_code_or_prompt: str = Field(description="Minimal flawed snippet or scaffold to debug")
    target_misconception: str = Field(description="The specific misconception concept being addressed")


class ReassessVerdict(BaseModel):
    """What the Gating Judge produces. PASS completes the session; BLOCK fires a backward loop."""

    status: Literal["PASS", "BLOCK"]
    score: int = Field(ge=0, le=4, description="Evaluated mastery score 0-4")
    feedback: str = Field(description="Assessment feedback detailing why it passed or what remains flawed")
    unresolved_evidence: str | None = Field(default=None, description="Flawed quote if blocked")


class LearnerUpdate(BaseModel):
    """What is recorded upon session completion, reflecting the updated learner state."""

    learner_id: str
    concept_scores: dict[str, int]
    confidence_state: dict[str, str]
    resolved_misconceptions: list[str]
    session_count: int


# Legacy aliases for backwards compatibility
class LearningPlan(BaseModel):
    scaffold_level: Literal["low", "medium", "high"] = "medium"
    concept_sequence: list[str] = Field(default_factory=list)
    teaching_strategy: str = "direct"

class TutorExchange(BaseModel):
    explanation: str
    analogy: str
    checkpoint_concept: str

class SocraticChallenge(BaseModel):
    problem_statement: str
    buggy_code_or_prompt: str
    target_misconception: str
