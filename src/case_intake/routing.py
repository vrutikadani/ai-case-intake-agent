"""Owner assignment: who works a new case.

Deterministic and data-driven: a routing table maps customer IDs (or ranges)
to an owner queue. An unknown customer goes to the shared queue and is called
out in the daily summary, rather than being given to whoever is first in a list.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    low: int
    high: int
    owner: str


DEFAULT_ROUTES = (
    Route(10000, 29999, "collections-team-a"),
    Route(30000, 59999, "collections-team-b"),
    Route(60000, 99999, "credit-desk"),
)


def owner_for(customer_id: str, routes: tuple[Route, ...] = DEFAULT_ROUTES,
              default: str = "ar-shared-queue") -> str:
    n = int(customer_id)
    for r in routes:
        if r.low <= n <= r.high:
            return r.owner
    return default
