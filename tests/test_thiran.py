"""Golden test suite for Thiran AI adaptive learning loop.

All tests run on canned responses: zero API keys, no network, zero tokens.
Proves the multi-agent wiring, state machine transitions, backward loops, and SQLite persistence.
"""
from __future__ import annotations

import sqlite3
import pytest

from demo.smoke.flow import MAX_LOOPS, build_flow
from demo.smoke.store_ext import LearnerStore
from demo.smoke.stub import (
    AlwaysBlocksStub,
    BinarySearchStub,
    CleanStub,
    Session2Stub,
    ThiranStub,
    TwoPointersStub,
)
from slice import runner
from slice.config import settings as load_settings
from slice.records import RunState
from slice.store import Store


def _run(tmp_path, call=None, learner_id="surya", topic="recursion", answers=None):
    store = Store(str(tmp_path / "t.db"))
    run_id = store.create_run("thiran")
    input_payload = {
        "learner_id": learner_id,
        "name": learner_id.capitalize(),
        "topic": topic,
    }
    if answers:
        input_payload["answers"] = answers

    store.append(run_id, "input", input_payload, produced_by="system")
    store.append(run_id, "phase", {"name": "ASSESS"}, produced_by="system")

    final = runner.advance(store, run_id, build_flow(call or ThiranStub()), load_settings())
    return store, run_id, final


# ------------------------------------------------------------- Golden Path Tests

def test_the_learning_loop_completes(tmp_path):
    """Proves the full 5-agent adaptive learning loop reaches RunState.COMPLETE."""
    _, _, final = _run(tmp_path)
    assert final is RunState.COMPLETE


def test_work_goes_backwards_on_misconception(tmp_path):
    """Proves that a BLOCK verdict triggers a backward loop back to COGNITIVE."""
    store, run_id, _ = _run(tmp_path)
    loops = store.history(run_id, "backward_loop")
    assert len(loops) == 1, "Expected exactly 1 backward loop in default golden script"
    assert loops[0].payload["from_phase"] == "GATING"
    assert loops[0].payload["to_phase"] == "INTERVENE"

    # Verifies both first (blocked) and second (passed) verdicts are recorded
    verdicts = store.history(run_id, "verdict")
    assert len(verdicts) == 2
    assert verdicts[0].payload["status"] == "BLOCK"
    assert verdicts[1].payload["status"] == "PASS"


def test_backward_loop_counter_increments(tmp_path):
    """Proves that the backward_loops counter persists in the store."""
    store, run_id, _ = _run(tmp_path)
    assert store.counter(run_id, "backward_loops") == 1.0


def test_misconception_marked_resolved(tmp_path):
    """Proves that upon reaching PASS, the diagnosed misconception is marked resolved."""
    store, run_id, _ = _run(tmp_path)
    lstore = LearnerStore(store)
    profile = lstore.get_learner("surya")
    assert profile is not None
    assert len(profile.misconceptions) > 0
    assert any(m.concept == "base_case" and m.resolved for m in profile.misconceptions)


def test_learner_profile_persists_in_sqlite(tmp_path):
    """Proves that LearnerProfile persists across store instances in the same SQLite file."""
    store, _, _ = _run(tmp_path)
    db_path = str(tmp_path / "t.db")

    # Open fresh Store connection to simulate new process
    new_store = Store(db_path)
    lstore = LearnerStore(new_store)
    profile = lstore.get_learner("surya")
    assert profile is not None
    assert profile.knowledge_state.get("recursion") == 4
    assert profile.session_count == 1


def test_second_session_uses_existing_profile(tmp_path):
    """Proves that Session 2 builds upon Session 1's profile."""
    store, _, _ = _run(tmp_path)
    # Session 2 on the same db
    store2 = Store(str(tmp_path / "t.db"))
    run_id2 = store2.create_run("thiran")
    store2.append(run_id2, "input", {"learner_id": "surya", "name": "Surya", "topic": "recursion"}, produced_by="system")
    store2.append(run_id2, "phase", {"name": "ASSESS"}, produced_by="system")

    # For session 2, clean pass
    final2 = runner.advance(store2, run_id2, build_flow(CleanStub()), load_settings())
    assert final2 is RunState.COMPLETE

    lstore = LearnerStore(store2)
    profile = lstore.get_learner("surya")
    assert profile.session_count == 2


def test_clean_run_completes_in_one_pass(tmp_path):
    """Proves that when learner passes immediately, 0 backward loops occur."""
    store, run_id, final = _run(tmp_path, call=CleanStub())
    assert final is RunState.COMPLETE
    assert len(store.history(run_id, "backward_loop")) == 0
    assert store.counter(run_id, "backward_loops") == 0.0


def test_max_backward_loops_fails_run(tmp_path):
    """Proves that exceeding MAX_LOOPS stops the run with RunState.FAILED and a recorded reason."""
    store, run_id, final = _run(tmp_path, call=AlwaysBlocksStub())
    assert final is RunState.FAILED
    assert store.counter(run_id, "backward_loops") == float(MAX_LOOPS)

    failures = store.history(run_id, "failure")
    assert failures, "Failure reason must be recorded in store"
    assert failures[-1].payload["kind"] == "max_loops_exhausted"


def test_tokens_are_counted(tmp_path):
    """Proves token consumption is tracked against the run."""
    store, run_id, _ = _run(tmp_path)
    assert store.counter(run_id, "tokens") > 0


def test_all_events_attributed_correctly(tmp_path):
    """Proves every version entry has a well-defined produced_by attribute."""
    store, run_id, _ = _run(tmp_path)
    producers = {v.kind: v.produced_by for v in store.replay(run_id)}

    assert producers["diagnostic_challenge"] == "agent:assess"
    assert producers["learner_answer"] == "learner"
    assert producers["cognitive_analysis"] == "agent:cognitive"
    assert producers["intervention"] == "agent:intervention"
    assert producers["verdict"] == "agent:judge"
    assert producers["backward_loop"] == "system"
    assert producers["learner_update"] == "system"


def test_history_cannot_be_rewritten(tmp_path):
    """Proves that the SQLite append-only invariant holds."""
    store, run_id, _ = _run(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("UPDATE versions SET payload_json='{}' WHERE run_id=? AND seq=1", (run_id,))
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM versions WHERE run_id=?", (run_id,))


def test_per_agent_token_counters_and_efficiency(tmp_path):
    """Proves that granular per-agent token telemetry is tracked and stays well within budget."""
    store, run_id, _ = _run(tmp_path)
    steps = ["assess", "cognitive", "intervention", "gate"]
    for step in steps:
        assert store.counter(run_id, f"tokens:{step}") > 0, f"tokens:{step} was not tracked"
        assert store.counter(run_id, f"calls:{step}") > 0, f"calls:{step} was not tracked"

    # Overall token usage for a full backward-loop run must be <= 500 tokens (down from 723)
    total_tokens = store.counter(run_id, "tokens")
    assert total_tokens <= 500, f"Token usage {total_tokens} exceeded optimization ceiling"

    # Call consolidation: 6 calls total (down from 11)
    total_calls = sum(store.counter(run_id, f"calls:{s}") for s in steps)
    assert total_calls == 6.0, f"Expected exactly 6 consolidated calls, got {total_calls}"


def test_strategy_escalation_and_cognitive_call_saving(tmp_path):
    """Proves that the strategy shifts on backward loop and Cognitive call is not repeated redundantly."""
    store, run_id, _ = _run(tmp_path)
    interventions = [v.payload for v in store.history(run_id, "intervention")]
    assert len(interventions) == 2
    assert interventions[0]["teaching_strategy_used"] == "conceptual_analogy"
    assert interventions[1]["teaching_strategy_used"] == "execution_trace_guard"

    # Cognitive called exactly once, reused for subsequent interventions
    assert store.counter(run_id, "calls:cognitive") == 1.0


def test_clean_run_token_budget_efficiency(tmp_path):
    """Proves that a 1-pass clean run consumes near ~300 tokens."""
    store, run_id, _ = _run(tmp_path, call=CleanStub())
    total_tokens = store.counter(run_id, "tokens")
    assert total_tokens <= 350, f"Clean run tokens ({total_tokens}) exceeded 350 token target"


def test_session2_cross_session_memory_and_progression(tmp_path):
    """Proves that Session 2 dynamically loads Session 1 profile and tests advanced concepts."""
    db_path = str(tmp_path / "t.db")

    # Session 1: Learns base case
    store1 = Store(db_path)
    run_id1 = store1.create_run("thiran")
    store1.append(run_id1, "input", {"learner_id": "surya", "name": "Surya", "topic": "recursion", "session_number": 1}, produced_by="system")
    store1.append(run_id1, "phase", {"name": "ASSESS"}, produced_by="system")
    final1 = runner.advance(store1, run_id1, build_flow(ThiranStub()), load_settings())
    assert final1 is RunState.COMPLETE

    # Verify session 1 profile
    lstore1 = LearnerStore(store1)
    p1 = lstore1.get_learner("surya")
    assert p1.session_count == 1
    assert p1.knowledge_state["recursion"] == 4
    assert any(m.concept == "base_case" and m.resolved for m in p1.misconceptions)

    # Session 2: Advances to return values (factorial)
    store2 = Store(db_path)
    run_id2 = store2.create_run("thiran")
    store2.append(run_id2, "input", {"learner_id": "surya", "name": "Surya", "topic": "recursion", "session_number": 2}, produced_by="system")
    store2.append(run_id2, "phase", {"name": "ASSESS"}, produced_by="system")
    final2 = runner.advance(store2, run_id2, build_flow(Session2Stub()), load_settings())
    assert final2 is RunState.COMPLETE

    # Verify session 2 profile reflects accumulated learning across both sessions
    lstore2 = LearnerStore(store2)
    p2 = lstore2.get_learner("surya")
    assert p2.session_count == 2
    concepts = {m.concept: m.resolved for m in p2.misconceptions}
    assert concepts.get("base_case") is True, "Session 1 resolved misconception must persist"
    assert concepts.get("return_values") is True, "Session 2 resolved misconception must be added"


# ------------------------------------------------------------- Multi-DSA & Confidence Engine Tests

def test_two_pointers_learning_loop(tmp_path):
    """Proves that Thiran generalizes to Two Pointers with diagnosis, concept teaching, toy example, practice, and gating."""
    store, run_id, final = _run(tmp_path, call=TwoPointersStub(), topic="two_pointers")
    assert final is RunState.COMPLETE

    # Verify 1 backward loop occurred
    loops = store.history(run_id, "backward_loop")
    assert len(loops) == 1

    # Verify intervention structure contains all required pedagogical fields
    interventions = [v.payload for v in store.history(run_id, "intervention")]
    assert len(interventions) == 2
    assert "nested loops" in interventions[0]["mistake_diagnosis"].lower() or "o(n^2)" in interventions[0]["mistake_diagnosis"].lower()
    assert "opposite" in interventions[0]["core_dsa_concept"].lower() or "left" in interventions[0]["core_dsa_concept"].lower()
    assert interventions[0]["simple_example"]
    assert interventions[0]["problem_statement"]

    # Verify persistence in SQLite
    lstore = LearnerStore(store)
    p = lstore.get_learner("surya")
    assert p is not None
    assert p.knowledge_state.get("two_pointers") == 4
    assert any(m.concept == "pointer_movement" and m.resolved for m in p.misconceptions)


def test_binary_search_learning_loop(tmp_path):
    """Proves that Thiran generalizes to Binary Search."""
    store, run_id, final = _run(tmp_path, call=BinarySearchStub(), topic="binary_search")
    assert final is RunState.COMPLETE

    # Verify binary search intervention fields
    interventions = [v.payload for v in store.history(run_id, "intervention")]
    assert len(interventions) == 1
    assert "low = mid" in interventions[0]["mistake_diagnosis"]
    assert "strictly exclude" in interventions[0]["core_dsa_concept"].lower() or "mid + 1" in interventions[0]["core_dsa_concept"].lower()

    # Verify profile
    lstore = LearnerStore(store)
    p = lstore.get_learner("surya")
    assert p.knowledge_state.get("binary_search") == 4
    assert any(m.concept == "boundary_update" and m.resolved for m in p.misconceptions)


def test_two_consecutive_correct_sets_confident(tmp_path):
    """Proves: 2 consecutive correct answers on different questions -> confident."""
    db_path = str(tmp_path / "t.db")

    # Session 1: Pass on recursion
    store1 = Store(db_path)
    run_id1 = store1.create_run("thiran")
    store1.append(run_id1, "input", {"learner_id": "anita", "name": "Anita", "topic": "recursion", "session_number": 1}, produced_by="system")
    store1.append(run_id1, "phase", {"name": "ASSESS"}, produced_by="system")
    final1 = runner.advance(store1, run_id1, build_flow(CleanStub()), load_settings())
    assert final1 is RunState.COMPLETE

    lstore1 = LearnerStore(store1)
    p1 = lstore1.get_learner("anita")
    assert p1.consecutive_correct.get("recursion") == 1
    assert p1.confidence_state.get("recursion") == "learning"

    # Session 2: Pass on recursion (question 2)
    store2 = Store(db_path)
    run_id2 = store2.create_run("thiran")
    store2.append(run_id2, "input", {"learner_id": "anita", "name": "Anita", "topic": "recursion", "session_number": 2}, produced_by="system")
    store2.append(run_id2, "phase", {"name": "ASSESS"}, produced_by="system")
    final2 = runner.advance(store2, run_id2, build_flow(Session2Stub()), load_settings())
    assert final2 is RunState.COMPLETE

    lstore2 = LearnerStore(store2)
    p2 = lstore2.get_learner("anita")
    assert p2.consecutive_correct.get("recursion") == 2
    assert p2.confidence_state.get("recursion") == "confident"


def test_subsequent_mistake_reduces_confidence_to_revisiting(tmp_path):
    """Proves: subsequent mistake on a confident topic reduces confidence to 'revisiting' and resets streak to 0."""
    db_path = str(tmp_path / "t.db")

    # Seed profile directly with confident status and streak=2
    store = Store(db_path)
    lstore = LearnerStore(store)
    p = lstore.get_or_create_learner("anita", "Anita")
    p.confidence_state["recursion"] = "confident"
    p.consecutive_correct["recursion"] = 2
    lstore.save_learner(p)

    # Session 3: An answer is blocked (mistake)
    run_id = store.create_run("thiran")
    store.append(run_id, "input", {"learner_id": "anita", "name": "Anita", "topic": "recursion", "session_number": 3}, produced_by="system")
    store.append(run_id, "phase", {"name": "ASSESS"}, produced_by="system")

    # Run flow with ThiranStub (which encounters 1 block then recovers)
    final = runner.advance(store, run_id, build_flow(ThiranStub()), load_settings())

    # Check that confidence update event was recorded during the mistake
    conf_events = store.history(run_id, "confidence_update")
    assert len(conf_events) >= 1
    assert conf_events[0].payload["confidence"] == "revisiting"
    assert conf_events[0].payload["consecutive_correct"] == 0
    assert conf_events[0].payload["event"] == "mistake_reset"

    # After recovering and passing the second challenge, streak becomes 1
    p_after = lstore.get_learner("anita")
    assert p_after.consecutive_correct["recursion"] == 1


def test_repeated_misconception_escalates_teaching_strategy(tmp_path):
    """Proves: repeated misconception recognizes failed past interventions and changes strategy."""
    db_path = str(tmp_path / "t.db")

    # Seed profile with past failed intervention
    store = Store(db_path)
    lstore = LearnerStore(store)
    p = lstore.get_or_create_learner("anita", "Anita")
    from demo.smoke.schema import Misconception
    p.misconceptions.append(
        Misconception(
            concept="base_case",
            description="Infinite recursion",
            evidence="countdown(n - 1)",
            past_interventions=["conceptual_analogy"],
            resolved=False,
        )
    )
    lstore.save_learner(p)

    # In a new run, Attempt 1 must skip conceptual_analogy and escalate to execution_trace_guard
    evidence = lstore.get_relevant_evidence("anita", "recursion")
    assert "conceptual_analogy" in evidence["past_interventions"]

    from demo.smoke.flow import get_escalated_strategy
    next_strat = get_escalated_strategy(attempt=1, past_strategies=evidence["past_interventions"])
    assert next_strat == "execution_trace_guard", f"Expected execution_trace_guard, got {next_strat}"



