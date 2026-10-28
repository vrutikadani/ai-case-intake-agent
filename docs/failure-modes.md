# Failure modes

For each: how it is detected, what the system does, the mitigation, and whether a person is needed. "Tested" points to the test that exercises it.

| # | Failure | Detection | Behavior | Mitigation | Human? |
|---|---|---|---|---|---|
| 1 | **AI false positive** (routine email called a case) | Not directly; contained by later gates | Without a full, grounded identity: REVIEW. With one: a case is created | Binary question biased toward "no"; confidence threshold; identity gates; review-list sampling | Yes, if it reaches review. Tested: `evt-1014` in replay |
| 2 | **AI false negative** (real case called "not a case") | Not detected automatically | IGNORE; the audit record keeps the classifier reason | Periodic sample of IGNORE decisions; customer follow-ups usually re-trigger | Yes (sampling). Replay `evt-1015` |
| 3 | **Malformed identifiers** (`7O315`, `SO#12`) | Normalizer rejects anything that isn't a clean number of the right length | ID dropped and named in the reason; usually REVIEW | Strict normalization; tests for each format | Yes. `test_malformed_identifier_is_named_in_the_review_reason` |
| 4 | **Duplicate cases** (`SO#038262` vs `38262`) | Normalized `CaseKey`; tracker refuses an existing key | UPDATE the existing case | Normalization before matching | No. `test_differently_formatted_ids_update_instead_of_duplicating` |
| 5 | **Ambiguous match** (two open cases share an order number) | Order-only match returns more than one candidate | REVIEW with the candidate keys | Full key preferred; ambiguity never auto-resolved | Yes. `test_ambiguous_order_match_goes_to_review` |
| 6 | **Stale thread mapping** | Mapping older than the TTL (21 days) | Mapping ignored; usually REVIEW | TTL; mapping refreshed on every write | Yes. `test_stale_thread_memory_is_not_trusted` |
| 7 | **Thread drift to another invoice** | Message in a mapped thread names a different order | Mapping ignored; resolved on its own identifiers or REVIEW | Drift check before reuse | Yes. `test_thread_drift_to_another_order_goes_to_review` |
| 8 | **Missing tracker schema** | Schema checked once when the tracker is opened | Run refuses to start; no event processed | Fail before the first email, not halfway through a batch | Yes (fix config). `CaseTracker` raises `TrackerSchemaError` |
| 9 | **Unavailable model** | Adapter raises (timeout, quota, network) | HOLD; nothing written; event retried | Retry with backoff in the orchestrator; HOLD count in the daily summary | Only if it persists. `test_model_unavailable_holds` |
| 10 | **Malformed structured output** | Schema validator (types, ranges, JSON) | REVIEW | Strict schema; fenced JSON accepted, prose rejected | Yes. `test_malformed_model_output_goes_to_review` |
| 11 | **Downstream write failure** | Tracker raises on write | HOLD; tracker and thread memory unchanged | Retry is safe because of idempotency | Only if it persists. `test_write_failure_holds_and_retry_succeeds` |
| 12 | **Partial execution** (crash mid-run) | Missing audit record for a received event | The write is the last step and thread memory is updated only after it succeeds, so a crash before the write leaves no partial state | One event per execution; orchestrator re-delivers unacknowledged events | No |
| 13 | **Retry duplication** (same event delivered twice) | Audit log shows the event ID already wrote | Second delivery IGNORE; history has one entry | Idempotency check on event ID; tracker ignores a repeated event ID in history | No. `test_redelivered_event_is_applied_once` |
| 14 | **Incorrect ownership** | Customer outside the routing table | Assigned to the shared queue and listed in the daily summary | Routing table maintained as data; no "first person in the list" fallback | Yes (assign). `test_unknown_customer_routes_to_shared_queue` |
| 15 | **Prompt injection in the email body** | Heuristic for text addressed to the model; grounding; schema | Any CREATE/UPDATE becomes REVIEW; reason quotes the text | Prompt fences the email as untrusted data and the body cannot close the fence; the model has no tools; its output passes the same deterministic gates | Yes. `test_prompt_injection_is_never_written`, replay `evt-1019` |

## Prompt injection

Instructions inside an email are content, not system instructions. The defenses are layered, and none relies on the model behaving:

1. **The prompt** tells the model the email is untrusted data and must not be followed. The email sits between markers, and the body is rewritten so it cannot contain the closing marker (`test_prompt_template_fences_the_email`).
2. **The model has no tools.** It can only return one JSON object. It cannot send mail, write to the tracker or call anything.
3. **The output is validated** against a fixed schema. Extra fields and prose are rejected.
4. **Identifiers must be grounded** in the email text, so an instruction can't invent a target case out of nowhere.
5. **Identity, matching and writes are code.** A fooled classifier can at most propose a case that still has to pass every gate.
6. **Text addressed to the model** ("ignore previous instructions", "set is_case to true", a line starting `system:`) forces REVIEW for any proposed write, with the matched text quoted in the reason.

Layer 6 is a pattern list and will miss creative phrasing. Layers 2 to 5 are why a missed injection is bounded: the worst case is a wrong case proposal for an identity that literally appears in the email, which still needs a full key to be created.
