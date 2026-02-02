from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..ingest.local_email import ingest_local_emails
from ..ingest.outlook_win32 import OutlookIngestError, ingest_outlook_mail
from ..ingest.uploaded_files import ingest_uploads
from ..process.extract import safe_extract_signals_for_thread
from ..process.filters import filter_events_for_processing
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

    def ingest(self, *, since_iso: str | None = None) -> ExtractionStats:
        conn = db.connect(self._settings.db_path)
        try:
            since_iso = since_iso or "1970-01-01T00:00:00+00:00"
            email_events = []
            if self._settings.email_ingest_mode in ("local_json", "both"):
                email_events.extend(ingest_local_emails(emails_dir=self._settings.local_emails_dir))
            if self._settings.email_ingest_mode in ("outlook", "both"):
                try:
                    # Outlook ingestion pulls from the signed-in Outlook profile (no separate credentials).
                    email_events.extend(
                        ingest_outlook_mail(
                            since_iso=since_iso,
                            account_hint=self._settings.outlook_account,
                        )
                    )
                except OutlookIngestError:
                    # Keep ingestion resilient; caller can switch modes/config.
                    if self._settings.email_ingest_mode == "outlook":
                        raise
            file_events = ingest_uploads(uploads_dir=self._settings.uploads_dir)
            count = db.upsert_events(conn, [*email_events, *file_events])
            return ExtractionStats(ingested_events=count)
        finally:
            conn.close()

    def thread(self, *, since_iso: str) -> ExtractionStats:
        conn = db.connect(self._settings.db_path)
        try:
            events = db.fetch_events_since(conn, since_iso)
            events = filter_events_for_processing(events, settings=self._settings)
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
                events = db.fetch_events_by_ids(conn, thread.event_ids)
                signals = safe_extract_signals_for_thread(settings=self._settings, events=events)
                total_signals += db.insert_signals(conn, signals)
                loops = signals_to_open_loops(signals)
                total_loops += db.insert_open_loops(conn, loops)
            return ExtractionStats(signals_extracted=total_signals, open_loops_created=total_loops)
        finally:
            conn.close()
