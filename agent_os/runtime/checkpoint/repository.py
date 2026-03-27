from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from agent_os.runtime.state.models import RunState


class CheckpointRepository:
    """Persist full run state to SQLite and JSON snapshots."""

    def __init__(self, db_path: Path, snapshot_dir: Path) -> None:
        self._db_path = db_path
        self._snapshot_dir = snapshot_dir
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_run_id ON checkpoints(run_id)"
            )
            conn.commit()

    def save(self, state: RunState) -> str:
        checkpoint_id = f"ckpt_{uuid4().hex[:12]}"
        snapshot_path = self._snapshot_dir / f"{checkpoint_id}.json"
        state_json = state.model_dump_json()
        snapshot_path.write_text(state_json, encoding="utf-8")

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO checkpoints(checkpoint_id, run_id, created_at, state_json, snapshot_path)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    state.run_id,
                    state.updated_at.isoformat(),
                    state_json,
                    str(snapshot_path),
                ),
            )
            conn.commit()

        return checkpoint_id

    def load_latest(self, run_id: str) -> RunState | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT state_json
                FROM checkpoints
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None
        return RunState.model_validate(json.loads(row[0]))
