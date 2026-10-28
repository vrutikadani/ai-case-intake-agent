"""Customer directory and owner assignment.

The directory is master data: which customer IDs exist and who owns them. A
case is only created for a customer the directory knows, so a number
taken from the wrong place in an email can't become a new customer. A known
customer with no assigned owner goes to the shared queue and is called out in
the daily summary, rather than being given to whoever is first in a list.
"""
from __future__ import annotations

from typing import Optional

SHARED_QUEUE = "ar-shared-queue"

# Synthetic master data matching the fixtures. In a deployment this is a lookup
# against the customer system, cached for the run.
DEFAULT_DIRECTORY: dict[str, Optional[str]] = {
    "10442": "collections-team-a",   # Tidewater Supply Co.
    "15520": "collections-team-a",   # Quarry Lane Builders
    "22610": "collections-team-a",   # Ashgrove Kitchens
    "31877": "collections-team-b",   # Pinehill Print Works
    "47731": "collections-team-b",   # Bellwether Freight
    "58003": "collections-team-b",   # Copperline Foods
    "62094": "credit-desk",          # Saltmarsh Analytics
    "7781": None,                    # Fernway Studios: no owner assigned yet
}


def known_customer(customer_id: str, directory: dict[str, Optional[str]] = DEFAULT_DIRECTORY) -> bool:
    return customer_id in directory


def owner_for(customer_id: str, directory: dict[str, Optional[str]] = DEFAULT_DIRECTORY) -> str:
    return directory.get(customer_id) or SHARED_QUEUE
