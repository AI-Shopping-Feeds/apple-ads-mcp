"""End-to-end tests through `mcp.Client` against the real server (fake auth, mocked HTTP)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import Tool

from apple_ads_mcp import __version__, server, tools
from apple_ads_mcp.client import BASE_URL, AppleAdsClient
from apple_ads_mcp.config import Config, load_config
from apple_ads_mcp.tool_catalog import ALWAYS_REGISTERED, TOOL_SPECS

from .conftest import ACCOUNT, FakeAuth

META_TOOLS = [
    "apple_ads_describe_server",
    "apple_ads_health_check",
    "apple_ads_audit_tail",
    "apple_ads_audit_lookup",
    "apple_ads_set_dry_run",
]


@pytest.fixture(autouse=True)
def fake_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "make_auth", lambda config: FakeAuth())


def _build(config: Config, **changes: Any) -> MCPServer:
    return server.build_server(dataclasses.replace(config, **changes))


async def _tools(mcp: MCPServer) -> list[Tool]:
    async with Client(mcp) as c:
        return (await c.list_tools()).tools


def _payload(result) -> Any:
    return result.structured_content or json.loads(result.content[0].text)


def _group_tool_names(client: AppleAdsClient) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for group in tools.TOOL_GROUPS:
        mcp = MCPServer("probe")
        getattr(tools, group).register(mcp, client)
        out[group] = list(mcp._tool_manager._tools)
    return out


# ---------------------------------------------------------------- metadata


async def test_server_reports_version_and_instructions(config: Config) -> None:
    async with Client(_build(config)) as c:
        assert c.server_info is not None
        assert c.server_info.name == "apple-ads-mcp"
        assert c.server_info.version == __version__
        assert c.instructions
        assert "apple_ads_describe_server" in c.instructions
        assert "dry-run" in c.instructions
        assert "APPLE_ADS_TOOL_GROUPS" in c.instructions
        assert 4 <= len(c.instructions.splitlines()) <= 10


async def test_every_tool_has_a_catalog_entry(config: Config) -> None:
    listed = await _tools(_build(config))
    names = {t.name for t in listed}
    # Every registered tool has a catalog entry, and the catalog has no stale entries.
    assert names == set(TOOL_SPECS)
    assert len(listed) == len(TOOL_SPECS)
    for tool in listed:
        assert tool.name.startswith("apple_ads_"), tool.name
        assert tool.title, tool.name
        assert tool.title[0].isupper(), tool.name
        assert tool.description, tool.name
        a = tool.annotations
        assert a is not None, tool.name
        assert a.read_only_hint is not None, tool.name
        assert a.destructive_hint is not None, tool.name
        assert a.idempotent_hint is not None, tool.name
        assert a.open_world_hint is not None, tool.name


async def test_annotations_are_plausible(config: Config) -> None:
    by_name = {t.name: t.annotations for t in await _tools(_build(config))}
    read_only = {n for n, a in by_name.items() if a and a.read_only_hint}
    destructive = {n for n, a in by_name.items() if a and a.destructive_hint}
    assert not read_only & destructive
    for name in by_name:
        verb = name.removeprefix("apple_ads_").split("_")[0]
        if verb in {"get", "query", "list", "search", "lookup", "check"}:
            assert name in read_only, name
        if verb == "delete":
            assert name in destructive, name
        if (
            verb in {"create", "update", "set", "add", "apply", "dismiss"}
            and name != "apple_ads_set_dry_run"
        ):
            assert name not in read_only, name
    assert "apple_ads_report" in read_only
    assert "apple_ads_apply_recommendations" in destructive
    closed = {n for n, a in by_name.items() if a and a.open_world_hint is False}
    assert closed == set(META_TOOLS) - {"apple_ads_health_check"}


async def test_tools_list_order_is_deterministic(config: Config, client: AppleAdsClient) -> None:
    first = [t.name for t in await _tools(_build(config))]
    per_group = _group_tool_names(client)
    assert first == META_TOOLS + [n for g in tools.TOOL_GROUPS for n in per_group[g]]


# ---------------------------------------------------------------- filtering


async def test_tool_groups_limit_registration(config: Config, client: AppleAdsClient) -> None:
    names = [t.name for t in await _tools(_build(config, tool_groups=["reports", "campaigns"]))]
    per_group = _group_tool_names(client)
    assert names == META_TOOLS + per_group["campaigns"] + per_group["reports"]


async def test_read_only_registers_only_read_tools(config: Config) -> None:
    listed = await _tools(_build(config, read_only=True))
    names = {t.name for t in listed}
    assert set(META_TOOLS) <= names
    for tool in listed:
        if tool.name not in ALWAYS_REGISTERED:
            assert tool.annotations and tool.annotations.read_only_hint, tool.name
    assert "apple_ads_delete_campaign" not in names
    assert "apple_ads_request" not in names
    assert "apple_ads_query_campaigns" in names
    expected = {n for n, s in TOOL_SPECS.items() if s.annotations.read_only_hint}
    assert names == expected | set(META_TOOLS)


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path, **values: str) -> Path:
    monkeypatch.setenv("APPLE_ADS_CLIENT_ID", "SEARCHADS.abc")
    monkeypatch.setenv("APPLE_ADS_TEAM_ID", "SEARCHADS.abc")
    monkeypatch.setenv("APPLE_ADS_KEY_ID", "kid")
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    monkeypatch.setenv("APPLE_ADS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    for var in ("APPLE_ADS_AD_ACCOUNT_ID", "APPLE_ADS_TOOL_GROUPS", "APPLE_ADS_READ_ONLY"):
        monkeypatch.delenv(var, raising=False)
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return tmp_path / "missing.env"


async def test_env_vars_filter_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    env_file = _env(
        monkeypatch,
        tmp_path,
        key_file,
        APPLE_ADS_TOOL_GROUPS="accounts,geo",
        APPLE_ADS_READ_ONLY="1",
    )
    names = {t.name for t in await _tools(server.build_server(env_file=env_file))}
    assert names == set(META_TOOLS) | {
        "apple_ads_get_me",
        "apple_ads_list_acls",
        "apple_ads_get_org",
        "apple_ads_get_ad_account",
        "apple_ads_get_advertiser_resources",
        "apple_ads_search_geo",
        "apple_ads_lookup_geo",
    }


def test_unknown_group_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    env_file = _env(monkeypatch, tmp_path, key_file, APPLE_ADS_TOOL_GROUPS="campaigns,nope")
    with pytest.raises(RuntimeError) as exc_info:
        load_config(env_file=env_file)
    message = str(exc_info.value)
    assert "nope" in message
    for group in tools.TOOL_GROUPS:
        assert group in message


def test_missing_credentials_are_explained(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> None:
    env_file = _env(monkeypatch, tmp_path, key_file)
    monkeypatch.delenv("APPLE_ADS_KEY_ID")
    with pytest.raises(RuntimeError, match="APPLE_ADS_KEY_ID"):
        load_config(env_file=env_file)


# ---------------------------------------------------------------- calls


@respx.mock
async def test_get_campaign_returns_result(config: Config) -> None:
    respx.get(f"{BASE_URL}/campaigns/42").mock(
        return_value=httpx.Response(200, json={"result": {"id": 42, "name": "UK"}})
    )
    async with Client(_build(config)) as c:
        result = await c.call_tool("apple_ads_get_campaign", {"campaign_id": "42"})
    assert not result.is_error
    assert _payload(result)["name"] == "UK"


@respx.mock
async def test_api_error_reaches_the_client(config: Config) -> None:
    respx.get(f"{BASE_URL}/campaigns/9").mock(
        return_value=httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "nope"}})
    )
    async with Client(_build(config)) as c:
        result = await c.call_tool("apple_ads_get_campaign", {"campaign_id": "9"})
    assert result.is_error
    text = " ".join(getattr(b, "text", "") for b in result.content)
    assert "Apple Ads API error 404" in text
    assert "NOT_FOUND" in text


@respx.mock
async def test_org_override_via_tool_argument(config: Config) -> None:
    route = respx.post(f"{BASE_URL}/campaigns/query").mock(
        return_value=httpx.Response(200, json={"result": [], "pagination": {"totalCount": 0}})
    )
    async with Client(_build(config)) as c:
        await c.call_tool("apple_ads_query_campaigns", {"ad_account_id": "555"})
        await c.call_tool("apple_ads_query_campaigns", {})
    assert route.calls[0].request.headers["X-AP-Context"] == "adAccountId=555"
    assert route.calls[1].request.headers["X-AP-Context"] == f"adAccountId={ACCOUNT}"


@respx.mock
async def test_health_check_lists_ad_accounts(config: Config) -> None:
    respx.get(f"{BASE_URL}/me").mock(
        return_value=httpx.Response(200, json={"result": {"userId": 1, "orgId": 2}})
    )
    acls = respx.get(f"{BASE_URL}/acls").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "acls": [
                        {
                            "adAccount": {"id": 123456789, "name": "Example App", "orgId": 2},
                            "roles": ["API Account Manager"],
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{BASE_URL}/ad-accounts/{ACCOUNT}").mock(
        return_value=httpx.Response(200, json={"result": {"id": 123456789, "currency": "GBP"}})
    )
    async with Client(_build(config)) as c:
        payload = _payload(await c.call_tool("apple_ads_health_check", {}))
    assert payload["ok"] is True
    assert payload["ad_accounts"][0]["roles"] == ["API Account Manager"]
    assert payload["default_ad_account"]["currency"] == "GBP"
    assert "X-AP-Context" not in acls.calls[0].request.headers


@respx.mock
async def test_campaign_report_builds_the_request_and_keeps_data_out_of_audit(
    config: Config,
) -> None:
    bodies: list[dict] = []

    def report(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "result": {
                    "rows": [
                        {
                            "metadata": {"id": 1, "name": "UK Search", "status": "ENABLED"},
                            "totalMetrics": {
                                "localSpend": {"amount": "30.00", "currency": "GBP"},
                                "impressions": 1000,
                                "taps": 60,
                                "tapInstalls": 15,
                                "totalInstalls": 20,
                            },
                        },
                        {
                            "metadata": {"id": 2, "name": "US Search", "status": "PAUSED"},
                            "totalMetrics": {
                                "localSpend": {"amount": "10.00", "currency": "GBP"},
                                "impressions": 1000,
                                "taps": 40,
                                "tapInstalls": 5,
                                "totalInstalls": 5,
                            },
                        },
                    ],
                    "summary": {"grandTotal": {"impressions": 2000}},
                },
                "pagination": {"offset": 0, "pageSize": 1000, "totalCount": 2},
            },
        )

    respx.post(f"{BASE_URL}/reports/apps/campaigns/query").mock(side_effect=report)
    async with Client(_build(config)) as c:
        raw = _payload(
            await c.call_tool(
                "apple_ads_report",
                {
                    "level": "campaigns",
                    "start": "2026-10-01",
                    "end": "2026-10-31",
                    "granularity": "DAILY",
                    "group_by": ["countryOrRegion"],
                },
            )
        )
        summary = _payload(
            await c.call_tool("apple_ads_performance_summary", {"days": 7, "end": "2026-11-05"})
        )
    assert raw["summary"] == {"grandTotal": {"impressions": 2000}}
    assert len(raw["result"]) == 2
    assert bodies[0]["timeRange"] == {
        "start": "2026-10-01",
        "end": "2026-10-31",
        "timeZone": "ORTZ",
        "granularity": "DAILY",
    }
    assert bodies[0]["groupBy"] == ["countryOrRegion"]
    assert bodies[0]["pagination"] == {"offset": 0, "pageSize": 1000}
    assert bodies[1]["timeRange"]["start"] == "2026-10-30"
    totals = summary["totals"]
    assert totals["spend"] == {"amount": "40.00", "currency": "GBP"}
    assert totals["taps"] == 100
    assert totals["avg_cpt"] == "0.40"
    assert totals["cost_per_install"] == "1.60"
    assert [r["id"] for r in summary["rows"]] == [1, 2]
    assert not config.audit_log.exists()


async def test_report_validates_granularity_and_campaign(config: Config) -> None:
    async with Client(_build(config)) as c:
        r1 = await c.call_tool(
            "apple_ads_report",
            {
                "level": "campaigns",
                "start": "2026-01-01",
                "end": "2026-06-01",
                "granularity": "DAILY",
            },
        )
        r2 = await c.call_tool(
            "apple_ads_report", {"level": "keywords", "start": "2026-10-01", "end": "2026-10-02"}
        )
    assert r1.is_error and "90 days" in r1.content[0].text
    assert r2.is_error and "campaign_id" in r2.content[0].text


# ---------------------------------------------------------------- safety


@respx.mock
async def test_budget_increase_over_limit_needs_confirm(config: Config) -> None:
    respx.get(f"{BASE_URL}/campaigns/7").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "id": 7,
                    "dailyBudget": {"value": {"amount": "10.00", "currency": "GBP"}},
                }
            },
        )
    )
    put = respx.put(f"{BASE_URL}/campaigns/7").mock(
        return_value=httpx.Response(200, json={"result": {"id": 7}})
    )
    args = {"campaign_id": "7", "amount": "15", "currency": "GBP"}
    async with Client(_build(config)) as c:
        refused = await c.call_tool("apple_ads_set_campaign_daily_budget", args)
        small = await c.call_tool(
            "apple_ads_set_campaign_daily_budget", {**args, "amount": "11.50"}
        )
        applied = await c.call_tool(
            "apple_ads_set_campaign_daily_budget", {**args, "confirm": "APPLY"}
        )
    assert refused.is_error
    assert "confirm='APPLY'" in refused.content[0].text
    assert "+50.0%" in refused.content[0].text
    assert not small.is_error
    assert not applied.is_error
    assert put.call_count == 2
    sent = json.loads(put.calls[1].request.content)
    assert sent == {"dailyBudget": {"value": {"amount": "15.00", "currency": "GBP"}}}
    audit = [json.loads(x) for x in config.audit_log.read_text(encoding="utf-8").splitlines()]
    assert audit[-1]["before"]["dailyBudget"]["value"]["amount"] == "10.00"
    assert audit[-1]["op"] == "set_campaign_daily_budget"


async def test_delete_needs_confirm(config: Config) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.delete(f"{BASE_URL}/campaigns/7").mock(return_value=httpx.Response(200))
        async with Client(_build(config)) as c:
            result = await c.call_tool("apple_ads_delete_campaign", {"campaign_id": "7"})
    assert result.is_error
    assert "confirm='DELETE'" in result.content[0].text
    assert not route.called


async def test_bulk_keywords_need_confirm_but_dry_run_previews(config: Config) -> None:
    keywords = [
        {"adGroupId": 1, "text": "puzzle game", "matchType": "EXACT"},
        {"adGroupId": 1, "text": "soccer manager", "matchType": "EXACT"},
    ]
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{BASE_URL}/keywords/bulk-create").mock(
            return_value=httpx.Response(200, json={"result": []})
        )
        async with Client(_build(config)) as c:
            refused = await c.call_tool("apple_ads_add_keywords", {"keywords": keywords})
            await c.call_tool("apple_ads_set_dry_run", {"enabled": True})
            preview = _payload(await c.call_tool("apple_ads_add_keywords", {"keywords": keywords}))
    assert refused.is_error and "bulk change of 2 keywords" in refused.content[0].text
    assert preview["_dry_run"] is True
    assert preview["confirm_required_when_live"] == "APPLY"
    assert [i["correlationId"] for i in preview["body"]["items"]] == [0, 1]
    assert not route.called
    [entry] = [json.loads(x) for x in config.audit_log.read_text(encoding="utf-8").splitlines()]
    assert entry["dry_run"] is True and entry["op"] == "add_keywords"


@respx.mock
async def test_keyword_bid_increase_checks_current_bids(config: Config) -> None:
    respx.post(f"{BASE_URL}/keywords/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [{"id": 5, "bid": {"amount": "1.00", "currency": "GBP"}}],
                "pagination": {"totalCount": 1},
            },
        )
    )
    update = respx.post(f"{BASE_URL}/keywords/bulk-update").mock(
        return_value=httpx.Response(200, json={"result": [{"correlationId": 0, "success": True}]})
    )
    async with Client(_build(config)) as c:
        refused = await c.call_tool(
            "apple_ads_update_keywords",
            {"updates": [{"id": 5, "bid": {"amount": "2.00", "currency": "GBP"}}]},
        )
        ok = await c.call_tool(
            "apple_ads_update_keywords",
            {"updates": [{"id": 5, "bid": {"amount": "1.10", "currency": "GBP"}}]},
        )
    assert refused.is_error and "+100.0%" in refused.content[0].text
    assert not ok.is_error
    assert _payload(ok)["succeeded"] == 1
    assert update.call_count == 1


@respx.mock
async def test_budget_order_writes_omit_ad_account_header(config: Config) -> None:
    route = respx.post(f"{BASE_URL}/shared-budgets").mock(
        return_value=httpx.Response(200, json={"result": {"id": 1}})
    )
    async with Client(_build(config)) as c:
        result = await c.call_tool(
            "apple_ads_create_budget_order",
            {
                "budget_order": {"name": "Q1", "value": {"amount": "500", "currency": "GBP"}},
                "confirm": "APPLY",
            },
        )
    assert not result.is_error
    assert "X-AP-Context" not in route.calls[0].request.headers


async def test_escape_hatch_refuses_other_hosts_and_unconfirmed_writes(config: Config) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.put(f"{BASE_URL}/ads/1").mock(return_value=httpx.Response(200, json={}))
        async with Client(_build(config)) as c:
            url = await c.call_tool(
                "apple_ads_request", {"method": "GET", "path": "https://example.com/v1/me"}
            )
            write = await c.call_tool(
                "apple_ads_request",
                {"method": "PUT", "path": "/v1/ads/1", "body": {"status": "PAUSED"}},
            )
    assert url.is_error and "not a full URL" in url.content[0].text
    assert write.is_error and "confirm='APPLY'" in write.content[0].text
    assert not route.called


async def test_escape_hatch_refuses_query_strings_and_odd_paths(config: Config) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host="api.ads.apple.com").mock(
            return_value=httpx.Response(200, json={})
        )
        async with Client(_build(config)) as c:
            results = [
                await c.call_tool("apple_ads_request", {"method": "GET", "path": path})
                for path in ("/v1/campaigns?limit=1", "/v1/campaigns/%2e%2e/acls", "/v1/a//b")
            ]
    assert all(r.is_error for r in results)
    assert not route.called


async def test_string_ids_must_be_single_path_segments(config: Config) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host="api.ads.apple.com").mock(
            return_value=httpx.Response(200, json={})
        )
        async with Client(_build(config)) as c:
            get = await c.call_tool("apple_ads_get_brand", {"brand_id": "1/../../acls"})
            delete = await c.call_tool(
                "apple_ads_delete_location_group",
                {"location_group_id": "5/locations", "confirm": "DELETE"},
            )
    assert get.is_error and "single ID" in get.content[0].text
    assert delete.is_error and "single ID" in delete.content[0].text
    assert not route.called


async def test_report_row_ceiling(config: Config) -> None:
    async with Client(_build(config)) as c:
        result = await c.call_tool(
            "apple_ads_report",
            {"level": "campaigns", "start": "2026-10-01", "end": "2026-10-07", "max_rows": 10**7},
        )
    assert result.is_error and "max_rows can be at most" in result.content[0].text


@respx.mock
async def test_escape_hatch_query_is_a_read(config: Config) -> None:
    respx.post(f"{BASE_URL}/ads/query").mock(
        return_value=httpx.Response(200, json={"result": [{"id": 1}]})
    )
    async with Client(_build(config)) as c:
        out = _payload(
            await c.call_tool(
                "apple_ads_request", {"method": "POST", "path": "/v1/ads/query", "body": {}}
            )
        )
    assert out["result"] == [{"id": 1}]
    assert not config.audit_log.exists()


async def test_describe_server_reports_settings_without_secrets(config: Config) -> None:
    async with Client(_build(config, tool_groups=["reports"], read_only=True)) as c:
        payload = _payload(await c.call_tool("apple_ads_describe_server", {}))
    assert payload["tool_groups"] == ["reports"]
    assert payload["read_only"] is True
    assert payload["default_ad_account_id"] == ACCOUNT
    assert payload["version"] == __version__
    text = json.dumps(payload)
    assert "PRIVATE KEY" not in text
    assert "private_key" not in text
    assert "SEARCHADS.11111111-2222-3333-4444-555555555555" not in text


def test_version_matches_pyproject() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert f'\nversion = "{__version__}"\n' in pyproject
