# Architecture

## Flow

```
Email / event
  │
  ├─ Idempotency ─────────── event ID already decided (anything but HOLD)? → IGNORE (no model call)
  │
  ├─ Pre-filter ──────────── auto-reply header · non-case sender · routine subject (original messages only)
  │                          → IGNORE (no model call)
  │
  ├─ Classifier (model) ──── one JSON object, validated against a schema (no extra fields)
  │                          unavailable → HOLD · invalid → REVIEW · not a case → IGNORE
  │                          text addressed to the model → REVIEW · confidence < 0.75 → REVIEW
  │
  ├─ Normalizer (code) ───── customer and order IDs → digits only; malformed → dropped and named
  │                          each ID must appear next to a label of its kind (grounding) → else REVIEW
  │                          customer == order, or customer not in the directory → REVIEW
  │
  ├─ Identity resolution ─── 1. CaseKey customer|order: existing open case → UPDATE · closed → REVIEW
  │                             none → CREATE, unless the order is open under another customer → REVIEW
  │   (code)                 2. thread memory (TTL, no drift, case open)    → UPDATE
  │                          3. order only, exactly one open case            → UPDATE · more than one → REVIEW
  │                          4. otherwise                                     → REVIEW
  │
  ├─ Write ───────────────── WRITE_TO_TRACKER=false → log only · write error → HOLD (nothing changed)
  │                          CREATE: new case, owner from routing table · UPDATE: append to history
  │                          on success: remember thread → case
  │
  └─ Audit record ────────── exactly one per event, whatever the outcome (unexpected errors → audited HOLD)
                                      │
                               Daily summary
```

## Modules

| Module | Responsibility | Typical low-code equivalent (Copilot Studio / Power Automate) |
|---|---|---|
| `filters.py` | Rules that discard routine mail before inference | Trigger conditions and early "terminate" steps |
| `classifier.py` | Prompt, schema validation, model adapter, injection heuristic | The AI prompt action with a JSON output schema |
| `normalization.py` | Identifier normalization, `CaseKey`, grounding | Expressions on the extracted fields |
| `thread_memory.py` | Thread → case mapping with limits | A lookup on the conversation ID stored with the case |
| `matching.py` | Identity resolution | Filter queries against the tracker list |
| `tracker.py` | Case store: schema check once, append-only updates | The tracker list (create item / update item) |
| `routing.py` | Customer directory and owner assignment | Customer master lookup and assignment table |
| `decision_engine.py` | `process_event`: one event per call | One flow run per incoming email |
| `audit_log.py` | One structured record per event | A log list |
| `summary.py` | Daily digest | A scheduled summary email |

## Contracts

**Classifier output** (anything else is rejected):

```json
{
  "is_case": true,
  "reason": "customer is withholding payment over an invoice amount that differs from the quote",
  "case_type": "pricing_discrepancy",
  "customer_name": "Saltmarsh Analytics",
  "customer_id": "Cust #062094",
  "order_or_invoice_id": "SO-0081537",
  "summary": "Invoice is $15,850 vs quoted $14,200; payment on hold pending a corrected invoice.",
  "confidence": 0.93
}
```

`case_type` outside the allowed list becomes `other`. Identifiers are returned raw; normalization happens in code.

**Case:** `case_key`, `customer_id`, `order_id`, `customer_name`, `case_type`, `owner`, `status`, `created_at`, `updated_at`, `history[]` (each entry: `at`, `event_id`, `summary`). The tracker checks these fields once at start-up and refuses to run if any are missing.

**Audit record:** `timestamp`, `event_id`, `thread_id`, `decision`, `reason`, `prefilter_rule`, `classifier`, `normalized_customer_id`, `normalized_order_id`, `case_key`, `matched_case`, `match_method`, `owner`, `wrote`, `dry_run`, `review_reason`, `model_called`.

## Why one event per execution

The orchestrator (a scheduled flow, a queue consumer, a webhook) calls `process_event` once per email. The engine holds no batch state between calls except what is persisted: the tracker, thread memory and the audit log. A crash affects one email, a retry is one email, and the audit log has exactly one record per run.

## What a production deployment adds

These are outside this repository: a real mail connector and tracker adapter, durable storage for thread memory and the audit log, secrets management for the model key, a review UI, alerting on HOLD volume, and a dry-run period against the real inbox before writes are enabled.
