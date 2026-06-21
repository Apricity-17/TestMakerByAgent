"""Long-term memory via SQLite for cross-session persistence."""

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional


class LongTermMemory:
    """Persists user preferences, project patterns, and session history."""

    def __init__(self, db_path: str = "~/.testmaker/memory.db"):
        expanded = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        self._conn = sqlite3.connect(expanded)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS project_patterns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path    TEXT NOT NULL,
                module_name     TEXT NOT NULL,
                test_dir        TEXT,
                mock_library    TEXT,
                coverage_target REAL,
                created_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(project_path, module_name)
            );
            CREATE TABLE IF NOT EXISTS session_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                target_path         TEXT NOT NULL,
                total_tests         INTEGER,
                final_line_rate     REAL,
                final_branch_rate   REAL,
                iterations          INTEGER,
                termination_reason  TEXT,
                created_at          TEXT DEFAULT (datetime('now'))
            );
            """
        )
        self._conn.commit()

    # ── Preferences ──────────────────────────────────────────────────────

    def get_preference(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_preference(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO preferences (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        self._conn.commit()

    def get_all_preferences(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM preferences").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── Project Patterns ─────────────────────────────────────────────────

    def get_project_pattern(
        self, project_path: str, module_name: str
    ) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM project_patterns WHERE project_path = ? AND module_name = ?",
            (project_path, module_name),
        ).fetchone()
        return dict(row) if row else None

    def upsert_project_pattern(
        self, project_path: str, module_name: str, **kwargs: Any
    ) -> None:
        existing = self.get_project_pattern(project_path, module_name)
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            self._conn.execute(
                f"UPDATE project_patterns SET {sets} WHERE id = ?",
                list(kwargs.values()) + [existing["id"]],
            )
        else:
            cols = ["project_path", "module_name"] + list(kwargs.keys())
            placeholders = ", ".join("?" * len(cols))
            self._conn.execute(
                f"INSERT INTO project_patterns ({', '.join(cols)}) VALUES ({placeholders})",
                [project_path, module_name] + list(kwargs.values()),
            )
        self._conn.commit()

    # ── Session History ──────────────────────────────────────────────────

    def record_session(self, **kwargs: Any) -> None:
        if not kwargs:
            return
        cols = list(kwargs.keys())
        placeholders = ", ".join("?" * len(cols))
        self._conn.execute(
            f"INSERT INTO session_history ({', '.join(cols)}) VALUES ({placeholders})",
            list(kwargs.values()),
        )
        self._conn.commit()

    def get_recent_sessions(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM session_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
