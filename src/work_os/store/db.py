from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CanonicalEvent, OpenLoopRecord, SignalRecord, ThreadRecord


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_account TEXT,
  conversation_id TEXT,
  timestamp TEXT,
  participants_json TEXT,
  title TEXT,
  body_text TEXT,
  extracted_text TEXT,
  attachments_or_links_json TEXT,
  raw_pointer TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_conversation_id ON events(conversation_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

CREATE TABLE IF NOT EXISTS threads (
  conversation_id TEXT PRIMARY KEY,
  thread_title TEXT,
  event_ids_json TEXT NOT NULL,
  last_activity_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_threads_last_activity_at ON threads(last_activity_at);

CREATE TABLE IF NOT EXISTS signals (
  signal_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  due_date TEXT,
  evidence_event_ids_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_conversation_id ON signals(conversation_id);
CREATE INDEX IF NOT EXISTS idx_signals_kind ON signals(kind);

CREATE TABLE IF NOT EXISTS open_loops (
  loop_id TEXT PRIMARY KEY,
  conversation_id TEXT,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL,
  owner TEXT NOT NULL,
  due_date TEXT,
  created_at TEXT NOT NULL,
  last_touched_at TEXT NOT NULL,
  evidence_event_ids_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_open_loops_status ON open_loops(status);
CREATE INDEX IF NOT EXISTS idx_open_loops_due_date ON open_loops(due_date);

CREATE TABLE IF NOT EXISTS audit_log (
  run_id TEXT PRIMARY KEY,
  command TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  stats_json TEXT,
  error TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA_SQL)
    return conn


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def upsert_events(conn: sqlite3.Connection, events: Iterable[CanonicalEvent]) -> int:
    rows = [
        (
            e.event_id,
            e.source,
            e.source_account,
            e.conversation_id,
            e.timestamp,
            json.dumps(e.participants),
            e.title,
            e.body_text,
            e.extracted_text,
            json.dumps(e.attachments_or_links),
            e.raw_pointer,
            utc_now_iso(),
        )
        for e in events
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO events(
          event_id, source, source_account, conversation_id, timestamp, participants_json, title,
          body_text, extracted_text, attachments_or_links_json, raw_pointer, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
          source=excluded.source,
          source_account=excluded.source_account,
          conversation_id=excluded.conversation_id,
          timestamp=excluded.timestamp,
          participants_json=excluded.participants_json,
          title=excluded.title,
          body_text=excluded.body_text,
          extracted_text=excluded.extracted_text,
          attachments_or_links_json=excluded.attachments_or_links_json,
          raw_pointer=excluded.raw_pointer
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def fetch_events_since(conn: sqlite3.Connection, since_iso: str) -> list[CanonicalEvent]:
    cur = conn.execute(
        """
        SELECT event_id, source, source_account, conversation_id, timestamp, participants_json, title,
               body_text, extracted_text, attachments_or_links_json, raw_pointer
        FROM events
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
        """,
        (since_iso,),
    )
    out: list[CanonicalEvent] = []
    for row in cur.fetchall():
        out.append(
            CanonicalEvent(
                event_id=row["event_id"],
                source=row["source"],
                source_account=row["source_account"],
                conversation_id=row["conversation_id"],
                timestamp=row["timestamp"],
                participants=json.loads(row["participants_json"] or "[]"),
                title=row["title"],
                body_text=row["body_text"],
                extracted_text=row["extracted_text"],
                attachments_or_links=json.loads(row["attachments_or_links_json"] or "[]"),
                raw_pointer=row["raw_pointer"],
            )
        )
    return out


def fetch_events_by_conversation(conn: sqlite3.Connection, conversation_id: str) -> list[CanonicalEvent]:
    cur = conn.execute(
        """
        SELECT event_id, source, source_account, conversation_id, timestamp, participants_json, title,
               body_text, extracted_text, attachments_or_links_json, raw_pointer
        FROM events
        WHERE conversation_id = ?
        ORDER BY timestamp ASC
        """,
        (conversation_id,),
    )
    out: list[CanonicalEvent] = []
    for row in cur.fetchall():
        out.append(
            CanonicalEvent(
                event_id=row["event_id"],
                source=row["source"],
                source_account=row["source_account"],
                conversation_id=row["conversation_id"],
                timestamp=row["timestamp"],
                participants=json.loads(row["participants_json"] or "[]"),
                title=row["title"],
                body_text=row["body_text"],
                extracted_text=row["extracted_text"],
                attachments_or_links=json.loads(row["attachments_or_links_json"] or "[]"),
                raw_pointer=row["raw_pointer"],
            )
        )
    return out


def upsert_threads(conn: sqlite3.Connection, threads: Iterable[ThreadRecord]) -> int:
    rows = [
        (
            t.conversation_id,
            t.thread_title,
            json.dumps(t.event_ids),
            t.last_activity_at,
            utc_now_iso(),
        )
        for t in threads
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO threads(conversation_id, thread_title, event_ids_json, last_activity_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
          thread_title=excluded.thread_title,
          event_ids_json=excluded.event_ids_json,
          last_activity_at=excluded.last_activity_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def fetch_threads_since(conn: sqlite3.Connection, since_iso: str) -> list[ThreadRecord]:
    cur = conn.execute(
        """
        SELECT conversation_id, thread_title, event_ids_json, last_activity_at
        FROM threads
        WHERE last_activity_at >= ?
        ORDER BY last_activity_at DESC
        """,
        (since_iso,),
    )
    out: list[ThreadRecord] = []
    for row in cur.fetchall():
        out.append(
            ThreadRecord(
                conversation_id=row["conversation_id"],
                thread_title=row["thread_title"],
                event_ids=json.loads(row["event_ids_json"] or "[]"),
                last_activity_at=row["last_activity_at"],
            )
        )
    return out


def insert_signals(conn: sqlite3.Connection, signals: Iterable[SignalRecord]) -> int:
    rows = [
        (
            s.signal_id,
            s.conversation_id,
            s.kind,
            s.summary,
            s.due_date,
            json.dumps(s.evidence_event_ids),
            utc_now_iso(),
        )
        for s in signals
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT OR REPLACE INTO signals(
          signal_id, conversation_id, kind, summary, due_date, evidence_event_ids_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def insert_open_loops(conn: sqlite3.Connection, loops: Iterable[OpenLoopRecord]) -> int:
    rows = [
        (
            l.loop_id,
            l.conversation_id,
            l.kind,
            l.status,
            l.summary,
            l.owner,
            l.due_date,
            l.created_at,
            l.last_touched_at,
            json.dumps(l.evidence_event_ids),
        )
        for l in loops
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT OR REPLACE INTO open_loops(
          loop_id, conversation_id, kind, status, summary, owner, due_date,
          created_at, last_touched_at, evidence_event_ids_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def fetch_open_loops(conn: sqlite3.Connection, status: str = "open") -> list[OpenLoopRecord]:
    cur = conn.execute(
        """
        SELECT loop_id, conversation_id, kind, status, summary, owner, due_date, created_at, last_touched_at,
               evidence_event_ids_json
        FROM open_loops
        WHERE status = ?
        ORDER BY COALESCE(due_date, '9999-12-31') ASC, last_touched_at DESC
        """,
        (status,),
    )
    out: list[OpenLoopRecord] = []
    for row in cur.fetchall():
        out.append(
            OpenLoopRecord(
                loop_id=row["loop_id"],
                conversation_id=row["conversation_id"],
                kind=row["kind"],
                status=row["status"],
                summary=row["summary"],
                owner=row["owner"],
                due_date=row["due_date"],
                created_at=row["created_at"],
                last_touched_at=row["last_touched_at"],
                evidence_event_ids=json.loads(row["evidence_event_ids_json"] or "[]"),
            )
        )
    return out


def insert_audit_log(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    command: str,
    started_at: str,
    finished_at: str | None,
    stats: dict[str, Any] | None,
    error: str | None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO audit_log(run_id, command, started_at, finished_at, stats_json, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            command,
            started_at,
            finished_at,
            json.dumps(stats) if stats is not None else None,
            error,
        ),
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def dump_records(records: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in records:
        if hasattr(r, "__dataclass_fields__"):
            out.append(asdict(r))
        else:
            out.append(dict(r))
    return out

