# All tools

**89 tools: 84 across 13 groups + 5 meta tools.** 56 are read-only.

Built on the [Apple Ads Platform API](https://developer.apple.com/documentation/apple-ads-platform-api)
v1 (`https://api.ads.apple.com/v1`). Ad account scoped calls send
`X-AP-Context: adAccountId=<id>`: the default comes from
`APPLE_ADS_AD_ACCOUNT_ID`, and every such tool takes `ad_account_id` to
override it for one call.

| Group | Tools |
|---|---|
| **meta** (always on) | `apple_ads_describe_server`, `apple_ads_health_check`, `apple_ads_audit_tail`, `apple_ads_audit_lookup`, `apple_ads_set_dry_run` |
| **accounts** | `apple_ads_get_me`, `apple_ads_list_acls`, `apple_ads_get_org`, `apple_ads_get_ad_account`, `apple_ads_get_advertiser_resources` |
| **apps** | `apple_ads_search_apps`, `apple_ads_get_app`, `apple_ads_query_app_locale_details`, `apple_ads_check_app_eligibility`, `apple_ads_query_rejection_reasons`, `apple_ads_get_rejection_reason`, `apple_ads_query_supported_languages`, `apple_ads_query_product_pages`, `apple_ads_get_product_page`, `apple_ads_query_product_page_locales` |
| **geo** | `apple_ads_search_geo`, `apple_ads_lookup_geo` |
| **campaigns** | `apple_ads_query_campaigns`, `apple_ads_get_campaign`, `apple_ads_get_campaign_limited_status_reasons`, `apple_ads_create_campaign`, `apple_ads_update_campaign`, `apple_ads_set_campaign_status`, `apple_ads_set_campaign_daily_budget`, `apple_ads_delete_campaign` |
| **adgroups** | `apple_ads_query_adgroups`, `apple_ads_get_adgroup`, `apple_ads_create_adgroup`, `apple_ads_update_adgroup`, `apple_ads_set_adgroup_status`, `apple_ads_set_adgroup_bid`, `apple_ads_delete_adgroup` |
| **keywords** | `apple_ads_query_keywords`, `apple_ads_get_keyword`, `apple_ads_add_keywords`, `apple_ads_update_keywords`, `apple_ads_delete_keywords`, `apple_ads_query_negative_keywords`, `apple_ads_get_negative_keyword`, `apple_ads_add_negative_keywords`, `apple_ads_update_negative_keywords`, `apple_ads_delete_negative_keywords` |
| **ads** | `apple_ads_query_ads`, `apple_ads_get_ad`, `apple_ads_create_ad`, `apple_ads_update_ad`, `apple_ads_delete_ad`, `apple_ads_query_creatives`, `apple_ads_get_creative`, `apple_ads_create_creative`, `apple_ads_update_creative`, `apple_ads_delete_creative` |
| **budget_orders** | `apple_ads_query_budget_orders`, `apple_ads_get_budget_order`, `apple_ads_create_budget_order`, `apple_ads_update_budget_order`, `apple_ads_delete_budget_order` |
| **reports** | `apple_ads_report`, `apple_ads_performance_summary`, `apple_ads_impression_share`, `apple_ads_search_term_popularity` |
| **recommendations** | `apple_ads_query_recommendations`, `apple_ads_apply_recommendations`, `apple_ads_dismiss_recommendations`, `apple_ads_keyword_suggestions`, `apple_ads_suggestions` |
| **maps** | `apple_ads_query_brands`, `apple_ads_get_brand`, `apple_ads_query_business_categories`, `apple_ads_get_business_category`, `apple_ads_query_brand_rejection_reasons`, `apple_ads_query_locations`, `apple_ads_get_location`, `apple_ads_query_location_groups`, `apple_ads_get_location_group`, `apple_ads_create_location_group`, `apple_ads_update_location_group`, `apple_ads_delete_location_group`, `apple_ads_query_assets`, `apple_ads_get_asset`, `apple_ads_delete_asset` |
| **change_history** | `apple_ads_query_change_history`, `apple_ads_get_change_detail` |
| **advanced** | `apple_ads_request` |

CLI: `apple-ads-mcp run`, `keygen`, `purge`, `describe`, `version`. Options and
every setting are in [mcp-client-config.md](mcp-client-config.md).

## Endpoint coverage

Every documented Platform API v1 endpoint has a tool except these, which are
reachable through `apple_ads_request`:

| Endpoint | Why not wrapped |
|---|---|
| `POST /v1/ad-accounts`, `PUT /v1/ad-accounts/{id}` | Creating ad accounts and changing delegations is rare, org-level admin work |
| `POST /v1/assets/upload` | Multipart image upload; use the Apple Ads UI |
| `POST/GET/PUT/DELETE` single keyword and negative keyword endpoints (`/v1/keywords`, `/v1/keywords/{id}`, …) | The bulk tools cover create, update and delete, for one item or many |

`apple_ads_request` treats `GET` and `POST …/query` as reads. Every other
method goes through dry-run and the audit log and needs `confirm='APPLY'`
(`'DELETE'` for `DELETE`).

## Conventions

- **Queries.** `/query` endpoints take `filters` (`[{"field", "operator",
  "value", "ignoreCase"}]`), `sorting` (`[{"field", "order": "ASC"|"DESC"}]`)
  and offset pagination. Tools follow pages up to `max_items`; Apple caps
  `pageSize` at 1000 for entity queries, 5000 for reports and 10000 for
  impression share. Deleted entities are returned only if you filter for them.
  One call collects at most 100,000 rows (`max_items` / `max_rows`), and a
  single response over 200 MB is refused: narrow the request instead.
- **Paths and IDs.** `apple_ads_request` takes a path such as
  `/v1/campaigns/query`, not a URL. Paths may only contain letters, digits,
  `-`, `_`, `.`, `~` and `/` (no `..`, no query string: use `query`). String
  IDs must be a single path segment.
- **Partial updates.** `PUT` changes only the fields you send, but arrays
  replace the whole existing array: read first, send the full list.
- **Bulk.** Keyword and negative keyword writes use Apple's bulk endpoints
  (`items: [{correlationId, data}]`). `allow_partial_success=true` keeps the
  valid items when some fail; the result says how many succeeded and failed.
  This server caps a call at 1000 items (Apple documents no limit).
- **Money.** `{"amount": "1.50", "currency": "GBP"}`, amount as a decimal
  string in the ad account's currency. Daily budgets: `{"dailyBudget":
  {"value": {…}}}`. Ad group default bid: `bidStrategy.bid`. Keyword bid: `bid`.
- **Bid strategies.** `bidStrategyType` and `bidStrategyGoal` must be sent
  together and match (e.g. `MANUAL_CPT` with `TAP`, `MAX_CONVERSIONS` with
  `INSTALL`).
- **Reports.** `campaignId` is required for every level except campaigns.
  Granularity: `HOURLY` ≤ 7 days, `DAILY` ≤ 90 days, `WEEKLY` ≥ 14 days,
  `MONTHLY` ≥ 90 days; omit it for a single day. Time zone `ORTZ` (the
  account's) or `UTC`; search term reports are `ORTZ` only.
- **Budget orders** are organization-scoped: create, update and delete are
  sent without `X-AP-Context` (Apple returns 403 if it's present).

## Safety summary

| Action | Needs |
|---|---|
| Any delete | `confirm='DELETE'` |
| More than one keyword / negative keyword in a call | `confirm='APPLY'` |
| Budget or bid raised by more than `APPLE_ADS_MAX_INCREASE_PCT` (default 20%), or set where the current value can't be read | `confirm='APPLY'` |
| `apple_ads_apply_recommendations`, `apple_ads_create_budget_order` | `confirm='APPLY'` |
| Raw writes via `apple_ads_request` | `confirm='APPLY'` / `'DELETE'` |
| Anything in dry-run mode | Nothing: it's previewed and logged, and the preview names the confirm the live call will need |
