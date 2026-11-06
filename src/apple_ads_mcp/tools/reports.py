"""Reports and insights.

Report rows and insights are Apple Ads Reporting Metrics, which Apple's terms
treat as confidential. These tools return them to the caller only: nothing is
written to the audit log or to disk.

Report endpoints: POST /v1/reports/{apps|business-brands}/{campaigns|adgroups|
ads|keywords|searchterms}/query. campaignId is a required filter for every
level except campaigns. Report pageSize max 5000 (default 100).
Granularity limits: HOURLY <= 7 days (start within 365 days), DAILY <= 90 days,
WEEKLY >= 14 days, MONTHLY >= 90 days; omit granularity for one day.
Time zone ORTZ (account reporting time zone, default) or UTC; search-term
reports are ORTZ only.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from mcp.server.mcpserver import Context

from ..client import AppleAdsClient, check_row_limit
from ._common import flt
from ._progress import report, run_blocking

LEVELS = ("campaigns", "adgroups", "ads", "keywords", "searchterms")
PRODUCTS = {
    "apps": "apps",
    "app_store": "apps",
    "brands": "business-brands",
    "maps": "business-brands",
    "business-brands": "business-brands",
}
REPORT_MAX_PAGE_SIZE = 5000
GRANULARITIES = ("HOURLY", "DAILY", "WEEKLY", "MONTHLY")


def _check_dates(start: str, end: str, granularity: str | None) -> tuple[dt.date, dt.date]:
    try:
        s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except ValueError as exc:
        raise ValueError("start and end must be YYYY-MM-DD") from exc
    if e < s:
        raise ValueError("end is before start")
    days = (e - s).days + 1
    g = (granularity or "").upper()
    if g and g not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {', '.join(GRANULARITIES)}")
    if g == "HOURLY" and days > 7:
        raise ValueError("HOURLY reports cover at most 7 days")
    if g == "DAILY" and days > 90:
        raise ValueError("DAILY reports cover at most 90 days; use WEEKLY or MONTHLY")
    if g == "WEEKLY" and days < 14:
        raise ValueError("WEEKLY reports need at least 14 days")
    if g == "MONTHLY" and days < 90:
        raise ValueError("MONTHLY reports need at least 90 days")
    return s, e


def _amount(v: Any) -> Decimal:
    if isinstance(v, dict) and "amount" in v:
        try:
            return Decimal(str(v["amount"]))
        except Exception:
            return Decimal(0)
    return Decimal(0)


def _num(v: Any) -> Decimal:
    try:
        return Decimal(str(v)) if v is not None else Decimal(0)
    except Exception:
        return Decimal(0)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals and ratios across report rows' totalMetrics."""
    spend = impressions = taps = installs = tap_installs = Decimal(0)
    currency = None
    for r in rows:
        m = r.get("totalMetrics") or {}
        spend += _amount(m.get("localSpend"))
        currency = currency or (m.get("localSpend") or {}).get("currency")
        impressions += _num(m.get("impressions"))
        taps += _num(m.get("taps"))
        installs += _num(m.get("totalInstalls"))
        tap_installs += _num(m.get("tapInstalls"))

    def ratio(a: Decimal, b: Decimal, places: str) -> str | None:
        return str((a / b).quantize(Decimal(places))) if b else None

    return {
        "spend": {"amount": str(spend.quantize(Decimal("0.01"))), "currency": currency},
        "impressions": int(impressions),
        "taps": int(taps),
        "tap_installs": int(tap_installs),
        "total_installs": int(installs),
        "ttr": ratio(taps, impressions, "0.0001"),
        "avg_cpt": ratio(spend, taps, "0.01"),
        "cost_per_install": ratio(spend, installs, "0.01"),
        "conversion_rate": ratio(tap_installs, taps, "0.0001"),
    }


def register(mcp, client: AppleAdsClient) -> None:
    async def run_report(
        product: str,
        level: str,
        body: dict[str, Any],
        max_rows: int,
        ad_account_id: str | None,
        ctx: Context | None,
    ) -> dict[str, Any]:
        prod = PRODUCTS.get(product.lower())
        if prod is None:
            raise ValueError("product must be 'apps' (App Store) or 'brands' (Apple Maps)")
        if level not in LEVELS:
            raise ValueError(f"level must be one of {', '.join(LEVELS)}")
        path = f"reports/{prod}/{level}/query"
        max_rows = check_row_limit(max_rows, "max_rows")
        size = max(1, min(max_rows, REPORT_MAX_PAGE_SIZE))
        rows: list[Any] = []
        summary: Any = None
        total: int | None = None
        offset = 0
        truncated = False
        while True:
            body["pagination"] = {"offset": offset, "pageSize": size}
            payload = await run_blocking(
                client.request,
                "POST",
                path,
                json_body=dict(body),
                read_only=True,
                ad_account_id=ad_account_id,
            )
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, dict):
                page = result.get("rows") or []
                if summary is None:
                    summary = result.get("summary")
            else:
                page = result if isinstance(result, list) else []
            pag = payload.get("pagination") if isinstance(payload, dict) else None
            if isinstance(pag, dict) and pag.get("totalCount") is not None:
                total = int(pag["totalCount"])
            rows.extend(page)
            offset += len(page)
            if page:
                await report(
                    ctx, len(rows), max(total or 0, len(rows)), f"Fetched {len(rows)} report rows"
                )
            if len(rows) >= max_rows:
                truncated = total is None or total > max_rows
                rows = rows[:max_rows]
                break
            if not page or len(page) < size or (total is not None and offset >= total):
                break
        body.pop("pagination", None)
        return {
            "result": rows,
            "summary": summary,
            "pagination": {"returned": len(rows), "totalCount": total},
            "truncated": truncated,
        }

    @mcp.tool()
    async def apple_ads_report(
        level: str,
        start: str,
        end: str,
        campaign_id: str | None = None,
        product: str = "apps",
        granularity: str | None = None,
        group_by: list[str] | None = None,
        fields: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        sorting: list[dict[str, Any]] | None = None,
        time_zone: str = "ORTZ",
        include_grand_total: bool = True,
        max_rows: int = 1000,
        ad_account_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Performance report (POST /v1/reports/{apps|business-brands}/{level}/query).

        level: campaigns | adgroups | ads | keywords | searchterms.
        campaign_id: required for every level except campaigns.
        product: apps (App Store) or brands (Apple Maps).
        start/end: YYYY-MM-DD, inclusive. granularity: HOURLY (<=7 days),
        DAILY (<=90), WEEKLY (>=14), MONTHLY (>=90), or omit for totals.
        group_by: deviceClass, ageRange, gender, countryCode, adminArea, locality,
        countryOrRegion (keywords/searchterms: only deviceClass, countryOrRegion).
        fields: limit metric columns, e.g. ["impressions", "taps", "localSpend",
        "tapInstalls"]. time_zone: ORTZ (account) or UTC (searchterms: ORTZ only).
        Spend values are Money objects {"amount": "12.34", "currency": "GBP"}.
        Rows come back to you only; nothing is saved. Reports progress per page.
        """
        if level != "campaigns" and not campaign_id:
            raise ValueError(f"campaign_id is required for {level} reports")
        _check_dates(start, end, granularity)
        tz = time_zone.upper()
        if tz not in ("ORTZ", "UTC"):
            raise ValueError("time_zone must be ORTZ or UTC")
        if level == "searchterms" and tz != "ORTZ":
            raise ValueError("search term reports only support time_zone ORTZ")
        time_range: dict[str, Any] = {"start": start, "end": end, "timeZone": tz}
        if granularity:
            time_range["granularity"] = granularity.upper()
        body: dict[str, Any] = {"timeRange": time_range}
        all_filters = list(filters or [])
        if campaign_id:
            all_filters.insert(0, flt("campaignId", "EQUALS", str(int(campaign_id))))
        if all_filters:
            body["filters"] = all_filters
        if group_by:
            body["groupBy"] = group_by
        if fields:
            body["fields"] = fields
        if sorting:
            body["sorting"] = sorting
        if include_grand_total and not group_by:
            body["options"] = {"includeRows": ["GRAND_TOTAL"]}
        out = await run_report(product, level, body, max_rows, ad_account_id, ctx)
        return {**out, "request": body}

    @mcp.tool()
    async def apple_ads_performance_summary(
        days: int = 7,
        level: str = "campaigns",
        campaign_id: str | None = None,
        product: str = "apps",
        end: str | None = None,
        include_rows: bool = True,
        max_rows: int = 500,
        ad_account_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Quick performance summary for the last N days (default 7, ending yesterday).

        Returns totals (spend, impressions, taps, installs, TTR, average CPT,
        cost per install, tap conversion rate) and, if include_rows, one row per
        campaign (or ad group/keyword when level and campaign_id are set) sorted
        by spend. Uses DAILY granularity under the hood (max 90 days).
        """
        if not 1 <= days <= 90:
            raise ValueError("days must be between 1 and 90")
        end_date = dt.date.fromisoformat(end) if end else dt.date.today() - dt.timedelta(days=1)
        start_date = end_date - dt.timedelta(days=days - 1)
        result = await apple_ads_report(
            level=level,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            campaign_id=campaign_id,
            product=product,
            granularity=None if days == 1 else "DAILY",
            include_grand_total=False,
            max_rows=max_rows,
            ad_account_id=ad_account_id,
            ctx=ctx,
        )
        rows = [r for r in result["result"] if isinstance(r, dict)]
        compact = []
        for r in rows:
            meta = r.get("metadata") or {}
            compact.append(
                {
                    "id": meta.get("id"),
                    "name": meta.get("name") or meta.get("text") or meta.get("searchTerm"),
                    "status": meta.get("status"),
                    **summarise([r]),
                }
            )
        compact.sort(key=lambda x: Decimal(x["spend"]["amount"]), reverse=True)
        out: dict[str, Any] = {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "level": level,
            "totals": summarise(rows),
            "row_count": len(rows),
            "truncated": result.get("truncated", False),
        }
        if include_rows:
            out["rows"] = compact
        return out

    @mcp.tool()
    def apple_ads_impression_share(
        start: str,
        end: str,
        adam_ids: list[str] | None = None,
        country_or_region: str | None = None,
        search_term_contains: str | None = None,
        granularity: str = "DAILY",
        report_type: str = "ALL_SLOTS",
        filters: list[dict[str, Any]] | None = None,
        sorting: list[dict[str, Any]] | None = None,
        max_rows: int = 1000,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Impression share by search term and country (POST /v1/insights/apps/impression-share/query).

        granularity: DAILY (max 30 days) or WEEKLY_SUN_SAT (max 4 weeks, start
        must be a Sunday). report_type: ALL_SLOTS or FIRST_SLOT. Time zone is
        UTC. lowImpressionShare/highImpressionShare are bands: 0.91-1 means
        over 90%. Terms with fewer than 10 impressions are hidden by Apple.
        """
        g = granularity.upper()
        if g not in ("DAILY", "WEEKLY_SUN_SAT"):
            raise ValueError("granularity must be DAILY or WEEKLY_SUN_SAT")
        s, e = _check_dates(start, end, None)
        if g == "DAILY" and (e - s).days + 1 > 30:
            raise ValueError("DAILY impression share covers at most 30 days")
        if g == "WEEKLY_SUN_SAT":
            if s.weekday() != 6:
                raise ValueError("WEEKLY_SUN_SAT needs start on a Sunday")
            if (e - s).days + 1 > 28:
                raise ValueError("WEEKLY_SUN_SAT covers at most 4 weeks")
        all_filters = list(filters or [])
        if adam_ids:
            all_filters.append(flt("promotedObjectId", "IN", [str(a) for a in adam_ids]))
        if country_or_region:
            all_filters.append(flt("countryOrRegion", "EQUALS", country_or_region.upper()))
        if search_term_contains:
            all_filters.append(flt("searchTerm", "CONTAINS", search_term_contains))
        body: dict[str, Any] = {
            "timeRange": {"start": start, "end": end, "granularity": g},
            "options": {"impressionShareReportType": report_type.upper()},
        }
        if all_filters:
            body["filters"] = all_filters
        if sorting:
            body["sorting"] = sorting[:2]
        check_row_limit(max_rows, "max_rows")
        return client.query(
            "insights/apps/impression-share/query",
            body,
            max_items=max_rows,
            page_size=1000,
            max_page_size=10000,
            ad_account_id=ad_account_id,
            fetch_total=False,
        )

    @mcp.tool()
    def apple_ads_search_term_popularity(
        start: str,
        end: str,
        country_or_region: str,
        genre: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        sorting: list[dict[str, Any]] | None = None,
        granularity: str = "WEEKLY_SUN_SAT",
        max_rows: int = 500,
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Search term popularity rankings by country and App Store genre
        (POST /v1/insights/apps/search-term-popularity/query).

        genre: e.g. GAMES_SPORTS or PRODUCTIVITY_UTILITIES (see Apple's docs for
        the list). start should be a Sunday for WEEKLY_SUN_SAT.
        """
        _check_dates(start, end, None)
        all_filters = [flt("countryOrRegion", "EQUALS", country_or_region.upper())]
        if genre:
            all_filters.append(flt("genre", "EQUALS", genre.upper()))
        all_filters += list(filters or [])
        body: dict[str, Any] = {
            "filters": all_filters,
            "timeRange": {"start": start, "end": end, "granularity": granularity.upper()},
        }
        if sorting:
            body["sorting"] = sorting
        check_row_limit(max_rows, "max_rows")
        return client.query(
            "insights/apps/search-term-popularity/query",
            body,
            max_items=max_rows,
            ad_account_id=ad_account_id,
            fetch_total=False,
        )
