from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, StateGraph  # type: ignore

from ..config import Settings
from ..llm.client import GeminiClient
from ..llm.prompts import build_react_final_prompt, build_react_planner_prompt
from ..llm.schemas import ReactAction
from ..store import db


class QaState(TypedDict, total=False):
    question: str
    since_iso: str
    context: str
    steps: list[dict[str, object]]
    final_answer: str


def build_qa_agent(settings: Settings):
    graph = StateGraph(QaState)

    graph.add_node("plan", lambda state: _node_plan(settings, state))
    graph.add_node("tool", lambda state: _node_tool(settings, state))
    graph.add_node("final", lambda state: _node_final(settings, state))

    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", _route_plan)
    graph.add_edge("tool", END)
    graph.add_edge("final", END)

    return graph.compile()


def _route_plan(state: QaState) -> str:
    action = state.get("steps", [])[-1] if state.get("steps") else {}
    name = str(action.get("action") or "")
    if name == "final":
        return "final"
    return "tool"


def _node_plan(settings: Settings, state: QaState) -> QaState:
    question = state.get("question") or ""
    context = state.get("context") or ""
    tools = {
        "search_events": "args: {query: string, since_iso?: string, limit?: int}",
        "get_event": "args: {event_id: string}",
        "list_open_loops": "args: {status?: string, limit?: int}",
        "final": "args: { }",
    }
    prompt = build_react_planner_prompt(question=question, tools=tools, context=context)
    client = GeminiClient(settings)
    result = client.generate_json(prompt)
    action = ReactAction.model_validate(result.data)
    steps = list(state.get("steps") or [])
    steps.append(action.model_dump())
    return {**state, "steps": steps}


def _node_tool(settings: Settings, state: QaState) -> QaState:
    steps = list(state.get("steps") or [])
    last = steps[-1] if steps else {}
    action = str(last.get("action") or "")
    args = last.get("args") or {}

    conn = db.connect(settings.db_path)
    try:
        if action == "search_events":
            query = str(args.get("query") or "")
            since_iso = str(args.get("since_iso") or state.get("since_iso") or "1970-01-01T00:00:00+00:00")
            limit = int(args.get("limit") or 10)
            snippet = _search_events(conn, query=query, since_iso=since_iso, limit=limit)
            state_context = (state.get("context") or "") + "\n\n" + snippet
            return {**state, "context": state_context}
        if action == "get_event":
            event_id = str(args.get("event_id") or "")
            snippet = _get_event(conn, event_id=event_id)
            state_context = (state.get("context") or "") + "\n\n" + snippet
            return {**state, "context": state_context}
        if action == "list_open_loops":
            status = str(args.get("status") or "open")
            limit = int(args.get("limit") or 20)
            snippet = _list_open_loops(conn, status=status, limit=limit)
            state_context = (state.get("context") or "") + "\n\n" + snippet
            return {**state, "context": state_context}
        return state
    finally:
        conn.close()


def _node_final(settings: Settings, state: QaState) -> QaState:
    question = state.get("question") or ""
    context = state.get("context") or ""
    prompt = build_react_final_prompt(question=question, gathered_context=context)
    client = GeminiClient(settings)
    return {**state, "final_answer": client.generate_text(prompt)}


def _search_events(conn, *, query: str, since_iso: str, limit: int) -> str:
    q = f"%{query}%"
    cur = conn.execute(
        """
        SELECT event_id, timestamp, title, COALESCE(body_text, extracted_text, '') AS text
        FROM events
        WHERE timestamp >= ?
          AND (title LIKE ? OR body_text LIKE ? OR extracted_text LIKE ?)
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (since_iso, q, q, q, limit),
    )
    rows = cur.fetchall()
    if not rows:
        return f"[search_events] No matches for query={query!r} since={since_iso}"
    lines = [f"[search_events] query={query!r} since={since_iso}"]
    for r in rows:
        snippet = (r["text"] or "")[:300].replace("\n", " ")
        lines.append(f"- {r['event_id']} | {r['timestamp']} | {r['title']}: {snippet}")
    return "\n".join(lines)


def _get_event(conn, *, event_id: str) -> str:
    cur = conn.execute(
        """
        SELECT event_id, timestamp, title, participants_json, COALESCE(body_text, extracted_text, '') AS text
        FROM events
        WHERE event_id = ?
        LIMIT 1
        """,
        (event_id,),
    )
    row = cur.fetchone()
    if not row:
        return f"[get_event] Not found: {event_id}"
    text = (row["text"] or "")[:2000]
    participants = json.loads(row["participants_json"] or "[]")
    return "\n".join(
        [
            f"[get_event] {row['event_id']} | {row['timestamp']} | {row['title']}",
            f"participants: {participants}",
            f"text: {text}",
        ]
    )


def _list_open_loops(conn, *, status: str, limit: int) -> str:
    cur = conn.execute(
        """
        SELECT loop_id, kind, summary, due_date, evidence_event_ids_json
        FROM open_loops
        WHERE status = ?
        ORDER BY COALESCE(due_date, '9999-12-31') ASC
        LIMIT ?
        """,
        (status, limit),
    )
    rows = cur.fetchall()
    if not rows:
        return f"[list_open_loops] No open loops for status={status!r}"
    lines = [f"[list_open_loops] status={status!r}"]
    for r in rows:
        evidence = ", ".join(json.loads(r["evidence_event_ids_json"] or "[]"))
        due = f" (due {r['due_date']})" if r["due_date"] else ""
        lines.append(f"- {r['loop_id']} [{r['kind']}] {r['summary']}{due} | evidence: {evidence}")
    return "\n".join(lines)
