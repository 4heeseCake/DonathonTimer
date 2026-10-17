from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class Profile:
    id: int
    name: str
    da_user_id: Optional[str]
    da_code: Optional[str]
    avatar_url: Optional[str]
    rate_amount: float
    rate_seconds: int
    running: bool
    end_epoch: Optional[float]
    paused_remaining: float
    overlay_theme: str
    overlay_title: str
    overlay_show_rate: bool
    twitch_user_id: Optional[str]
    twitch_login: Optional[str]
    twitch_display_name: Optional[str]


@dataclass(slots=True)
class Session:
    id: int
    profile_id: int
    name: str
    started_at: float
    ended_at: Optional[float]
    starting_seconds: int
    paused_at: Optional[float]
    paused_total: float


@dataclass(slots=True)
class Event:
    id: int
    profile_id: int
    session_id: Optional[int]
    kind: str
    title: str
    amount: Optional[float]
    currency: Optional[str]
    credited_amount: Optional[float]
    seconds_delta: int
    external_id: Optional[str]
    created_at: float
    undone: bool
    undo_of_event_id: Optional[int]


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init_db(self) -> None:
        with self._lock, self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    da_user_id TEXT UNIQUE,
                    da_code TEXT,
                    avatar_url TEXT,
                    rate_amount REAL NOT NULL DEFAULT 100,
                    rate_seconds INTEGER NOT NULL DEFAULT 300,
                    running INTEGER NOT NULL DEFAULT 0,
                    end_epoch REAL,
                    paused_remaining REAL NOT NULL DEFAULT 0,
                    overlay_theme TEXT NOT NULL DEFAULT 'classic',
                    overlay_title TEXT NOT NULL DEFAULT '',
                    overlay_show_rate INTEGER NOT NULL DEFAULT 1,
                    twitch_user_id TEXT,
                    twitch_login TEXT,
                    twitch_display_name TEXT,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    starting_seconds INTEGER NOT NULL DEFAULT 0,
                    paused_at REAL,
                    paused_total REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    session_id INTEGER,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    amount REAL,
                    currency TEXT,
                    credited_amount REAL,
                    seconds_delta INTEGER NOT NULL DEFAULT 0,
                    external_id TEXT,
                    created_at REAL NOT NULL,
                    undone INTEGER NOT NULL DEFAULT 0,
                    undo_of_event_id INTEGER,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_event_external
                ON events(profile_id, external_id)
                WHERE external_id IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_events_profile_created
                ON events(profile_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sessions_profile_started
                ON sessions(profile_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS processed_donations (
                    profile_id INTEGER NOT NULL,
                    external_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(profile_id, external_id),
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS twitch_chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    session_id INTEGER,
                    external_id TEXT,
                    user_id TEXT,
                    user_name TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_twitch_chat_external
                ON twitch_chat_messages(profile_id, external_id) WHERE external_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_twitch_chat_profile_created
                ON twitch_chat_messages(profile_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS twitch_viewer_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    session_id INTEGER,
                    viewer_count INTEGER NOT NULL,
                    live INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_twitch_viewers_profile_created
                ON twitch_viewer_samples(profile_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS speech_recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    session_id INTEGER,
                    path TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    status TEXT NOT NULL DEFAULT 'recording',
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_speech_recordings_session
                ON speech_recordings(profile_id, session_id, started_at);

                CREATE TABLE IF NOT EXISTS speech_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    session_id INTEGER,
                    recording_id INTEGER,
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL,
                    FOREIGN KEY(recording_id) REFERENCES speech_recordings(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_speech_segments_profile_started
                ON speech_segments(profile_id, started_at);
                """
            )

            # Lightweight migrations. Updating program files must never destroy an
            # existing timer, profiles, processed donation ids or appearance settings.
            profile_columns = {row["name"] for row in con.execute("PRAGMA table_info(profiles)").fetchall()}
            if "overlay_theme" not in profile_columns:
                con.execute("ALTER TABLE profiles ADD COLUMN overlay_theme TEXT NOT NULL DEFAULT 'classic'")
            if "overlay_title" not in profile_columns:
                con.execute("ALTER TABLE profiles ADD COLUMN overlay_title TEXT NOT NULL DEFAULT ''")
            if "overlay_show_rate" not in profile_columns:
                con.execute("ALTER TABLE profiles ADD COLUMN overlay_show_rate INTEGER NOT NULL DEFAULT 1")
            if "twitch_user_id" not in profile_columns:
                con.execute("ALTER TABLE profiles ADD COLUMN twitch_user_id TEXT")
            if "twitch_login" not in profile_columns:
                con.execute("ALTER TABLE profiles ADD COLUMN twitch_login TEXT")
            if "twitch_display_name" not in profile_columns:
                con.execute("ALTER TABLE profiles ADD COLUMN twitch_display_name TEXT")

            session_columns = {row["name"] for row in con.execute("PRAGMA table_info(sessions)").fetchall()}
            if "paused_at" not in session_columns:
                con.execute("ALTER TABLE sessions ADD COLUMN paused_at REAL")
            if "paused_total" not in session_columns:
                con.execute("ALTER TABLE sessions ADD COLUMN paused_total REAL NOT NULL DEFAULT 0")

            event_columns = {row["name"] for row in con.execute("PRAGMA table_info(events)").fetchall()}
            if "session_id" not in event_columns:
                con.execute("ALTER TABLE events ADD COLUMN session_id INTEGER")
            if "undone" not in event_columns:
                con.execute("ALTER TABLE events ADD COLUMN undone INTEGER NOT NULL DEFAULT 0")
            if "undo_of_event_id" not in event_columns:
                con.execute("ALTER TABLE events ADD COLUMN undo_of_event_id INTEGER")
            if "credited_amount" not in event_columns:
                con.execute("ALTER TABLE events ADD COLUMN credited_amount REAL")

            row = con.execute("SELECT id FROM profiles ORDER BY id LIMIT 1").fetchone()
            if row is None:
                cur = con.execute(
                    """
                    INSERT INTO profiles
                    (name, rate_amount, rate_seconds, running, paused_remaining, created_at)
                    VALUES (?, 100, 300, 0, 0, ?)
                    """,
                    ("Локальный профиль", time.time()),
                )
                profile_id = cur.lastrowid
                con.execute(
                    "INSERT OR REPLACE INTO app_settings(key, value) VALUES('active_profile_id', ?)",
                    (str(profile_id),),
                )

    @staticmethod
    def _to_profile(row: sqlite3.Row) -> Profile:
        return Profile(
            id=row["id"],
            name=row["name"],
            da_user_id=row["da_user_id"],
            da_code=row["da_code"],
            avatar_url=row["avatar_url"],
            rate_amount=float(row["rate_amount"]),
            rate_seconds=int(row["rate_seconds"]),
            running=bool(row["running"]),
            end_epoch=row["end_epoch"],
            paused_remaining=float(row["paused_remaining"]),
            overlay_theme=str(row["overlay_theme"] or "classic"),
            overlay_title=str(row["overlay_title"] or ""),
            overlay_show_rate=bool(row["overlay_show_rate"]),
            twitch_user_id=str(row["twitch_user_id"]) if "twitch_user_id" in row.keys() and row["twitch_user_id"] is not None else None,
            twitch_login=str(row["twitch_login"]) if "twitch_login" in row.keys() and row["twitch_login"] is not None else None,
            twitch_display_name=str(row["twitch_display_name"]) if "twitch_display_name" in row.keys() and row["twitch_display_name"] is not None else None,
        )

    @staticmethod
    def _to_session(row: sqlite3.Row) -> Session:
        return Session(
            id=int(row["id"]),
            profile_id=int(row["profile_id"]),
            name=str(row["name"]),
            started_at=float(row["started_at"]),
            ended_at=float(row["ended_at"]) if row["ended_at"] is not None else None,
            starting_seconds=int(row["starting_seconds"] or 0),
            paused_at=float(row["paused_at"]) if "paused_at" in row.keys() and row["paused_at"] is not None else None,
            paused_total=float(row["paused_total"] or 0) if "paused_total" in row.keys() else 0.0,
        )

    @staticmethod
    def _to_event(row: sqlite3.Row) -> Event:
        keys = set(row.keys())
        return Event(
            id=int(row["id"]),
            profile_id=int(row["profile_id"]),
            session_id=int(row["session_id"]) if "session_id" in keys and row["session_id"] is not None else None,
            kind=str(row["kind"]),
            title=str(row["title"]),
            amount=float(row["amount"]) if row["amount"] is not None else None,
            currency=str(row["currency"]) if row["currency"] is not None else None,
            credited_amount=float(row["credited_amount"]) if "credited_amount" in keys and row["credited_amount"] is not None else None,
            seconds_delta=int(row["seconds_delta"] or 0),
            external_id=str(row["external_id"]) if row["external_id"] is not None else None,
            created_at=float(row["created_at"]),
            undone=bool(row["undone"]) if "undone" in keys else False,
            undo_of_event_id=int(row["undo_of_event_id"]) if "undo_of_event_id" in keys and row["undo_of_event_id"] is not None else None,
        )

    def list_profiles(self) -> list[Profile]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT * FROM profiles ORDER BY id").fetchall()
            return [self._to_profile(r) for r in rows]

    def get_profile(self, profile_id: int) -> Profile:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                raise KeyError(profile_id)
            return self._to_profile(row)

    def active_profile_id(self) -> int:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT value FROM app_settings WHERE key='active_profile_id'").fetchone()
            if row:
                return int(row["value"])
            row = con.execute("SELECT id FROM profiles ORDER BY id LIMIT 1").fetchone()
            return int(row["id"])

    def set_active_profile(self, profile_id: int) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO app_settings(key, value) VALUES('active_profile_id', ?)",
                (str(profile_id),),
            )

    def get_setting(self, key: str) -> str | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO app_settings(key, value) VALUES(?, ?)",
                (key, value),
            )

    def update_timer(
        self,
        profile_id: int,
        *,
        running: bool,
        end_epoch: Optional[float],
        paused_remaining: float,
    ) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                """
                UPDATE profiles
                SET running=?, end_epoch=?, paused_remaining=?
                WHERE id=?
                """,
                (int(running), end_epoch, max(0.0, paused_remaining), profile_id),
            )

    def update_rate(self, profile_id: int, amount: float, seconds: int) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "UPDATE profiles SET rate_amount=?, rate_seconds=? WHERE id=?",
                (amount, seconds, profile_id),
            )

    def update_overlay_settings(
        self,
        profile_id: int,
        *,
        theme: str,
        title: str,
        show_rate: bool,
    ) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                """
                UPDATE profiles
                SET overlay_theme=?, overlay_title=?, overlay_show_rate=?
                WHERE id=?
                """,
                (theme, title, int(show_rate), profile_id),
            )

    # ---------- stream sessions ----------

    def active_session(self, profile_id: int) -> Session | None:
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE profile_id=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
            return self._to_session(row) if row else None

    def start_session(self, profile_id: int, name: str, starting_seconds: int) -> Session:
        now = time.time()
        name = (name or "Донатофон").strip() or "Донатофон"
        with self._lock, self._connect() as con:
            # A profile has at most one active session. Starting a new one safely
            # closes the old session but does not touch the timer itself.
            con.execute(
                "UPDATE sessions SET ended_at=? WHERE profile_id=? AND ended_at IS NULL",
                (now, profile_id),
            )
            cur = con.execute(
                "INSERT INTO sessions(profile_id, name, started_at, starting_seconds, paused_at, paused_total) VALUES(?, ?, ?, ?, NULL, 0)",
                (profile_id, name, now, max(0, int(starting_seconds))),
            )
            row = con.execute("SELECT * FROM sessions WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._to_session(row)

    def end_session(self, profile_id: int) -> Session | None:
        now = time.time()
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE profile_id=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
            if not row:
                return None
            paused_total = float(row["paused_total"] or 0)
            if row["paused_at"] is not None:
                paused_total += max(0.0, now - float(row["paused_at"]))
            con.execute("UPDATE sessions SET ended_at=?, paused_at=NULL, paused_total=? WHERE id=?", (now, paused_total, row["id"]))
            updated = con.execute("SELECT * FROM sessions WHERE id=?", (row["id"],)).fetchone()
            return self._to_session(updated)

    def session_stats(self, session_id: int) -> dict:
        with self._lock, self._connect() as con:
            row = con.execute(
                """
                SELECT
                    COUNT(CASE WHEN kind='donation' THEN 1 END) AS donation_count,
                    COALESCE(SUM(CASE WHEN kind='donation' THEN COALESCE(credited_amount, amount, 0) ELSE 0 END), 0) AS donation_amount,
                    COALESCE(SUM(CASE WHEN kind='donation' AND undone=0 THEN seconds_delta ELSE 0 END), 0) AS donation_seconds
                FROM events
                WHERE session_id=?
                """,
                (session_id,),
            ).fetchone()
            return {
                "donation_count": int(row["donation_count"] or 0),
                "donation_amount": float(row["donation_amount"] or 0),
                "donation_seconds": int(row["donation_seconds"] or 0),
            }

    def list_sessions(self, profile_id: int, limit: int = 100) -> list[Session]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as con:
            rows = con.execute(
                "SELECT * FROM sessions WHERE profile_id=? ORDER BY started_at DESC, id DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
            return [self._to_session(row) for row in rows]

    def get_session(self, profile_id: int, session_id: int) -> Session | None:
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE id=? AND profile_id=? LIMIT 1",
                (int(session_id), int(profile_id)),
            ).fetchone()
            return self._to_session(row) if row else None

    def rename_session(self, profile_id: int, session_id: int, name: str) -> Session | None:
        name = (name or "").strip()
        if not name:
            raise ValueError("Название сессии не может быть пустым")
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE id=? AND profile_id=? LIMIT 1",
                (int(session_id), int(profile_id)),
            ).fetchone()
            if not row:
                return None
            con.execute("UPDATE sessions SET name=? WHERE id=?", (name, int(session_id)))
            updated = con.execute("SELECT * FROM sessions WHERE id=?", (int(session_id),)).fetchone()
            return self._to_session(updated)

    def list_session_summaries(self, profile_id: int, limit: int = 100) -> list[dict]:
        """Return newest sessions with aggregate donation statistics."""
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as con:
            rows = con.execute(
                """
                SELECT
                    s.id, s.profile_id, s.name, s.started_at, s.ended_at, s.starting_seconds, s.paused_at, s.paused_total,
                    COUNT(CASE WHEN e.kind='donation' THEN 1 END) AS donation_count,
                    COALESCE(SUM(CASE WHEN e.kind='donation' THEN COALESCE(e.credited_amount, e.amount, 0) ELSE 0 END), 0) AS donation_amount,
                    COALESCE(SUM(CASE WHEN e.kind='donation' AND e.undone=0 THEN e.seconds_delta ELSE 0 END), 0) AS donation_seconds
                FROM sessions s
                LEFT JOIN events e ON e.session_id=s.id
                WHERE s.profile_id=?
                GROUP BY s.id
                ORDER BY s.started_at DESC, s.id DESC
                LIMIT ?
                """,
                (profile_id, limit),
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "profile_id": int(row["profile_id"]),
                    "name": str(row["name"]),
                    "started_at": float(row["started_at"]),
                    "ended_at": float(row["ended_at"]) if row["ended_at"] is not None else None,
                    "starting_seconds": int(row["starting_seconds"] or 0),
                    "paused_at": float(row["paused_at"]) if row["paused_at"] is not None else None,
                    "paused_total": float(row["paused_total"] or 0),
                    "donation_count": int(row["donation_count"] or 0),
                    "donation_amount": float(row["donation_amount"] or 0),
                    "donation_seconds": int(row["donation_seconds"] or 0),
                }
                for row in rows
            ]

    def recent_donations(self, profile_id: int, *, session_id: int | None = None, limit: int = 3) -> list[Event]:
        limit = max(1, min(int(limit), 50))
        with self._lock, self._connect() as con:
            sql = "SELECT * FROM events WHERE profile_id=? AND kind='donation'"
            params: list[object] = [profile_id]
            if session_id is not None:
                sql += " AND session_id=?"
                params.append(int(session_id))
            sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
            params.append(limit)
            rows = con.execute(sql, tuple(params)).fetchall()
            return [self._to_event(row) for row in rows]

    def session_donor_ranking(self, session_id: int, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as con:
            rows = con.execute(
                """
                SELECT
                    CASE WHEN TRIM(COALESCE(title, ''))='' THEN 'Аноним' ELSE title END AS donor,
                    COUNT(*) AS donation_count,
                    COALESCE(SUM(COALESCE(credited_amount, amount, 0)), 0) AS donation_amount,
                    COALESCE(SUM(CASE WHEN undone=0 THEN seconds_delta ELSE 0 END), 0) AS donation_seconds
                FROM events
                WHERE session_id=? AND kind='donation'
                GROUP BY CASE WHEN TRIM(COALESCE(title, ''))='' THEN 'Аноним' ELSE title END
                ORDER BY donation_amount DESC, donation_count DESC, donor COLLATE NOCASE ASC
                LIMIT ?
                """,
                (int(session_id), limit),
            ).fetchall()
            return [
                {
                    "donor": str(row["donor"]),
                    "donation_count": int(row["donation_count"] or 0),
                    "donation_amount": float(row["donation_amount"] or 0),
                    "donation_seconds": int(row["donation_seconds"] or 0),
                }
                for row in rows
            ]

    def set_session_paused(self, profile_id: int, session_id: int, paused: bool) -> Session | None:
        now = time.time()
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE id=? AND profile_id=? AND ended_at IS NULL LIMIT 1",
                (int(session_id), int(profile_id)),
            ).fetchone()
            if not row:
                return None
            if paused:
                if row["paused_at"] is None:
                    con.execute("UPDATE sessions SET paused_at=? WHERE id=?", (now, int(session_id)))
            else:
                if row["paused_at"] is not None:
                    paused_total = float(row["paused_total"] or 0) + max(0.0, now - float(row["paused_at"]))
                    con.execute(
                        "UPDATE sessions SET paused_at=NULL, paused_total=? WHERE id=?",
                        (paused_total, int(session_id)),
                    )
            updated = con.execute("SELECT * FROM sessions WHERE id=?", (int(session_id),)).fetchone()
            return self._to_session(updated) if updated else None

    @staticmethod
    def session_elapsed_seconds(session: Session, now: float | None = None) -> int:
        now = time.time() if now is None else float(now)
        endpoint = float(session.ended_at) if session.ended_at is not None else now
        paused = float(session.paused_total or 0)
        if session.ended_at is None and session.paused_at is not None:
            paused += max(0.0, now - float(session.paused_at))
        return max(0, int(endpoint - float(session.started_at) - paused))

    def delete_session(self, profile_id: int, session_id: int) -> Session | None:
        """Delete a completed session while preserving its events as profile-level history."""
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM sessions WHERE id=? AND profile_id=? LIMIT 1",
                (int(session_id), int(profile_id)),
            ).fetchone()
            if not row:
                return None
            session = self._to_session(row)
            if session.ended_at is None:
                raise ValueError("Активную сессию сначала нужно завершить")
            # The FK is ON DELETE SET NULL: donations and audit events remain in the
            # global history, but are no longer tied to the deleted session.
            con.execute("DELETE FROM sessions WHERE id=?", (int(session_id),))
            return session

    def donation_records(
        self,
        profile_id: int,
        *,
        start_ts: float | None = None,
        end_ts: float | None = None,
        session_id: int | None = None,
        donor: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 10000))
        with self._lock, self._connect() as con:
            sql = """
                SELECT e.*, s.name AS session_name
                FROM events e
                LEFT JOIN sessions s ON s.id=e.session_id
                WHERE e.profile_id=? AND e.kind='donation'
            """
            params: list[object] = [int(profile_id)]
            if start_ts is not None:
                sql += " AND e.created_at>=?"
                params.append(float(start_ts))
            if end_ts is not None:
                sql += " AND e.created_at<=?"
                params.append(float(end_ts))
            if session_id is not None:
                sql += " AND e.session_id=?"
                params.append(int(session_id))
            if donor is not None:
                sql += " AND CASE WHEN TRIM(COALESCE(e.title,''))='' THEN 'Аноним' ELSE e.title END = ? COLLATE NOCASE"
                params.append(str(donor or "Аноним"))
            sql += " ORDER BY e.created_at DESC, e.id DESC LIMIT ?"
            params.append(limit)
            rows = con.execute(sql, tuple(params)).fetchall()
            result=[]
            for row in rows:
                result.append({
                    "event": self._to_event(row),
                    "session_name": str(row["session_name"]) if row["session_name"] is not None else None,
                })
            return result

    def donation_summary(
        self,
        profile_id: int,
        *,
        start_ts: float | None = None,
        end_ts: float | None = None,
        session_id: int | None = None,
        donor: str | None = None,
    ) -> dict:
        with self._lock, self._connect() as con:
            where = ["profile_id=?", "kind='donation'"]
            params: list[object] = [int(profile_id)]
            if start_ts is not None:
                where.append("created_at>=?"); params.append(float(start_ts))
            if end_ts is not None:
                where.append("created_at<=?"); params.append(float(end_ts))
            if session_id is not None:
                where.append("session_id=?"); params.append(int(session_id))
            if donor is not None:
                where.append("CASE WHEN TRIM(COALESCE(title,''))='' THEN 'Аноним' ELSE title END = ? COLLATE NOCASE")
                params.append(str(donor or "Аноним"))
            clause = " AND ".join(where)
            row = con.execute(
                f"""SELECT COUNT(*) AS c, COALESCE(SUM(COALESCE(credited_amount, amount, 0)),0) AS total,
                           COALESCE(AVG(COALESCE(credited_amount, amount, 0)),0) AS avg_amount,
                           COALESCE(SUM(CASE WHEN undone=0 THEN seconds_delta ELSE 0 END),0) AS seconds
                    FROM events WHERE {clause}""",
                tuple(params),
            ).fetchone()
            top = con.execute(
                f"""SELECT CASE WHEN TRIM(COALESCE(title,''))='' THEN 'Аноним' ELSE title END AS donor,
                           COALESCE(SUM(COALESCE(credited_amount, amount, 0)),0) AS total
                    FROM events WHERE {clause}
                    GROUP BY CASE WHEN TRIM(COALESCE(title,''))='' THEN 'Аноним' ELSE title END
                    ORDER BY total DESC, donor COLLATE NOCASE ASC LIMIT 1""",
                tuple(params),
            ).fetchone()
            return {
                "count": int(row["c"] or 0),
                "total": float(row["total"] or 0),
                "average": float(row["avg_amount"] or 0),
                "seconds": int(row["seconds"] or 0),
                "top_donor": str(top["donor"]) if top else "—",
                "top_donor_total": float(top["total"] or 0) if top else 0.0,
            }

    # ---------- event log ----------

    def _current_session_id_locked(self, con: sqlite3.Connection, profile_id: int) -> int | None:
        row = con.execute(
            "SELECT id FROM sessions WHERE profile_id=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
        return int(row["id"]) if row else None

    def _active_session_id_locked(self, con: sqlite3.Connection, profile_id: int) -> int | None:
        row = con.execute(
            "SELECT id FROM sessions WHERE profile_id=? AND ended_at IS NULL AND paused_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
        return int(row["id"]) if row else None

    def add_event(
        self,
        profile_id: int,
        kind: str,
        title: str,
        seconds_delta: int,
        *,
        amount: float | None = None,
        currency: str | None = None,
        credited_amount: float | None = None,
        external_id: str | None = None,
        session_id: int | None = None,
        undo_of_event_id: int | None = None,
        auto_session: bool = True,
    ) -> bool:
        try:
            with self._lock, self._connect() as con:
                if session_id is None and auto_session:
                    session_id = self._active_session_id_locked(con, profile_id)
                con.execute(
                    """
                    INSERT INTO events
                    (profile_id, session_id, kind, title, amount, currency, credited_amount, seconds_delta,
                     external_id, created_at, undone, undo_of_event_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        profile_id,
                        session_id,
                        kind,
                        title,
                        amount,
                        currency,
                        credited_amount,
                        int(seconds_delta),
                        external_id,
                        time.time(),
                        undo_of_event_id,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def list_events(self, profile_id: int, limit: int = 60, session_id: int | None = None) -> list[Event]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as con:
            if session_id is None:
                rows = con.execute(
                    "SELECT * FROM events WHERE profile_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                    (profile_id, limit),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM events WHERE profile_id=? AND session_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                    (profile_id, session_id, limit),
                ).fetchall()
            return [self._to_event(r) for r in rows]

    def list_reversible_events(self, profile_id: int, limit: int = 150) -> list[Event]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as con:
            active_session_id = self._current_session_id_locked(con, profile_id)
            sql = """
                SELECT * FROM events
                WHERE profile_id=?
                  AND seconds_delta != 0
                  AND undone=0
                  AND kind IN ('donation','manual')
            """
            params: list[object] = [profile_id]
            if active_session_id is not None:
                sql += " AND session_id=?"
                params.append(active_session_id)
            sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
            params.append(limit)
            rows = con.execute(sql, tuple(params)).fetchall()
            return [self._to_event(row) for row in rows]

    def last_reversible_event(self, profile_id: int) -> Event | None:
        events = self.list_reversible_events(profile_id, limit=1)
        return events[0] if events else None

    def get_reversible_event(self, profile_id: int, event_id: int) -> Event | None:
        with self._lock, self._connect() as con:
            row = con.execute(
                """
                SELECT * FROM events
                WHERE id=? AND profile_id=?
                  AND seconds_delta != 0
                  AND undone=0
                  AND kind IN ('donation','manual')
                LIMIT 1
                """,
                (int(event_id), profile_id),
            ).fetchone()
            return self._to_event(row) if row else None

    def undo_event(self, event: Event) -> bool:
        with self._lock, self._connect() as con:
            current = con.execute("SELECT undone FROM events WHERE id=?", (event.id,)).fetchone()
            if not current or bool(current["undone"]):
                return False
            con.execute("UPDATE events SET undone=1 WHERE id=?", (event.id,))
            con.execute(
                """
                INSERT INTO events
                (profile_id, session_id, kind, title, amount, currency, credited_amount, seconds_delta,
                 external_id, created_at, undone, undo_of_event_id)
                VALUES (?, ?, 'undo', ?, NULL, NULL, NULL, ?, NULL, ?, 0, ?)
                """,
                (
                    event.profile_id,
                    event.session_id,
                    f"Отмена: {event.title}",
                    -int(event.seconds_delta),
                    time.time(),
                    event.id,
                ),
            )
            return True

    def mark_processed(self, profile_id: int, external_id: str) -> bool:
        with self._lock, self._connect() as con:
            cur = con.execute(
                "INSERT OR IGNORE INTO processed_donations(profile_id, external_id, created_at) VALUES(?, ?, ?)",
                (profile_id, external_id, time.time()),
            )
            return cur.rowcount > 0

    def is_processed(self, profile_id: int, external_id: str) -> bool:
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT 1 FROM processed_donations WHERE profile_id=? AND external_id=?",
                (profile_id, external_id),
            ).fetchone()
            return row is not None

    def recent_events(self, profile_id: int, limit: int = 8) -> list[dict]:
        return [
            {
                "kind": e.kind,
                "title": e.title,
                "amount": e.amount,
                "currency": e.currency,
                "seconds_delta": e.seconds_delta,
                "created_at": e.created_at,
            }
            for e in self.list_events(profile_id, limit=limit)
        ]


    # ---------- Twitch analytics ----------

    def link_twitch_profile(self, profile_id: int, *, user_id: str, login: str, display_name: str) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "UPDATE profiles SET twitch_user_id=?, twitch_login=?, twitch_display_name=? WHERE id=?",
                (str(user_id), str(login), str(display_name), int(profile_id)),
            )

    def add_chat_messages(self, items: list[dict]) -> int:
        if not items:
            return 0
        inserted=0
        with self._lock, self._connect() as con:
            session_cache: dict[int, int | None] = {}
            for item in items:
                profile_id=int(item["profile_id"])
                session_id=item.get("session_id")
                if session_id is None:
                    if profile_id not in session_cache:
                        session_cache[profile_id]=self._active_session_id_locked(con,profile_id)
                    session_id=session_cache[profile_id]
                try:
                    con.execute(
                        """INSERT INTO twitch_chat_messages
                           (profile_id,session_id,external_id,user_id,user_name,message_text,created_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (profile_id,session_id,item.get("external_id"),str(item.get("user_id") or ""),str(item.get("user_name") or "Аноним"),str(item.get("text") or ""),float(item.get("created_at") or time.time())),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
        return inserted

    def add_chat_message(
        self,
        profile_id: int,
        *,
        external_id: str | None,
        user_id: str,
        user_name: str,
        text: str,
        created_at: float | None = None,
        session_id: int | None = None,
    ) -> bool:
        created_at = time.time() if created_at is None else float(created_at)
        try:
            with self._lock, self._connect() as con:
                if session_id is None:
                    session_id = self._active_session_id_locked(con, int(profile_id))
                con.execute(
                    """INSERT INTO twitch_chat_messages
                       (profile_id, session_id, external_id, user_id, user_name, message_text, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (int(profile_id), session_id, external_id, str(user_id or ""), str(user_name or "Аноним"), str(text), created_at),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def chat_records(
        self,
        profile_id: int,
        *,
        start_ts: float | None = None,
        end_ts: float | None = None,
        session_id: int | None = None,
        limit: int = 20000,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 50000))
        with self._lock, self._connect() as con:
            sql = """SELECT c.*, s.name AS session_name FROM twitch_chat_messages c
                     LEFT JOIN sessions s ON s.id=c.session_id WHERE c.profile_id=?"""
            params: list[object] = [int(profile_id)]
            if start_ts is not None: sql += " AND c.created_at>=?"; params.append(float(start_ts))
            if end_ts is not None: sql += " AND c.created_at<=?"; params.append(float(end_ts))
            if session_id is not None: sql += " AND c.session_id=?"; params.append(int(session_id))
            sql += " ORDER BY c.created_at ASC, c.id ASC LIMIT ?"; params.append(limit)
            return [dict(row) for row in con.execute(sql, tuple(params)).fetchall()]

    def chat_summary(self, profile_id: int, *, start_ts: float | None = None, end_ts: float | None = None, session_id: int | None = None) -> dict:
        """Return chat counters without materialising thousands of messages in Python."""
        with self._lock, self._connect() as con:
            where=["profile_id=?"]
            params: list[object]=[int(profile_id)]
            if start_ts is not None: where.append("created_at>=?"); params.append(float(start_ts))
            if end_ts is not None: where.append("created_at<=?"); params.append(float(end_ts))
            if session_id is not None: where.append("session_id=?"); params.append(int(session_id))
            clause=" AND ".join(where)
            row=con.execute(
                f"""SELECT COUNT(*) AS c,
                           COUNT(DISTINCT CASE WHEN TRIM(COALESCE(user_id,''))<>'' THEN user_id ELSE LOWER(user_name) END) AS users,
                           MIN(created_at) AS first_ts, MAX(created_at) AS last_ts
                    FROM twitch_chat_messages WHERE {clause}""", tuple(params)
            ).fetchone()
            count=int(row["c"] or 0)
            if not count:
                return {"count":0,"unique_users":0,"messages_per_minute":0.0,"peak_per_minute":0}
            peak=con.execute(
                f"""SELECT COALESCE(MAX(c),0) AS peak FROM (
                        SELECT COUNT(*) AS c FROM twitch_chat_messages
                        WHERE {clause}
                        GROUP BY CAST(created_at/60 AS INTEGER)
                    )""", tuple(params)
            ).fetchone()
            if session_id is not None:
                sr=con.execute("SELECT * FROM sessions WHERE id=? AND profile_id=?",(int(session_id),int(profile_id))).fetchone()
                duration=self.session_elapsed_seconds(self._to_session(sr)) if sr else max(60.0,float(row["last_ts"])-float(row["first_ts"]))
            elif start_ts is not None and end_ts is not None:
                duration=max(60.0,float(end_ts)-float(start_ts))
            else:
                duration=max(60.0,float(row["last_ts"])-float(row["first_ts"]))
            return {
                "count":count,
                "unique_users":int(row["users"] or 0),
                "messages_per_minute":count/max(1.0,duration/60.0),
                "peak_per_minute":int(peak["peak"] or 0),
            }

    def add_viewer_sample(self, profile_id: int, viewer_count: int, *, live: bool = True, created_at: float | None = None, session_id: int | None = None) -> None:
        created_at = time.time() if created_at is None else float(created_at)
        with self._lock, self._connect() as con:
            if session_id is None:
                session_id = self._active_session_id_locked(con, int(profile_id))
            con.execute(
                "INSERT INTO twitch_viewer_samples(profile_id,session_id,viewer_count,live,created_at) VALUES(?,?,?,?,?)",
                (int(profile_id), session_id, max(0,int(viewer_count)), 1 if live else 0, created_at),
            )

    def viewer_records(self, profile_id: int, *, start_ts: float | None = None, end_ts: float | None = None, session_id: int | None = None, limit: int = 20000) -> list[dict]:
        limit=max(1,min(int(limit),50000))
        with self._lock, self._connect() as con:
            sql="""SELECT v.*, s.name AS session_name FROM twitch_viewer_samples v
                   LEFT JOIN sessions s ON s.id=v.session_id WHERE v.profile_id=?"""
            params: list[object]=[int(profile_id)]
            if start_ts is not None: sql += " AND v.created_at>=?"; params.append(float(start_ts))
            if end_ts is not None: sql += " AND v.created_at<=?"; params.append(float(end_ts))
            if session_id is not None: sql += " AND v.session_id=?"; params.append(int(session_id))
            sql += " ORDER BY v.created_at ASC, v.id ASC LIMIT ?"; params.append(limit)
            return [dict(r) for r in con.execute(sql,tuple(params)).fetchall()]

    def viewer_summary(self, profile_id: int, *, start_ts: float | None = None, end_ts: float | None = None, session_id: int | None = None) -> dict:
        """Summarise live viewer samples in SQL to keep RAM flat on long-running streams."""
        with self._lock, self._connect() as con:
            where=["profile_id=?","live=1"]
            params: list[object]=[int(profile_id)]
            if start_ts is not None: where.append("created_at>=?"); params.append(float(start_ts))
            if end_ts is not None: where.append("created_at<=?"); params.append(float(end_ts))
            if session_id is not None: where.append("session_id=?"); params.append(int(session_id))
            row=con.execute(
                f"SELECT COUNT(*) c, COALESCE(AVG(viewer_count),0) av, COALESCE(MIN(viewer_count),0) mn, COALESCE(MAX(viewer_count),0) mx FROM twitch_viewer_samples WHERE {' AND '.join(where)}",
                tuple(params),
            ).fetchone()
            return {"count":int(row["c"] or 0),"average":float(row["av"] or 0),"minimum":int(row["mn"] or 0),"maximum":int(row["mx"] or 0)}

    def donation_revision(self, profile_id: int) -> tuple[int, int, int]:
        with self._lock, self._connect() as con:
            row=con.execute("SELECT COUNT(*) c, COALESCE(MAX(id),0) m, COALESCE(MAX(undone),0) u FROM events WHERE profile_id=? AND kind='donation'",(int(profile_id),)).fetchone()
            # MAX(undone) alone does not capture toggles back, so include sum as a cheap state token.
            undone=con.execute("SELECT COALESCE(SUM(undone),0) s FROM events WHERE profile_id=? AND kind='donation'",(int(profile_id),)).fetchone()
            return (int(row["c"] or 0),int(row["m"] or 0),int(undone["s"] or 0))

    def analytics_revision(self, profile_id: int) -> tuple[int,int,int,int,int,int,int,int]:
        """Cheap change token used by the UI to avoid rereading thousands of rows every refresh tick."""
        with self._lock, self._connect() as con:
            d=con.execute("SELECT COUNT(*) c, COALESCE(MAX(id),0) m FROM events WHERE profile_id=? AND kind='donation'",(int(profile_id),)).fetchone()
            v=con.execute("SELECT COUNT(*) c, COALESCE(MAX(id),0) m FROM twitch_viewer_samples WHERE profile_id=?",(int(profile_id),)).fetchone()
            c=con.execute("SELECT COUNT(*) c, COALESCE(MAX(id),0) m FROM twitch_chat_messages WHERE profile_id=?",(int(profile_id),)).fetchone()
            sp=con.execute("SELECT COUNT(*) c, COALESCE(MAX(id),0) m FROM speech_segments WHERE profile_id=?",(int(profile_id),)).fetchone()
            return (int(d["c"]),int(d["m"]),int(v["c"]),int(v["m"]),int(c["c"]),int(c["m"]),int(sp["c"]),int(sp["m"]))

    # ---------- Retention / storage maintenance ----------

    def storage_stats(self) -> dict:
        """Small counters used by the Settings page; does not load table contents."""
        with self._lock, self._connect() as con:
            def count(table: str) -> int:
                return int(con.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"] or 0)
            return {
                "chat": count("twitch_chat_messages"),
                "viewers": count("twitch_viewer_samples"),
                "speech_segments": count("speech_segments"),
                "speech_recordings": count("speech_recordings"),
                "events": count("events"),
                "sessions": count("sessions"),
            }

    def cleanup_old_data(
        self,
        cutoff_ts: float,
        *,
        delete_chat: bool = True,
        delete_viewers: bool = True,
        delete_speech_segments: bool = True,
        delete_speech_recordings: bool = True,
        delete_non_donation_events: bool = False,
    ) -> dict:
        """Delete selected old analytics while keeping donations and sessions safe.

        Returns row counts and recording file paths that can be removed from disk by
        the caller. Donation events are deliberately never deleted here.
        """
        cutoff=float(cutoff_ts)
        result={"chat":0,"viewers":0,"speech_segments":0,"speech_recordings":0,"events":0,"recording_paths":[]}
        with self._lock, self._connect() as con:
            if delete_chat:
                cur=con.execute("DELETE FROM twitch_chat_messages WHERE created_at<?",(cutoff,)); result["chat"]=max(0,int(cur.rowcount or 0))
            if delete_viewers:
                cur=con.execute("DELETE FROM twitch_viewer_samples WHERE created_at<?",(cutoff,)); result["viewers"]=max(0,int(cur.rowcount or 0))
            if delete_speech_segments:
                cur=con.execute("DELETE FROM speech_segments WHERE started_at<?",(cutoff,)); result["speech_segments"]=max(0,int(cur.rowcount or 0))
            if delete_speech_recordings:
                rows=con.execute("SELECT id,path FROM speech_recordings WHERE started_at<? AND status<>'recording'",(cutoff,)).fetchall()
                ids=[int(r["id"]) for r in rows]; result["recording_paths"]=[str(r["path"]) for r in rows]
                if ids:
                    placeholders=','.join('?' for _ in ids)
                    cur=con.execute(f"DELETE FROM speech_recordings WHERE id IN ({placeholders})",tuple(ids)); result["speech_recordings"]=max(0,int(cur.rowcount or 0))
            if delete_non_donation_events:
                cur=con.execute("DELETE FROM events WHERE created_at<? AND kind<>'donation'",(cutoff,)); result["events"]=max(0,int(cur.rowcount or 0))
        return result

    def vacuum(self) -> None:
        """Compact the SQLite file after a large manual cleanup."""
        with self._lock:
            with self._connect() as con:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con=sqlite3.connect(self.path, timeout=30)
            try:
                con.execute("VACUUM")
            finally:
                con.close()

    # ---------- Streamer speech ----------

    def create_speech_recording(self, profile_id: int, session_id: int, path: str, started_at: float) -> int:
        with self._lock, self._connect() as con:
            cur=con.execute(
                "INSERT INTO speech_recordings(profile_id,session_id,path,started_at,status) VALUES(?,?,?,?, 'recording')",
                (int(profile_id),int(session_id),str(path),float(started_at)),
            )
            return int(cur.lastrowid)

    def finish_speech_recording(self, recording_id: int, ended_at: float, status: str) -> None:
        with self._lock, self._connect() as con:
            con.execute("UPDATE speech_recordings SET ended_at=?, status=? WHERE id=?",(float(ended_at),str(status),int(recording_id)))

    def list_speech_recordings(self, profile_id: int, *, session_id: int | None = None) -> list[dict]:
        with self._lock, self._connect() as con:
            sql="SELECT * FROM speech_recordings WHERE profile_id=?"; params: list[object] =[int(profile_id)]
            if session_id is not None: sql += " AND session_id=?"; params.append(int(session_id))
            sql += " ORDER BY started_at ASC"
            return [dict(r) for r in con.execute(sql,tuple(params)).fetchall()]

    def add_speech_segment(self, profile_id: int, *, session_id: int, recording_id: int | None, started_at: float, ended_at: float, text: str) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO speech_segments(profile_id,session_id,recording_id,started_at,ended_at,text) VALUES(?,?,?,?,?,?)",
                (int(profile_id),int(session_id),recording_id,float(started_at),float(ended_at),str(text)),
            )

    def speech_records(self, profile_id: int, *, start_ts: float | None = None, end_ts: float | None = None, session_id: int | None = None, limit: int = 50000) -> list[dict]:
        limit=max(1,min(int(limit),50000))
        with self._lock, self._connect() as con:
            sql="""SELECT sp.*, s.name AS session_name FROM speech_segments sp
                   LEFT JOIN sessions s ON s.id=sp.session_id WHERE sp.profile_id=?"""
            params: list[object] =[int(profile_id)]
            if start_ts is not None: sql += " AND sp.started_at>=?"; params.append(float(start_ts))
            if end_ts is not None: sql += " AND sp.started_at<=?"; params.append(float(end_ts))
            if session_id is not None: sql += " AND sp.session_id=?"; params.append(int(session_id))
            sql += " ORDER BY sp.started_at ASC, sp.id ASC LIMIT ?"; params.append(limit)
            return [dict(r) for r in con.execute(sql,tuple(params)).fetchall()]

    def upsert_da_profile(
        self,
        *,
        user_id: str,
        code: str,
        name: str,
        avatar_url: str | None,
    ) -> int:
        """Create/update a DonationAlerts profile and return its local id."""
        with self._lock, self._connect() as con:
            row = con.execute("SELECT id FROM profiles WHERE da_user_id=?", (str(user_id),)).fetchone()
            if row:
                profile_id = int(row["id"])
                con.execute(
                    "UPDATE profiles SET name=?, da_code=?, avatar_url=? WHERE id=?",
                    (name, code, avatar_url, profile_id),
                )
                return profile_id
            cur = con.execute(
                """
                INSERT INTO profiles
                (name, da_user_id, da_code, avatar_url, rate_amount, rate_seconds,
                 running, paused_remaining, overlay_theme, overlay_title,
                 overlay_show_rate, created_at)
                VALUES (?, ?, ?, ?, 100, 300, 0, 0, 'classic', '', 1, ?)
                """,
                (name, str(user_id), code, avatar_url, time.time()),
            )
            return int(cur.lastrowid)
