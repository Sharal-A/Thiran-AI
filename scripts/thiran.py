#!/usr/bin/env python3
"""Thiran AI CLI — Adaptive Multi-Agent Learning System.

Usage:
    python -m scripts.thiran run --stub               # run session 1 with stub
    python -m scripts.thiran run --interactive        # run interactive session (type code live)
    python -m scripts.thiran session2 --stub          # run session 2 (cross-session progression)
    python -m scripts.thiran replay <run_id>          # view complete audit trail of a run
    python -m scripts.thiran learners                 # inspect persistent learner profiles
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slice import runner
from slice.config import settings as load_settings
from slice.records import RunState
from slice.store import Store

from demo.smoke.flow import build_flow
from demo.smoke.store_ext import LearnerStore

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
GREEN, RED, AMBER, CYAN, MAGENTA = "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[35m"


def _c(s: str, colour: str) -> str:
    return s if not sys.stdout.isatty() else f"{colour}{s}{RESET}"


def _execute_session(args: argparse.Namespace, session_num: int = 1) -> int:
    if args.stub:
        if session_num == 2:
            from demo.smoke.stub import Session2Stub
            call = Session2Stub()
        elif getattr(args, "case", "loop") == "clean":
            from demo.smoke.stub import CleanStub
            call = CleanStub()
        elif getattr(args, "case", "loop") == "hopeless":
            from demo.smoke.stub import AlwaysBlocksStub
            call = AlwaysBlocksStub()
        else:
            from demo.smoke.stub import ThiranStub
            call = ThiranStub()
        st = load_settings()
    else:
        from slice.llm import complete as call
        st = load_settings()
        if not st.api_key:
            print(_c("No OPENROUTER_API_KEY in .env.", RED),
                  "\nRun with --stub to test offline without an API key.")
            return 2

    store = Store(args.db)
    lstore = LearnerStore(store)
    run_id = store.create_run("thiran", meta={"learner_id": args.learner, "topic": args.topic, "session": session_num})

    prior_profile = lstore.get_learner(args.learner)
    learner_name = getattr(args, "name", None) or (prior_profile.name if prior_profile else args.learner.capitalize())

    input_payload = {
        "learner_id": args.learner,
        "name": learner_name,
        "topic": args.topic,
        "session_number": session_num,
        "interactive": getattr(args, "interactive", False),
    }
    if getattr(args, "answers", None):
        input_payload["answers"] = args.answers

    store.append(run_id, "input", input_payload, produced_by="system")
    store.append(run_id, "phase", {"name": "ASSESS"}, produced_by="system")

    mode = "stub" if args.stub else st.model
    session_tag = f"Session {session_num}"
    print(f"\n{_c('run', DIM)} {BOLD}{run_id}{RESET}   {_c(session_tag, CYAN)}   learner: {CYAN}{args.learner}{RESET}   topic: {BOLD}{args.topic}{RESET}   ({_c(mode, DIM)})\n")

    if prior_profile:
        print(f"  {_c('memory', MAGENTA)} Loaded profile for {prior_profile.name} (sessions: {prior_profile.session_count}, scores: {prior_profile.knowledge_state})")

    final = runner.advance(store, run_id, build_flow(call), st)

    for v in store.replay(run_id):
        k = v.kind
        p = v.payload
        if k == "diagnostic_challenge":
            print(f"  {_c('assess   ', CYAN)} Diagnostic: {p.get('challenge_question')[:80]}...")
        elif k == "learner_answer":
            phase = p.get("phase", "")
            ans = p.get("text", "").replace("\n", " ")
            print(f"  {_c('student  ', DIM)} [{phase}] {ans[:80]}...")
        elif k == "cognitive_analysis":
            misconceptions = p.get("misconceptions", [])
            m_desc = misconceptions[0]["description"] if misconceptions else "No misconceptions"
            print(f"  {_c('cognitive', MAGENTA)} Diagnosed: {m_desc[:80]}...")
        elif k == "intervention":
            strat = p.get('teaching_strategy_used', 'analogy')
            expl = p.get('explanation', '').replace('\n', ' ')
            prob = p.get('problem_statement', '').replace('\n', ' ')
            print(f"  {_c('intervene', GREEN)} [{strat}] {expl[:80]}...")
            print(f"  {_c('socratic ', AMBER)} Challenge: {prob[:80]}...")
        elif k == "decision":
            if p.get("action") == "skip_cognitive":
                print(f"  {_c('telemetry', DIM)} Cognitive re-call skipped (no new evidence)")
        elif k == "learning_plan":
            seq = ", ".join(p.get("concept_sequence", []))
            print(f"  {_c('planner  ', DIM)} Scaffold: {p.get('scaffold_level')} | Sequence: {seq}")
        elif k == "tutor_exchange":
            print(f"  {_c('tutor    ', GREEN)} Explaining: {p.get('explanation')[:80]}...")
        elif k == "socratic_challenge":
            print(f"  {_c('socratic ', AMBER)} Challenge: {p.get('problem_statement')[:80]}...")
        elif k == "verdict":
            tag = _c("PASS ", GREEN) if p.get("status") == "PASS" else _c("BLOCK", AMBER)
            print(f"  {_c('judge    ', DIM)} {tag} (score={p.get('score')}/4) - {p.get('feedback')[:75]}...")
        elif k == "backward_loop":
            strat = p.get('escalated_strategy', '')
            print(f"  {_c('loop     ', AMBER)} <- Backward loop #{p.get('loop_count')} (Strategy: {strat}): {p.get('reason')[:60]}...")
        elif k == "learner_update":
            print(f"  {_c('update   ', GREEN)} Profile saved: scores={p.get('concept_scores')}, resolved={p.get('resolved_misconceptions')}")
        elif k == "failure":
            print(f"  {_c('failed   ', RED)} {p.get('kind')}: {p.get('detail')}")

    tokens = store.counter(run_id, "tokens")
    ok = final is RunState.COMPLETE
    print()
    print(f"  {_c('=>', DIM)} {_c(final.value.upper(), GREEN if ok else RED)}"
          f"   {len(store.replay(run_id))} events | {int(tokens):,} tok")

    loops = int(store.counter(run_id, "backward_loops"))
    if loops > 0:
        print(f"  {_c('=>', DIM)} {_c(f'work went backwards ({loops} loop(s))', GREEN)}: "
              "Agent adapted instruction to learner's diagnosed misconception.")

    agent_steps = ["assess", "cognitive", "intervention", "gate"]
    print(f"\n  {BOLD}Per-Agent Token Usage:{RESET}")
    total_calls = 0
    for step in agent_steps:
        s_tok = int(store.counter(run_id, f"tokens:{step}"))
        s_calls = int(store.counter(run_id, f"calls:{step}"))
        total_calls += s_calls
        if s_calls > 0:
            print(f"    {_c(step.ljust(12), DIM)}: {s_tok:>4} tok  ({s_calls} call{'s' if s_calls > 1 else ''})")
    print(f"    {_c('TOTAL CALLS'.ljust(12), BOLD)}: {total_calls} calls total")

    # Post-session profile review
    updated_profile = lstore.get_learner(args.learner)
    if updated_profile:
        print(f"\n  {BOLD}Updated Learner Memory:{RESET} Sessions={updated_profile.session_count} | Mastery={updated_profile.knowledge_state}")

    print(f"\n  {_c('replay:', DIM)} python -m scripts.thiran replay {run_id}\n")
    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    return _execute_session(args, session_num=1)


def cmd_session2(args: argparse.Namespace) -> int:
    store = Store(args.db)
    lstore = LearnerStore(store)
    prior = lstore.get_learner(args.learner)
    if not prior or prior.session_count == 0:
        print(_c(f"Note: No previous session recorded for '{args.learner}'. Running Session 2 will seed a new profile.", AMBER))
    return _execute_session(args, session_num=2)


def cmd_replay(args: argparse.Namespace) -> int:
    store = Store(args.db)
    for v in store.replay(args.run_id):
        body = json.dumps(v.payload, indent=2)
        print(f"\n{_c(f'#{v.seq}', DIM)} {BOLD}{v.kind}{RESET} {_c(v.produced_by, DIM)}")
        print("\n".join("    " + line for line in body.splitlines()))
    print()
    return 0


def cmd_learners(args: argparse.Namespace) -> int:
    store = Store(args.db)
    lstore = LearnerStore(store)
    learners = lstore.list_learners()
    if not learners:
        print("No learners found in database.")
        return 0

    print(f"\n{BOLD}Registered Learners:{RESET}\n")
    for row in learners:
        profile = lstore.get_learner(row["learner_id"])
        if profile:
            resolved = sum(1 for m in profile.misconceptions if m.resolved)
            total_m = len(profile.misconceptions)
            print(f"  {CYAN}{profile.name}{RESET} ({profile.learner_id})")
            print(f"    Domain: {profile.domain} | Sessions: {profile.session_count} | Last: {profile.last_topic}")
            print(f"    Knowledge State: {profile.knowledge_state}")
            print(f"    Misconceptions: {resolved}/{total_m} resolved\n")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--db", default="thiran.db", help="SQLite database path")
    sub = p.add_subparsers(dest="cmd", required=True)

    # run command (session 1)
    r = sub.add_parser("run", help="Run Thiran learning loop (Session 1)")
    r.add_argument("--stub", action="store_true", help="Run with canned responses; no API key needed")
    r.add_argument("--learner", default="surya", help="Learner ID")
    r.add_argument("--name", default="Surya", help="Learner display name")
    r.add_argument("--topic", default="recursion", help="Concept / topic to learn")
    r.add_argument("--interactive", action="store_true", help="Interactive terminal mode: type student code live")
    r.add_argument(
        "--case",
        choices=["loop", "clean", "hopeless"],
        default="loop",
        help="loop: blocks once then recovers (default); clean: passes 1st try; hopeless: fails max attempts",
    )
    r.add_argument("--answers", nargs="*", default=None, help="Learner answers to inject")
    r.set_defaults(fn=cmd_run)

    # session2 command
    s2 = sub.add_parser("session2", help="Run Thiran Session 2 with cross-session progression")
    s2.add_argument("--stub", action="store_true", help="Run with canned responses; no API key needed")
    s2.add_argument("--learner", default="surya", help="Learner ID")
    s2.add_argument("--topic", default="recursion", help="Concept / topic to learn")
    s2.add_argument("--interactive", action="store_true", help="Interactive terminal mode: type student code live")
    s2.add_argument("--answers", nargs="*", default=None, help="Learner answers to inject")
    s2.set_defaults(fn=cmd_session2)

    # replay command
    rp = sub.add_parser("replay", help="Display all events in a run")
    rp.add_argument("run_id", help="Run ID to replay")
    rp.set_defaults(fn=cmd_replay)

    # learners inspect command
    lp = sub.add_parser("learners", help="List persistent learner profiles")
    lp.set_defaults(fn=cmd_learners)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
