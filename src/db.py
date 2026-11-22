from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _migrate(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            base_config TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            scenario_name TEXT NOT NULL,
            parent_run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
            config_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS llm_events (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_llm_events_created ON llm_events(created_at);
        """
        with self._lock, self.connect() as connection:
            connection.executescript(schema)

    def upsert_user(self, display_name: str, email: str) -> tuple[str, str]:
        email = email.strip().lower()
        display_name = display_name.strip()
        if not display_name or "@" not in email:
            raise ValueError("دخل الاسم وإيميل صحيح.")
        now = utc_now()
        with self._lock, self.connect() as connection:
            row = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                user_id = row["id"]
                connection.execute(
                    "UPDATE users SET display_name = ?, last_seen = ? WHERE id = ?",
                    (display_name, now, user_id),
                )
            else:
                user_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                    (user_id, display_name, email, now, now),
                )
            session_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                (session_id, user_id, now, now),
            )
        return user_id, session_id

    def save_project(self, user_id: str, name: str, activity_type: str, config: dict[str, Any]) -> str:
        if not user_id:
            raise ValueError("سجل الدخول أولاً.")
        project_id = str(uuid.uuid4())
        now = utc_now()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, user_id, name.strip() or "مشروع جديد", activity_type, json.dumps(config, ensure_ascii=False), now, now),
            )
        return project_id

    def save_run(
        self,
        project_id: str,
        scenario_name: str,
        config: dict[str, Any],
        result: dict[str, Any],
        provider: str,
        model: str,
        parent_run_id: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    project_id,
                    scenario_name,
                    parent_run_id,
                    json.dumps(config, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    provider,
                    model,
                    utc_now(),
                ),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utc_now(), project_id))
        return run_id

    def log_llm_event(self, event: dict[str, Any]) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO llm_events
                (id, run_id, provider, model, status, input_tokens, output_tokens,
                 estimated_cost_usd, latency_ms, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), event.get("run_id"), event["provider"], event["model"],
                    event["status"], int(event.get("input_tokens", 0)), int(event.get("output_tokens", 0)),
                    float(event.get("estimated_cost_usd", 0)), int(event.get("latency_ms", 0)),
                    event.get("error"), utc_now(),
                ),
            )

    def set_setting(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, payload, utc_now()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, name, activity_type, created_at, updated_at FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["base_config"] = json.loads(result["base_config"])
        return result

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["config_json"] = json.loads(result["config_json"])
        result["result_json"] = json.loads(result["result_json"])
        return result

    def latest_run(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM runs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1", (project_id,)
            ).fetchone()
        return self.get_run(row["id"]) if row else None

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM runs WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        return [run for row in rows if (run := self.get_run(row["id"])) is not None]

    def admin_stats(self) -> dict[str, Any]:
        active_cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat(timespec="seconds")
        with self.connect() as connection:
            users = connection.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
            active_users = connection.execute("SELECT COUNT(*) n FROM users WHERE last_seen >= ?", (active_cutoff,)).fetchone()["n"]
            projects = connection.execute("SELECT COUNT(*) n FROM projects").fetchone()["n"]
            runs = connection.execute("SELECT COUNT(*) n FROM runs").fetchone()["n"]
            llm = connection.execute(
                """SELECT COUNT(*) calls,
                COALESCE(SUM(input_tokens), 0) input_tokens,
                COALESCE(SUM(output_tokens), 0) output_tokens,
                COALESCE(SUM(estimated_cost_usd), 0) cost,
                COALESCE(SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END), 0) successful
                FROM llm_events"""
            ).fetchone()
            providers = connection.execute(
                "SELECT provider, model, COUNT(*) calls, COALESCE(SUM(estimated_cost_usd), 0) cost FROM llm_events GROUP BY provider, model ORDER BY calls DESC"
            ).fetchall()
            recent_users = connection.execute(
                "SELECT display_name, email, created_at, last_seen FROM users ORDER BY last_seen DESC LIMIT 50"
            ).fetchall()
            recent_runs = connection.execute(
                """SELECT p.name project, p.activity_type, r.scenario_name, r.provider, r.model, r.created_at
                FROM runs r JOIN projects p ON p.id=r.project_id ORDER BY r.created_at DESC LIMIT 50"""
            ).fetchall()
        calls = int(llm["calls"])
        return {
            "users": users,
            "active_users": active_users,
            "projects": projects,
            "runs": runs,
            "llm_calls": calls,
            "success_rate": round((int(llm["successful"]) / calls * 100) if calls else 100, 1),
            "input_tokens": int(llm["input_tokens"]),
            "output_tokens": int(llm["output_tokens"]),
            "cost_usd": round(float(llm["cost"]), 6),
            "providers": [dict(row) for row in providers],
            "recent_users": [dict(row) for row in recent_users],
            "recent_runs": [dict(row) for row in recent_runs],
        }

