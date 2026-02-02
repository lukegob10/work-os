# Project Plan — Personal Work OS (Pilot): Outlook Email + Uploaded Files (Python)

## Objective
Build a **personal** work assistant that ingests:
1) Outlook email (corporate domain)  
2) Uploaded files (manual upload into the tool)

…and produces:
- **Daily “open loops”** (questions/actions you owe)
- **7‑day executive brief** (high-level changes, blockers, decisions needed, open questions)
- **On-demand Q&A** grounded in stored evidence (message/file citations)

**Explicit non-goals (for V1):**
- Teams ingestion
- Org-wide monitoring of other people’s mailboxes
- Auto-sending emails or taking irreversible actions

---

## Data Sources (V1 = 4 “feeds”)
All four are still “email + files,” but separated because they have different semantics and retrieval patterns:

### Email feeds
1. **Inbox** (primary inbound work requests)
2. **Sent Items** (closure detection, commitments you made, proof you replied)
3. **Project folders / rules-based folders** (optional, but valuable for noise reduction)
4. **Uploaded files** (manual uploads: decks, specs, notes, exports)

> The third email feed can be skipped in the first pilot if you don’t use folders; keep the interface so it’s easy to add later.

---

## Final Open Questions (Decisions) + Recommended Defaults
These are the “gating” choices that determine the architecture. Defaults below are safe for a pilot.

### 1) Auth / Access Method
- **Decision:** Microsoft Graph delegated access (recommended) vs IMAP fallback  
- **Default:** **Graph delegated** (your user only)

### 2) Lookback and Sync
- **Decision:** “Always last 7 days” only vs last 7 days + incremental cursor/delta  
- **Default:** **Both**  
  - fetch last 7 days each run (safety net)  
  - also maintain a cursor for efficiency (delta)

### 3) Storage and Retention
- **Decision:** store message bodies locally? how long?  
- **Default:**  
  - store **raw bodies** for **180 days**  
  - store **metadata + derived signals** for **2 years**  
  - store **weekly briefs** indefinitely

### 4) Privacy / Redaction for LLM Calls
- **Decision:** send full bodies to LLM or redact?  
- **Default:**  
  - redact common PII patterns (phone, addresses)  
  - allow full text for your mailbox only  
  - keep a config switch: `LLM_BODY_MODE = full|snippet|redacted`

### 5) Trust Policy
- **Decision:** are citations mandatory?  
- **Default:** **Yes**  
  - any extracted decision/action must include `evidence_event_ids`  
  - weekly brief bullets link back to message/thread IDs (and file hashes/paths)

### 6) Action Scope
- **Decision:** do we auto-create tasks/reminders?  
- **Default:** **No** (draft-only queue)

If you disagree with any default, change it in config; the rest of the plan remains valid.

---

## High-Level Architecture
### Ingestion
- Pull email via Graph:
  - fetch messages for date range and/or delta
  - store minimal canonical record per message
- Accept uploaded files:
  - store file + extracted text (PDF/DOCX/etc.) + metadata

### Canonical Event Model (single format for all sources)
**CanonicalEvent**
- `event_id` (stable primary key)
- `source` = `email_inbox | email_sent | email_folder | uploaded_file`
- `source_account` (mailbox identity)
- `conversation_id` (thread id where available)
- `timestamp`
- `participants` (emails/ids)
- `title` (subject/filename)
- `body_text` (for email) OR `extracted_text` (for files)
- `attachments_or_links` (metadata only)
- `raw_pointer` (how to re-fetch: Graph message id / local file path)

### Derived Records
**Thread**
- `conversation_id`
- `thread_title`
- `event_ids[]`
- `last_activity_at`

**OpenLoop** (first-class “things you owe / unresolved”)
- `loop_id`
- `type`: `question | action | decision_needed | followup`
- `owner` (you)
- `project` (nullable; can be `unknown`)
- `status`: `open|closed`
- `created_at`, `last_touched_at`, `due_date` (nullable)
- `evidence_event_ids[]` (**required**)

**ProjectState** (lightweight)
- `project_id`, `name`
- `status` (optional)
- `deliverables[]` (optional/manual)
- `open_loops_count`
- `last_activity_at`
- `notes` (confirmed facts, key links)

---

## LLM Usage (via `genai.Client`) — Strict and Bounded
### Where LLM is used
1) Thread-level **signal extraction** → structured JSON with citations  
2) Thread-level **summaries** for compression (optional)  
3) Brief composition **from verified signals only**

### What LLM is NOT used for (V1)
- project assignment (start deterministic + your labels)
- loop closure (require explicit reply evidence or manual close)
- anything without citations

### Hard Constraints
- JSON-only output with schema
- `evidence_event_ids` required for actions/decisions
- low temperature (e.g., 0.2)
- drop uncertain items rather than guessing

---

## ReAct-style “Worker” Loop (Bounded)
This is a controlled ReAct agent (tool-first, auditable), not a free-form inbox rummager.

### Daily job
1) **Act:** ingest (email feeds + uploaded files)
2) **Act:** normalize, dedupe, thread
3) **Act:** extract signals (LLM) → OpenLoops + decisions + risks
4) **Act:** verify constraints (citations, date window, duplicates)
5) **Act:** update ProjectState
6) **Final:** generate:
   - `daily_open_loops.md`
   - optional `draft_replies_queue.md`

### Weekly job
1) query signals from last 7 days
2) rank threads/projects deterministically
3) assemble `weekly_brief.md` with evidence links

### On-demand Q&A
- retrieve relevant threads/signals
- fetch more only if needed
- answer with citations

---

## Data Storage (Pilot)
**SQLite** for pilot (fast to build, easy to inspect), with upgrade path to Postgres.

Tables (minimum):
- `events` (CanonicalEvent)
- `threads`
- `signals` (decisions/actions/questions/risks)
- `open_loops`
- `projects`
- `labels` (your manual project tagging)
- `briefs` (weekly outputs)
- `audit_log` (what ran, when, counts, errors)

---

## CLI Commands (Minimum)
- `ingest --since 7d` (email + files)
- `threads --since 7d`
- `extract --since 7d`
- `open-loops --since 30d`
- `brief --since 7d --out briefs/weekly_YYYY-MM-DD.md`
- `label --thread <conversation_id> --project "Project X"`
- `close-loop --loop <id> --note "resolved via reply" --evidence <event_id>`

---

## Ranking Heuristics (Deterministic)
Score threads higher if they contain:
- deadlines / explicit dates
- “decision needed” language
- repeated follow-ups (“circling back”, “ping”)
- many participants
- high volume in short window

Score lower if:
- newsletters/automations
- FYI-only threads
- duplicates/forwards

---

## Work Breakdown Structure (WBS) — V1
### Phase 0 — Repo + Config (Day 0–1)
- repo scaffold, config, logging
- local secrets handling (.env)
**Exit:** `python -m tool --help` works

### Phase 1 — Email Ingestion (Days 1–3)
- Graph auth (delegated)
- fetch Inbox + Sent
- store to SQLite; dedupe
**Exit:** repeatable 7-day ingestion with stable IDs

### Phase 2 — Uploaded Files Ingestion (Days 3–5)
- file upload CLI/dir watcher
- extract text (pdf/docx/txt)
- store events + metadata
**Exit:** file is searchable and citeable

### Phase 3 — Threading + Noise Filters (Days 5–7)
- group by conversation_id (fallback: normalized subject)
- exclude automated noise
**Exit:** thread list looks reasonable for a week

### Phase 4 — Signal Extraction + OpenLoops (Days 7–12)
- LLM extraction schema + verification
- create OpenLoops
- closure heuristics (conservative)
**Exit:** daily open loops list is accurate enough to use

### Phase 5 — Weekly Brief Generator (Days 12–15)
- brief template + ranking
- citations everywhere
**Exit:** weekly brief is “sendable” internally

### Phase 6 — Feedback Loop (Days 15–20)
- manual project labeling
- unknown bucket workflow
**Exit:** unknown bucket shrinks week over week

---

## Deliverables
- `briefs/weekly_*.md` (weekly executive brief)
- `briefs/daily_open_loops_*.md`
- SQLite DB + minimal dashboard/inspection CLI
- `config.yml` with:
  - lookback window
  - retention
  - redaction mode
  - source toggles
  - model choice

---

## Acceptance Criteria (V1)
A single command produces a 7-day brief that:
- lists top changes, decisions needed, blockers/risks, open questions
- includes a **“You Owe”** section (OpenLoops) with age + due date
- contains evidence links/IDs for all claims
- runs locally in <5 minutes for a typical week

---

## Repo Skeleton (Suggested)
```
work_os/
  README.md
  pyproject.toml
  .env.example
  src/
    config.py
    llm/
      client.py
      schemas.py
      prompts.py
    ingest/
      graph_email.py
      uploaded_files.py
    store/
      db.py
      models.py
    process/
      threading.py
      filters.py
      extract.py
      verify.py
      loops.py
    report/
      daily.py
      weekly.py
    cli.py
  data/
    work_os.db
    uploads/
    briefs/
```

---

## Immediate Next Step (concrete)
Build **Phase 1** end-to-end first:
- ingest Inbox + Sent (7 days) → SQLite → list threads

Once that is stable, add uploaded files (Phase 2). Everything else depends on a clean canonical event store.
