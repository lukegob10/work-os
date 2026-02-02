# Work OS (Pilot) — Email + Files (Python)

Local-first “personal work OS” that ingests email + uploaded files into a canonical event store, then runs a **bounded ReAct-style** analysis loop using **LangGraph** and **`genai.Client`** (Gemini).

## Quickstart
1) Create a venv and install:
   - Windows (PowerShell):
     - `py -m venv .venv`
     - `.venv\\Scripts\\Activate.ps1`
   - macOS/Linux:
     - `python3 -m venv .venv`
     - `source .venv/bin/activate`
   - Install: `pip install -e .`
2) Configure env:
   - `cp .env.example .env` and set `GEMINI_API_KEY`
3) Put data in:
   - Emails: Outlook (win32) or `data/local_emails/*.json`
   - Files: `data/uploads/*`
4) Run daily pipeline (LangGraph):
   - `work-os run-daily --since 7d`

Outputs land in `data/briefs/` and everything is stored in `data/work_os.db`.

## Local email JSON format (current ingestion)
Drop `*.json` files in `data/local_emails/` with this shape:

```json
{
  "source": "email_inbox",
  "message_id": "unique-id",
  "conversation_id": "thread-id",
  "timestamp": "2026-02-01T18:30:00Z",
  "from": "alice@example.com",
  "to": ["me@example.com"],
  "subject": "Subject line",
  "body": "Email body text"
}
```

## Outlook ingestion (Windows / win32com)
This uses the signed-in Outlook desktop profile (no separate credential config in this app).

1) Install Outlook deps:
   - `pip install -e ".[outlook]"`
   - Note: requires **Outlook (classic)** desktop. **New Outlook** does not expose the COM automation interface.
2) List available mailboxes:
   - `work-os outlook-accounts`
3) Ingest from Outlook:
   - `work-os ingest --email-mode outlook --since 7d`
   - or run end-to-end: `work-os run-daily --email-mode outlook --since 7d`

Optional account selection:
- Set `WORK_OS_OUTLOOK_ACCOUNT` (SMTP address or a unique substring of the display name), or pass `--outlook-account`.

## Rules-based filtering (before AI)
Threading + extraction only process non-noise emails. Configure patterns via `.env`:
- `WORK_OS_FILTER_EMAIL_SUBJECT_DENY`
- `WORK_OS_FILTER_EMAIL_PARTICIPANT_DENY`
- `WORK_OS_FILTER_EMAIL_SUBJECT_ALLOW`
- `WORK_OS_FILTER_EMAIL_PARTICIPANT_ALLOW`
