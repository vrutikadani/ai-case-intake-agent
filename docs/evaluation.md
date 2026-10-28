# Evaluation

**Synthetic replay validation.** Everything here is invented data. None of it is a production metric, and none of it says how often a real model makes mistakes on a real inbox.

## What the replay does

`python evals/replay.py`:

1. Loads 27 emails ([`fixtures/sample_emails.json`](../fixtures/sample_emails.json)), five existing cases and two thread mappings ([`fixtures/sample_cases.json`](../fixtures/sample_cases.json)).
2. Replays each email in delivery order through `process_event` with writes on, one event per call.
3. Uses a recorded model output per email ([`fixtures/recorded_model_outputs.json`](../fixtures/recorded_model_outputs.json)) instead of calling a model. Seven of them are deliberately wrong or broken.
4. Scores the run against human labels ([`evals/expected_results.json`](../evals/expected_results.json)) and writes [`evals/report.json`](../evals/report.json). CI fails if the committed report is out of date.
5. Runs the batch again in dry-run mode and checks that nothing was written.

## The deliberate model failures

| Event | Recorded model behavior | Pipeline outcome |
|---|---|---|
| evt-1014 | False positive: calls an account-status question a case | REVIEW (no identity), not written |
| evt-1015 | False negative: misses a duplicate-billing dispute | IGNORE. A real miss |
| evt-1016 | Real case, confidence 0.55 | REVIEW |
| evt-1017 | Prose instead of JSON | REVIEW (schema) |
| evt-1018 | Returns order 66191, which is not in the email | REVIEW (ungrounded) |
| evt-1019 | Follows an instruction embedded in the email | REVIEW (injection heuristic), not written |
| evt-1020 | Model unavailable | HOLD |

## Metrics

| Metric | Definition | Result |
|---|---|---|
| Decision accuracy | Final decision equals the label | 25 / 27 (0.926) |
| Classification accuracy | Recorded `is_case` equals the label, over emails where the model returned a valid result | 17 / 20 (0.85) |
| Model false positives / negatives | Recorded `is_case` true when label is false, and the reverse | 2 / 1 |
| False-positive writes | Tracker writes for emails labeled "not a case" | 0 |
| Missed cases | Labeled cases that ended as IGNORE | 1 (evt-1015) |
| Duplicate cases created | Creates for a key that existed or was created earlier in the run | 0 |
| Update matching | Emails labeled UPDATE that updated the labeled case | 4 / 4 |
| Deterministic match accuracy | Writes whose `CaseKey` equals the labeled key | 7 / 7 |
| Review rate | REVIEW decisions / events | 11 / 27 (0.41) |
| Discarded before the model | Pre-filter IGNOREs | 4 |
| Dry-run writes | Writes with `WRITE_TO_TRACKER=false` | 0 |

## How to read this

- **Two of the three model mistakes were contained.** The false positive had no identity, and the injection was caught by the heuristic. Neither was written.
- **The false negative was not.** The deterministic layers only act on what the model calls a case. Sampling IGNORE decisions for human review is the mitigation, and it isn't automated here.
- **The review rate is not a forecast.** The fixture set is built from edge cases on purpose. On a real inbox, the share of routine mail and clean cases decides the rate. The dry-run period is how to measure it.
- **Classification accuracy measures the recorded outputs I wrote,** not a model. To evaluate a real model, record its outputs on a labeled sample in the same format and rerun the replay.

## What the replay caught during development

The first replay ([evidence](evidence/replay_before_normalization_fix.txt)) sent the clean new case in scenario 1 to REVIEW: `Cust #062094` was rejected as malformed because the prefix regex matched `c` before `cust`. The tests then found the same bug for `Invoice` and `Customer`, plus a routine-report pattern that was too narrow ([evidence](evidence/tests_before_fix.txt)). A later review found that subject filters dropped human replies to routine mail. All three are fixed, and each has a test.
