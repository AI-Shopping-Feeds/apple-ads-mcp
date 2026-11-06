"""Ads on Apple Maps: brands, business categories, locations, location groups, assets.

Only relevant to ad accounts with the BUSINESS_BRAND_MANUAL product feature.
Uploading new image assets (multipart, POST /v1/assets/upload) is not wrapped;
do it in the Apple Ads UI.
"""

from __future__ import annotations

from typing import Any

from ..client import AppleAdsClient
from ._common import guarded_delete, guarded_update, query_body


def register(mcp, client: AppleAdsClient) -> None:
    def q(
        path: str, filters: list[dict[str, Any]] | None, max_items: int, ad_account_id: str | None
    ):
        return client.query(
            path, query_body(filters), max_items=max_items, ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_query_brands(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 100,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Apple Maps business brands available to the ad account (POST /v1/business-brands/query)."""
        return q("business-brands/query", filters, max_items, ad_account_id)

    @mcp.tool()
    def apple_ads_get_brand(brand_id: str, ad_account_id: str | None = None) -> dict[str, Any]:
        """One Apple Maps brand (GET /v1/business-brands/{id})."""
        return client.get_result(f"business-brands/{brand_id}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_query_business_categories(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Apple Maps business categories (POST /v1/business-categories/query)."""
        return q("business-categories/query", filters, max_items, ad_account_id)

    @mcp.tool()
    def apple_ads_get_business_category(
        category_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One Apple Maps business category (GET /v1/business-categories/{id})."""
        return client.get_result(f"business-categories/{category_id}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_query_brand_rejection_reasons(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Why Apple Maps brand creatives were rejected
        (POST /v1/rejection-reasons/business-brands/query)."""
        return q("rejection-reasons/business-brands/query", filters, max_items, ad_account_id)

    @mcp.tool()
    def apple_ads_query_locations(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 500,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """A brand's business locations on Apple Maps (POST /v1/locations/query)."""
        return q("locations/query", filters, max_items, ad_account_id)

    @mcp.tool()
    def apple_ads_get_location(
        location_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One business location (GET /v1/locations/{id})."""
        return client.get_result(f"locations/{location_id}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_query_location_groups(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Named groups of business locations used by Maps ad group targeting
        (POST /v1/location-groups/query)."""
        return q("location-groups/query", filters, max_items, ad_account_id)

    @mcp.tool()
    def apple_ads_get_location_group(
        location_group_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One location group (GET /v1/location-groups/{id})."""
        return client.get_result(
            f"location-groups/{location_group_id}", ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_create_location_group(
        location_group: dict[str, Any], ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Create a location group (POST /v1/location-groups).

        location_group: {"name": "Central stores", "brandId": "...", "adAccountId": "...",
                         "groupType": "STATIC", "locationIds": ["...", "..."]}
        """
        return client.request(
            "POST",
            "location-groups",
            json_body=location_group,
            op="create_location_group",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_update_location_group(
        location_group_id: str, update: dict[str, Any], ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Partially update a location group (PUT /v1/location-groups/{id}). Arrays replace."""
        return guarded_update(
            client,
            get_path=f"location-groups/{location_group_id}",
            put_path=f"location-groups/{location_group_id}",
            update=update,
            confirm="",
            op="update_location_group",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_delete_location_group(
        location_group_id: str, confirm: str = "", ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Delete a location group (DELETE /v1/location-groups/{id}). confirm: must be 'DELETE'."""
        return guarded_delete(
            client,
            path=f"location-groups/{location_group_id}",
            confirm=confirm,
            op="delete_location_group",
            what=f"location group {location_group_id}",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_query_assets(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Apple Maps creative assets (POST /v1/assets/query)."""
        return q("assets/query", filters, max_items, ad_account_id)

    @mcp.tool()
    def apple_ads_get_asset(asset_id: str, ad_account_id: str | None = None) -> dict[str, Any]:
        """One Apple Maps creative asset (GET /v1/assets/{id})."""
        return client.get_result(f"assets/{asset_id}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_delete_asset(
        asset_id: str, confirm: str = "", ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Delete an Apple Maps creative asset (DELETE /v1/assets/{id}). confirm: must be 'DELETE'."""
        return guarded_delete(
            client,
            path=f"assets/{asset_id}",
            confirm=confirm,
            op="delete_asset",
            what=f"asset {asset_id}",
            ad_account_id=ad_account_id,
        )
