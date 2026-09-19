"""Persistent learner state storage extension for Thiran AI.

Stores learner profiles across sessions in the same SQLite database used by
slice.store.Store, without modifying any slice/ files.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from slice.store import Store
from .schema import LearnerProfile

LEARNERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    learner_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    domain       TEXT NOT NULL,
    profile_json TEXT NOT NULL DEFAULT '{}',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
"""


class LearnerStore:
    """Manages persistent LearnerProfile records in SQLite."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.db = store.db
        self.init_schema()

    def init_schema(self) -> None:
        self.db.executescript(LEARNERS_SCHEMA)

    def get_learner(self, learner_id: str) -> LearnerProfile | None:
        row = self.db.execute(
            "SELECT profile_json FROM learners WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        if not row:
            return None
        return LearnerProfile.model_validate_json(row["profile_json"])

    def get_or_create_learner(
        self, learner_id: str, name: str, domain: str = "computer_science"
    ) -> LearnerProfile:
        existing = self.get_learner(learner_id)
        if existing:
            return existing
        profile = LearnerProfile(learner_id=learner_id, name=name, domain=domain)
        self.save_learner(profile)
        return profile

    def save_learner(self, profile: LearnerProfile) -> None:
        now = time.time()
        raw = profile.model_dump_json()
        row = self.db.execute(
            "SELECT created_at FROM learners WHERE learner_id = ?",
            (profile.learner_id,),
        ).fetchone()
        if row:
            self.db.execute(
                "UPDATE learners SET name = ?, domain = ?, profile_json = ?, updated_at = ? WHERE learner_id = ?",
                (profile.name, profile.domain, raw, now, profile.learner_id),
            )
        else:
            self.db.execute(
                "INSERT INTO learners (learner_id, name, domain, profile_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (profile.learner_id, profile.name, profile.domain, raw, now, now),
            )

    def get_relevant_evidence(self, learner_id: str, topic: str) -> dict[str, Any]:
        """Extracts strictly topic-relevant evidence: scores, unresolved misconceptions, and failed interventions."""
        profile = self.get_learner(learner_id)
        if not profile:
            return {"score": None, "unresolved": [], "past_interventions": [], "session_count": 0}

        score = profile.knowledge_state.get(topic)
        unresolved = [m.concept for m in profile.misconceptions if not m.resolved]
        past_int = []
        for m in profile.misconceptions:
            past_int.extend(m.past_interventions)

        return {
            "score": score,
            "unresolved": unresolved,
            "past_interventions": list(dict.fromkeys(past_int)),  # preserve order & deduplicate
            "session_count": profile.session_count,
        }

    def list_learners(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT learner_id, name, domain, created_at, updated_at FROM learners ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
