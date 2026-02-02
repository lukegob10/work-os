from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..store.models import CanonicalEvent, stable_email_event_id


class OutlookIngestError(RuntimeError):
    pass


OL_FOLDER_INBOX = 6
OL_FOLDER_SENT_MAIL = 5


@dataclass(frozen=True)
class OutlookMailbox:
    display_name: str
    smtp_address: str | None


def list_outlook_mailboxes() -> list[OutlookMailbox]:
    namespace = _get_mapi_namespace()
    accounts = getattr(namespace.Session, "Accounts", None)
    out: list[OutlookMailbox] = []
    if not accounts:
        return out
    for i in range(1, accounts.Count + 1):
        account = accounts.Item(i)
        out.append(
            OutlookMailbox(
                display_name=str(getattr(account, "DisplayName", "") or ""),
                smtp_address=_safe_str(getattr(account, "SmtpAddress", None)),
            )
        )
    return out


def ingest_outlook_mail(
    *,
    since_iso: str,
    include_inbox: bool = True,
    include_sent: bool = True,
    account_hint: str | None = None,
    max_per_folder: int | None = None,
) -> list[CanonicalEvent]:
    since_dt = _parse_iso_datetime(since_iso)
    namespace = _get_mapi_namespace()
    store, source_account = _select_store(namespace, account_hint)

    events: list[CanonicalEvent] = []
    if include_inbox:
        inbox = store.GetDefaultFolder(OL_FOLDER_INBOX)
        events.extend(
            _ingest_folder(
                folder=inbox,
                source="email_inbox",
                source_account=source_account,
                since_dt_utc=since_dt,
                max_items=max_per_folder,
                time_attr="ReceivedTime",
                sort_prop="[ReceivedTime]",
            )
        )
    if include_sent:
        sent = store.GetDefaultFolder(OL_FOLDER_SENT_MAIL)
        events.extend(
            _ingest_folder(
                folder=sent,
                source="email_sent",
                source_account=source_account,
                since_dt_utc=since_dt,
                max_items=max_per_folder,
                time_attr="SentOn",
                sort_prop="[SentOn]",
            )
        )
    return events


def _get_mapi_namespace():
    if sys.platform != "win32":
        raise OutlookIngestError("Outlook win32 ingestion requires Windows (sys.platform == 'win32').")
    try:
        import pythoncom  # type: ignore
        import pywintypes  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise OutlookIngestError(
            "pywin32 is not installed. Install with: `pip install 'work-os[outlook]'`"
        ) from exc

    pythoncom.CoInitialize()
    progids = [
        "Outlook.Application",
        "Outlook.Application.16",
        "Outlook.Application.15",
        "Outlook.Application.14",
    ]
    last_exc: pywintypes.com_error | None = None
    outlook = None
    for progid in progids:
        try:
            outlook = win32com.client.Dispatch(progid)
            break
        except pywintypes.com_error as exc:
            last_exc = exc
            outlook = None

    if outlook is None:
        if last_exc is not None and getattr(last_exc, "hresult", None) == -2147221005:
            raise OutlookIngestError(
                "Could not create the Outlook COM object (Outlook.Application). "
                "This usually means Outlook desktop (classic) isn't installed, "
                "you're using the New Outlook client (no COM automation), or Office/Outlook COM registration is broken. "
                "Fixes: install/launch Outlook (classic), run `outlook.exe /regserver`, or Repair Office."
            ) from last_exc
        raise OutlookIngestError(f"Outlook COM error: {last_exc}") from last_exc
    return outlook.GetNamespace("MAPI")


def _select_store(namespace, account_hint: str | None):
    if not account_hint:
        store = getattr(namespace, "DefaultStore", None)
        if store is None:
            raise OutlookIngestError("Could not access Outlook DefaultStore.")
        display = _safe_str(getattr(store, "DisplayName", None))
        return store, display

    account_hint_norm = account_hint.strip().lower()
    accounts = getattr(namespace.Session, "Accounts", None)
    if not accounts:
        raise OutlookIngestError("No Outlook accounts found in this profile/session.")
    for i in range(1, accounts.Count + 1):
        account = accounts.Item(i)
        display = str(getattr(account, "DisplayName", "") or "")
        smtp = _safe_str(getattr(account, "SmtpAddress", None))
        haystack = " ".join([display, smtp or ""]).lower()
        if account_hint_norm in haystack:
            store = getattr(account, "DeliveryStore", None)
            if store is None:
                raise OutlookIngestError(f"Matched account {display!r} but has no DeliveryStore.")
            return store, smtp or display
    raise OutlookIngestError(
        f"Could not find Outlook account matching {account_hint!r}. Try one of: "
        + ", ".join(repr(a.display_name) for a in list_outlook_mailboxes())
    )


def _ingest_folder(
    *,
    folder,
    source: str,
    source_account: str | None,
    since_dt_utc: datetime,
    max_items: int | None,
    time_attr: str,
    sort_prop: str,
) -> list[CanonicalEvent]:
    items = folder.Items
    try:
        items.Sort(sort_prop, True)
    except Exception:
        pass

    store_id = _safe_str(getattr(getattr(folder, "Store", None), "StoreID", None))
    events: list[CanonicalEvent] = []

    item = items.GetFirst()
    while item:
        if max_items is not None and len(events) >= max_items:
            break

        if not _is_mail_item(item):
            item = items.GetNext()
            continue

        dt = _safe_datetime(getattr(item, time_attr, None))
        if dt is not None:
            dt_utc = _to_utc(dt)
            if dt_utc < since_dt_utc:
                break
        else:
            dt_utc = datetime.now(timezone.utc).replace(microsecond=0)

        entry_id = _safe_str(getattr(item, "EntryID", None)) or ""
        if not entry_id:
            item = items.GetNext()
            continue
        subject = _safe_str(getattr(item, "Subject", None)) or "(no subject)"
        body = _safe_str(getattr(item, "Body", None)) or ""

        conversation_id = _safe_str(getattr(item, "ConversationID", None))
        sender = _best_sender_string(item)
        participants = _normalize_participants(
            [sender, _safe_str(getattr(item, "To", None)), _safe_str(getattr(item, "CC", None))]
        )

        attachments = _attachments_metadata(item)
        raw_pointer = f"outlook:{store_id}:{entry_id}" if store_id else f"outlook::{entry_id}"
        event_id = stable_email_event_id(source, entry_id)

        events.append(
            CanonicalEvent(
                event_id=event_id,
                source=source,  # type: ignore[arg-type]
                source_account=source_account,
                conversation_id=conversation_id,
                timestamp=dt_utc.isoformat(),
                participants=participants,
                title=subject,
                body_text=body,
                extracted_text=None,
                attachments_or_links=attachments,
                raw_pointer=raw_pointer,
            )
        )
        item = items.GetNext()

    return events


def _is_mail_item(item) -> bool:
    message_class = _safe_str(getattr(item, "MessageClass", None)) or ""
    if message_class.startswith("IPM.Note"):
        return True
    try:
        return int(getattr(item, "Class", 0)) == 43  # olMail
    except Exception:
        return False


def _best_sender_string(item) -> str:
    sender = _safe_str(getattr(item, "SenderEmailAddress", None))
    if sender and "@" in sender:
        return sender
    name = _safe_str(getattr(item, "SenderName", None))
    return sender or name or ""


def _attachments_metadata(item) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        attachments = getattr(item, "Attachments", None)
        if not attachments:
            return out
        for i in range(1, attachments.Count + 1):
            a = attachments.Item(i)
            filename = _safe_str(getattr(a, "FileName", None)) or ""
            size = getattr(a, "Size", None)
            record: dict[str, Any] = {"filename": filename}
            if isinstance(size, int):
                record["size"] = size
            out.append(record)
    except Exception:
        return out
    return out


def _normalize_participants(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if not raw:
            continue
        for token in str(raw).replace(",", ";").split(";"):
            token = token.strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
    return out


def _parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0)


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    try:
        s = str(value)
    except Exception:
        return None
    s = s.strip()
    return s or None


def _safe_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


def _to_utc(value: datetime) -> datetime:
    try:
        return value.astimezone(timezone.utc).replace(microsecond=0)
    except ValueError:
        return value.astimezone(timezone.utc).replace(microsecond=0)
