"""SQLite storage for games, events, and annotations.

One file per deployment. Tables:
    games         — one row per processed replay
    events        — critical events extracted from games
    annotations   — human-submitted annotations, N per event
    event_blob    — pointer to on-disk JSON blob with full belief/game state
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

    from hitl.schema import Annotation, Event, Game

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS games (
    replay_id      TEXT PRIMARY KEY,
    our_side       TEXT NOT NULL,
    opponent       TEXT NOT NULL,
    map_name       TEXT NOT NULL,
    winner         TEXT,
    end_turn       INTEGER NOT NULL,
    outcome_auto   TEXT NOT NULL,
    outcome_subj   TEXT NOT NULL,
    imported_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id       TEXT PRIMARY KEY,
    replay_id      TEXT NOT NULL REFERENCES games(replay_id),
    turn           INTEGER NOT NULL,
    unit_id        INTEGER NOT NULL,
    unit_type      TEXT NOT NULL,
    team           TEXT NOT NULL,
    trigger        TEXT NOT NULL,
    bot_action     TEXT NOT NULL,
    blob_path      TEXT NOT NULL,
    png_path       TEXT
);
CREATE INDEX IF NOT EXISTS events_by_replay ON events(replay_id);
CREATE INDEX IF NOT EXISTS events_by_trigger ON events(trigger);

CREATE TABLE IF NOT EXISTS annotations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL REFERENCES events(event_id),
    session_id      TEXT NOT NULL,
    direction       TEXT NOT NULL,
    action          TEXT NOT NULL,
    build_type      TEXT,
    reasons         TEXT NOT NULL,
    free_text       TEXT NOT NULL,
    bot_was_right   INTEGER,
    outcome_context TEXT NOT NULL,
    timestamp_ms    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ann_by_event ON annotations(event_id);
CREATE INDEX IF NOT EXISTS ann_by_session ON annotations(session_id);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def upsert_game(self, game: Game) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT OR REPLACE INTO games
                   (replay_id, our_side, opponent, map_name, winner, end_turn,
                    outcome_auto, outcome_subj, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    game.replay_id,
                    game.our_side,
                    game.opponent,
                    game.map_name,
                    game.winner,
                    game.end_turn,
                    json.dumps([t.value for t in game.outcome_auto]),
                    json.dumps([t.value for t in game.outcome_subjective]),
                    int(time.time()),
                ),
            )

    def insert_event(
        self, event: Event, blob_path: Path, png_path: Path | None
    ) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT OR REPLACE INTO events
                   (event_id, replay_id, turn, unit_id, unit_type, team, trigger,
                    bot_action, blob_path, png_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.replay_id,
                    event.turn,
                    event.unit_id,
                    event.unit_type,
                    event.team,
                    event.trigger.value,
                    event.bot_action,
                    str(blob_path),
                    str(png_path) if png_path else None,
                ),
            )

    def insert_annotation(self, ann: Annotation) -> int:
        with self.tx() as c:
            cur = c.execute(
                """INSERT INTO annotations
                   (event_id, session_id, direction, action, build_type,
                    reasons, free_text, bot_was_right, outcome_context, timestamp_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ann.event_id,
                    ann.session_id,
                    ann.direction.value,
                    ann.action.value,
                    ann.build_type.value if ann.build_type else None,
                    json.dumps([r.value for r in ann.reasons]),
                    ann.free_text,
                    None if ann.bot_was_right is None else int(ann.bot_was_right),
                    json.dumps([o.value for o in ann.outcome_context]),
                    ann.timestamp_ms,
                ),
            )
            return int(cur.lastrowid or 0)

    def pick_next_event(self, session_id: str) -> sqlite3.Row | None:
        """Return an event the given session hasn't annotated yet, prioritising
        under-annotated events across all sessions."""
        return self._conn.execute(
            """SELECT e.*, COUNT(a.id) AS n_ann
               FROM events e
               LEFT JOIN annotations a ON a.event_id = e.event_id
               WHERE e.event_id NOT IN (
                   SELECT event_id FROM annotations WHERE session_id = ?
               )
               GROUP BY e.event_id
               ORDER BY n_ann ASC, RANDOM()
               LIMIT 1""",
            (session_id,),
        ).fetchone()

    def event_counts(self) -> tuple[int, int]:
        """(total events, total annotations)"""
        n_events = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        n_ann = self._conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
        return int(n_events), int(n_ann)

    def list_events(self, limit: int = 50) -> Iterable[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM events ORDER BY replay_id, turn LIMIT ?", (limit,)
        ).fetchall()

    def get_event(self, event_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()

    def get_event_png(self, event_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT png_path FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return row["png_path"]

    def set_bot_was_right(self, annotation_id: int, *, right: bool) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE annotations SET bot_was_right = ? WHERE id = ?",
                (int(right), annotation_id),
            )
