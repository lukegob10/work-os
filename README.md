# Work OS (Pilot) — Email + Files (Python)

Local-first “personal work OS” that ingests email + uploaded files into a canonical event store, then runs a **bounded ReAct-style** analysis loop using **LangGraph** and **`genai.Client`** (Gemini).

## Quickstart
1) Create a venv and install:
   - `python3 -m venv .venv && source .venv/bin/activate`
   - `pip install -e .`
2) Configure env:
   - `cp .env.example .env` and set `GEMINI_API_KEY`
3) Put data in:
   - Emails: `data/local_emails/*.json`
   - Files: `data/uploads/*`
4) Run daily pipeline (LangGraph):
   - `python -m work_os run-daily --since 7d`

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

