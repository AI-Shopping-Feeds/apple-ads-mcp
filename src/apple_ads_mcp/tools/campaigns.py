"""Campaigns: /v1/campaigns (query, get, create, update, delete) plus shortcuts."""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient
from ._common import flt, guarded_delete, guarded_update, query_body

STATUSES = {"ENABLED", "PAUSED"}


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_query_campaigns(
        filters: list[dict[str, Any]] | None = None,
        sorting: list[dict[str, Any]] | None = None,
        name_contains: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List campaigns in the ad account (POST /v1/campaigns/query).

        Shortcuts: name_contains, status (ENABLED or PAUSED), include_deleted.
        filters: raw QueryFilter list, e.g.
        [{"field": "promotedObjectId", "operator": "EQUALS", "value": "1234567890"}].
        Filterable: id, name, status, systemStatus, promotedObjectType,
        promotedObjectId, startTime, endTime, deleted, and more.
        Page size is capped at 1000 by Apple; this tool follows pages up to max_items.
        """
        base = []
        if name_contains:
            base.append({**flt("name", "LIKE", name_contains), "ignoreCase": True})
        if status:
            base.append(flt("status", "EQUALS", status.upper()))
        if include_deleted:
            base.append(flt("deleted", "IN", [True, False]))
        return client.query(
            "campaigns/query",
            query_body(filters, sorting, base_filters=base),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_campaign(
        campaign_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One campaign: budget, bid strategy, targeting, status and serving reasons."""
        return client.get_result(f"campaigns/{int(campaign_id)}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_get_campaign_limited_status_reasons(
        campaign_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Details of why a legacy app campaign's delivery is limited
        (GET /v1/campaigns/{id}/legacy-app-limited-status-reason-details)."""
        return client.get_result(
            f"campaigns/{int(campaign_id)}/legacy-app-limited-status-reason-details",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_create_campaign(
        campaign: dict[str, Any],
        start_paused: bool = True,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a campaign (POST /v1/campaigns). Spends money once enabled.

        campaign (App Store example):
        {"name": "MyApp UK Search", "adAccountId": 123,
         "startTime": "2026-12-01T00:00:00.000", "endTime": "2027-03-31T23:59:59.000",
         "billingEvent": "TAPS", "promotedObjectType": "APPSTORE_APP",
         "promotedObjectId": "<adamId>",
         "dailyBudget": {"value": {"amount": "20.00", "currency": "GBP"}},
         "targeting": {"countryOrRegion": {"include": ["GB"]},
                       "supplyPlacement": {"include": ["APPSTORE_SEARCH_RESULTS"]}},
         "bidStrategy": {"bidStrategyType": "MANUAL_CPT", "bidStrategyGoal": "TAP"}}
        Money amounts are decimal strings in the ad account's currency.
        adAccountId defaults to the selected ad account. start_paused (default
        true) forces status PAUSED so nothing serves until you enable it with
        apple_ads_set_campaign_status.
        """
        body = dict(campaign)
        account = client.resolve_account(ad_account_id)
        if account and "adAccountId" not in body:
            body["adAccountId"] = int(account)
        if start_paused:
            body["status"] = "PAUSED"
        if guard.amount_of(body.get("dailyBudget")) is None:
            raise ValueError(
                "dailyBudget is required: {'value': {'amount': '20.00', 'currency': 'GBP'}}"
            )
        return client.request(
            "POST", "campaigns", json_body=body, op="create_campaign", ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_update_campaign(
        campaign_id: str,
        update: dict[str, Any],
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Partially update a campaign (PUT /v1/campaigns/{id}). Send only changed fields.

        Updatable: name, status, startTime, endTime, dailyBudget, sharedBudgets,
        targeting, bidStrategy, invoiceDetail. Arrays replace the whole existing
        array. Raising dailyBudget or a bid/target CPA by more than
        APPLE_ADS_MAX_INCREASE_PCT needs confirm='APPLY'.
        """
        cid = int(campaign_id)
        return guarded_update(
            client,
            get_path=f"campaigns/{cid}",
            put_path=f"campaigns/{cid}",
            update=update,
            confirm=confirm,
            op="update_campaign",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_set_campaign_status(
        campaign_id: str, status: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Pause (PAUSED) or resume (ENABLED) a campaign."""
        status = status.upper()
        if status not in STATUSES:
            raise ValueError("status must be ENABLED or PAUSED")
        cid = int(campaign_id)
        return guarded_update(
            client,
            get_path=f"campaigns/{cid}",
            put_path=f"campaigns/{cid}",
            update={"status": status},
            confirm="",
            op="set_campaign_status",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_set_campaign_daily_budget(
        campaign_id: str,
        amount: str,
        currency: str,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Set a campaign's daily budget, e.g. amount="25.00", currency="GBP".

        The currency must be the ad account's. Raising it by more than
        APPLE_ADS_MAX_INCREASE_PCT needs confirm='APPLY'.
        """
        cid = int(campaign_id)
        return guarded_update(
            client,
            get_path=f"campaigns/{cid}",
            put_path=f"campaigns/{cid}",
            update={"dailyBudget": {"value": guard.money(amount, currency)}},
            confirm=confirm,
            op="set_campaign_daily_budget",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_delete_campaign(
        campaign_id: str, confirm: str = "", ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Delete a campaign and stop all its ads (DELETE /v1/campaigns/{id}).

        confirm: must be 'DELETE'. Consider pausing instead.
        """
        cid = int(campaign_id)
        return guarded_delete(
            client,
            path=f"campaigns/{cid}",
            confirm=confirm,
            op="delete_campaign",
            what=f"campaign {cid}",
            ad_account_id=ad_account_id,
        )
