# demo/smoke/THIRAN-SPEC.md — Thiran AI Adaptive Learning System

**An adaptive multi-agent learning loop built in place on the Slice Kit architecture.**

---

## 1. Setting & Problem

Standard AI tutors act as passive chat bots or linear text generators. When a learner exhibits a deep-seated mental model flaw (misconception), simple chat systems either regurgitate the full solution or blindly repeat the same explanation without diagnosing *why* the student failed.

**Thiran AI** provides an adaptive pedagogical state machine:
`ASSESS -> ANALYZE -> PERSONALIZE -> LEARN -> PRACTICE -> REASSESS -> UPDATE -> ADAPT`

It is a true agent because:
1. **Work goes backwards**: When a misconception persists, the Reassessment Judge blocks the submission and loops back to the Cognitive and Tutor agents to adapt the instruction.
2. **Context survives the process**: The student's knowledge state and misconception histories persist across separate sessions in a local SQLite database.
3. **Deterministic code controls sequencing**: Transition rules, safety fences (`MAX_LOOPS = 3`), and database mutations are pure Python; LLMs provide reasoning, diagnostics, and instruction.

---

## 2. Specialized Roles & Handlers

Thiran consolidates the pedagogy into 5 LLM agents and 2 deterministic handlers:

| # | Role / Agent | Phase Name | Function | Model Call? |
|---|---|---|---|:---:|
| 1 | **Assessment Agent** | `ASSESS` | Analyzes prior knowledge and poses an opening diagnostic challenge. | Yes |
| 2 | **Cognitive Agent** | `COGNITIVE` | Analyzes learner code to isolate mental model flaws and misconceptions. | Yes |
| 3 | **Planner Agent** | `PLAN` | Determines scaffolding level (`low`, `medium`, `high`) and concept sequence. | Yes |
| 4 | **Tutor Agent** | `TEACH` | Delivers concise concept instruction (<= 2 sentences) and a concrete analogy. | Yes |
| 5 | **Socratic Debugger** | `SOCRATIC` | Challenges learner with a 1-sentence debugging problem without giving away the fix. | Yes |
| — | **Reassessment Judge** | `GATING` | Evaluates learner submission (`PASS` vs `BLOCK`) and triggers backward loops. | Yes |
| — | **State Updater** | `UPDATE` | Deterministic code updating `LearnerProfile` in the SQLite `learners` table. | No (Pure Code) |

---

## 3. The State Machine & Backward Loop

Mapped strictly to `slice/records.py` `RunState` enums without touching `slice/`:
- `DRAFTING`: Active execution of agent steps (`ASSESS`, `COGNITIVE`, `PLAN`, `TEACH`, `SOCRATIC`).
- `PROBING`: Pauses execution to receive student input (diagnostic answer or Socratic debugging code).
- `GATING`: Reassessment checkpoint evaluating student mastery.
- `COMPLETE`: Profile saved; session finished.
- `FAILED`: Max backward loops (3) exhausted.

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                   DRAFTING: handle_drafting             │
                    │                                                         │
                    │  ASSESS ──> PROBING (wait diagnostic answer)            │
                    │               │                                         │
                    │               ▼                                         │
                    │  COGNITIVE ──> PLAN ──> TEACH ──> SOCRATIC ──> PROBING  │
                    └───────────────────────────────────────────────────┬─────┘
                                                                        │ (wait Socratic answer)
                                                                        ▼
                                                                 GATING: handle_gating
                                                                    │            │
                                                     [PASS]         │            │ [FAIL & loop < 3]
                                                       ┌────────────┘            │
                                                       ▼                         ▼
                                                 DRAFTING: UPDATE        <- BACKWARD LOOP (COGNITIVE)
                                                       │
                                                       ▼
                                                    COMPLETE
```

---

## 4. Persistent Learner State (Cross-Session Memory)

Stored in the `learners` table in `thiran.db`:
```sql
CREATE TABLE IF NOT EXISTS learners (
    learner_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    domain       TEXT NOT NULL,
    profile_json TEXT NOT NULL DEFAULT '{}',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
```

### Profile JSON Structure
- `knowledge_state`: Dictionary mapping concepts to mastery scores (`0` to `4`).
- `misconceptions`: List of diagnosed misconceptions with verbatim quotes, attempt counts, and `resolved` boolean flags.
- `session_count`: Integer tracking total learning sessions.
- `last_topic`: Most recent concept studied.

When Surya returns for Session 2, Thiran loads this memory and automatically escalates challenge difficulty (e.g. from single-branch countdown to recursive return value accumulation in `factorial(n)`).

---

## 5. Token Optimization & Context Telemetry

1. **Context Pruning**: Never resends conversational replays or large JSON transcripts. Injects only atomic deltas (raw student code, 1-line failure feedback).
2. **Terse Schemas**: Strict length caps (Tutor explanation <= 2 sentences; analogy <= 1 sentence; Socratic challenge = 1 sentence).
3. **Per-Agent Accounting**: Telemetry tracks `tokens:{step}` and `calls:{step}` in SQLite counters.
4. **Token Footprint**:
   - Clean 1-pass session: **~303 tokens** total across all 6 model calls.
   - Backward loop session: **~560 tokens** total across 11 model calls.

---

## 6. CLI Usage

```powershell
# 1. Offline stub testing (zero tokens, no API key)
python -m scripts.thiran run --stub --learner surya --topic recursion

# 2. Live LLM execution (uses OPENROUTER_API_KEY from .env)
python -m scripts.thiran run --learner surya --topic recursion

# 3. Interactive learning (type code live into terminal)
python -m scripts.thiran run --interactive

# 4. Second session with cross-session progression
python -m scripts.thiran session2 --stub --learner surya --topic recursion

# 5. Inspect learner memory
python -m scripts.thiran learners

# 6. Replay audit trail
python -m scripts.thiran replay <run_id>
```
