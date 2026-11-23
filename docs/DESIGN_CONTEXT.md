# Design context

This repo turns operational email into tracked cases.
It drops routine mail with rules, asks a model one yes/no question with a strict JSON answer, and then uses code for identity, matching, routing and writes.
Each email ends as CREATE, UPDATE, REVIEW, IGNORE or HOLD, with one audit record.
The example domain is accounts receivable, where a customer email about a pricing error can block payment.
In the GTM stack it covers the post-sale side: inbound customer email turned into case state that finance or ops can work.
It is a synthetic rebuild of a workflow that runs in production on a low-code stack.
No mail connector, tracker or model provider is wired here.

## Where it sits in the four GTM engineering layers

The four layers come from Everett Berry's (Clay) talk "GTM Engineering: The Technical Bits."

| Layer | What this repo implements |
|---|---|
| Data | `tracker.py:CaseTracker` is the local copy of cases, with a schema check at start-up. `normalization.py:normalize_order_id`, `normalize_customer_id` and `case_key` turn raw IDs into one stable key. `normalization.py:grounded_as` requires each ID to appear in the email next to a label of its kind. `routing.py:known_customer` checks master data. `matching.py:resolve` is the entity resolution step: exact key, then thread memory (`thread_memory.py:ThreadMemory.lookup`), then a unique open order. There is no enrichment. |
| Orchestration | `decision_engine.py:process_event` handles one email per call, and any unexpected error becomes an audited HOLD. `audit_log.py:AuditLog.decided` makes every decision except HOLD final for an event ID. `filters.py:prefilter` stops routine mail before the model. The caller (a scheduled flow, a queue consumer) is outside this repo. There is no fan-out. |
| Agents | One judgment step. `classifier.py:LLMClassifier` wraps any `complete(prompt) -> str` function. `classifier.py:validate_output` rejects wrong types, extra fields, prose and confidence outside 0 to 1. `classifier.py:suspected_injection` sends text that addresses the model to REVIEW. The model has no tools. `RecordedClassifier` and `RuleClassifier` stand in for a live model. |
| Execution | `config.py:Settings.write_to_tracker` defaults to false, so the first run is a dry run. `CaseTracker.create` and `CaseTracker.append_update` are the only writes, and updates append to history. A `TrackerWriteError` becomes HOLD with nothing changed. `routing.py:owner_for` assigns an owner. `summary.py:daily_summary` sends one digest a day instead of one alert per review item. |

Berry's points that show up here:

- **Updates cost money.** `cost.py:monthly_cost` models where the model sits and what that costs.
  The pre-filter exists mainly to keep model calls and the review queue small.
- **Keep agent-written data apart from human-written data.** Updates add history entries.
  Status and owner change only by human action.
  The original description is never overwritten.
- **High bar for error.** A wrong case is a record someone later trusts.
  So the pipeline fails closed: ambiguity, a missing ID, a closed case or an ungrounded ID goes to REVIEW.
- **The human-agent interface.** Every event, including IGNORE and HOLD, has an audit record with the classifier output, normalized IDs, match method and whether a write happened.
  The daily summary lists the review items with reasons.

Berry's points it does not cover: waterfall enrichment, selective refresh, keeping many tools in sync, and outbound deliverability.

## Comparison with LangChain's published GTM agents

- **"How we built LangChain's GTM Agent": trigger, check, gather context, draft for a person to approve.** Partly the same.
  An inbound email is the trigger, the pre-filter and `is_case` are the check, and the tracker and thread memory are the context.
  The difference: nothing is drafted for a customer, so there is no per-item approval.
  Writes are gated by rules and the dry-run switch, and unclear items go to REVIEW.
- **Same post: learn rep style by diffing rep edits.** Not done.
  There are no drafts to edit, and no per-user memory.
- **Same post: constrained tools and structured output schemas.** Same.
  The model returns one JSON object and has no tools.
  `validate_output` rejects anything else, and rejected output goes to REVIEW, never to a write.
- **"How we built LangChain's Paid Media Agent": the model for judgment, code for computation, matching and safeguards.** Same.
  This is the repo's stated design thesis.
  Normalization, grounding, matching, routing and state changes are code.
  The customer directory is the source of truth for whether a customer exists, and uncertain identity is kept as REVIEW, not resolved by a guess.
- **Same post: a path from analysis to action with permissions and post-apply checks, and explicit isolation.** Partly.
  The write permission is one setting, off by default.
  There is no read-back after a write.
  Isolation is one event per execution: each email has its own audit record and its own retry, and `AuditLog.decided` is its completion flag.
- **"How We Built Our Design Agent": hard ordering in code, and deleting rules as models improve.** Ordering: same.
  `decision_engine.py:_process` runs idempotency, pre-filter, classification, normalization, matching, decision and write in a fixed order.
  Deleting rules: not done.
  `suspected_injection` is a pattern list that compensates for the model.
  It is still in place.
  The design notes say the structural limits (no tools, schema, grounding) are what bound the damage.
  The feedback loop is slow only: a replay over labeled emails (`replay.py:run`, `replay.py:score`), run by hand.

This repo does not use LangGraph, Deep Agents or LangSmith.
The package is the standard library only, with no dependencies in `pyproject.toml`.
Each email is one short, deterministic pass with at most one model call.
The hard problems are side effects, identity and idempotency: `SO#038262` and `38262` must be one order, a re-delivered email must not get a second answer, and a failed write must change nothing.
A framework does not solve those on its own.

## Not built here

- No per-user learned memory and no learning from reviewer decisions.
- No tracing or LangSmith.
  The audit log (`AuditLog.to_jsonl`) is the trace, and it lives in memory.
- No live integrations.
  There is no mail connector, tracker adapter or model provider SDK.
- No durable storage for thread memory or the audit log.
- No review UI.
  Review items appear in the daily summary.
- No automated sample review of IGNORE decisions, so a model false negative is not caught downstream.
- Dry run does not simulate its own writes, so dry-run counts are per-event intent.
- Single process, and no scheduler.

These comparisons are my reading of public posts; they are not claims about how those systems work internally beyond what the posts say.
