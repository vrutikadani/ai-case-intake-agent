"""Synthetic replay: run the labeled fixture set through the pipeline and score it.

The classifier is replayed from recorded outputs (fixtures/recorded_model_outputs.json),
which include deliberate model mistakes. So these numbers describe how the
deterministic layers behave around an imperfect model on invented data. They
are not production metrics.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .classifier import RecordedClassifier
from .config import Settings
from .decision_engine import Context, process_event
from .models import Email
from .summary import daily_summary
from .thread_memory import ThreadMemory
from .tracker import CaseTracker

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
EVALS = Path(__file__).resolve().parents[2] / "evals"


def load_fixtures(base: Optional[Path] = None) -> tuple[list[dict], list[dict], dict, list[dict]]:
    f = base or FIXTURES
    emails = json.loads((f / "sample_emails.json").read_text())
    outputs = json.loads((f / "recorded_model_outputs.json").read_text())
    world = json.loads((f / "sample_cases.json").read_text())
    labels = json.loads(((base.parent / "evals") if base else EVALS).joinpath("expected_results.json").read_text())
    return emails, outputs, world, labels


def to_email(d: dict) -> Email:
    return Email(**{k: v for k, v in d.items() if not k.startswith("_")})


def new_context(world: dict, write: bool = True, clock: str = "2026-10-06T23:00:00+00:00") -> Context:
    return Context(settings=Settings(write_to_tracker=write), classifier=RecordedClassifier({}),
                   tracker=CaseTracker(world["cases"]), threads=ThreadMemory.from_dict(world["threads"]),
                   clock=clock)


def run(write: bool = True, emails=None, outputs=None, world=None):
    if emails is None:
        emails, outputs, world, _ = load_fixtures()
    ctx = new_context(world, write)
    results = []
    for e, o in zip(emails, outputs):
        ctx.classifier = RecordedClassifier({o["event_id"]: o["output"]})
        results.append(process_event(to_email(e), ctx))
    return ctx, results


def score(results, labels, ctx, initial_keys: set[str]) -> dict:
    n = len(results)
    reached_model = [(r, l) for r, l in zip(results, labels) if r.audit.model_called]
    cls_correct = sum(1 for r, l in reached_model
                      if (r.audit.classifier or {}).get("is_case", None) == l["is_case"])
    cls_scored = sum(1 for r, _ in reached_model if r.audit.classifier is not None)
    model_fp = sum(1 for r, l in reached_model if r.audit.classifier and r.audit.classifier["is_case"] and not l["is_case"])
    model_fn = sum(1 for r, l in reached_model if r.audit.classifier and not r.audit.classifier["is_case"] and l["is_case"])

    decision_ok = sum(1 for r, l in zip(results, labels) if r.decision.value == l["decision"])
    writes = [(r, l) for r, l in zip(results, labels) if r.audit.wrote]
    false_writes = [r.audit.event_id for r, l in writes if not l["is_case"]]
    missed = [r.audit.event_id for r, l in zip(results, labels)
              if l["is_case"] and r.decision.value == "IGNORE" and l["decision"] != "IGNORE"]

    keyed = [(r, l) for r, l in zip(results, labels) if r.audit.wrote and l["case_key"]]
    key_ok = sum(1 for r, l in keyed if r.audit.case_key == l["case_key"])

    # duplicate prevention: every event that should update an existing case did, and
    # no case key was ever created twice (the tracker would refuse) or created when it already existed
    should_update = [(r, l) for r, l in zip(results, labels) if l["decision"] == "UPDATE_CASE"]
    upd_ok = sum(1 for r, l in should_update if r.decision.value == "UPDATE_CASE" and r.audit.case_key == l["case_key"])
    created_keys = [r.audit.case_key for r in results if r.audit.wrote and r.decision.value == "CREATE_CASE"]
    duplicates = len(created_keys) - len(set(created_keys)) + sum(1 for k in created_keys if k in initial_keys)

    review = sum(1 for r in results if r.decision.value == "REVIEW")
    summary = daily_summary(ctx.audit.records())
    return {
        "events": n,
        "decision_accuracy": round(decision_ok / n, 3),
        "classification_accuracy": round(cls_correct / cls_scored, 3) if cls_scored else None,
        "model_false_positives": model_fp,
        "model_false_negatives": model_fn,
        "false_positive_writes": false_writes,
        "missed_cases": missed,
        "deterministic_match_accuracy": round(key_ok / len(keyed), 3) if keyed else None,
        "updates_matched_correctly": f"{upd_ok}/{len(should_update)}",
        "duplicate_cases_created": duplicates,
        "review_rate": round(review / n, 3),
        "model_calls": summary["model_calls"],
        "discarded_before_model": summary["ignored_before_model"],
        "mismatches": [{"event_id": r.audit.event_id, "expected": l["decision"], "got": r.decision.value,
                        "scenario": l.get("scenario")}
                       for r, l in zip(results, labels) if r.decision.value != l["decision"]],
    }
