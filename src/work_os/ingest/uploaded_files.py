from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..store.models import (
    CanonicalEvent,
    stable_file_event_id,
    sha256_bytes,
)


@dataclass(frozen=True)
class IngestedFile:
    path: Path
    event: CanonicalEvent


def ingest_uploads(*, uploads_dir: Path) -> list[CanonicalEvent]:
    uploads_dir.mkdir(parents=True, exist_ok=True)
    events: list[CanonicalEvent] = []
    for path in sorted(uploads_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        extracted_text = _extract_text(path)
        content_hash = sha256_bytes(path.read_bytes())
        event_id = stable_file_event_id(path, content_hash)
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        events.append(
            CanonicalEvent(
                event_id=event_id,
                source="uploaded_file",
                source_account=None,
                conversation_id=None,
                timestamp=ts,
                participants=[],
                title=path.name,
                body_text=None,
                extracted_text=extracted_text,
                attachments_or_links=[],
                raw_pointer=str(path),
            )
        )
    return events


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".log"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    # best-effort: treat as text
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PDF extraction requires optional dependency. Install with: `pip install 'work-os[file_extract]'`"
        ) from exc
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def _extract_docx(path: Path) -> str:
    try:
        import docx  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "DOCX extraction requires optional dependency. Install with: `pip install 'work-os[file_extract]'`"
        ) from exc
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs if p.text)
