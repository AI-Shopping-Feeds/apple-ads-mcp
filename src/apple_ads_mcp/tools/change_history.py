"""Apple's own change history for the ad account: who changed what, and when."""

from __future__ import annotations

from typing import Any

from ..client import AppleAdsClient, path_segment
from ._common import flt


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_query_change_history(
        start: str,
        end: str,
        entity_types: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Change summaries grouped by transaction (POST /v1/change-history/query).

        start/end: YYYY-MM-DD. entity_types: e.g. ["Campaign", "AdGroup", "Keyword"].
        Use apple_ads_get_change_detail for field-level before/after values.
        """
        all_filters = [flt("eventTime", "BETWEEN", [start, end])]
        if entity_types:
            all_filters.append(flt("entityType", "IN", entity_types))
        all_filters += list(filters or [])
        body = {
            "filters": all_filters,
            "sorting": [{"field": "eventTime", "order": "DESC"}],
            "options": {"needTotals": "true"},
        }
        return client.query(
            "change-history/query",
            body,
            max_items=max_items,
            page_size=min(max_items, 100),
            ad_account_id=ad_account_id,
            fetch_total=False,
        )

    @mcp.tool()
    def apple_ads_get_change_detail(
        detail_id: str, ad_account_id: str | None = None
    ) -> dict[str, Any]:
        """Field-level old and new values for one change (GET /v1/change-history/{detailId})."""
        return client.get_result(
            f"change-history/{path_segment(detail_id, 'detail_id')}", ad_account_id=ad_account_id
        )
