from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph  # type: ignore

from ..config import Settings
from ..ingest.local_email import ingest_local_emails
from ..ingest.outlook_win32 import OutlookIngestError, ingest_outlook_mail
from ..ingest.uploaded_files import ingest_uploads
from ..process.extract import safe_extract_signals_for_thread
from ..process.filters import filter_events_for_processing
from ..process.loops import signals_to_open_loops
from ..process.threading import build_threads
from ..report.daily import render_daily_open_loops_md
from ..store import db


class DailyState(TypedDict, total=False):
    since_iso: str
    ingested_events: int
    threads_built: int
    signals_extracted: int
    open_loops_created: int
    daily_report_path: str


def build_daily_worker(settings: Settings):
    graph = StateGraph(DailyState)

    graph.add_node("ingest", lambda state: _node_ingest(settings, state))
    graph.add_node("thread", lambda state: _node_thread(settings, state))
    graph.add_node("extract", lambda state: _node_extract(settings, state))
    graph.add_node("report", lambda state: _node_report(settings, state))

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "thread")
    graph.add_edge("thread", "extract")
    graph.add_edge("extract", "report")
    graph.add_edge("report", END)

    return graph.compile()


def _node_ingest(settings: Settings, state: DailyState) -> DailyState:
    conn = db.connect(settings.db_path)
    email_events = []
    if settings.email_ingest_mode in ("local_json", "both"):
        email_events.extend(ingest_local_emails(emails_dir=settings.local_emails_dir))
    if settings.email_ingest_mode in ("outlook", "both"):
        since_iso = state.get("since_iso") or "1970-01-01T00:00:00+00:00"
        try:
            email_events.extend(ingest_outlook_mail(since_iso=since_iso, account_hint=settings.outlook_account))
        except OutlookIngestError:
            if settings.email_ingest_mode == "outlook":
                raise
    file_events = ingest_uploads(uploads_dir=settings.uploads_dir)
    count = db.upsert_events(conn, [*email_events, *file_events])
    conn.close()
    return {**state, "ingested_events": count}


def _node_thread(settings: Settings, state: DailyState) -> DailyState:
    since_iso = state.get("since_iso") or "1970-01-01T00:00:00+00:00"
    conn = db.connect(settings.db_path)
    events = db.fetch_events_since(conn, since_iso)
    events = filter_events_for_processing(events, settings=settings)
    threads = build_threads(events)
    threads_count = db.upsert_threads(conn, threads)
    conn.close()
    return {**state, "threads_built": threads_count}


def _node_extract(settings: Settings, state: DailyState) -> DailyState:
    since_iso = state.get("since_iso") or "1970-01-01T00:00:00+00:00"
    conn = db.connect(settings.db_path)
    threads = db.fetch_threads_since(conn, since_iso)
    total_signals = 0
    total_loops = 0
    for thread in threads:
        events = db.fetch_events_by_ids(conn, thread.event_ids)
        signals = safe_extract_signals_for_thread(settings=settings, events=events)
        total_signals += db.insert_signals(conn, signals)
        loops = signals_to_open_loops(signals)
        total_loops += db.insert_open_loops(conn, loops)
    conn.close()
    return {**state, "signals_extracted": total_signals, "open_loops_created": total_loops}


def _node_report(settings: Settings, state: DailyState) -> DailyState:
    since_iso = state.get("since_iso") or "1970-01-01T00:00:00+00:00"
    conn = db.connect(settings.db_path)
    loops = db.fetch_open_loops(conn, status="open")
    conn.close()
    md = render_daily_open_loops_md(loops=loops, since_iso=since_iso)
    settings.briefs_dir.mkdir(parents=True, exist_ok=True)
    path = settings.briefs_dir / "daily_open_loops.md"
    path.write_text(md, encoding="utf-8")
    return {**state, "daily_report_path": str(path)}
