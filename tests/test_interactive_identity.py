import io
import sys
import argparse
from pathlib import Path
from slice.records import RunState
from slice.store import Store
from demo.smoke.store_ext import LearnerStore
from scripts.thiran import _prompt_identity_if_interactive, _post_session_menu, _execute_session

def test_auth_flows(tmp_path):
    db_path = tmp_path / "test_auth.db"
    store = Store(str(db_path))
    lstore = LearnerStore(store)

    # 1. Seed an existing user
    p1 = lstore.get_or_create_learner("test_user", "Test User")
    p1.session_count = 2
    p1.last_topic = "binary_search"
    p1.knowledge_state = {"binary_search": 3}
    p1.confidence_state = {"binary_search": "confident"}
    lstore.save_learner(p1)

    # 2. Test Login flow with mock stdin
    # Choice 1 -> login -> test_user
    stdin_login = io.StringIO("1\ntest_user\n")
    sys.stdin = stdin_login
    sys.stdin.isatty = lambda: True

    args = argparse.Namespace(interactive=True, learner="surya", name="Surya")
    _prompt_identity_if_interactive(args, lstore)

    assert args.learner == "test_user", f"Expected test_user, got {args.learner}"
    assert args.name == "Test User", f"Expected Test User, got {args.name}"

    # 3. Test New User registration flow
    # Choice 2 -> Name "New Learner" -> username "newbie"
    stdin_new = io.StringIO("2\nNew Learner\nnewbie\n")
    sys.stdin = stdin_new
    sys.stdin.isatty = lambda: True

    args2 = argparse.Namespace(interactive=True, learner="surya", name="Surya")
    _prompt_identity_if_interactive(args2, lstore)

    assert args2.learner == "newbie", f"Expected newbie, got {args2.learner}"
    assert args2.name == "New Learner", f"Expected New Learner, got {args2.name}"

    # Verify persisted in SQLite learners table
    saved_profile = lstore.get_learner("newbie")
    assert saved_profile is not None, "Profile was not saved in SQLite learners table"
    assert saved_profile.name == "New Learner"

    # 4. Verify run and events persistence with this new user
    run_id = store.create_run("thiran", meta={"learner_id": args2.learner, "topic": "recursion", "session": 1})
    run_meta = store.meta(run_id)
    assert run_meta["learner_id"] == "newbie"

    # Append events (e.g. learner_answer, diagnosis, verdict)
    store.append(run_id, "learner_answer", {"phase": "ASSESS", "text": "def solve(): return 1"}, produced_by="learner")
    events = store.replay(run_id)
    assert len(events) == 1
    assert events[0].kind == "learner_answer"
    assert events[0].produced_by == "learner"
    assert events[0].payload["text"] == "def solve(): return 1"

    # 5. Test Registering existing username -> prompts if want to login instead -> yes
    stdin_duplicate = io.StringIO("2\nTest User Duplicate\ntest_user\ny\n")
    sys.stdin = stdin_duplicate
    sys.stdin.isatty = lambda: True

    args3 = argparse.Namespace(interactive=True, learner="surya", name="Surya")
    _prompt_identity_if_interactive(args3, lstore)
    assert args3.learner == "test_user"
    assert args3.name == "Test User"


def test_post_session_menu_options(tmp_path):
    db_path = tmp_path / "test_menu.db"
    store = Store(str(db_path))
    lstore = LearnerStore(store)

    # 1. Option 1: Start a new topic
    sys.stdin = io.StringIO("1\n")
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="recursion", familiarity="comfortable")
    action = _post_session_menu(args, lstore, final=RunState.COMPLETE)
    assert action == "new_topic"
    assert args.topic == ""
    assert args.familiarity == "beginner"

    # 2. Option 2: Go more in depth on PASS (COMPLETE) -> bumps familiarity
    # beginner -> some_experience
    sys.stdin = io.StringIO("2\n")
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="arrays", familiarity="beginner")
    action = _post_session_menu(args, lstore, final=RunState.COMPLETE)
    assert action == "depth"
    assert args.topic == "arrays"
    assert args.familiarity == "some_experience"

    # some_experience -> comfortable
    sys.stdin = io.StringIO("2\n")
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="arrays", familiarity="some_experience")
    action = _post_session_menu(args, lstore, final=RunState.COMPLETE)
    assert action == "depth"
    assert args.familiarity == "comfortable"

    # comfortable -> stays comfortable
    sys.stdin = io.StringIO("2\n")
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="arrays", familiarity="comfortable")
    action = _post_session_menu(args, lstore, final=RunState.COMPLETE)
    assert action == "depth"
    assert args.familiarity == "comfortable"

    # 3. Option 2: Go more in depth on FAIL -> retains same familiarity
    sys.stdin = io.StringIO("2\n")
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="trees", familiarity="beginner")
    action = _post_session_menu(args, lstore, final=RunState.FAILED)
    assert action == "depth"
    assert args.topic == "trees"
    assert args.familiarity == "beginner"  # Not bumped!

    # 4. Option 3: Exit
    sys.stdin = io.StringIO("3\n")
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="trees", familiarity="beginner")
    action = _post_session_menu(args, lstore, final=RunState.COMPLETE)
    assert action is None

    # 5. EOF / Ctrl-C: Graceful Exit
    sys.stdin = io.StringIO("")  # immediate EOF
    sys.stdin.isatty = lambda: True
    args = argparse.Namespace(interactive=True, learner="test_user", name="Test User", topic="trees", familiarity="beginner")
    action = _post_session_menu(args, lstore, final=RunState.COMPLETE)
    assert action is None


def test_interactive_continuation_end_to_end(tmp_path):
    db_path = tmp_path / "test_chain.db"
    store = Store(str(db_path))
    lstore = LearnerStore(store)

    # Simulated user inputs:
    # 1. Identity: Register new user (2 -> Arun -> arun)
    # 2. Intake: Topic Enter (recursion) -> Familiarity 1 (beginner)
    # 3. Session 1 Diagnostic Answer: "countdown(n - 1)\n\n"
    # 4. Session 1 Socratic Answer: "if n <= 0: return\n\n"
    # 5. Menu after Session 1: "2\n" (Go more in depth)
    # 6. Session 2 Diagnostic Answer: "def fact(n): return n * fact(n-1)\n\n"
    # 7. Session 2 Socratic Answer: "if n <= 1: return 1\n\n"
    # 8. Menu after Session 2: "3\n" (Exit)
    simulated_input = (
        "2\nArun\narun\n"
        "\n1\n"
        "countdown(n - 1)\n\n"
        "if n <= 0: return\n\n"
        "2\n"
        "def fact(n): return n * fact(n-1)\n\n"
        "if n <= 1: return 1\n\n"
        "3\n"
    )

    sys.stdin = io.StringIO(simulated_input)
    sys.stdin.isatty = lambda: True

    args = argparse.Namespace(
        db=str(db_path),
        stub=True,
        interactive=True,
        learner="default",
        name=None,
        topic="",
        familiarity="",
        case="clean",
    )

    exit_code = _execute_session(args, session_num=1)
    assert exit_code == 0

    # Verify persistent state:
    profile = lstore.get_learner("arun")
    assert profile is not None
    assert profile.name == "Arun"
    assert profile.session_count == 2
    assert profile.consecutive_correct["recursion"] == 2
    assert profile.confidence_state["recursion"] == "confident"
    assert args.familiarity == "some_experience"


def test_interactive_new_topic_continuation(tmp_path):
    db_path = tmp_path / "test_new_topic.db"
    store = Store(str(db_path))
    lstore = LearnerStore(store)

    # Simulated user inputs:
    # 1. Identity: Register new user (2 -> Divya -> divya)
    # 2. Intake: Topic recursion -> Familiarity 1 (beginner)
    # 3. Session 1 Diagnostic Answer: "countdown(n - 1)\n\n"
    # 4. Session 1 Socratic Answer: "if n <= 0: return\n\n"
    # 5. Menu after Session 1: "1\n" (Start a new topic)
    # 6. Intake for Session 2: Topic "two_pointers\n" -> Familiarity "1\n"
    # 7. Session 2 Diagnostic Answer: "left, right = 0, len(nums) - 1\n\n"
    # 8. Session 2 Socratic Answer: "while left < right:\n\n"
    # 9. Menu after Session 2: "3\n" (Exit)
    simulated_input = (
        "2\nDivya\ndivya\n"
        "recursion\n1\n"
        "countdown(n - 1)\n\n"
        "if n <= 0: return\n\n"
        "1\n"
        "two_pointers\n1\n"
        "left, right = 0, len(nums) - 1\n\n"
        "while left < right:\n\n"
        "3\n"
    )

    sys.stdin = io.StringIO(simulated_input)
    sys.stdin.isatty = lambda: True

    args = argparse.Namespace(
        db=str(db_path),
        stub=True,
        interactive=True,
        learner="default",
        name=None,
        topic="",
        familiarity="",
        case="clean",
    )

    exit_code = _execute_session(args, session_num=1)
    assert exit_code == 0

    profile = lstore.get_learner("divya")
    assert profile is not None
    assert profile.name == "Divya"
    assert profile.session_count == 2
    assert "recursion" in profile.knowledge_state
    assert "two_pointers" in profile.knowledge_state
    assert profile.last_topic == "two_pointers"



