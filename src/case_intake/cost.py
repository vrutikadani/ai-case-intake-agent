"""Cost model: why filter -> model -> write beats model everything -> write everything.

All inputs are variables. The sample numbers in docs/ are illustrative
assumptions, not measurements from any real inbox.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Volumes:
    emails: int                 # per month
    routine_share: float        # share a cheap rule can discard
    case_share: float           # share of non-routine mail that is a real case


@dataclass(frozen=True)
class UnitCosts:
    filter_cost: float          # per email evaluated by rules (near zero)
    inference_cost: float       # per model call
    workflow_cost: float        # per tracker write / workflow action
    review_cost: float          # per item a person has to look at


def monthly_cost(v: Volumes, c: UnitCosts, prefilter: bool = True, gate_writes: bool = True,
                 review_share: float = 0.25, model_fp_share: float = 0.05) -> dict:
    """Return the cost of one design.

    prefilter=False sends every email to the model.
    gate_writes=False writes a tracker action for every email the model calls a case,
    including its false positives, with no review step.
    """
    routine = v.emails * v.routine_share if prefilter else 0
    model_events = v.emails - routine
    real_cases = v.emails * (1 - v.routine_share) * v.case_share
    false_pos = model_events * model_fp_share
    if gate_writes:
        writes = real_cases * (1 - review_share)
        reviews = real_cases * review_share + false_pos
    else:
        writes = real_cases + false_pos
        reviews = 0
    total = (v.emails * c.filter_cost + model_events * c.inference_cost
             + writes * c.workflow_cost + reviews * c.review_cost)
    return {"model_events": round(model_events), "writes": round(writes), "reviews": round(reviews),
            "bad_writes": 0 if gate_writes else round(false_pos), "monthly_cost": round(total, 2)}
