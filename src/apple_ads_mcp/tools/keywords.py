"""Targeting keywords and negative keywords (campaign- and ad-group-level).

Writes go through Apple's bulk endpoints (/v1/keywords/bulk-*,
/v1/negative-keywords/bulk-*), which also take a single item. More than one
item needs confirm='APPLY'; any delete needs confirm='DELETE'.
"""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient
from ._common import bulk, flt, id_filter, query_body

MAX_BULK = 1000


def _scope_filters(campaign_id: str | None, adgroup_id: str | None) -> list[dict[str, Any]]:
    out = []
    if campaign_id:
        out.append(flt("campaignId", "EQUALS", int(campaign_id)))
    if adgroup_id:
        out.append(flt("adGroupId", "EQUALS", int(adgroup_id)))
    return out


def _check_size(items: list[Any], what: str) -> None:
    if not items:
        raise ValueError(f"Pass at least one {what}.")
    if len(items) > MAX_BULK:
        raise ValueError(f"At most {MAX_BULK} {what} per call; split the list.")


def register(mcp, client: AppleAdsClient) -> None:
    def current(path: str, ids: list[Any], ad_account_id: str | None) -> list[dict[str, Any]]:
        try:
            return client.query(
                path,
                query_body(base_filters=[id_filter(ids)]),
                max_items=len(ids),
                ad_account_id=ad_account_id,
            )["result"]
        except Exception:
            return []

    def bid_check(
        before: list[dict[str, Any]], updates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        by_id = {str(b.get("id")): b for b in before if isinstance(b, dict)}
        changes = []
        for u in updates:
            for c in guard.money_changes(
                by_id.get(str(u.get("id"))), {"bid": u["bid"]} if "bid" in u else {}
            ):
                changes.append({"id": u.get("id"), **c})
        return changes

    # ------------------------------------------------------------ keywords

    @mcp.tool()
    def apple_ads_query_keywords(
        campaign_id: str | None = None,
        adgroup_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        sorting: list[dict[str, Any]] | None = None,
        max_items: int = 1000,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List targeting keywords (POST /v1/keywords/query), optionally for one
        campaign and/or ad group. Each has text, matchType (EXACT/BROAD), status
        and an optional bid overriding the ad group default."""
        return client.query(
            "keywords/query",
            query_body(filters, sorting, base_filters=_scope_filters(campaign_id, adgroup_id)),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_keyword(keyword_id: str, ad_account_id: str | None = None) -> dict[str, Any]:
        """One targeting keyword (GET /v1/keywords/{id})."""
        return client.get_result(f"keywords/{int(keyword_id)}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_add_keywords(
        keywords: list[dict[str, Any]],
        allow_partial_success: bool = False,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Add targeting keywords (POST /v1/keywords/bulk-create).

        keywords: [{"adGroupId": 555666777, "text": "puzzle game",
                    "matchType": "EXACT", "bid": {"amount": "1.20", "currency": "GBP"}}]
        bid is optional (defaults to the ad group bid). More than one keyword
        needs confirm='APPLY'. allow_partial_success=true keeps the valid items
        when some fail.
        """
        _check_size(keywords, "keywords")
        note = guard.require(
            confirm,
            guard.CONFIRM_APPLY,
            guard.bulk_reasons(len(keywords), "keywords"),
            dry_run=client.config.dry_run,
        )
        out = bulk(
            client,
            path="keywords/bulk-create",
            items=keywords,
            allow_partial_success=allow_partial_success,
            op="add_keywords",
            before=None,
            ad_account_id=ad_account_id,
        )
        return {**out, **note}

    @mcp.tool()
    def apple_ads_update_keywords(
        updates: list[dict[str, Any]],
        allow_partial_success: bool = False,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Change keyword bids or status (POST /v1/keywords/bulk-update).

        updates: [{"id": 888999000, "bid": {"amount": "1.50", "currency": "GBP"}},
                  {"id": 888999001, "status": "PAUSED"}]
        More than one item, or a bid raised by more than
        APPLE_ADS_MAX_INCREASE_PCT (or set on a keyword with no bid of its own),
        needs confirm='APPLY'. The current keywords are saved in the audit log.
        """
        _check_size(updates, "updates")
        if any("id" not in u for u in updates):
            raise ValueError("Every update needs the keyword 'id'.")
        before = current("keywords/query", [u["id"] for u in updates], ad_account_id)
        changes = bid_check(before, updates)
        reasons = guard.bulk_reasons(len(updates), "keywords") + guard.increase_reasons(
            changes, client.config.max_increase_pct
        )
        note = guard.require(confirm, guard.CONFIRM_APPLY, reasons, dry_run=client.config.dry_run)
        out = bulk(
            client,
            path="keywords/bulk-update",
            items=updates,
            allow_partial_success=allow_partial_success,
            op="update_keywords",
            before=before,
            ad_account_id=ad_account_id,
        )
        return {**out, **note, "bid_changes": changes or None}

    @mcp.tool()
    def apple_ads_delete_keywords(
        keyword_ids: list[str],
        allow_partial_success: bool = False,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete targeting keywords (POST /v1/keywords/bulk-delete). confirm: must be 'DELETE'."""
        _check_size(keyword_ids, "keyword IDs")
        note = guard.require(
            confirm,
            guard.CONFIRM_DELETE,
            [f"deletes {len(keyword_ids)} keyword(s)"],
            dry_run=client.config.dry_run,
        )
        before = current("keywords/query", keyword_ids, ad_account_id)
        out = bulk(
            client,
            path="keywords/bulk-delete",
            items=[{"id": int(i)} for i in keyword_ids],
            allow_partial_success=allow_partial_success,
            op="delete_keywords",
            before=before,
            ad_account_id=ad_account_id,
        )
        return {**out, **note}

    # ------------------------------------------------------------ negatives

    @mcp.tool()
    def apple_ads_query_negative_keywords(
        campaign_id: str | None = None,
        adgroup_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 1000,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List negative keywords (POST /v1/negative-keywords/query). Campaign-level
        negatives have no adGroupId; ad-group-level ones do."""
        return client.query(
            "negative-keywords/query",
            query_body(filters, base_filters=_scope_filters(campaign_id, adgroup_id)),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_negative_keyword(
        negative_keyword_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One negative keyword (GET /v1/negative-keywords/{id})."""
        return client.get_result(
            f"negative-keywords/{int(negative_keyword_id)}", ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_add_negative_keywords(
        negative_keywords: list[dict[str, Any]],
        allow_partial_success: bool = False,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Add negative keywords (POST /v1/negative-keywords/bulk-create).

        Campaign level: {"campaignId": 444555666, "text": "free", "matchType": "BROAD"}
        Ad group level: add "adGroupId". More than one needs confirm='APPLY'.
        """
        _check_size(negative_keywords, "negative keywords")
        note = guard.require(
            confirm,
            guard.CONFIRM_APPLY,
            guard.bulk_reasons(len(negative_keywords), "negative keywords"),
            dry_run=client.config.dry_run,
        )
        out = bulk(
            client,
            path="negative-keywords/bulk-create",
            items=negative_keywords,
            allow_partial_success=allow_partial_success,
            op="add_negative_keywords",
            before=None,
            ad_account_id=ad_account_id,
        )
        return {**out, **note}

    @mcp.tool()
    def apple_ads_update_negative_keywords(
        updates: list[dict[str, Any]],
        allow_partial_success: bool = False,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Change negative keyword status or match type (POST /v1/negative-keywords/bulk-update).

        updates: [{"id": 1, "status": "PAUSED"}]. More than one needs confirm='APPLY'.
        """
        _check_size(updates, "updates")
        if any("id" not in u for u in updates):
            raise ValueError("Every update needs the negative keyword 'id'.")
        note = guard.require(
            confirm,
            guard.CONFIRM_APPLY,
            guard.bulk_reasons(len(updates), "negative keywords"),
            dry_run=client.config.dry_run,
        )
        before = current("negative-keywords/query", [u["id"] for u in updates], ad_account_id)
        out = bulk(
            client,
            path="negative-keywords/bulk-update",
            items=updates,
            allow_partial_success=allow_partial_success,
            op="update_negative_keywords",
            before=before,
            ad_account_id=ad_account_id,
        )
        return {**out, **note}

    @mcp.tool()
    def apple_ads_delete_negative_keywords(
        negative_keyword_ids: list[str],
        allow_partial_success: bool = False,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete negative keywords (POST /v1/negative-keywords/bulk-delete). confirm: must be 'DELETE'."""
        _check_size(negative_keyword_ids, "negative keyword IDs")
        note = guard.require(
            confirm,
            guard.CONFIRM_DELETE,
            [f"deletes {len(negative_keyword_ids)} negative keyword(s)"],
            dry_run=client.config.dry_run,
        )
        before = current("negative-keywords/query", negative_keyword_ids, ad_account_id)
        out = bulk(
            client,
            path="negative-keywords/bulk-delete",
            items=[{"id": int(i)} for i in negative_keyword_ids],
            allow_partial_success=allow_partial_success,
            op="delete_negative_keywords",
            before=before,
            ad_account_id=ad_account_id,
        )
        return {**out, **note}
