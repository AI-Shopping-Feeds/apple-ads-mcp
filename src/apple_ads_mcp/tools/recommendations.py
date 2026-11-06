"""Apple's budget and target CPA recommendations, and keyword/phrase/category/
target CPA suggestions.

Applying a recommendation changes a live campaign's daily budget or target
CPA, so the apply tools always need confirm='APPLY'.
"""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient
from ._common import flt, query_body

KINDS = {"daily_budget": "daily-budgets", "target_cpa": "target-cpas"}


def _kind(kind: str) -> str:
    k = KINDS.get(kind.lower().replace("-", "_"))
    if k is None:
        raise ValueError("kind must be 'daily_budget' or 'target_cpa'")
    return k


def _promoted(adam_id: str | None) -> list[dict[str, Any]]:
    if not adam_id:
        return []
    return [
        flt("promotedObjectId", "EQUALS", [str(adam_id)]),
        flt("promotedObjectType", "EQUALS", ["APPSTORE_APP"]),
    ]


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_query_recommendations(
        kind: str = "daily_budget",
        adam_id: str | None = None,
        state: str | None = "AVAILABLE",
        filters: list[dict[str, Any]] | None = None,
        max_items: int = 100,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Apple's recommendations (POST /v1/recommendations/{daily-budgets|target-cpas}/query).

        kind: daily_budget (raise a campaign's daily cap) or target_cpa (adjust
        the target CPA of Maximize Conversions campaigns). Each has an id,
        suggested amount and expected performance.
        """
        base = _promoted(adam_id)
        if state:
            base.append(flt("state", "EQUALS", [state.upper()]))
        return client.query(
            f"recommendations/{_kind(kind)}/query",
            query_body(filters, base_filters=base),
            max_items=max_items,
            ad_account_id=ad_account_id,
            fetch_total=False,
        )

    @mcp.tool()
    def apple_ads_apply_recommendations(
        kind: str,
        recommendations: list[dict[str, Any]],
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply recommendations (POST /v1/recommendations/{kind}/apply). Changes live spend.

        kind: daily_budget or target_cpa. recommendations:
        [{"id": "rec-1", "promotedObjectId": "123", "promotedObjectType": "APPSTORE_APP"}]
        Optional override per item: "appliedDailyBudget" (daily_budget) or
        "appliedTargetCPA" (target_cpa) as {"amount": "...", "currency": "..."}.
        confirm: must be 'APPLY'.
        """
        if not recommendations:
            raise ValueError("Pass at least one recommendation.")
        note = guard.require(
            confirm,
            guard.CONFIRM_APPLY,
            [f"applies {len(recommendations)} {kind} recommendation(s) to live campaigns"],
            dry_run=client.config.dry_run,
        )
        out = client.request(
            "POST",
            f"recommendations/{_kind(kind)}/apply",
            json_body=recommendations,
            op=f"apply_{kind}_recommendations",
            ad_account_id=ad_account_id,
        )
        return {**out, **note} if isinstance(out, dict) else out

    @mcp.tool()
    def apple_ads_dismiss_recommendations(
        kind: str,
        recommendations: list[dict[str, Any]],
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Dismiss recommendations (POST /v1/recommendations/{kind}/dismiss). No spend change.

        recommendations: [{"id": "rec-1", "promotedObjectId": "123",
                           "promotedObjectType": "APPSTORE_APP"}]
        """
        if not recommendations:
            raise ValueError("Pass at least one recommendation.")
        return client.request(
            "POST",
            f"recommendations/{_kind(kind)}/dismiss",
            json_body=recommendations,
            op=f"dismiss_{kind}_recommendations",
            ad_account_id=ad_account_id,
        )

    @mcp.tool()
    def apple_ads_keyword_suggestions(
        adam_id: str,
        seed_terms: list[str] | None = None,
        countries_or_regions: list[str] | None = None,
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Keyword ideas for an app (POST /v1/suggestions/keywords/query)."""
        base = _promoted(adam_id)
        if seed_terms:
            base.append(flt("terms", "IN", seed_terms))
        if countries_or_regions:
            base.append(flt("countriesOrRegions", "IN", [c.upper() for c in countries_or_regions]))
        return client.query(
            "suggestions/keywords/query",
            query_body(base_filters=base),
            max_items=max_items,
            ad_account_id=ad_account_id,
            fetch_total=False,
        )

    @mcp.tool()
    def apple_ads_suggestions(
        kind: str,
        filters: list[dict[str, Any]],
        max_items: int = 200,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Other suggestions (POST /v1/suggestions/{kind}/query).

        kind: phrases (natural-language search phrases), categories (genre
        categories) or target_cpa (recommended target CPA from recent CPI).
        filters: e.g. [{"field": "promotedObjectId", "operator": "EQUALS", "value": ["123"]},
                       {"field": "promotedObjectType", "operator": "EQUALS", "value": ["APPSTORE_APP"]},
                       {"field": "queryType", "operator": "EQUALS", "value": ["SUGGESTION"]}]
        """
        paths = {"phrases": "phrases", "categories": "categories", "target_cpa": "target-cpas"}
        key = kind.lower().replace("-", "_")
        if key not in paths:
            raise ValueError("kind must be phrases, categories or target_cpa")
        return client.query(
            f"suggestions/{paths[key]}/query",
            query_body(filters),
            max_items=max_items,
            ad_account_id=ad_account_id,
            fetch_total=False,
        )
