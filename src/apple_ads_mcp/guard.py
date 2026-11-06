"""Spend guards: confirm strings, money parsing and budget/bid increase checks.

Apple Ads money values are objects with a decimal *string* amount, for example
{"amount": "1.50", "currency": "GBP"}. Campaign daily budgets wrap one in
`value`: {"dailyBudget": {"value": {"amount": "50", "currency": "GBP"}}}.
The amount's currency must match the ad account's currency.

Rules (see README, "Safety"):
* Deletes need confirm='DELETE'.
* Bulk changes (more than one item) need confirm='APPLY'.
* A budget or bid change that raises a value by more than
  APPLE_ADS_MAX_INCREASE_PCT (default 20%), or sets one where the current value
  can't be read, needs confirm='APPLY'.
* In dry-run mode none of these block: nothing is sent, and the preview says
  which confirm the live call will need.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

CONFIRM_APPLY = "APPLY"
CONFIRM_DELETE = "DELETE"


def money(amount: str | float | int | Decimal, currency: str) -> dict[str, str]:
    """Build an Apple Ads Money object. Amount becomes a 2-dp decimal string."""
    try:
        value = Decimal(str(amount))
    except InvalidOperation as e:
        raise ValueError(f"Not a valid amount: {amount!r}") from e
    if value < 0:
        raise ValueError("Amounts can't be negative")
    cur = (currency or "").strip().upper()
    if len(cur) != 3 or not cur.isalpha():
        raise ValueError(f"currency must be an ISO 4217 code such as GBP or USD, got {currency!r}")
    return {"amount": f"{value.quantize(Decimal('0.01'))}", "currency": cur}


def amount_of(value: Any) -> Decimal | None:
    """Decimal amount of a Money object (or a {"value": Money} wrapper); None if absent."""
    if isinstance(value, dict):
        if "amount" in value:
            try:
                return Decimal(str(value["amount"]))
            except InvalidOperation:
                return None
        if "value" in value:
            return amount_of(value["value"])
    return None


def _money_paths(obj: Any, prefix: str = "") -> dict[str, Decimal]:
    """Every Money amount inside `obj`, keyed by dotted path (wrappers collapse)."""
    out: dict[str, Decimal] = {}
    if isinstance(obj, dict):
        if "amount" in obj and ("currency" in obj or isinstance(obj.get("amount"), str)):
            amt = amount_of(obj)
            if amt is not None:
                out[prefix.removesuffix(".value") or "amount"] = amt
            return out
        for k, v in obj.items():
            out.update(_money_paths(v, f"{prefix}.{k}" if prefix else str(k)))
    return out


def money_changes(before: Any, update: Any) -> list[dict[str, Any]]:
    """Compare money values an update would set against the current entity.

    Returns one dict per money field in `update`: path, old, new, pct (None if
    there is no old value to compare with).
    """
    new_vals = _money_paths(update)
    old_vals = _money_paths(before) if before is not None else {}
    changes = []
    for path, new in new_vals.items():
        old = old_vals.get(path)
        pct: float | None = None
        if old is not None and old > 0:
            pct = float((new - old) / old * 100)
        elif old is not None and old == 0:
            pct = 0.0 if new == 0 else float("inf")
        changes.append(
            {
                "path": path,
                "old": str(old) if old is not None else None,
                "new": str(new),
                "pct_change": None if pct is None else round(pct, 2),
            }
        )
    return changes


def increase_reasons(changes: list[dict[str, Any]], max_pct: float) -> list[str]:
    reasons = []
    for c in changes:
        if c["old"] is None:
            reasons.append(f"{c['path']}: sets {c['new']} where the current value is unknown")
        elif c["pct_change"] is not None and c["pct_change"] > max_pct:
            reasons.append(
                f"{c['path']}: {c['old']} -> {c['new']} (+{c['pct_change']}%, limit {max_pct}%)"
            )
    return reasons


def require(confirm: str, expected: str, reasons: list[str], *, dry_run: bool) -> dict[str, Any]:
    """Raise ValueError unless `confirm == expected` (or nothing needs confirming).

    In dry-run mode it never raises; it returns a note for the preview instead.
    """
    if not reasons or confirm == expected:
        return {}
    note = f"Needs confirm='{expected}' when live: " + "; ".join(reasons)
    if dry_run:
        return {"confirm_required_when_live": expected, "confirm_reasons": reasons}
    raise ValueError(
        f"Refused: {note}. Show the user exactly what will change and, once they agree, "
        f"call again with confirm='{expected}'."
    )


def bulk_reasons(count: int, what: str) -> list[str]:
    return [f"bulk change of {count} {what}"] if count > 1 else []
