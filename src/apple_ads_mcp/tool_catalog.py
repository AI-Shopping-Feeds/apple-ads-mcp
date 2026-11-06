"""Title and MCP annotations for every apple_ads_* tool.

`AppleAdsMCPServer.tool()` looks each tool up here by name, so the tool modules
stay free of metadata. Every tool must have an entry: tests/test_mcp_client.py
fails if a registered tool is missing or an entry has no tool.

Annotation kinds (all API tools are open-world: they call Apple Ads):

* READ: changes nothing in Apple Ads. Includes read-only POSTs (`/query`,
  reports, insights, suggestions).
* WRITE: creates something or triggers an action; repeating it has an effect.
* UPSERT: an update or status toggle; repeating it changes nothing more.
* DESTRUCTIVE: deletes, or applies changes to live spend that are hard to undo.
* LOCAL_*: touches only this server (audit log, session settings).
"""

from __future__ import annotations

from typing import NamedTuple

from mcp.types import ToolAnnotations


def _ann(*, read_only: bool, destructive: bool, idempotent: bool, open_world: bool = True):
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=open_world,
    )


READ = _ann(read_only=True, destructive=False, idempotent=True)
WRITE = _ann(read_only=False, destructive=False, idempotent=False)
UPSERT = _ann(read_only=False, destructive=False, idempotent=True)
DESTRUCTIVE = _ann(read_only=False, destructive=True, idempotent=True)
DESTRUCTIVE_ONCE = _ann(read_only=False, destructive=True, idempotent=False)
LOCAL_READ = _ann(read_only=True, destructive=False, idempotent=True, open_world=False)
LOCAL_SETTING = _ann(read_only=False, destructive=False, idempotent=True, open_world=False)


class ToolSpec(NamedTuple):
    title: str
    annotations: ToolAnnotations


# Registered regardless of APPLE_ADS_TOOL_GROUPS and APPLE_ADS_READ_ONLY.
ALWAYS_REGISTERED = frozenset(
    {
        "apple_ads_describe_server",
        "apple_ads_health_check",
        "apple_ads_audit_tail",
        "apple_ads_audit_lookup",
        "apple_ads_set_dry_run",
    }
)

_CATALOG: dict[str, tuple[str, ToolAnnotations]] = {
    # server (meta)
    "apple_ads_describe_server": ("Describe the server configuration", LOCAL_READ),
    "apple_ads_health_check": ("Check credentials and ad account access", READ),
    "apple_ads_audit_tail": ("Show recent audit log entries", LOCAL_READ),
    "apple_ads_audit_lookup": ("Look up an audit log entry", LOCAL_READ),
    "apple_ads_set_dry_run": ("Turn dry-run mode on or off", LOCAL_SETTING),
    # accounts
    "apple_ads_get_me": ("Get the API user and org", READ),
    "apple_ads_list_acls": ("List accessible ad accounts", READ),
    "apple_ads_get_org": ("Get an organization", READ),
    "apple_ads_get_ad_account": ("Get an ad account", READ),
    "apple_ads_get_advertiser_resources": ("List delegable advertiser resources", READ),
    # apps
    "apple_ads_search_apps": ("Search App Store apps", READ),
    "apple_ads_get_app": ("Get app details", READ),
    "apple_ads_query_app_locale_details": ("Get an app's localized page details", READ),
    "apple_ads_check_app_eligibility": ("Check an app's ad eligibility", READ),
    "apple_ads_query_rejection_reasons": ("List creative rejection reasons", READ),
    "apple_ads_get_rejection_reason": ("Get a rejection reason", READ),
    "apple_ads_query_supported_languages": ("List supported App Store languages", READ),
    "apple_ads_query_product_pages": ("List custom product pages", READ),
    "apple_ads_get_product_page": ("Get a custom product page", READ),
    "apple_ads_query_product_page_locales": ("Get custom product page locales", READ),
    # geo
    "apple_ads_search_geo": ("Search geo targets by name", READ),
    "apple_ads_lookup_geo": ("Look up geo targets by ID", READ),
    # campaigns
    "apple_ads_query_campaigns": ("List campaigns", READ),
    "apple_ads_get_campaign": ("Get a campaign", READ),
    "apple_ads_get_campaign_limited_status_reasons": (
        "Explain a campaign's limited delivery",
        READ,
    ),
    "apple_ads_create_campaign": ("Create a campaign", WRITE),
    "apple_ads_update_campaign": ("Update a campaign", UPSERT),
    "apple_ads_set_campaign_status": ("Pause or resume a campaign", UPSERT),
    "apple_ads_set_campaign_daily_budget": ("Set a campaign's daily budget", UPSERT),
    "apple_ads_delete_campaign": ("Delete a campaign", DESTRUCTIVE),
    # ad groups
    "apple_ads_query_adgroups": ("List ad groups", READ),
    "apple_ads_get_adgroup": ("Get an ad group", READ),
    "apple_ads_create_adgroup": ("Create an ad group", WRITE),
    "apple_ads_update_adgroup": ("Update an ad group", UPSERT),
    "apple_ads_set_adgroup_status": ("Pause or resume an ad group", UPSERT),
    "apple_ads_set_adgroup_bid": ("Set an ad group's default bid", UPSERT),
    "apple_ads_delete_adgroup": ("Delete an ad group", DESTRUCTIVE),
    # keywords
    "apple_ads_query_keywords": ("List targeting keywords", READ),
    "apple_ads_get_keyword": ("Get a targeting keyword", READ),
    "apple_ads_add_keywords": ("Add targeting keywords", WRITE),
    "apple_ads_update_keywords": ("Update keyword bids or status", UPSERT),
    "apple_ads_delete_keywords": ("Delete targeting keywords", DESTRUCTIVE),
    "apple_ads_query_negative_keywords": ("List negative keywords", READ),
    "apple_ads_get_negative_keyword": ("Get a negative keyword", READ),
    "apple_ads_add_negative_keywords": ("Add negative keywords", WRITE),
    "apple_ads_update_negative_keywords": ("Update negative keywords", UPSERT),
    "apple_ads_delete_negative_keywords": ("Delete negative keywords", DESTRUCTIVE),
    # ads and creatives
    "apple_ads_query_ads": ("List ads", READ),
    "apple_ads_get_ad": ("Get an ad", READ),
    "apple_ads_create_ad": ("Create an ad", WRITE),
    "apple_ads_update_ad": ("Update an ad", UPSERT),
    "apple_ads_delete_ad": ("Delete an ad", DESTRUCTIVE),
    "apple_ads_query_creatives": ("List ad creatives", READ),
    "apple_ads_get_creative": ("Get an ad creative", READ),
    "apple_ads_create_creative": ("Create an ad creative", WRITE),
    "apple_ads_update_creative": ("Update an ad creative", UPSERT),
    "apple_ads_delete_creative": ("Delete an ad creative", DESTRUCTIVE),
    # budget orders
    "apple_ads_query_budget_orders": ("List budget orders", READ),
    "apple_ads_get_budget_order": ("Get a budget order", READ),
    "apple_ads_create_budget_order": ("Create a budget order", WRITE),
    "apple_ads_update_budget_order": ("Update a budget order", UPSERT),
    "apple_ads_delete_budget_order": ("Delete a budget order", DESTRUCTIVE),
    # reports and insights
    "apple_ads_report": ("Run a performance report", READ),
    "apple_ads_performance_summary": ("Summarize recent performance", READ),
    "apple_ads_impression_share": ("Get impression share by search term", READ),
    "apple_ads_search_term_popularity": ("Get search term popularity", READ),
    # recommendations and suggestions
    "apple_ads_query_recommendations": ("List budget and target CPA recommendations", READ),
    "apple_ads_apply_recommendations": ("Apply recommendations", DESTRUCTIVE_ONCE),
    "apple_ads_dismiss_recommendations": ("Dismiss recommendations", UPSERT),
    "apple_ads_keyword_suggestions": ("Suggest keywords for an app", READ),
    "apple_ads_suggestions": ("Get phrase, category or target CPA suggestions", READ),
    # Apple Maps
    "apple_ads_query_brands": ("List Apple Maps brands", READ),
    "apple_ads_get_brand": ("Get an Apple Maps brand", READ),
    "apple_ads_query_business_categories": ("List business categories", READ),
    "apple_ads_get_business_category": ("Get a business category", READ),
    "apple_ads_query_brand_rejection_reasons": ("List Apple Maps creative rejection reasons", READ),
    "apple_ads_query_locations": ("List business locations", READ),
    "apple_ads_get_location": ("Get a business location", READ),
    "apple_ads_query_location_groups": ("List location groups", READ),
    "apple_ads_get_location_group": ("Get a location group", READ),
    "apple_ads_create_location_group": ("Create a location group", WRITE),
    "apple_ads_update_location_group": ("Update a location group", UPSERT),
    "apple_ads_delete_location_group": ("Delete a location group", DESTRUCTIVE),
    "apple_ads_query_assets": ("List Apple Maps creative assets", READ),
    "apple_ads_get_asset": ("Get an Apple Maps creative asset", READ),
    "apple_ads_delete_asset": ("Delete an Apple Maps creative asset", DESTRUCTIVE),
    # change history
    "apple_ads_query_change_history": ("List account change history", READ),
    "apple_ads_get_change_detail": ("Get a change's before and after values", READ),
    # advanced
    "apple_ads_request": ("Call any Apple Ads API endpoint", DESTRUCTIVE_ONCE),
}

TOOL_SPECS: dict[str, ToolSpec] = {
    name: ToolSpec(title, annotations) for name, (title, annotations) in _CATALOG.items()
}
