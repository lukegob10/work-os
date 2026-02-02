from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_settings
from .engine import ExtractionEngine, ReactEngine
from .store import db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="work-os")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest local emails + uploaded files into SQLite")
    p_ingest.add_argument("--since", default="7d", help="Lookback window (e.g. 7d, 24h). For reports only.")

    p_threads = sub.add_parser("threads", help="Build/update threads from events")
    p_threads.add_argument("--since", default="7d")

    p_extract = sub.add_parser("extract", help="Extract signals + open loops (LLM)")
    p_extract.add_argument("--since", default="7d")

    p_open = sub.add_parser("open-loops", help="List open loops")
    p_open.add_argument("--status", default="open")

    p_daily = sub.add_parser("run-daily", help="Run bounded ReAct-style daily pipeline (LangGraph)")
    p_daily.add_argument("--since", default="7d")

    p_qa = sub.add_parser("qa", help="Ask a question (bounded ReAct agent)")
    p_qa.add_argument("question")
    p_qa.add_argument("--since", default="30d")
    p_qa.add_argument("--max-steps", type=int, default=6)

    args = parser.parse_args(argv)
    settings = load_settings()

    if args.cmd == "ingest":
        return _cmd_ingest(settings)
    if args.cmd == "threads":
        since_iso = _parse_since(args.since)
        return _cmd_threads(settings, since_iso)
    if args.cmd == "extract":
        since_iso = _parse_since(args.since)
        return _cmd_extract(settings, since_iso)
    if args.cmd == "open-loops":
        return _cmd_open_loops(settings, args.status)
    if args.cmd == "run-daily":
        since_iso = _parse_since(args.since)
        return _cmd_run_daily(settings, since_iso)
    if args.cmd == "qa":
        since_iso = _parse_since(args.since)
        return _cmd_qa(settings, question=args.question, since_iso=since_iso, max_steps=args.max_steps)
    parser.error("unknown command")
    return 2


def _cmd_ingest(settings) -> int:
    stats = ExtractionEngine(settings).ingest()
    print(json.dumps({"ingested_events": stats.ingested_events}))
    return 0


def _cmd_threads(settings, since_iso: str) -> int:
    stats = ExtractionEngine(settings).thread(since_iso=since_iso)
    print(json.dumps({"threads_built": stats.threads_built}))
    return 0


def _cmd_extract(settings, since_iso: str) -> int:
    stats = ExtractionEngine(settings).extract(since_iso=since_iso)
    print(json.dumps({"signals": stats.signals_extracted, "open_loops": stats.open_loops_created}))
    return 0


def _cmd_open_loops(settings, status: str) -> int:
    conn = db.connect(settings.db_path)
    loops = db.fetch_open_loops(conn, status=status)
    conn.close()
    print(json.dumps(db.dump_records(loops), indent=2))
    return 0


def _cmd_run_daily(settings, since_iso: str) -> int:
    result = ReactEngine(settings).run_daily(since_iso=since_iso)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_qa(settings, *, question: str, since_iso: str, max_steps: int) -> int:
    state = ReactEngine(settings).answer_question(question=question, since_iso=since_iso, max_steps=max_steps)
    answer = state.get("final_answer") or "(no answer)"
    print(answer)
    return 0


def _parse_since(value: str) -> str:
    value = value.strip().lower()
    now = datetime.now(timezone.utc)
    if value.endswith("d"):
        days = int(value[:-1])
        return (now - timedelta(days=days)).replace(microsecond=0).isoformat()
    if value.endswith("h"):
        hours = int(value[:-1])
        return (now - timedelta(hours=hours)).replace(microsecond=0).isoformat()
    # allow ISO directly
    return value
