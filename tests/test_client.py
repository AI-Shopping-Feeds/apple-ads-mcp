"""HTTP layer: headers, ad account context, retries, rate limits, dry-run, audit."""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
import respx

from apple_ads_mcp.audit import AuditLog
from apple_ads_mcp.client import BASE_URL, AppleAdsAPIError, AppleAdsClient, normalise_path

from .conftest import ACCOUNT, FakeAuth


def _audit_lines(path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@respx.mock
def test_requests_carry_bearer_and_ad_account_context(client: AppleAdsClient) -> None:
    route = respx.get(f"{BASE_URL}/campaigns/1").mock(
        return_value=httpx.Response(200, json={"result": {"id": 1}})
    )
    assert client.get_result("campaigns/1") == {"id": 1}
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer fake-token"
    assert req.headers["X-AP-Context"] == f"adAccountId={ACCOUNT}"
    assert req.headers["User-Agent"].startswith("apple-ads-mcp/")


@respx.mock
def test_ad_account_can_be_overridden_per_call(client: AppleAdsClient) -> None:
    route = respx.get(f"{BASE_URL}/campaigns/1").mock(
        return_value=httpx.Response(200, json={"result": {}})
    )
    client.get_result("campaigns/1", ad_account_id="999")
    assert route.calls[0].request.headers["X-AP-Context"] == "adAccountId=999"


@respx.mock
def test_account_less_endpoints_omit_the_header(client: AppleAdsClient) -> None:
    route = respx.get(f"{BASE_URL}/acls").mock(
        return_value=httpx.Response(200, json={"result": {}})
    )
    client.get_result("acls", context="none")
    assert "X-AP-Context" not in route.calls[0].request.headers


def test_missing_ad_account_is_a_clear_error(client: AppleAdsClient) -> None:
    client.config = dataclasses.replace(client.config, ad_account_id=None)
    with pytest.raises(ValueError, match="apple_ads_list_acls"):
        client.get_result("campaigns/1")


def test_non_numeric_ad_account_is_rejected(client: AppleAdsClient) -> None:
    with pytest.raises(ValueError, match="numeric"):
        client.get_result("campaigns/1", ad_account_id="abc")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/v1/campaigns/query", "campaigns/query"),
        ("v1/campaigns", "campaigns"),
        ("campaigns/1", "campaigns/1"),
        ("/acls", "acls"),
    ],
)
def test_paths_are_normalised(raw: str, expected: str) -> None:
    assert normalise_path(raw) == expected


@pytest.mark.parametrize("bad", ["https://evil.example/v1/x", "//evil.example/x", "v1/../x"])
def test_other_hosts_and_traversal_are_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        normalise_path(bad)


@respx.mock
def test_reads_are_not_audited(client: AppleAdsClient, tmp_audit_log) -> None:
    respx.post(f"{BASE_URL}/reports/apps/campaigns/query").mock(
        return_value=httpx.Response(200, json={"result": {"rows": [{"spend": 1}]}})
    )
    client.request("POST", "reports/apps/campaigns/query", json_body={}, read_only=True)
    assert _audit_lines(tmp_audit_log) == []


@respx.mock
def test_writes_are_audited_with_before_and_redacted(client: AppleAdsClient, tmp_audit_log) -> None:
    respx.put(f"{BASE_URL}/campaigns/1").mock(
        return_value=httpx.Response(
            200, json={"result": {"id": 1, "status": "PAUSED", "token": "should-hide"}}
        )
    )
    out = client.request(
        "PUT",
        "campaigns/1",
        json_body={"status": "PAUSED", "note": "Bearer abc.def.ghi"},
        op="set_status",
        before={"id": 1, "status": "ENABLED"},
    )
    assert out["audit_id"]
    [entry] = _audit_lines(tmp_audit_log)
    assert entry["op"] == "set_status"
    assert entry["before"] == {"id": 1, "status": "ENABLED"}
    assert entry["ad_account_id"] == ACCOUNT
    assert entry["response_status"] == 200
    assert entry["response_body"]["result"]["token"] == "[REDACTED]"
    assert "abc.def.ghi" not in json.dumps(entry)


def test_dry_run_sends_nothing_and_audits(client: AppleAdsClient, tmp_audit_log) -> None:
    client.config.dry_run = True
    with respx.mock(assert_all_called=False) as router:
        route = router.put(f"{BASE_URL}/campaigns/1").mock(return_value=httpx.Response(200))
        out = client.request("PUT", "campaigns/1", json_body={"status": "PAUSED"})
    assert out["_dry_run"] is True
    assert out["body"] == {"status": "PAUSED"}
    assert not route.called
    [entry] = _audit_lines(tmp_audit_log)
    assert entry["dry_run"] is True


def test_dry_run_still_allows_reads(client: AppleAdsClient) -> None:
    client.config.dry_run = True
    with respx.mock() as router:
        router.post(f"{BASE_URL}/campaigns/query").mock(
            return_value=httpx.Response(
                200, json={"result": [{"id": 1}], "pagination": {"totalCount": 1}}
            )
        )
        out = client.query("campaigns/query", {})
    assert out["result"] == [{"id": 1}]


@respx.mock
def test_failed_write_is_audited_and_raises(client: AppleAdsClient, tmp_audit_log) -> None:
    respx.post(f"{BASE_URL}/adgroups").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Validation errors found",
                    "details": [
                        {"code": "DUPLICATE_NAME", "message": "exists", "info": {"field": "name"}}
                    ],
                }
            },
        )
    )
    with pytest.raises(AppleAdsAPIError) as exc_info:
        client.request("POST", "adgroups", json_body={"name": "x"})
    assert "DUPLICATE_NAME" in str(exc_info.value)
    assert "(name)" in str(exc_info.value)
    [entry] = _audit_lines(tmp_audit_log)
    assert entry["error"] == "HTTP 400"


@respx.mock
def test_429_waits_for_retry_after(client: AppleAdsClient, sleeps: list[float]) -> None:
    route = respx.get(f"{BASE_URL}/campaigns/1").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7", "RateLimit-Reset": "30"}),
            httpx.Response(200, json={"result": {"id": 1}}),
        ]
    )
    assert client.get_result("campaigns/1") == {"id": 1}
    assert route.call_count == 2
    assert sleeps == [7.0]


@respx.mock
def test_429_falls_back_to_ratelimit_reset(client: AppleAdsClient, sleeps: list[float]) -> None:
    respx.get(f"{BASE_URL}/campaigns/1").mock(
        side_effect=[
            httpx.Response(429, headers={"RateLimit-Reset": "12"}),
            httpx.Response(200, json={"result": {}}),
        ]
    )
    client.get_result("campaigns/1")
    assert sleeps == [12.0]


@respx.mock
def test_low_remaining_quota_pauses_before_next_request(
    client: AppleAdsClient, sleeps: list[float]
) -> None:
    respx.get(f"{BASE_URL}/campaigns/1").mock(
        return_value=httpx.Response(
            200,
            json={"result": {}},
            headers={"RateLimit-Limit": "100", "RateLimit-Remaining": "1", "RateLimit-Reset": "9"},
        )
    )
    client.get_result("campaigns/1")
    assert client.rate_limit == {"limit": 100, "remaining": 1, "reset_seconds": 9}
    assert sleeps == []
    client.get_result("campaigns/1")
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 9


@respx.mock
def test_401_refreshes_the_token_once(config, audit, sleeps) -> None:
    class CountingAuth(FakeAuth):
        def __init__(self) -> None:
            self.invalidated = 0

        def invalidate(self) -> None:
            self.invalidated += 1

    auth = CountingAuth()
    c = AppleAdsClient(config, auth, audit, sleep=sleeps.append)  # type: ignore[arg-type]
    respx.get(f"{BASE_URL}/campaigns/1").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"result": {"ok": True}})]
    )
    assert c.get_result("campaigns/1") == {"ok": True}
    assert auth.invalidated == 1


@respx.mock
def test_query_follows_offset_pagination(client: AppleAdsClient) -> None:
    bodies: list[dict] = []

    def page(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        offset = body["pagination"]["offset"]
        size = body["pagination"]["pageSize"]
        rows = [{"id": i} for i in range(offset, min(offset + size, 120))]
        return httpx.Response(200, json={"result": rows, "pagination": {"totalCount": 120}})

    respx.post(f"{BASE_URL}/keywords/query").mock(side_effect=page)
    out = client.query("keywords/query", {"filters": []}, page_size=50)
    assert [b["pagination"]["offset"] for b in bodies] == [0, 50, 100]
    assert bodies[0]["pagination"]["fetchTotalCount"] is True
    assert len(out["result"]) == 120
    assert out["truncated"] is False

    bodies.clear()
    out = client.query("keywords/query", {}, page_size=50, max_items=60)
    assert len(out["result"]) == 60
    assert out["truncated"] is True


def test_audit_prune_and_purge(tmp_path) -> None:
    log = AuditLog(tmp_path / "a.jsonl", retention_days=30)
    old = log.record(op="old", resource="r", method="PUT", url="u")
    new = log.record(op="new", resource="r", method="PUT", url="u")
    lines = [json.loads(x) for x in log.path.read_text().splitlines()]
    lines[0]["ts"] -= 31 * 86400
    log.path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert log.prune() == 1
    assert log.find(old) is None
    assert log.find(new) is not None
    assert oct(log.path.stat().st_mode & 0o777) == "0o600"
    assert log.purge() is True
    assert not log.path.exists()
