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


def _prompt_identity_if_interactive(args: argparse.Namespace, lstore: LearnerStore) -> None:
    """Prompt the learner for identity in interactive mode: [1] Log in or [2] I'm new here."""
    if not (getattr(args, "interactive", False) and sys.stdin.isatty()):
        return

    print(f"\n{BOLD}{CYAN}=== Thiran AI Authentication ==={RESET}")
    print(f"  {BOLD}[1] Log in{RESET}         (existing learner with unique username)")
    print(f"  {BOLD}[2] I'm new here{RESET}   (create new learner profile)\n")

    while True:
        choice = input("Select an option [1]: ").strip().lower()
        if choice in {"", "1", "login", "log in", "l"}:
            # Log in path
            while True:
                username = input("\nEnter your unique username (or 'b' to go back): ").strip()
                if not username:
                    print(f"  {_c('Username cannot be empty.', AMBER)}")
                    continue
                if username.lower() in {"b", "back"}:
                    break

                learner_id = username.lower().replace(" ", "_")
                profile = lstore.get_learner(learner_id)
                if not profile:
                    # Check case-insensitive match on learner_id or name in all learners
                    for row in lstore.list_learners():
                        if row["learner_id"].lower() == learner_id or row.get("name", "").lower() == username.lower():
                            profile = lstore.get_learner(row["learner_id"])
                            break

                if profile:
                    args.learner = profile.learner_id
                    args.name = profile.name
                    print(f"\n{_c('Welcome back,', GREEN)} {BOLD}{profile.name}!{RESET} 👋")
                    if profile.session_count > 0:
                        print(f"  {_c('Sessions recorded :', DIM)} {profile.session_count}")
                        if profile.last_topic:
                            print(f"  {_c('Last topic studied:', DIM)} {profile.last_topic}")
                        if profile.knowledge_state:
                            print(f"  {_c('Knowledge state   :', DIM)} {profile.knowledge_state}")
                        if profile.confidence_state:
                            print(f"  {_c('Confidence state  :', DIM)} {profile.confidence_state}")
                    else:
                        print(f"  {_c('Profile loaded. Ready for your first session!', DIM)}")
                    print()
                    return
                else:
                    print(f"  {_c('Learner not found:', RED)} '{username}'")
                    print(f"  Try again, type {BOLD}'b'{RESET} to go back, or choose {BOLD}[2]{RESET} to register.")

            print(f"\n  {BOLD}[1] Log in{RESET}  |  {BOLD}[2] I'm new here{RESET}")
            continue

        elif choice in {"2", "new", "register", "r"}:
            # New user path
            print(f"\n{BOLD}=== Create New Learner Profile ==={RESET}")
            while True:
                name = input("Enter your full name: ").strip()
                if not name:
                    print(f"  {_c('Name cannot be empty.', AMBER)}")
                    continue
                break

            default_uname = name.lower().replace(" ", "_")
            while True:
                uname_prompt = f"Choose a unique username [{default_uname}]: "
                uname = input(uname_prompt).strip()
                username = uname.lower().replace(" ", "_") if uname else default_uname

                if not username:
                    print(f"  {_c('Username cannot be empty.', AMBER)}")
                    continue

                # Check if already taken
                existing = lstore.get_learner(username)
                if existing:
                    print(f"  {_c('Notice:', AMBER)} Username '{username}' is already taken by {existing.name}.")
                    retry_choice = input("  Would you like to log in as this user instead? [y/N]: ").strip().lower()
                    if retry_choice in {"y", "yes"}:
                        args.learner = existing.learner_id
                        args.name = existing.name
                        print(f"\n{_c('Welcome back,', GREEN)} {BOLD}{existing.name}!{RESET} 👋\n")
                        return
                    continue

                # Create the learner profile immediately in SQLite learners table
                profile = lstore.get_or_create_learner(learner_id=username, name=name)
                args.learner = profile.learner_id
                args.name = profile.name
                print(f"\n{_c('Profile created successfully for', GREEN)} {BOLD}{profile.name}{RESET} (username: {CYAN}{profile.learner_id}{RESET})! Welcome to Thiran AI.\n")
                return

        else:
            print(f"  {_c('Invalid choice. Please select 1 or 2.', AMBER)}")


def _prompt_intake_if_interactive(args: argparse.Namespace) -> None:
    """Prompt the learner through the structured intake workflow: Topic -> Familiarity."""
    if not (getattr(args, "interactive", False) and sys.stdin.isatty()):
        return

    print(f"\n{BOLD}{CYAN}=== Thiran AI Assessment Setup ==={RESET}")
    print("What would you like to learn?")
    print(f"  - Built-in offline topics: {BOLD}recursion{RESET}, {BOLD}two_pointers{RESET}, {BOLD}binary_search{RESET}")
    print(f"  - Or type {BOLD}any DSA topic{RESET} (e.g. arrays, dynamic_programming, graphs, trees)\n")

    default_topic = args.topic 
    try:
        choice = input(f"Topic [{default_topic}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = ""

    if choice:
        args.topic = choice.lower().replace(" ", "_")
    else:
        args.topic = default_topic

    if args.stub and args.topic not in {"recursion", "two_pointers", "binary_search"}:
        print(f"  {_c('Notice:', AMBER)} '{args.topic}' has no canned stub script; falling back to recursion stub.")

    print(f"\nHow familiar are you with {BOLD}{args.topic}{RESET}?")
    print(f"  {BOLD}[1] Beginner{RESET}        - Learning from scratch, need foundational concepts")
    print(f"  {BOLD}[2] Some experience{RESET} - Know basics and indexing, need practice with patterns")
    print(f"  {BOLD}[3] Comfortable{RESET}     - Confident with fundamentals, ready for tricky edge cases\n")

    try:
        fam_choice = input("Select familiarity [1]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        fam_choice = "1"
    if fam_choice in {"1", "beginner", "b"}:
        args.familiarity = "beginner"
    elif fam_choice in {"2", "some experience", "some_experience", "intermediate", "some", "s"}:
        args.familiarity = "some_experience"
    elif fam_choice in {"3", "comfortable", "advanced", "c"}:
        args.familiarity = "comfortable"
    else:
        args.familiarity = getattr(args, "familiarity", None) or "beginner"

    diff_map = {"beginner": "Easy", "some_experience": "Medium", "comfortable": "Hard"}
    print(f"  Starting with: {BOLD}{diff_map.get(args.familiarity, 'Easy')} Concept Check{RESET}\n")


def _post_session_menu(args: argparse.Namespace, lstore: LearnerStore, final: RunState) -> str | None:
    """Display post-session options to the learner in interactive mode.

    Returns:
        "new_topic": Prompt fresh topic and familiarity selection.
        "depth": Continue on same topic with elevated difficulty (if PASSED).
        None: Exit session.
    """
    if not (getattr(args, "interactive", False) and sys.stdin.isatty()):
        return None

    learner_name = getattr(args, "name", None) or getattr(args, "learner", "there")

    print(f"{BOLD}{'-' * 53}{RESET}")
    print("  Session complete! What would you like to do next?")
    print(f"  {BOLD}[1] Start a new topic{RESET}        (choose a different topic)")
    print(f"  {BOLD}[2] Go more in depth{RESET}         (same topic, higher difficulty)")
    print(f"  {BOLD}[3] Exit{RESET}")
    print(f"{BOLD}{'-' * 53}{RESET}\n")

    while True:
        try:
            choice = input("Select [1]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\nGoodbye, {learner_name}! See you next time. 👋\n")
            return None

        if choice in {"", "1", "start a new topic", "new", "new topic", "topic"}:
            args.topic = ""
            args.familiarity = "beginner"
            return "new_topic"
        elif choice in {"2", "go more in depth", "depth", "in depth", "d"}:
            fam_map = {
                "beginner": "some_experience",
                "some_experience": "comfortable",
                "comfortable": "comfortable",
            }
            if final is RunState.COMPLETE:
                args.familiarity = fam_map.get(getattr(args, "familiarity", "beginner"), "comfortable")
            # If session was FAILED, retain the same familiarity level
            diff_map = {"beginner": "Easy", "some_experience": "Medium", "comfortable": "Hard"}
            current_fam = getattr(args, "familiarity", "beginner")
            diff_label = diff_map.get(current_fam, "Medium")
            print(f"\n  Diving deeper into: {BOLD}{args.topic}{RESET}  |  Difficulty: {BOLD}{diff_label} Concept Check{RESET}\n")
            return "depth"
        elif choice in {"3", "exit", "quit", "q", "e"}:
            print(f"\nGoodbye, {learner_name}! See you next time. 👋\n")
            return None
        else:
            print(f"  {_c('Invalid choice. Please select 1, 2, or 3.', AMBER)}")


def _execute_session(
    args: argparse.Namespace,
    session_num: int = 1,
    is_continuation: bool = False,
    skip_intake: bool = False,
) -> int:
    store = Store(args.db)
    lstore = LearnerStore(store)

    if not is_continuation:
        _prompt_identity_if_interactive(args, lstore)
    if not skip_intake:
        _prompt_intake_if_interactive(args)
    if is_continuation and hasattr(args, "answers"):
        args.answers = None

    if args.stub:
        if getattr(args, "case", "loop") == "clean":
            from demo.smoke.stub import CleanStub
            call = CleanStub(topic=args.topic)
        elif getattr(args, "case", "loop") == "hopeless":
            from demo.smoke.stub import AlwaysBlocksStub
            call = AlwaysBlocksStub()
        elif args.topic == "two_pointers":
            from demo.smoke.stub import TwoPointersStub
            call = TwoPointersStub()
        elif args.topic == "binary_search":
            from demo.smoke.stub import BinarySearchStub
            call = BinarySearchStub()
        elif session_num == 2 and args.topic == "recursion":
            from demo.smoke.stub import Session2Stub
            call = Session2Stub()
        elif session_num == 2:
            from demo.smoke.stub import Session2Stub
            call = Session2Stub()
        else:
            from demo.smoke.stub import ThiranStub
            call = ThiranStub(topic=args.topic)
        st = load_settings()
    else:
        from slice.llm import complete as call
        st = load_settings()
        if not st.api_key:
            print(_c("No OPENROUTER_API_KEY in .env.", RED),
                  "\nRun with --stub to test offline without an API key.")
            return 2

    run_id = store.create_run("thiran", meta={"learner_id": args.learner, "topic": args.topic, "session": session_num})

    prior_profile = lstore.get_learner(args.learner)
    learner_name = getattr(args, "name", None) or (prior_profile.name if prior_profile else args.learner.capitalize())

    if session_num == 2 and getattr(args, "interactive", False) and (not prior_profile or prior_profile.session_count == 0):
        print(_c(f"Note: No previous session recorded for '{args.learner}'. Running Session 2 will seed a new profile.", AMBER))

    input_payload = {
        "learner_id": args.learner,
        "name": learner_name,
        "topic": args.topic,
        "familiarity": getattr(args, "familiarity", "beginner"),
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
        conf = prior_profile.confidence_state.get(args.topic, "learning")
        streak = prior_profile.consecutive_correct.get(args.topic, 0)
        print(f"  {_c('memory', MAGENTA)} Loaded profile for {prior_profile.name} (sessions: {prior_profile.session_count}, scores: {prior_profile.knowledge_state}, confidence: [{conf.upper()}], streak: {streak})")

    final = runner.advance(store, run_id, build_flow(call), st)

    for v in store.replay(run_id):
        k = v.kind
        p = v.payload
        if k == "diagnostic_challenge":
            print(f"  {_c('assess   ', CYAN)} Diagnostic: {p.get('challenge_question')}")
        elif k == "learner_answer":
            phase = p.get("phase", "")
            ans = p.get("text", "").replace("\n", " ")
            print(f"  {_c('student  ', DIM)} [{phase}] {ans}")
        elif k == "cognitive_analysis":
            misconceptions = p.get("misconceptions", [])
            m_desc = misconceptions[0]["description"] if misconceptions else "No misconceptions"
            print(f"  {_c('cognitive', MAGENTA)} Diagnosed: {m_desc}")
        elif k == "intervention":
            strat = p.get('teaching_strategy_used', 'analogy')
            diag = p.get('mistake_diagnosis', '')
            concept = p.get('core_dsa_concept', '')
            ex = p.get('simple_example', '')
            prob = p.get('problem_statement', '').replace('\n', ' ')
            if diag:
                print(f"  {_c('diagnose ', RED)} Mistake: {diag}")
            if concept:
                print(f"  {_c('concept  ', CYAN)} Core Concept: {concept}")
            if ex:
                print(f"  {_c('example  ', DIM)} Trace: {ex}")
            print(f"  {_c('practice ', AMBER)} [{strat}] Practice: {prob}")
        elif k == "confidence_update":
            c_val = p.get('confidence', 'learning').upper()
            c_color = GREEN if c_val == "CONFIDENT" else (AMBER if c_val == "REVISITING" else CYAN)
            print(f"  {_c('conf-eng ', c_color)} Confidence updated: [{c_val}] streak={p.get('consecutive_correct', 0)} ({p.get('event')})")
        elif k == "decision":
            if p.get("action") == "skip_cognitive":
                print(f"  {_c('telemetry', DIM)} Cognitive re-call skipped (no new evidence)")
        elif k == "learning_plan":
            seq = ", ".join(p.get("concept_sequence", []))
            print(f"  {_c('planner  ', DIM)} Scaffold: {p.get('scaffold_level')} | Sequence: {seq}")
        elif k == "tutor_exchange":
            print(f"  {_c('tutor    ', GREEN)} Explaining: {p.get('explanation')}")
        elif k == "socratic_challenge":
            print(f"  {_c('socratic ', AMBER)} Challenge: {p.get('problem_statement')}")
        elif k == "verdict":
            tag = _c("PASS ", GREEN) if p.get("status") == "PASS" else _c("BLOCK", AMBER)
            print(f"  {_c('judge    ', DIM)} {tag} (score={p.get('score')}/4) - {p.get('feedback')}")
        elif k == "backward_loop":
            strat = p.get('escalated_strategy', '')
            print(f"  {_c('loop     ', AMBER)} <- Backward loop #{p.get('loop_count')} (Strategy: {strat}): {p.get('reason')}")
        elif k == "learner_update":
            print(f"  {_c('update   ', GREEN)} Profile saved: scores={p.get('concept_scores')}, confidence={p.get('confidence_state')}, resolved={p.get('resolved_misconceptions')}")
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
        conf = updated_profile.confidence_state.get(args.topic, "learning").upper()
        streak = updated_profile.consecutive_correct.get(args.topic, 0)
        c_color = GREEN if conf == "CONFIDENT" else (AMBER if conf == "REVISITING" else CYAN)
        print(f"\n  {BOLD}Updated Learner Memory:{RESET} Sessions={updated_profile.session_count} | Mastery={updated_profile.knowledge_state} | Confidence={_c(f'[{conf}]', c_color)} | Streak={streak}")

    print(f"\n  {_c('replay:', DIM)} python -m scripts.thiran replay {run_id}\n")

    if getattr(args, "interactive", False) and sys.stdin.isatty():
        action = _post_session_menu(args, lstore, final)
        if action == "new_topic":
            return _execute_session(args, session_num=session_num + 1, is_continuation=True, skip_intake=False)
        elif action == "depth":
            return _execute_session(args, session_num=session_num + 1, is_continuation=True, skip_intake=True)
        else:
            return 0

    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    return _execute_session(args, session_num=1)


def cmd_session2(args: argparse.Namespace) -> int:
    if not getattr(args, "interactive", False):
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
            print(f"    Confidence State: {profile.confidence_state} | Streaks: {profile.consecutive_correct}")
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
    r.add_argument(
        "--familiarity",
        choices=["beginner", "some_experience", "comfortable"],
        default="beginner",
        help="Self-reported familiarity: beginner (easy), some_experience (medium), comfortable (hard)",
    )
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
    s2.add_argument(
        "--familiarity",
        choices=["beginner", "some_experience", "comfortable"],
        default="beginner",
        help="Self-reported familiarity: beginner, some_experience, comfortable",
    )
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
