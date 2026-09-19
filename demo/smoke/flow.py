"""The Thiran AI adaptive learning flow, domain rules, and Flow object.

State machine handlers:
- handle_drafting: Dispatches active agent steps (Assessment, Cognitive, Intervention)
- handle_probing: Ingests learner answers to diagnostic and Socratic challenges (automated or interactive)
- handle_gating: Evaluates Socratic answer, manages backward loops, and triggers profile updates

Redesigned for minimal LLM calls and token usage:
- Memory -> Relevant Evidence -> Diagnosis -> Unified Intervention -> Student -> Judge -> Update
- Tutor + Socratic combined into 1 single Intervention call
- Strategy escalation on recurring misconceptions (analogy -> execution trace -> fill-in scaffold)
- Conditional Cognitive call: skips re-diagnosis when code contains no new evidence
- Topic-filtered evidence retrieval from SQLite LearnerStore

Nothing in slice/ changes for this to run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from slice.llm import complete
from slice.records import RunState

from .schema import (
    CognitiveAnalysis,
    DiagnosticChallenge,
    Intervention,
    LearnerProfile,
    Misconception,
    ReassessVerdict,
)
from .store_ext import LearnerStore
from .stub import DEFAULT_ANSWERS, DEFAULT_ANSWERS_S2

# --------------------------------------------------------------- domain rules

MAX_LOOPS = 3
"""How many backward loops a learner gets before the run stops with a diagnostic failure."""

STRATEGIES = [
    "conceptual_analogy",      # Attempt 1: High-level mental model & analogy
    "execution_trace_guard",    # Attempt 2: Line-by-line trace & explicit guard clause
    "fill_in_scaffold",         # Attempt 3: Direct scaffold template
]


def get_escalated_strategy(attempt: int) -> str:
    """Deterministic strategy escalator: shifts instructional tactic on recurring failure."""
    idx = min(max(0, attempt - 1), len(STRATEGIES) - 1)
    return STRATEGIES[idx]


def has_new_evidence(old_code: str | None, new_code: str | None) -> bool:
    """Determines if the learner's new response provides meaningful new code evidence."""
    if not old_code or not new_code:
        return True
    return "".join(old_code.split()) != "".join(new_code.split())


_PROMPTS = Path(__file__).parent / "prompts"


def _prompt(name: str) -> str:
    path = _PROMPTS / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"You are the {name} agent for Thiran AI."


# ------------------------------------------------------------------ minimal message builders

def build_assess_messages(inp: dict, evidence: dict[str, Any]) -> list[dict]:
    topic = inp.get("topic", "recursion")
    user_lines = [f"Topic: {topic}"]
    score = evidence.get("score")
    if score is not None:
        user_lines.append(f"Prior Topic Score: {score}/4")
        user_lines.append(f"Completed Sessions: {evidence.get('session_count', 0)}")
    unresolved = evidence.get("unresolved", [])
    if unresolved:
        user_lines.append(f"Known Misconceptions: {', '.join(unresolved)}")
    return [
        {"role": "system", "content": _prompt("assess")},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def build_cognitive_messages(
    inp: dict,
    student_code: str | None,
    evidence: dict[str, Any],
    loop_count: int,
    feedback: str | None = None,
) -> list[dict]:
    topic = inp.get("topic", "recursion")
    parts = [f"Topic: {topic}", f"Attempt: {loop_count + 1}"]
    if student_code:
        parts.append(f"Student Code:\n{student_code}")
    if feedback:
        parts.append(f"Judge Feedback: {feedback}")
    past_int = evidence.get("past_interventions", [])
    if past_int:
        parts.append(f"Failed Past Interventions: {', '.join(past_int)}")
    return [
        {"role": "system", "content": _prompt("cognitive")},
        {"role": "user", "content": "\n".join(parts)},
    ]


def build_intervention_messages(
    inp: dict,
    analysis: CognitiveAnalysis,
    strategy: str,
    evidence: dict[str, Any],
) -> list[dict]:
    target = analysis.misconceptions[0].concept if analysis.misconceptions else inp.get("topic", "recursion")
    desc = analysis.misconceptions[0].description if analysis.misconceptions else "General recursion gap"
    return [
        {"role": "system", "content": _prompt("intervention")},
        {"role": "user", "content": (
            f"Topic: {inp.get('topic', 'recursion')}\n"
            f"Target Misconception: {target}\n"
            f"Diagnosed Flaw: {desc}\n"
            f"Mental Model: {analysis.mental_model_summary}\n"
            f"Required Strategy: {strategy}"
        )},
    ]


def build_gate_messages(
    intervention: dict | None,
    answer: dict | None,
) -> list[dict]:
    ch_text = intervention.get("problem_statement", "") if intervention else ""
    target = intervention.get("target_misconception", "") if intervention else ""
    ans_text = answer.get("text", "") if answer else ""
    return [
        {"role": "system", "content": _prompt("gate")},
        {"role": "user", "content": f"Challenge: {ch_text}\nTarget Concept: {target}\nStudent Code:\n{ans_text}"},
    ]


# ------------------------------------------------------------------ agent call with telemetry

def _invoke_agent(ctx, call, step: str, messages: list[dict], schema: Any) -> Any:
    """Invokes agent and tracks per-agent token and call metrics in the store."""
    tokens_before = ctx.store.counter(ctx.run_id, "tokens")
    record = call(
        settings=ctx.settings,
        budget=ctx.budget,
        messages=messages,
        schema=schema,
        step=step,
    )
    tokens_after = ctx.store.counter(ctx.run_id, "tokens")
    tokens_spent = max(0.0, tokens_after - tokens_before)

    ctx.store.bump(ctx.run_id, f"tokens:{step}", tokens_spent)
    ctx.store.bump(ctx.run_id, f"calls:{step}", 1)
    return record


# ------------------------------------------------------------------ handlers

def build_flow(call=complete):
    """Construct the Thiran Flow. `call` is injected for offline testing via ThiranStub."""

    def handle_drafting(ctx) -> RunState:
        phase_rec = ctx.latest("phase")
        phase = phase_rec["name"] if phase_rec else "ASSESS"
        inp = ctx.latest("input") or {}
        learner_id = inp.get("learner_id", "default_learner")
        topic = inp.get("topic", "recursion")
        lstore = LearnerStore(ctx.store)
        evidence = lstore.get_relevant_evidence(learner_id, topic)

        if phase == "ASSESS":
            diag = _invoke_agent(
                ctx,
                call,
                "assess",
                build_assess_messages(inp, evidence),
                DiagnosticChallenge,
            )
            ctx.append("diagnostic_challenge", diag.model_dump(), produced_by="agent:assess")
            ctx.append("phase", {"name": "AWAIT_DIAGNOSTIC"}, produced_by="system")
            return RunState.PROBING

        if phase == "COGNITIVE":
            loop_count = int(ctx.store.counter(ctx.run_id, "backward_loops"))
            diag_ans = ctx.latest("learner_answer")
            code_text = diag_ans.get("text", "") if diag_ans else ""
            latest_verdict = ctx.latest("verdict")
            feedback = latest_verdict.get("feedback") if latest_verdict else None

            analysis = _invoke_agent(
                ctx,
                call,
                "cognitive",
                build_cognitive_messages(inp, code_text, evidence, loop_count, feedback),
                CognitiveAnalysis,
            )
            ctx.append("cognitive_analysis", analysis.model_dump(), produced_by="agent:cognitive")
            phase = "INTERVENE"  # immediately advance to INTERVENE in current drafting step

        if phase == "INTERVENE":
            loop_count = int(ctx.store.counter(ctx.run_id, "backward_loops"))
            strategy = get_escalated_strategy(attempt=loop_count + 1)
            analysis_dict = ctx.latest("cognitive_analysis")
            analysis = CognitiveAnalysis.model_validate(analysis_dict)

            # Single Unified Intervention (Tutor + Socratic consolidated)
            intervention = _invoke_agent(
                ctx,
                call,
                "intervention",
                build_intervention_messages(inp, analysis, strategy, evidence),
                Intervention,
            )
            ctx.append("intervention", intervention.model_dump(), produced_by="agent:intervention")
            ctx.append("phase", {"name": "AWAIT_SOCRATIC"}, produced_by="system")
            return RunState.PROBING

        ctx.append("failure", {"kind": "unknown_phase", "detail": f"Unknown drafting phase: {phase}"}, produced_by="system")
        return RunState.FAILED

    def handle_probing(ctx) -> RunState:
        phase_rec = ctx.latest("phase")
        phase = phase_rec["name"] if phase_rec else "AWAIT_DIAGNOSTIC"
        inp = ctx.latest("input") or {}
        answers = inp.get("answers", [])
        ans_idx = int(ctx.store.counter(ctx.run_id, "answers_consumed"))
        session_num = inp.get("session_number", 1)

        # 1. Check if interactive user input was requested
        if inp.get("interactive") and sys.stdin.isatty():
            if phase == "AWAIT_DIAGNOSTIC":
                diag = ctx.latest("diagnostic_challenge") or {}
                prompt_text = diag.get("challenge_question", "Solve the challenge:")
            else:
                interv = ctx.latest("intervention") or {}
                prompt_text = interv.get("problem_statement", "Debug and fix the issue:")
                if interv.get("buggy_code_or_prompt"):
                    prompt_text += f"\nCode snippet:\n{interv.get('buggy_code_or_prompt')}"

            print(f"\n\033[1m[Thiran Prompt]\033[0m {prompt_text}")
            print("\033[2mEnter code (submit with an empty line or EOF):\033[0m")
            lines = []
            try:
                while True:
                    line = input()
                    if not line and lines:
                        break
                    lines.append(line)
            except EOFError:
                pass
            ans = "\n".join(lines).strip() or "pass"
        # 2. Check if specific answers were supplied
        elif ans_idx < len(answers):
            ans = answers[ans_idx]
        # 3. Fallback to appropriate canned answers
        else:
            ans_pool = DEFAULT_ANSWERS_S2 if session_num == 2 else DEFAULT_ANSWERS
            default_idx = min(ans_idx, len(ans_pool) - 1)
            ans = ans_pool[default_idx]

        ctx.store.bump(ctx.run_id, "answers_consumed")

        if phase == "AWAIT_DIAGNOSTIC":
            ctx.append(
                "learner_answer",
                {"text": ans, "phase": "DIAGNOSTIC", "attempt": 1},
                produced_by="learner",
            )
            ctx.append("phase", {"name": "COGNITIVE"}, produced_by="system")
            return RunState.DRAFTING

        if phase == "AWAIT_SOCRATIC":
            loop_count = int(ctx.store.counter(ctx.run_id, "backward_loops"))
            ctx.append(
                "learner_answer",
                {"text": ans, "phase": "SOCRATIC", "attempt": loop_count + 1},
                produced_by="learner",
            )
            return RunState.GATING

        ctx.append("failure", {"kind": "unexpected_probing_phase", "detail": f"Phase {phase} in probing"}, produced_by="system")
        return RunState.FAILED

    def handle_gating(ctx) -> RunState:
        intervention = ctx.latest("intervention")
        answer = ctx.latest("learner_answer")

        verdict = _invoke_agent(
            ctx,
            call,
            "gate",
            build_gate_messages(intervention, answer),
            ReassessVerdict,
        )
        ctx.append("verdict", verdict.model_dump(), produced_by="agent:judge")

        if verdict.status == "PASS":
            # State Update (pure deterministic code)
            _handle_update(ctx, verdict)
            return RunState.COMPLETE

        # Blocked: Evaluate backward loop
        loop_count = int(ctx.store.counter(ctx.run_id, "backward_loops"))
        if loop_count >= MAX_LOOPS:
            ctx.append(
                "failure",
                {
                    "kind": "max_loops_exhausted",
                    "detail": f"Blocked {loop_count} times; misconception persisted without resolution.",
                    "unresolved_evidence": verdict.unresolved_evidence,
                },
                produced_by="system",
            )
            return RunState.FAILED

        # Execute backward loop & strategy escalation
        ctx.store.bump(ctx.run_id, "backward_loops")
        next_attempt = loop_count + 2
        strategy = get_escalated_strategy(next_attempt)

        ctx.append(
            "backward_loop",
            {
                "loop_count": loop_count + 1,
                "reason": verdict.feedback,
                "escalated_strategy": strategy,
                "from_phase": "GATING",
                "to_phase": "INTERVENE",
            },
            produced_by="system",
        )

        # Reuse Cognitive diagnosis and route directly to INTERVENE with escalated strategy
        ctx.append("phase", {"name": "INTERVENE"}, produced_by="system")
        ctx.append("decision", {"action": "reuse_diagnosis", "escalated_strategy": strategy}, produced_by="system")

        return RunState.DRAFTING

    def _handle_update(ctx, verdict: ReassessVerdict) -> None:
        """Pure code handler to update persistent learner profile in SQLite."""
        inp = ctx.latest("input") or {}
        learner_id = inp.get("learner_id", "default_learner")
        name = inp.get("name", learner_id.capitalize())
        topic = inp.get("topic", "recursion")

        lstore = LearnerStore(ctx.store)
        profile = lstore.get_or_create_learner(learner_id, name)
        profile.knowledge_state[topic] = verdict.score
        profile.session_count += 1
        profile.last_topic = topic

        # Resolve misconceptions identified in this session and record interventions tried
        resolved_names = []
        cog = ctx.latest("cognitive_analysis")
        interv = ctx.latest("intervention")
        strategy_used = interv.get("teaching_strategy_used") if interv else None

        if cog and "misconceptions" in cog:
            for m_dict in cog["misconceptions"]:
                m = Misconception(**m_dict)
                m.resolved = True
                if strategy_used and strategy_used not in m.past_interventions:
                    m.past_interventions.append(strategy_used)
                resolved_names.append(m.concept)

                idx = next((i for i, existing in enumerate(profile.misconceptions) if existing.concept == m.concept), None)
                if idx is not None:
                    profile.misconceptions[idx].resolved = True
                    profile.misconceptions[idx].attempt_count = m.attempt_count
                    if strategy_used and strategy_used not in profile.misconceptions[idx].past_interventions:
                        profile.misconceptions[idx].past_interventions.append(strategy_used)
                else:
                    profile.misconceptions.append(m)

        lstore.save_learner(profile)
        ctx.append(
            "learner_update",
            {
                "learner_id": learner_id,
                "concept_scores": profile.knowledge_state,
                "resolved_misconceptions": resolved_names,
                "session_count": profile.session_count,
            },
            produced_by="system",
        )

    return SimpleNamespace(
        name="thiran",
        handlers={
            RunState.DRAFTING: handle_drafting,
            RunState.PROBING:  handle_probing,
            RunState.GATING:   handle_gating,
        },
    )
