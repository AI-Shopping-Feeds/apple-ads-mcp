"""Escape hatch: call any Apple Ads Platform API endpoint not wrapped by a tool."""

from __future__ import annotations

from typing import Any

from .. import guard
from ..client import AppleAdsClient, normalise_path

READ_POST_SUFFIXES = ("/query", "query")


def register(mcp, client: AppleAdsClient) -> None:
    @mcp.tool()
    def apple_ads_request(
        method: str,
        path: str,
        body: Any | None = None,
        query: dict[str, Any] | None = None,
        ad_account_header: str = "default",
        confirm: str = "",
        ad_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Call any Apple Ads Platform API v1 endpoint, e.g. method="POST",
        path="/v1/ads/query", body={"filters": [...]}.

        Only api.ads.apple.com is reachable: pass a path, not a URL.
        ad_account_header: default (send X-AP-Context when an ad account is set),
        required, or omit (for /me, /acls, /orgs, budget order writes).
        GET and POST .../query calls are reads. Any other write goes through
        dry-run and the audit log and needs confirm='APPLY' (or 'DELETE' for
        DELETE), because this tool can't check budget or bid increases.
        Prefer the dedicated tools when one exists.
        """
        m = method.strip().upper()
        if m not in {"GET", "POST", "PUT", "DELETE"}:
            raise ValueError("method must be GET, POST, PUT or DELETE")
        rel = normalise_path(path)
        modes = {"default": "optional", "required": "account", "omit": "none"}
        if ad_account_header not in modes:
            raise ValueError("ad_account_header must be default, required or omit")
        is_read = m == "GET" or (m == "POST" and rel.rstrip("/").endswith(READ_POST_SUFFIXES))
        note: dict[str, Any] = {}
        if not is_read:
            expected = guard.CONFIRM_DELETE if m == "DELETE" else guard.CONFIRM_APPLY
            note = guard.require(
                confirm,
                expected,
                [f"raw {m} /v1/{rel} changes the live account"],
                dry_run=client.config.dry_run,
            )
        out = client.request(
            m,
            rel,
            params=query,
            json_body=body,
            read_only=is_read,
            op=f"request {m} /v1/{rel}",
            ad_account_id=ad_account_id,
            context=modes[ad_account_header],  # type: ignore[arg-type]
        )
        if not isinstance(out, dict):
            out = {"result": out}
        return {**out, **note}
