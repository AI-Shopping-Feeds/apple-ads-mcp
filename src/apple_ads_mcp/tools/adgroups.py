"""Ad groups: /v1/adgroups (query, get, create, update, delete) plus shortcuts."""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient
from ._common import flt, guarded_delete, guarded_update, query_body


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_query_adgroups(
        campaign_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        sorting: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List ad groups, optionally in one campaign (POST /v1/adgroups/query).

        Without campaign_id this lists ad groups across the whole ad account.
        """
        base = [flt("campaignId", "EQUALS", int(campaign_id))] if campaign_id else []
        return client.query(
            "adgroups/query",
            query_body(filters, sorting, base_filters=base),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_adgroup(adgroup_id: str, ad_account_id: str | None = None) -> dict[str, Any]:
        """One ad group: bid strategy and default bid, targeting, schedule, status."""
        return client.get_result(f"adgroups/{int(adgroup_id)}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_create_adgroup(
        adgroup: dict[str, Any], ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Create an ad group in a campaign (POST /v1/adgroups).

        adgroup example:
        {"name": "UK exact", "campaignId": 444555666, "pricingModel": "CPT",
         "status": "ENABLED", "startTime": "2026-12-01T00:00:00.000",
         "bidStrategy": {"bidStrategyType": "MANUAL_CPT", "bidStrategyGoal": "TAP",
                         "bid": {"amount": "1.20", "currency": "GBP"}},
         "targeting": {"deviceClass": {"include": ["IPHONE", "IPAD"]}}}
        """
        return client.request(
            "POST", "adgroups", json_body=adgroup, op="create_adgroup", ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_update_adgroup(
        adgroup_id: str,
        update: dict[str, Any],
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Partially update an ad group (PUT /v1/adgroups/{id}). Send only changed fields.

        Arrays replace the existing array. Raising the bid by more than
        APPLE_ADS_MAX_INCREASE_PCT needs confirm='APPLY'.
        """
        gid = int(adgroup_id)
        return guarded_update(
            client,
            get_path=f"adgroups/{gid}",
            put_path=f"adgroups/{gid}",
            update=update,
            confirm=confirm,
            op="update_adgroup",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_set_adgroup_status(
        adgroup_id: str, status: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Pause (PAUSED) or resume (ENABLED) an ad group."""
        status = status.upper()
        if status not in {"ENABLED", "PAUSED"}:
            raise ValueError("status must be ENABLED or PAUSED")
        gid = int(adgroup_id)
        return guarded_update(
            client,
            get_path=f"adgroups/{gid}",
            put_path=f"adgroups/{gid}",
            update={"status": status},
            confirm="",
            op="set_adgroup_status",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_set_adgroup_bid(
        adgroup_id: str,
        amount: str,
        currency: str,
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Set an ad group's default bid (bidStrategy.bid), e.g. amount="1.50", currency="GBP".

        Keeps the current bidStrategyType/Goal (Apple needs them sent together).
        Raising it by more than APPLE_ADS_MAX_INCREASE_PCT needs confirm='APPLY'.
        """
        gid = int(adgroup_id)
        current = client.snapshot(f"adgroups/{gid}", ad_account_id=ad_account_id) or {}
        strategy = dict(current.get("bidStrategy") or {}) if isinstance(current, dict) else {}
        update_strategy = {
            k: strategy[k] for k in ("bidStrategyType", "bidStrategyGoal") if k in strategy
        }
        update_strategy["bid"] = guard.money(amount, currency)
        return guarded_update(
            client,
            get_path=f"adgroups/{gid}",
            put_path=f"adgroups/{gid}",
            update={"bidStrategy": update_strategy},
            confirm=confirm,
            op="set_adgroup_bid",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_delete_adgroup(
        adgroup_id: str, confirm: str = "", ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Delete an ad group (DELETE /v1/adgroups/{id}). confirm: must be 'DELETE'."""
        gid = int(adgroup_id)
        return guarded_delete(
            client,
            path=f"adgroups/{gid}",
            confirm=confirm,
            op="delete_adgroup",
            what=f"ad group {gid}",
            ad_account_id=ad_account_id,
        )
