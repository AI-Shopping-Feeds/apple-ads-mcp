"""Shared helpers for tool modules: query bodies, filters, guarded writes."""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient

Json = dict[str, Any]

ACCOUNT_DOC = (
    "ad_account_id: optional; overrides APPLE_ADS_AD_ACCOUNT_ID for this call "
    "(sent as X-AP-Context: adAccountId=...)."
)


def flt(field: str, operator: str, value: Any) -> Json:
    return {"field": field, "operator": operator, "value": value}


def query_body(
    filters: list[Json] | None = None,
    sorting: list[Json] | None = None,
    base_filters: list[Json] | None = None,
    **extra: Any,
) -> Json:
    """Build a QueryRequest: {filters, sorting, ...}. Pagination is added by client.query."""
    body: Json = {}
    all_filters = [*(base_filters or []), *(filters or [])]
    if all_filters:
        body["filters"] = all_filters
    if sorting:
        body["sorting"] = sorting
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


def id_filter(ids: list[int | str]) -> Json:
    return flt("id", "IN", [int(i) if str(i).isdigit() else i for i in ids])


def guarded_update(
    client: AppleAdsClient,
    *,
    get_path: str,
    put_path: str,
    update: Json,
    confirm: str,
    op: str,
    ad_account_id: str | int | None,
    context: Any = "account",
) -> Json:
    """PUT a partial update after checking budget/bid increases against the current entity."""
    if not update:
        raise ValueError("update is empty: pass only the fields to change.")
    before = client.snapshot(get_path, ad_account_id=ad_account_id, context=context)
    changes = guard.money_changes(before, update)
    note = guard.require(
        confirm,
        guard.CONFIRM_APPLY,
        guard.increase_reasons(changes, client.config.max_increase_pct),
        dry_run=client.config.dry_run,
    )
    out = client.request(
        "PUT",
        put_path,
        json_body=update,
        op=op,
        before=before,
        ad_account_id=ad_account_id,
        context=context,
    )
    return _with(out, money_changes=changes or None, **note)


def guarded_delete(
    client: AppleAdsClient,
    *,
    path: str,
    confirm: str,
    op: str,
    what: str,
    ad_account_id: str | int | None,
    context: Any = "account",
) -> Json:
    note = guard.require(
        confirm, guard.CONFIRM_DELETE, [f"deletes {what}"], dry_run=client.config.dry_run
    )
    before = client.snapshot(path, ad_account_id=ad_account_id, context=context)
    out = client.request(
        "DELETE", path, op=op, before=before, ad_account_id=ad_account_id, context=context
    )
    return _with(out, **note)


def bulk(
    client: AppleAdsClient,
    *,
    path: str,
    items: list[Json],
    allow_partial_success: bool,
    op: str,
    before: Any,
    ad_account_id: str | int | None,
) -> Json:
    body = {
        "allowPartialSuccess": allow_partial_success,
        "items": [{"correlationId": i, "data": item} for i, item in enumerate(items)],
    }
    out = client.request(
        "POST", path, json_body=body, op=op, before=before, ad_account_id=ad_account_id
    )
    if isinstance(out, dict) and isinstance(out.get("result"), list):
        failed = [r for r in out["result"] if isinstance(r, dict) and not r.get("success", True)]
        out = {**out, "succeeded": len(out["result"]) - len(failed), "failed": len(failed)}
    return out


def _with(out: Any, **extra: Any) -> Any:
    extra = {k: v for k, v in extra.items() if v is not None}
    if isinstance(out, dict) and extra:
        return {**out, **extra}
    return out
