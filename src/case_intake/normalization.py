"""Exact identifier handling. None of this is left to the model.

The model is good at finding "the order number" in messy text and bad at
producing the same string twice. Everything that has to be exact (what counts
as the same order, the case key, whether an identifier is real) is decided
here, by code that returns the same answer every time.
"""
from __future__ import annotations

import re
from typing import Optional

# Labels people actually type in front of identifiers, longest alternative first.
# Regex alternation takes the first branch that matches: with "c" before
# "customer", "Customer 10442" became "ustomer 10442" and was rejected (found
# by the replay). "PO" is deliberately absent: a customer's purchase-order
# number is a different ID space from our order numbers.
ORDER_LABEL = r"(?:sales\s*order|invoice|order|inv|ord|so)"
CUSTOMER_LABEL = r"(?:customer|account|cust|acct|c)"
_SUFFIX = r"\s*(?:no\.?|number|id)?\s*[#:.\-\s]*"

_ORDER_PREFIX = re.compile(rf"^\s*{ORDER_LABEL}{_SUFFIX}", re.IGNORECASE)
_CUSTOMER_PREFIX = re.compile(rf"^\s*{CUSTOMER_LABEL}{_SUFFIX}", re.IGNORECASE)

ORDER_MIN_DIGITS, ORDER_MAX_DIGITS = 4, 10
CUSTOMER_MIN_DIGITS, CUSTOMER_MAX_DIGITS = 4, 8


def _digits_core(raw: str, prefix: re.Pattern, lo: int, hi: int) -> Optional[str]:
    s = raw.strip()
    for _ in range(2):                       # "Customer ID: C-10442" has two labels
        s = prefix.sub("", s, count=1)
    s = s.strip()
    if not s.isdigit():
        return None            # letters, extra digit groups ("38262-1") or symbols: not trusted
    s = s.lstrip("0")
    if not (lo <= len(s) <= hi):
        return None
    return s


def normalize_order_id(raw: Optional[str]) -> Optional[str]:
    """'SO#038262', 'so 38262', 'Order #: 038262' -> '38262'. Malformed -> None."""
    if raw is None:
        return None
    return _digits_core(str(raw), _ORDER_PREFIX, ORDER_MIN_DIGITS, ORDER_MAX_DIGITS)


def normalize_customer_id(raw: Optional[str]) -> Optional[str]:
    """'C-010442', 'Cust #10442', 'Customer ID: C-10442' -> '10442'. Malformed -> None."""
    if raw is None:
        return None
    return _digits_core(str(raw), _CUSTOMER_PREFIX, CUSTOMER_MIN_DIGITS, CUSTOMER_MAX_DIGITS)


def case_key(customer_id: str, order_id: str) -> str:
    """The single identity used for matching and duplicate prevention."""
    return f"{customer_id}|{order_id}"


def grounded(normalized_id: Optional[str], email_text: str) -> bool:
    """True if the digits appear in the email as a standalone number (any label)."""
    if not normalized_id:
        return False
    pattern = rf"(?<!\d)0*{re.escape(normalized_id)}(?!\d)"
    return re.search(pattern, email_text) is not None


def grounded_as(kind: str, normalized_id: Optional[str], email_text: str) -> bool:
    """True if the identifier appears next to a label of the right kind.

    A bare number is not enough: an amount ("$12500"), a year ("2026-10-01")
    or the order number itself must not become a customer ID, and the two IDs
    must not be swapped. "SO#038262" grounds an order; "C-010442" or
    "customer 10442" grounds a customer.
    """
    if not normalized_id:
        return False
    label = ORDER_LABEL if kind == "order" else CUSTOMER_LABEL
    inner = r"(?:c\s*[-#]?\s*)?" if kind == "customer" else ""
    pattern = rf"\b{label}{_SUFFIX}{inner}0*{re.escape(normalized_id)}(?!\d)"
    return re.search(pattern, email_text, re.IGNORECASE) is not None
