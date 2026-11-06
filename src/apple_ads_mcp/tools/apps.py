"""Apps: search, details, eligibility, rejection reasons, product pages, languages."""

from __future__ import annotations

from typing import Any

from ..client import AppleAdsClient, path_segment
from ._common import flt, query_body


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_search_apps(
        query: str | None = None,
        return_owned_apps: bool = False,
        cpids: str | None = None,
        store_fronts: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Search the App Store for apps (GET /v1/search/apps).

        Pass at least one of: query (3+ characters, matches app or developer
        name), return_owned_apps=true (apps your org owns), or cpids
        (comma-separated content provider IDs). The returned adamId is the
        promotedObjectId for App Store campaigns.
        store_fronts: ISO country codes, e.g. ["GB", "US"].
        """
        if not (query or return_owned_apps or cpids):
            raise ValueError("Pass query, cpids or return_owned_apps=true.")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if query:
            params["query"] = query
        if return_owned_apps:
            params["returnOwnedApps"] = "true"
        if cpids:
            params["cpids"] = cpids
        if store_fronts:
            params["storeFronts"] = [s.upper() for s in store_fronts]
        return client.request("GET", "search/apps", params=params, ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_get_app(adam_id: str, ad_account_id: str | None = None) -> dict[str, Any]:
        """App details by Adam ID: name, developer, countries, device classes (GET /v1/apps/{adamId})."""
        return client.get_result(f"apps/{int(adam_id)}", ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_query_app_locale_details(
        adam_id: str,
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Localized default product page details for an app: names, subtitles,
        screenshots and previews per language (POST /v1/apps/{adamId}/locale-details/query)."""
        return client.query(
            f"apps/{int(adam_id)}/locale-details/query",
            query_body(filters),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_check_app_eligibility(
        adam_id: str,
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Whether an app can run ads, per country/region, device class and
        placement (POST /v1/eligibilities/apps/query)."""
        return client.query(
            "eligibilities/apps/query",
            query_body(filters, base_filters=[flt("adamId", "EQUALS", int(adam_id))]),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_query_rejection_reasons(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Why App Store creatives or product pages were rejected
        (POST /v1/rejection-reasons/apps/query). Filter e.g. by adamId or productPageId."""
        return client.query(
            "rejection-reasons/apps/query",
            query_body(filters),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_rejection_reason(
        rejection_reason_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One rejection reason by ID (GET /v1/rejection-reasons/apps/{id})."""
        return client.get_result(
            f"rejection-reasons/apps/{rejection_reason_id}", ad_account_id=ad_account_id
        )

    @mcp.tool()
    def apple_ads_query_supported_languages(
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 500,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """App Store languages supported per country or region
        (POST /v1/metadata/apps/supported-languages/query)."""
        return client.query(
            "metadata/apps/supported-languages/query",
            query_body(filters),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_query_product_pages(
        adam_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Custom product pages (from App Store Connect) usable as ad destinations
        (POST /v1/product-pages/query)."""
        base = [flt("adamId", "EQUALS", int(adam_id))] if adam_id else []
        return client.query(
            "product-pages/query",
            query_body(filters, base_filters=base),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_get_product_page(
        product_page_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """One custom product page, including its deep link (GET /v1/product-pages/{id})."""
        return client.get_result(
            f"product-pages/{path_segment(product_page_id, 'product_page_id')}",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_query_product_page_locales(
        filters: list[dict[str, Any]],
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Localized details (screenshots, previews, text) of custom product pages
        (POST /v1/product-pages/locale-details/query). Filter e.g. by productPageId."""
        return client.query(
            "product-pages/locale-details/query",
            query_body(filters),
            max_items=max_items,
            ad_account_id=ad_account_id,
        )
