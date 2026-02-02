from __future__ import annotations

from datetime import datetime

from ..store.models import OpenLoopRecord


def render_daily_open_loops_md(*, loops: list[OpenLoopRecord], since_iso: str) -> str:
    lines: list[str] = []
    lines.append(f"# Daily Open Loops")
    lines.append("")
    lines.append(f"Since: `{since_iso}`")
    lines.append("")
    if not loops:
        lines.append("_No open loops found._")
        lines.append("")
        return "\n".join(lines)
    for loop in loops:
        due = f" (due {loop.due_date})" if loop.due_date else ""
        lines.append(f"- [{loop.kind}] {loop.summary}{due}")
        lines.append(f"  - evidence: {', '.join(loop.evidence_event_ids)}")
    lines.append("")
    return "\n".join(lines)

