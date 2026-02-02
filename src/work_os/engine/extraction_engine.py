from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..ingest.local_email import ingest_local_emails
from ..ingest.uploaded_files import ingest_uploads
from ..process.extract import safe_extract_signals_for_thread
from ..process.loops import signals_to_open_loops
from ..process.threading import build_threads
from ..store import db


@dataclass(frozen=True)
class ExtractionStats:
    ingested_events: int = 0
    threads_built: int = 0
    signals_extracted: int = 0
    open_loops_created: int = 0


class ExtractionEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def ingest(self) -> ExtractionStats:
        conn = db.connect(self._settings.db_path)
        try:
            email_events = ingest_local_emails(emails_dir=self._settings.local_emails_dir)
            file_events = ingest_uploads(uploads_dir=self._settings.uploads_dir)
            count = db.upsert_events(conn, [*email_events, *file_events])
            return ExtractionStats(ingested_events=count)
        finally:
            conn.close()

    def thread(self, *, since_iso: str) -> ExtractionStats:
        conn = db.connect(self._settings.db_path)
        try:
            events = db.fetch_events_since(conn, since_iso)
            threads = build_threads(events)
            threads_count = db.upsert_threads(conn, threads)
            return ExtractionStats(threads_built=threads_count)
        finally:
            conn.close()

    def extract(self, *, since_iso: str) -> ExtractionStats:
        conn = db.connect(self._settings.db_path)
        try:
            threads = db.fetch_threads_since(conn, since_iso)
            total_signals = 0
            total_loops = 0
            for thread in threads:
                events = db.fetch_events_by_conversation(conn, thread.conversation_id)
                signals = safe_extract_signals_for_thread(settings=self._settings, events=events)
                total_signals += db.insert_signals(conn, signals)
                loops = signals_to_open_loops(signals)
                total_loops += db.insert_open_loops(conn, loops)
            return ExtractionStats(signals_extracted=total_signals, open_loops_created=total_loops)
        finally:
            conn.close()

