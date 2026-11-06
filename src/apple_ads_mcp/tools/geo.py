"""Geo targeting lookups: /v1/search/geo (GET by name, POST by ID)."""

from __future__ import annotations

from typing import Any

from ..client import AppleAdsClient


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_search_geo(
        supply_source: str = "APPSTORE",
        query: str | None = None,
        entity: str | None = None,
        country_code: str | None = None,
        eligible: bool = False,
        page_size: int = 20,
        offset: int = 0,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Find geo targets by name (GET /v1/search/geo).

        supply_source: APPSTORE or MAPS. entity: Country, AdminArea, Locality or
        PostalCode (MAPS only). country_code: ISO code (defaults to US for
        sub-national entities). eligible=true hides soft-blocked geos.
        """
        params: dict[str, Any] = {
            "supplySource": supply_source.upper(),
            "eligible": str(eligible).lower(),
            "pageSize": page_size,
            "offset": offset,
        }
        if query:
            params["query"] = query
        if entity:
            params["entity"] = entity
        if country_code:
            params["countrycode"] = country_code.upper()
        return client.request("GET", "search/geo", params=params, ad_account_id=ad_account_id)

    @mcp.tool()
    def apple_ads_lookup_geo(
        geo_ids: list[dict[str, str]],
        supply_source: str = "APPSTORE",
        page_size: int = 50,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Look up known geo IDs (POST /v1/search/geo).

        geo_ids: [{"id": "11390462", "entity": "Locality"}, ...]
        """
        body = {
            "geoRequest": geo_ids,
            "supplySource": supply_source.upper(),
            "pagination": {"offset": 0, "pageSize": page_size},
        }
        return client.request(
            "POST", "search/geo", json_body=body, read_only=True, ad_account_id=ad_account_id
        )
