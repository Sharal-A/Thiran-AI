"""Thiran AI Web Application — FastAPI backend for the MarketIQ-styled interface.

Provides:
- Branded Authentication and persistent Learner Profile management
- Step-by-step interactive learning session engine adhering to demo/smoke/flow.py
- Backward adaptation event emission and strategy escalation
- Purely deterministic SQLite analytics engine (zero LLM calls) with Before vs After evidence
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from demo.smoke.flow import (
    STRATEGIES,
    _invoke_agent,
    build_assess_messages,
    build_cognitive_messages,
    build_flow,
    build_gate_messages,
    build_intervention_messages,
    get_escalated_strategy,
    has_new_evidence,
)
from demo.smoke.schema import (
    CognitiveAnalysis,
    DiagnosticChallenge,
    Intervention,
    LearnerProfile,
    Misconception,
    ReassessVerdict,
)
from demo.smoke.store_ext import LearnerStore
from demo.smoke.stub import CleanStub, Session2Stub, ThiranStub
from slice.config import settings as load_settings
from slice.records import RunState
from slice.runner import Context
from slice.store import Store

DB_PATH = os.environ.get("THIRAN_DB", "thiran.db")
app = FastAPI(title="Thiran AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "images").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_store() -> Store:
    return Store(DB_PATH)


def get_lstore(store: Store | None = None) -> LearnerStore:
    return LearnerStore(store or get_store())


def get_call_engine(stub: bool = False, topic: str = "recursion", session_num: int = 1, loop_count: int = 0):
    st = load_settings()
    if stub or not st.api_key:
        if session_num == 2:
            eng = Session2Stub()
        else:
            eng = ThiranStub(topic=topic)
        if loop_count > 0:
            if "gate" in eng.script and len(eng.script["gate"]) > 1:
                eng._n["gate"] = min(loop_count, len(eng.script["gate"]) - 1)
            if "intervention" in eng.script and len(eng.script["intervention"]) > 1:
                eng._n["intervention"] = min(loop_count, len(eng.script["intervention"]) - 1)
        return eng, st, True
    from slice.llm import complete
    return complete, st, False


# ---------------------------------------------------------------- Models


class LoginRequest(BaseModel):
    username: str


class RegisterRequest(BaseModel):
    username: str
    name: str
    domain: str = "computer_science"


class StartSessionRequest(BaseModel):
    learner_id: str
    topic: str = "recursion"
    familiarity: str = "beginner"
    stub: bool = False
    session_number: int = 1


class SubmitAnswerRequest(BaseModel):
    run_id: str
    answer: str
    stub: bool = False


# ---------------------------------------------------------------- Routes: Auth & Learners


@app.get("/", response_class=FileResponse)
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(index_path))


@app.get("/api/learners")
def list_learners():
    lstore = get_lstore()
    return {"learners": lstore.list_learners()}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    lstore = get_lstore()
    username = req.username.strip().lower().replace(" ", "_")
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")

    profile = lstore.get_learner(username)
    if not profile:
        for row in lstore.list_learners():
            if row["learner_id"].lower() == username or row.get("name", "").lower() == req.username.strip().lower():
                profile = lstore.get_learner(row["learner_id"])
                break

    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{req.username}' not found. Please register.")

    return {"status": "ok", "profile": profile.model_dump()}


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    lstore = get_lstore()
    username = req.username.strip().lower().replace(" ", "_")
    name = req.name.strip()
    if not username or not name:
        raise HTTPException(status_code=400, detail="Username and Name are required.")

    existing = lstore.get_learner(username)
    if existing:
        return {"status": "existing", "message": f"Username '{username}' already exists.", "profile": existing.model_dump()}

    profile = lstore.get_or_create_learner(learner_id=username, name=name, domain=req.domain)
    return {"status": "created", "profile": profile.model_dump()}


# ---------------------------------------------------------------- Routes: Learning Sessions


@app.post("/api/session/start")
def session_start(req: StartSessionRequest):
    store = get_store()
    lstore = LearnerStore(store)
    profile = lstore.get_learner(req.learner_id)
    name = profile.name if profile else req.learner_id.capitalize()

    call, st, is_stub = get_call_engine(req.stub, topic=req.topic, session_num=req.session_number)

    run_id = store.create_run(
        "thiran",
        meta={
            "learner_id": req.learner_id,
            "topic": req.topic,
            "session": req.session_number,
        },
    )

    input_payload = {
        "learner_id": req.learner_id,
        "name": name,
        "topic": req.topic,
        "familiarity": req.familiarity,
        "session_number": req.session_number,
        "interactive": True,
    }
    store.append(run_id, "input", input_payload, produced_by="system")
    store.append(run_id, "phase", {"name": "ASSESS"}, produced_by="system")

    ctx = Context(store, run_id, st)
    evidence = lstore.get_relevant_evidence(req.learner_id, req.topic)

    # 1. Execute ASSESS step
    diag = _invoke_agent(
        ctx,
        call,
        "assess",
        build_assess_messages(input_payload, evidence),
        DiagnosticChallenge,
    )
    store.append(run_id, "diagnostic_challenge", diag.model_dump(), produced_by="agent:assess")
    store.append(run_id, "phase", {"name": "AWAIT_DIAGNOSTIC"}, produced_by="system")
    store.set_state(run_id, RunState.PROBING)

    streak = profile.consecutive_correct.get(req.topic, 0) if profile else 0
    confidence = profile.confidence_state.get(req.topic, "learning") if profile else "learning"

    return {
        "run_id": run_id,
        "stage": "ASSESS",
        "current_phase": "AWAIT_DIAGNOSTIC",
        "topic": req.topic,
        "familiarity": req.familiarity,
        "streak": streak,
        "confidence": confidence,
        "diagnostic_challenge": diag.model_dump(),
        "is_stub": is_stub,
    }


@app.post("/api/session/answer")
def session_answer(req: SubmitAnswerRequest):
    store = get_store()
    lstore = LearnerStore(store)
    run_meta = store.db.execute("SELECT meta_json FROM runs WHERE id = ?", (req.run_id,)).fetchone()
    if not run_meta:
        raise HTTPException(status_code=404, detail="Run not found")

    meta = json.loads(run_meta["meta_json"])
    learner_id = meta.get("learner_id", "surya")
    topic = meta.get("topic", "recursion")
    session_num = meta.get("session", 1)

    loop_count = int(store.counter(req.run_id, "backward_loops"))
    call, st, is_stub = get_call_engine(req.stub, topic=topic, session_num=session_num, loop_count=loop_count)
    ctx = Context(store, run_id=req.run_id, settings=st)

    phase_rec = ctx.latest("phase")
    phase = phase_rec["name"] if phase_rec else "AWAIT_DIAGNOSTIC"
    inp = ctx.latest("input") or {}
    evidence = lstore.get_relevant_evidence(learner_id, topic)

    if phase == "AWAIT_DIAGNOSTIC":
        # 1. Record student diagnostic answer
        ctx.append(
            "learner_answer",
            {"text": req.answer, "phase": "DIAGNOSTIC", "attempt": 1},
            produced_by="learner",
        )
        ctx.append("phase", {"name": "COGNITIVE"}, produced_by="system")
        store.set_state(req.run_id, RunState.DRAFTING)

        # 2. Run Cognitive Agent
        loop_count = int(store.counter(req.run_id, "backward_loops"))
        analysis = _invoke_agent(
            ctx,
            call,
            "cognitive",
            build_cognitive_messages(inp, req.answer, evidence, loop_count, None),
            CognitiveAnalysis,
        )
        ctx.append("cognitive_analysis", analysis.model_dump(), produced_by="agent:cognitive")

        # 3. Advance immediately to INTERVENE in same turn
        past_int = evidence.get("past_interventions", [])
        strategy = get_escalated_strategy(attempt=loop_count + 1, past_strategies=past_int)

        intervention = _invoke_agent(
            ctx,
            call,
            "intervention",
            build_intervention_messages(inp, analysis, strategy, evidence),
            Intervention,
        )
        ctx.append("intervention", intervention.model_dump(), produced_by="agent:intervention")
        ctx.append("phase", {"name": "AWAIT_SOCRATIC"}, produced_by="system")
        store.set_state(req.run_id, RunState.PROBING)

        return {
            "run_id": req.run_id,
            "stage": "INTERVENTION",
            "current_phase": "AWAIT_SOCRATIC",
            "analysis": analysis.model_dump(),
            "intervention": intervention.model_dump(),
            "backward_transition": False,
        }

    elif phase == "AWAIT_SOCRATIC":
        loop_count = int(store.counter(req.run_id, "backward_loops"))
        ctx.append(
            "learner_answer",
            {"text": req.answer, "phase": "SOCRATIC", "attempt": loop_count + 1},
            produced_by="learner",
        )
        store.set_state(req.run_id, RunState.GATING)

        # 4. Gating Judge evaluation
        intervention_dict = ctx.latest("intervention")
        answer_dict = ctx.latest("learner_answer")

        verdict = _invoke_agent(
            ctx,
            call,
            "gate",
            build_gate_messages(intervention_dict, answer_dict),
            ReassessVerdict,
        )
        ctx.append("verdict", verdict.model_dump(), produced_by="agent:judge")

        if verdict.status == "PASS":
            # --- PASS: Deterministic profile update ---
            profile = lstore.get_or_create_learner(learner_id, inp.get("name", learner_id.capitalize()))
            profile.knowledge_state[topic] = verdict.score
            profile.session_count += 1
            profile.last_topic = topic

            streak = profile.consecutive_correct.get(topic, 0) + 1
            profile.consecutive_correct[topic] = streak
            if streak >= 2:
                profile.confidence_state[topic] = "confident"
            elif profile.confidence_state.get(topic) != "confident":
                profile.confidence_state[topic] = "learning"

            # Resolve misconceptions
            resolved_names = []
            cog = ctx.latest("cognitive_analysis")
            strategy_used = intervention_dict.get("teaching_strategy_used") if intervention_dict else None

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
                    "confidence_state": profile.confidence_state,
                    "consecutive_correct": profile.consecutive_correct,
                    "resolved_misconceptions": resolved_names,
                    "session_count": profile.session_count,
                },
                produced_by="system",
            )
            store.set_state(req.run_id, RunState.COMPLETE)

            return {
                "run_id": req.run_id,
                "stage": "COMPLETE",
                "current_phase": "COMPLETE",
                "verdict": verdict.model_dump(),
                "streak": streak,
                "confidence": profile.confidence_state.get(topic, "learning"),
                "status": "PASS",
                "backward_transition": False,
            }

        else:
            # --- BLOCK: Backward Adaptation Loop ---
            # 1. Reset streak & update confidence
            profile = lstore.get_or_create_learner(learner_id, inp.get("name", learner_id.capitalize()))
            profile.consecutive_correct[topic] = 0
            if profile.confidence_state.get(topic) == "confident":
                profile.confidence_state[topic] = "revisiting"
            elif topic not in profile.confidence_state:
                profile.confidence_state[topic] = "learning"
            lstore.save_learner(profile)

            ctx.append(
                "confidence_update",
                {
                    "learner_id": learner_id,
                    "topic": topic,
                    "confidence": profile.confidence_state.get(topic, "learning"),
                    "consecutive_correct": 0,
                    "event": "mistake_reset",
                },
                produced_by="system",
            )

            # 2. Check max loops fence
            loop_count = int(store.counter(req.run_id, "backward_loops"))
            if loop_count >= 3:
                ctx.append(
                    "failure",
                    {
                        "kind": "max_loops_exhausted",
                        "detail": f"Blocked {loop_count} times; misconception persisted.",
                        "unresolved_evidence": verdict.unresolved_evidence,
                    },
                    produced_by="system",
                )
                store.set_state(req.run_id, RunState.FAILED)
                return {
                    "run_id": req.run_id,
                    "stage": "FAILED",
                    "status": "FAILED",
                    "verdict": verdict.model_dump(),
                    "backward_transition": False,
                    "detail": "Maximum attempts reached. Let's reset and review foundational principles.",
                }

            # 3. Bump backward loop and escalate strategy
            store.bump(req.run_id, "backward_loops")
            new_loop_count = loop_count + 1
            next_attempt = new_loop_count + 1
            strategy = get_escalated_strategy(next_attempt, evidence.get("past_interventions", []))

            ctx.append(
                "backward_loop",
                {
                    "loop_count": new_loop_count,
                    "reason": verdict.feedback,
                    "escalated_strategy": strategy,
                    "from_phase": "GATING",
                    "to_phase": "INTERVENE",
                },
                produced_by="system",
            )
            ctx.append("phase", {"name": "INTERVENE"}, produced_by="system")
            ctx.append("decision", {"action": "reuse_diagnosis", "escalated_strategy": strategy}, produced_by="system")

            # 4. Generate new escalated intervention
            analysis_dict = ctx.latest("cognitive_analysis")
            analysis = CognitiveAnalysis.model_validate(analysis_dict)
            escalated_intervention = _invoke_agent(
                ctx,
                call,
                "intervention",
                build_intervention_messages(inp, analysis, strategy, evidence),
                Intervention,
            )
            ctx.append("intervention", escalated_intervention.model_dump(), produced_by="agent:intervention")
            ctx.append("phase", {"name": "AWAIT_SOCRATIC"}, produced_by="system")
            store.set_state(req.run_id, RunState.PROBING)

            visualization = intervention_dict.get("visualization", "") or escalated_intervention.visualization

            return {
                "run_id": req.run_id,
                "stage": "PRACTICE_BLOCKED",
                "current_phase": "AWAIT_SOCRATIC",
                "status": "BLOCK",
                "verdict": verdict.model_dump(),
                "backward_transition": True,
                "backward_loop": {
                    "loop_count": new_loop_count,
                    "escalated_strategy": strategy,
                    "reason": verdict.feedback,
                    "from_phase": "Practice / Gate",
                    "to_phase": "Assess / Intervene",
                },
                "visualization": visualization,
                "escalated_intervention": escalated_intervention.model_dump(),
                "streak": 0,
                "confidence": profile.confidence_state.get(topic, "learning"),
            }

    else:
        raise HTTPException(status_code=400, detail=f"Invalid phase for submitting answer: {phase}")


@app.get("/api/session/{run_id}")
def get_session_state(run_id: str):
    store = get_store()
    lstore = LearnerStore(store)

    run_row = store.db.execute(
        "SELECT id, domain, state, created_at, updated_at, meta_json FROM runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if not run_row:
        raise HTTPException(status_code=404, detail="Session not found")

    meta = {}
    try:
        meta = json.loads(run_row["meta_json"])
    except Exception:
        pass

    learner_id = meta.get("learner_id", "surya")
    topic = meta.get("topic", "recursion")
    profile = lstore.get_learner(learner_id)

    versions = store.db.execute(
        "SELECT seq, kind, produced_by, payload_json, created_at FROM versions WHERE run_id = ? ORDER BY seq ASC",
        (run_id,),
    ).fetchall()

    diagnostic_challenge = None
    cognitive_analysis = None
    intervention = None
    verdict = None
    backward_loops = []
    learner_answers = []
    current_phase = "AWAIT_DIAGNOSTIC"
    familiarity = "beginner"

    for v in versions:
        kind = v["kind"]
        try:
            payload = json.loads(v["payload_json"])
        except Exception:
            payload = {}

        if kind == "input":
            familiarity = payload.get("familiarity", familiarity)
            topic = payload.get("topic", topic)
        elif kind == "phase":
            current_phase = payload.get("name", current_phase)
        elif kind == "diagnostic_challenge":
            diagnostic_challenge = payload
        elif kind == "cognitive_analysis":
            cognitive_analysis = payload
        elif kind == "intervention":
            intervention = payload
        elif kind == "learner_answer":
            learner_answers.append(payload)
        elif kind == "verdict":
            verdict = payload
        elif kind == "backward_loop":
            backward_loops.append(payload)

    streak = profile.consecutive_correct.get(topic, 0) if profile else 0
    confidence = profile.confidence_state.get(topic, "learning") if profile else "learning"

    return {
        "run_id": run_id,
        "learner_id": learner_id,
        "topic": topic,
        "familiarity": familiarity,
        "state": run_row["state"],
        "current_phase": current_phase,
        "diagnostic_challenge": diagnostic_challenge,
        "cognitive_analysis": cognitive_analysis,
        "intervention": intervention,
        "verdict": verdict,
        "backward_loops": backward_loops,
        "learner_answers": learner_answers,
        "streak": streak,
        "confidence": confidence,
    }


# ---------------------------------------------------------------- Routes: Recent Questions & History


@app.get("/api/recent-questions/{learner_id}")
def get_recent_questions(learner_id: str, limit: int = 10):
    store = get_store()
    runs_rows = store.db.execute(
        "SELECT id, domain, state, created_at, updated_at, meta_json FROM runs WHERE meta_json LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f'%"{learner_id}"%', limit),
    ).fetchall()

    recent = []
    for r in runs_rows:
        try:
            meta = json.loads(r["meta_json"])
        except Exception:
            meta = {}
        topic = meta.get("topic", "recursion")

        v_diag = store.db.execute(
            "SELECT payload_json FROM versions WHERE run_id = ? AND kind = 'diagnostic_challenge' ORDER BY seq ASC LIMIT 1",
            (r["id"],),
        ).fetchone()

        question = ""
        prior_score = None
        if v_diag:
            try:
                p = json.loads(v_diag["payload_json"])
                question = p.get("challenge_question", "")
                prior_score = p.get("prior_score")
            except Exception:
                pass

        v_verdict = store.db.execute(
            "SELECT payload_json FROM versions WHERE run_id = ? AND kind = 'verdict' ORDER BY seq DESC LIMIT 1",
            (r["id"],),
        ).fetchone()
        verdict_status = None
        if v_verdict:
            try:
                pv = json.loads(v_verdict["payload_json"])
                verdict_status = pv.get("status")
            except Exception:
                pass

        recent.append({
            "run_id": r["id"],
            "topic": topic,
            "question": question or f"{topic.replace('_', ' ').capitalize()} Practice Challenge",
            "created_at": r["created_at"],
            "state": r["state"],
            "verdict_status": verdict_status,
            "prior_score": prior_score,
        })

    return {"learner_id": learner_id, "recent_questions": recent}


# ---------------------------------------------------------------- Routes: Deterministic Analytics


@app.get("/api/analytics/{learner_id}")
def get_analytics(learner_id: str):
    store = get_store()
    lstore = LearnerStore(store)
    profile = lstore.get_learner(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Learner not found")

    # 1. Fetch all runs for this learner
    runs_rows = store.db.execute(
        "SELECT id, domain, state, created_at, updated_at, meta_json FROM runs WHERE meta_json LIKE ? ORDER BY created_at ASC",
        (f'%"{learner_id}"%',),
    ).fetchall()

    total_study_seconds = 0.0
    completed_sessions = 0
    active_days_set = set()
    daily_time_map: dict[str, float] = {}

    run_ids = []
    run_topics: dict[str, str] = {}

    for r in runs_rows:
        run_ids.append(r["id"])
        try:
            meta = json.loads(r["meta_json"])
        except Exception:
            meta = {}
        topic = meta.get("topic", "recursion")
        run_topics[r["id"]] = topic

        # Study time estimate: duration between first event and last event in run
        v_times = store.db.execute(
            "SELECT min(created_at) as start_t, max(created_at) as end_t, count(*) as c FROM versions WHERE run_id = ?",
            (r["id"],),
        ).fetchone()

        start_t = v_times["start_t"] or r["created_at"]
        end_t = v_times["end_t"] or r["updated_at"]
        duration = max(45.0, end_t - start_t)  # floor at 45 seconds minimum per interaction
        total_study_seconds += duration

        if r["state"] == "complete":
            completed_sessions += 1

        day_str = datetime.date.fromtimestamp(start_t).strftime("%Y-%m-%d")
        active_days_set.add(day_str)
        daily_time_map[day_str] = daily_time_map.get(day_str, 0.0) + duration

    # 2. Compute Daily Streak
    daily_streak = 0
    today = datetime.date.today()
    check_day = today
    # Check if active today or yesterday to preserve streak
    if check_day.strftime("%Y-%m-%d") not in active_days_set:
        check_day = today - datetime.timedelta(days=1)

    while check_day.strftime("%Y-%m-%d") in active_days_set:
        daily_streak += 1
        check_day -= datetime.timedelta(days=1)

    # 3. Last 7 Days Graph Data
    last_7_days = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        label = d.strftime("%a")
        mins = round(daily_time_map.get(d_str, 0.0) / 60.0, 1)
        last_7_days.append({
            "date": d_str,
            "label": label,
            "minutes": mins,
            "active": d_str in active_days_set,
        })

    # 4. Topics summary
    # Collect all topics from knowledge_state, confidence_state, runs, or misconceptions
    topics_set = set(profile.knowledge_state.keys()) | set(profile.confidence_state.keys()) | set(run_topics.values())
    if not topics_set:
        topics_set = {"recursion"}

    topics_summary = []
    before_after_by_topic: dict[str, list[dict]] = {}

    for topic in sorted(topics_set):
        score = profile.knowledge_state.get(topic, 0)
        conf = profile.confidence_state.get(topic, "learning")
        streak = profile.consecutive_correct.get(topic, 0)
        attempts = sum(1 for t in run_topics.values() if t == topic)
        unresolved_m = [m for m in profile.misconceptions if m.concept == topic or topic in m.concept]
        resolved_count = sum(1 for m in unresolved_m if m.resolved)

        topics_summary.append({
            "topic": topic,
            "score": score,
            "confidence": conf,
            "streak": streak,
            "attempts": max(attempts, 1 if score > 0 else 0),
            "misconceptions_count": len(unresolved_m),
            "resolved_count": resolved_count,
        })

        # 5. Extract Real BEFORE vs AFTER EVIDENCE from SQLite versions table
        evidence_list = []
        topic_run_ids = [rid for rid, t in run_topics.items() if t == topic]

        for rid in topic_run_ids:
            versions = store.db.execute(
                "SELECT seq, kind, produced_by, payload_json, created_at FROM versions WHERE run_id = ? ORDER BY seq ASC",
                (rid,),
            ).fetchall()

            diag_challenge = None
            diag_answer = None
            cog_analysis = None
            interventions = []
            socratic_answers = []
            verdicts = []
            backward_loops = []

            for v in versions:
                k = v["kind"]
                p = json.loads(v["payload_json"])
                if k == "diagnostic_challenge":
                    diag_challenge = p
                elif k == "learner_answer" and p.get("phase") == "DIAGNOSTIC":
                    diag_answer = p
                elif k == "cognitive_analysis":
                    cog_analysis = p
                elif k == "intervention":
                    interventions.append(p)
                elif k == "learner_answer" and p.get("phase") == "SOCRATIC":
                    socratic_answers.append(p)
                elif k == "verdict":
                    verdicts.append(p)
                elif k == "backward_loop":
                    backward_loops.append(p)

            # Build a Before vs After card if we have diagnostic or intervention/verdict data
            if diag_answer or socratic_answers or cog_analysis:
                # BEFORE snapshot: Initial code and diagnosed mistake
                before_code = diag_answer.get("text", "") if diag_answer else ""
                before_challenge = diag_challenge.get("challenge_question", "") if diag_challenge else f"Initial {topic} challenge"
                flaws = []
                if cog_analysis and "misconceptions" in cog_analysis:
                    for m in cog_analysis["misconceptions"]:
                        flaws.append(f"{m.get('description', '')} ({m.get('concept', '')})")
                mental_model = cog_analysis.get("mental_model_summary", "") if cog_analysis else ""

                # AFTER snapshot: Passing or final code, strategy used, verdict
                after_code = socratic_answers[-1].get("text", "") if socratic_answers else ""
                latest_verdict = verdicts[-1] if verdicts else {}
                latest_intervention = interventions[-1] if interventions else {}
                strategy = latest_intervention.get("teaching_strategy_used", "")
                viz = latest_intervention.get("visualization", "")

                evidence_list.append({
                    "run_id": rid,
                    "date": datetime.datetime.fromtimestamp(versions[0]["created_at"]).strftime("%b %d, %Y %H:%M") if versions else "",
                    "before": {
                        "challenge": before_challenge,
                        "code": before_code,
                        "diagnosed_gap": flaws[0] if flaws else (mental_model or "Initial misconception"),
                        "mental_model": mental_model,
                        "status": "FAILED / BLOCKED" if verdicts or backward_loops else "DIAGNOSTIC",
                    },
                    "after": {
                        "code": after_code,
                        "strategy_used": strategy,
                        "verdict_score": latest_verdict.get("score", 4 if latest_verdict.get("status") == "PASS" else 0),
                        "verdict_status": latest_verdict.get("status", "PASS" if score == 4 else "IN_PROGRESS"),
                        "feedback": latest_verdict.get("feedback", "Successfully mastered invariant and edge cases."),
                        "visualization": viz,
                    },
                    "backward_loops_count": len(backward_loops),
                    "backward_loops": backward_loops,
                })

        before_after_by_topic[topic] = evidence_list

    return {
        "learner_id": profile.learner_id,
        "name": profile.name,
        "domain": profile.domain,
        "total_study_time_seconds": round(total_study_seconds, 1),
        "total_study_time_formatted": f"{int(total_study_seconds // 3600)}h {int((total_study_seconds % 3600) // 60)}m" if total_study_seconds >= 3600 else f"{int(total_study_seconds // 60)} min",
        "study_sessions": completed_sessions or len(runs_rows),
        "daily_streak": max(daily_streak, 1 if runs_rows else 0),
        "last_7_days": last_7_days,
        "topics": topics_summary,
        "before_after_evidence": before_after_by_topic,
    }


def main():
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
