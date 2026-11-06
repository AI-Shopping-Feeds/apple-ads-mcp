"""Ads and ad creatives: /v1/ads and /v1/creatives.

A creative says what to show (the default product page, a custom product
page, or Apple Maps assets); an ad puts a creative into an ad group.
"""

from __future__ import annotations

from typing import Any

from ..client import AppleAdsClient
from ._common import flt, guarded_delete, guarded_update, query_body


def register(mcp, client: AppleAdsClient) -> None:
    # ------------------------------------------------------------ ads

    @mcp.tool()
    def apple_ads_query_ads(
        campaign_id: str | None = None,
        adgroup_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List ads (POST /v1/ads/query), optionally for one campaign or ad group."""
        base = []
        if campaign_id:
            base.append(flt("campaignId", "EQUALS", int(campaign_id)))
        if adgroup_id:
            base.append(flt("adGroupId", "EQUALS", int(adgroup_id)))
        return client.query(
            "ads/query",
            query_body(filters, base_filters=base),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_ad(ad_id: str, ad_account_id: str | None = None) -> dict[str, Any]:
        """One ad, with its creative, status and any rejection state (GET /v1/ads/{id})."""
        return client.get_result(f"ads/{int(ad_id)}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_create_ad(ad: dict[str, Any], ad_account_id: str | None = None) -> dict[str, Any]:
        """Create an ad from a creative in an ad group (POST /v1/ads).

        ad: {"name": "Default page", "adGroupId": 555666777, "creativeId": 666777888,
             "status": "ENABLED"}
        """
        return client.request(
            "POST", "ads", json_body=ad, op="create_ad", ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_update_ad(
        ad_id: str, update: dict[str, Any], ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Partially update an ad, e.g. {"status": "PAUSED"} or a new name (PUT /v1/ads/{id})."""
        aid = int(ad_id)
        return guarded_update(
            client,
            get_path=f"ads/{aid}",
            put_path=f"ads/{aid}",
            update=update,
            confirm="",
            op="update_ad",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_delete_ad(
        ad_id: str, confirm: str = "", ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Delete an ad (DELETE /v1/ads/{id}). confirm: must be 'DELETE'."""
        aid = int(ad_id)
        return guarded_delete(
            client,
            path=f"ads/{aid}",
            confirm=confirm,
            op="delete_ad",
            what=f"ad {aid}",
            ad_account_id=ad_account_id,
        )

    # ------------------------------------------------------------ creatives

    @mcp.tool()
    def apple_ads_query_creatives(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """List ad creatives (POST /v1/creatives/query)."""
        return client.query(
            "creatives/query", query_body(filters), max_items=max_items, ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_get_creative(
        creative_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One ad creative (GET /v1/creatives/{id})."""
        return client.get_result(f"creatives/{int(creative_id)}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_create_creative(
        creative: dict[str, Any], ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Create an ad creative (POST /v1/creatives): the default product page, a
        custom product page (productPageId from apple_ads_query_product_pages), or
        Apple Maps assets. See Apple's "Create an Ad Creative" docs for the
        exact body for each creative type."""
        return client.request(
            "POST",
            "creatives",
            json_body=creative,
            op="create_creative",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_update_creative(
        creative_id: str, update: dict[str, Any], ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Partially update an ad creative (PUT /v1/creatives/{id})."""
        cid = int(creative_id)
        return guarded_update(
            client,
            get_path=f"creatives/{cid}",
            put_path=f"creatives/{cid}",
            update=update,
            confirm="",
            op="update_creative",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_delete_creative(
        creative_id: str, confirm: str = "", ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Delete an ad creative (DELETE /v1/creatives/{id}). confirm: must be 'DELETE'."""
        cid = int(creative_id)
        return guarded_delete(
            client,
            path=f"creatives/{cid}",
            confirm=confirm,
            op="delete_creative",
            what=f"creative {cid}",
            ad_account_id=ad_account_id,
        )
