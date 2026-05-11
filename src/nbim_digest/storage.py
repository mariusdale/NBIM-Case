from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .actions import ActionCode
from .models import Article, RuleDecision


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def hash_input(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DigestStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    used_cached_outputs INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    published_at TEXT,
                    description TEXT,
                    discovery_path TEXT,
                    discovery_query TEXT,
                    is_demo INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(run_id, url)
                );

                CREATE TABLE IF NOT EXISTS rule_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    article_id INTEGER NOT NULL,
                    decided_at TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    matched_signals_json TEXT NOT NULL,
                    topic_tags_json TEXT NOT NULL,
                    reason TEXT,
                    exclusion_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    article_id INTEGER,
                    created_at TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    output_json TEXT,
                    parsed_output_json TEXT,
                    latency_ms INTEGER,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_estimate_usd REAL,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS digest_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    article_id INTEGER NOT NULL,
                    decided_at TEXT NOT NULL,
                    llm_relevance INTEGER NOT NULL,
                    initial_action TEXT NOT NULL,
                    reviewer_action TEXT NOT NULL,
                    final_action TEXT NOT NULL,
                    included INTEGER NOT NULL,
                    reason_for_action TEXT,
                    summary TEXT,
                    recommended_next_step TEXT,
                    reviewer_skipped INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS human_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    article_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    note TEXT
                );
                """
            )
            self._ensure_column(
                conn,
                table="digest_decisions",
                column="reviewer_skipped",
                definition="INTEGER NOT NULL DEFAULT 0",
            )

    def _ensure_column(self, conn: sqlite3.Connection, *, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_run(self, mode: str, used_cached_outputs: bool) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (created_at, mode, used_cached_outputs) VALUES (?, ?, ?)",
                (utc_now(), mode, int(used_cached_outputs)),
            )
            return int(cursor.lastrowid)

    def save_article(self, run_id: int, article: Article) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO articles
                    (run_id, title, url, source, published_at, description, discovery_path, discovery_query, is_demo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    article.title,
                    article.url,
                    article.source,
                    article.published_at,
                    article.description,
                    article.discovery_path,
                    article.discovery_query,
                    int(article.is_demo),
                ),
            )
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            row = conn.execute(
                "SELECT id FROM articles WHERE run_id = ? AND url = ?", (run_id, article.url)
            ).fetchone()
            return int(row["id"])

    def save_rule_decision(self, run_id: int, article_id: int, decision: RuleDecision) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO rule_decisions
                    (run_id, article_id, decided_at, decision, score, matched_signals_json,
                     topic_tags_json, reason, exclusion_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    article_id,
                    utc_now(),
                    decision.decision,
                    decision.score,
                    json.dumps(decision.matched_signals, ensure_ascii=False),
                    json.dumps(decision.topic_tags, ensure_ascii=False),
                    decision.reason,
                    decision.exclusion_reason,
                ),
            )

    def save_llm_call(
        self,
        *,
        run_id: int,
        article_id: int | None,
        stage: str,
        model: str,
        prompt_version: str,
        prompt_input: Any,
        output: Any = None,
        parsed_output: Any = None,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_estimate_usd: float | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls
                    (run_id, article_id, created_at, stage, model, prompt_version, input_hash,
                     output_json, parsed_output_json, latency_ms, input_tokens, output_tokens,
                     cost_estimate_usd, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    article_id,
                    utc_now(),
                    stage,
                    model,
                    prompt_version,
                    hash_input(prompt_input),
                    json.dumps(output, ensure_ascii=False) if output is not None else None,
                    json.dumps(parsed_output, ensure_ascii=False) if parsed_output is not None else None,
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    cost_estimate_usd,
                    error,
                ),
            )

    def save_digest_decision(
        self,
        *,
        run_id: int,
        article_id: int,
        llm_relevance_score: int,
        initial_action: ActionCode,
        reviewer_action: ActionCode,
        final_action: ActionCode,
        included: bool,
        reason_for_action: str,
        summary: str,
        recommended_next_step: str,
        reviewer_skipped: bool = False,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO digest_decisions
                    (run_id, article_id, decided_at, llm_relevance, initial_action, reviewer_action,
                     final_action, included, reason_for_action, summary, recommended_next_step, reviewer_skipped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    article_id,
                    utc_now(),
                    llm_relevance_score,
                    initial_action.value,
                    reviewer_action.value,
                    final_action.value,
                    int(included),
                    reason_for_action,
                    summary,
                    recommended_next_step,
                    int(reviewer_skipped),
                ),
            )

    def save_feedback(self, run_id: int, article_id: int, feedback: str, note: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO human_feedback (run_id, article_id, created_at, feedback, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, article_id, utc_now(), feedback, note),
            )

    def fetch_audit_rows(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    r.created_at AS time,
                    a.title AS article,
                    a.source AS source,
                    rd.decision AS rule_decision,
                    dd.llm_relevance AS llm_relevance,
                    dd.initial_action AS initial_action,
                    dd.reviewer_action AS reviewer_action,
                    COALESCE(dd.reviewer_skipped, 0) AS reviewer_skipped,
                    dd.final_action AS final_action,
                    dd.included AS included,
                    r.mode AS mode,
                    a.is_demo AS is_demo,
                    a.published_at AS published_at,
                    a.url AS url
                FROM articles a
                JOIN runs r ON r.id = a.run_id
                LEFT JOIN rule_decisions rd ON rd.article_id = a.id AND rd.run_id = a.run_id
                LEFT JOIN digest_decisions dd ON dd.article_id = a.id AND dd.run_id = a.run_id
                ORDER BY r.created_at DESC, a.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_cost_summary(self, run_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(cost_estimate_usd), 0) AS cost,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens
                FROM llm_calls
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            stages = conn.execute(
                "SELECT stage, COUNT(*) AS count FROM llm_calls WHERE run_id = ? GROUP BY stage",
                (run_id,),
            ).fetchall()
        return {
            "cost": float(row["cost"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "stages": {stage["stage"]: int(stage["count"]) for stage in stages},
        }
