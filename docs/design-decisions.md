# Design decisions

## Principles

1. **LLM for judgment, rules for exactness.** "Is this a real blocking issue?" is judgment. "Is `SO#038262` the same order as `38262`?" is not. The model never decides identity, matching, routing or state.
2. **Fail closed when identity is uncertain.** No full key, more than one candidate, a closed case, an untrusted thread, or an identifier the email doesn't contain: REVIEW. A missing identifier is never filled in.
3. **Filter cheap noise before expensive inference.** Auto-replies, reports and remittances never reach the model. That saves cost and latency, and removes a whole class of false positives.
4. **One event per execution.** Each email is processed on its own, with its own audit record and its own retry.
5. **State must be auditable.** Every event, including IGNORE and HOLD, leaves a record that explains the decision.
6. **Preserve history rather than overwrite it.** Updates append. Status and owner change only by human action.
7. **Design for operational ownership.** Dry-run mode, a daily summary, an explicit review queue and a shared-queue fallback for routing exist because someone has to run this every day.
8. **Cost is part of architecture.** Where the model sits in the pipeline decides how many calls you pay for and how many items a person has to review.

## Decisions and their alternatives

| Decision | Alternative considered | Why this one |
|---|---|---|
| Binary `is_case`, biased toward "no" | Ask the model to choose a case category | A forced category gives every email a category. The yes/no question has a safe default |
| Model returns raw identifiers; code normalizes | Ask the model for normalized IDs | The model's formatting drifts. Normalization has to be identical on every run |
| Grounding check on identifiers | Trust the extraction | Models occasionally produce plausible numbers that aren't in the text, and an email can try to steer them |
| `customer_id\|order_id` key | Order number alone | Order and invoice numbers can collide across entities (scenario 7). The customer ID disambiguates |
| Order-only match allowed when unique | Always require a full key for updates | Many follow-ups name only the invoice. Unique match is safe; ambiguity goes to review |
| Order-only can never CREATE | Create with an unknown customer | A case without a customer can't be routed or deduplicated later |
| Thread memory with TTL and drift checks | No thread memory / unlimited memory | Without it, most replies go to review. Unlimited, old threads get reused for new topics |
| Closed cases go to review | Reopen automatically | Reopening changes status, which is a human decision |
| Default `WRITE_TO_TRACKER=false` | Default to writing | The first run against a real tracker should be a dry run |
| Daily summary | Alert per review item | Per-item alerts become noise and get ignored |
| HOLD on model outage or write failure | Send to review | These are transient. Retrying is correct, and idempotency makes it safe |

## Known limits of the design

- **Dry run doesn't simulate its own writes.** Each event is evaluated against the tracker as it is. A follow-up to a case that the same dry run "would have created" goes to REVIEW, and a re-delivered event is proposed twice. Dry-run counts are per-event intent, not a forecast of a live day.
- **The injection heuristic is a pattern list.** It catches obvious attempts. The structural defenses (no tools, schema, grounding, deterministic matching) are what bound the damage.
- **A false negative is unrecoverable downstream.** If the model says "not a case", nothing later re-examines it. A periodic sample review of IGNORE decisions is the mitigation; it isn't automated here.
- **Routing is a static table.** Real ownership changes (leave, reassignment) need to be reflected in the table.
