# Thiran AI — Session Progress Report

**Date**: 19 September 2026
**Session**: Interactive Development Sprint

---

## Overview

This session focused on upgrading the Thiran AI adaptive learning loop from a
headless state machine into a fully interactive, pedagogically structured terminal
experience. All changes are in production and all 20 automated tests pass.

---

## Changes Delivered

### 1. Interactive Topic Selection
**File**: `scripts/thiran.py`

Added `_prompt_topic_if_interactive()` before `_execute_session()` so that when
running in `--interactive` mode, the system asks the learner **what they want to
study** before the assessment agent fires.

- Accepts any DSA topic (not just the 3 built-in stubs).
- Skipped entirely in non-interactive / CI mode.

---

### 2. Full Output — Removed Truncation
**File**: `scripts/thiran.py`

Every agent output in the replay log was being silently cut off at 60-80
characters. Removed all 9 `[:N]` hard limits across:
- `assess` (challenge_question)
- `student` (answer text)
- `cognitive` (misconception description)
- `diagnose` / `concept` / `example` / `practice` (all intervention fields)
- `judge` (feedback)
- `backward_loop` (reason)

All agent outputs now print in full.

---

### 3. Structured Pedagogical Intake Workflow
**Files**: `scripts/thiran.py`, `demo/smoke/flow.py`, `demo/smoke/prompts/assess.md`

Upgraded the intake from a single topic prompt into a structured 5-stage
pedagogical workflow:

```
"What would you like to learn?"
        |
User types topic (e.g. Arrays)
        |
"How familiar are you?"
        |
[1] Beginner / [2] Some experience / [3] Comfortable
        |
QUICK CONCEPT CHECK (EASY / MEDIUM / HARD)
        |
UNDERSTAND THE STUDENT
        |
PERSONALIZED LEARNING PATH
```

#### Stage 1 & 2 — Intake (`scripts/thiran.py`)
- Renamed helper to `_prompt_intake_if_interactive()`.
- Topic: `"What would you like to learn?"` with freeform input.
- Familiarity: numbered menu `[1] Beginner / [2] Some experience / [3] Comfortable`.
- Familiarity stored in `args.familiarity` and passed into `input_payload`.
- `--familiarity` CLI flag added to `run` and `session2` subcommands.

#### Stage 3 — Calibrated Concept Check (`assess.md` + `flow.py`)
- `build_assess_messages()` now injects `Self-Reported Familiarity` into the
  Assessment Agent prompt.
- Updated `assess.md` prompt with three-tier calibration:
  - **EASY** (beginner): foundational data layout, base case, 0-indexing.
  - **MEDIUM** (some_experience): standard invariants, pointer / boundary conditions.
  - **HARD** (comfortable): composite edge cases, optimal complexity.
- Live terminal label printed as: `=== QUICK CONCEPT CHECK (EASY) ===`

#### Stage 4 — Understand the Student (`flow.py`)
Before asking the learner for their practice fix, the terminal now displays the
Cognitive Agent's full diagnosis in real time:

```
=== UNDERSTAND THE STUDENT ===
  Mental Model: Treats recursion as unbounded iteration.
  Diagnosed Gap: Missing stopping condition causes infinite recursion (base_case)
```

#### Stage 5 — Personalized Learning Path (`flow.py`)
Immediately after the diagnosis, the Intervention Agent's full teaching plan is
shown before the learner is asked to code:

```
=== PERSONALIZED LEARNING PATH ===
  Core Concept: Recursion breaks problems down until a base case terminates calls.
  Execution Trace: countdown(0): 'if n <= 0: return' halts recursion.
  Teaching Strategy: conceptual_analogy

[Targeted Practice] What stops countdown(n) when n reaches 0? Add the base case.
Code snippet:
def countdown(n):
    countdown(n - 1)
```

#### Verdict — Immediate Real-Time Feedback (`flow.py`)
After the learner submits code, the verdict is shown live:

```
=== VERDICT: PASS (Score: 4/4) ===
  Base case correctly halts recursion safely.
```

---

## Test Results

```
tests/test_thiran.py ....................   [100%]
20 passed in 1.93s
```

All existing 20 golden-path tests pass without any modifications to the
test harness.

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/thiran.py` | Intake workflow, familiarity, CLI args, truncation removal |
| `demo/smoke/flow.py` | Familiarity in assess messages, live pedagogical display |
| `demo/smoke/prompts/assess.md` | 3-tier difficulty calibration (EASY / MEDIUM / HARD) |

---

## What Was Not Changed

- `slice/runner.py` - State machine unchanged.
- `demo/smoke/schema.py` - No new schema fields needed.
- `demo/smoke/stub.py` - Canned responses unchanged; fully backward compatible.
- `tests/test_thiran.py` - All existing tests untouched.
