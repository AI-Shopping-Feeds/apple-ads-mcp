"""Build the MCP server. Stays import-light so tests can patch pieces individually."""

from __future__ import annotations

import functools
import inspect
import time
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__, tools
from ._logging import configure_default, get_logger
from .audit import AuditLog
from .auth import AppleAdsAuth, AuthError
from .client import AppleAdsAPIError, AppleAdsClient
from .config import Config, load_config
from .redact import redact_text
from .tool_catalog import ALWAYS_REGISTERED, TOOL_SPECS

logger = get_logger("server")

INSTRUCTIONS = """\
Apple Ads Platform API v1: App Store and Apple Maps campaigns, ad groups, keywords, ads, reports, insights.
Start with apple_ads_describe_server and apple_ads_health_check; apple_ads_list_acls gives ad_account_id values.
Writes change live ads and spend money. Rehearse first with apple_ads_set_dry_run(true): logged, not sent.
Show the user exactly what will change (dry-run preview) and get their go-ahead before running it for real.
Deletes need confirm='DELETE'; bulk changes and budget/bid rises over APPLE_ADS_MAX_INCREASE_PCT need confirm='APPLY'.
Money is {"amount": "1.50", "currency": "GBP"} in the ad account's currency. Report data is confidential: share it only with the user.
Every write goes to an audit log (apple_ads_audit_tail). Limit tools with APPLE_ADS_TOOL_GROUPS or APPLE_ADS_READ_ONLY=true."""

# Errors whose message helps the agent fix the call (bad arguments, a refusal
# such as a missing confirm, API errors, permissions or config problems).
_EXPECTED_ERRORS = (
    ValueError,
    RuntimeError,
    PermissionError,
    FileNotFoundError,
    AppleAdsAPIError,
    AuthError,
    httpx.HTTPError,
)


def _tool_error(exc: Exception) -> ToolError:
    return ToolError(redact_text(str(exc)))


def _as_tool_error(fn):
    """Re-raises expected errors as ToolError so MCP SDK 2 shows their message.

    SDK 2 hides the text of any other exception from the client. Messages are
    redacted so a token or key can never reach the client.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except _EXPECTED_ERRORS as exc:
                raise _tool_error(exc) from exc

        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _EXPECTED_ERRORS as exc:
            raise _tool_error(exc) from exc

    return wrapper


class AppleAdsMCPServer(MCPServer):
    """MCPServer whose tools report expected errors to the client.

    Each tool gets its title and annotations from `tool_catalog.TOOL_SPECS`
    unless the decorator passes them. With `read_only=True`, tools that are not
    annotated read-only are skipped (the meta tools are always registered).
    """

    def __init__(self, *args: Any, read_only: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.read_only = read_only

    def tool(  # type: ignore[override]
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
        **kwargs: Any,
    ):
        def decorator(fn):
            tool_name = name or fn.__name__
            spec = TOOL_SPECS.get(tool_name)
            tool_title = title or (spec.title if spec else None)
            tool_annotations = annotations or (spec.annotations if spec else None)
            is_read_only = bool(tool_annotations and tool_annotations.read_only_hint)
            if self.read_only and not is_read_only and tool_name not in ALWAYS_REGISTERED:
                return fn
            register = super(AppleAdsMCPServer, self).tool(
                name=name,
                title=tool_title,
                description=description,
                annotations=tool_annotations,
                **kwargs,
            )
            register(_as_tool_error(fn))
            return fn

        return decorator


def make_auth(config: Config) -> AppleAdsAuth:
    return AppleAdsAuth(
        client_id=config.client_id,
        team_id=config.team_id,
        key_id=config.key_id,
        private_key_path=config.private_key_path,
        timeout=config.timeout,
    )


def build_server(config: Config | None = None, env_file: Path | None = None) -> MCPServer:
    """Construct an MCPServer instance with all apple_ads_* tools registered."""
    configure_default()
    if config is None:
        config = load_config(env_file=env_file)
    groups = tools.resolve_tool_groups(config.tool_groups)  # fail fast on unknown groups

    auth = make_auth(config)
    audit = AuditLog(config.audit_log, retention_days=config.audit_retention_days)
    pruned = audit.prune()
    if pruned:
        logger.info(
            "pruned %d audit entries older than %d days", pruned, config.audit_retention_days
        )
    client = AppleAdsClient(config, auth, audit)

    logger.info(
        "starting apple-ads-mcp ad_account=%s dry_run=%s read_only=%s",
        config.ad_account_id or "-",
        config.dry_run,
        config.read_only,
    )

    mcp = AppleAdsMCPServer(
        "apple-ads-mcp",
        title="Apple Ads",
        version=__version__,
        instructions=INSTRUCTIONS,
        read_only=config.read_only,
    )

    @mcp.tool()
    def apple_ads_describe_server() -> dict[str, Any]:
        """Show how this server is configured: default ad account, dry-run,
        read-only, tool groups, spend guard and audit settings. No secrets."""
        return {
            "version": __version__,
            "api": "Apple Ads Platform API v1 (https://api.ads.apple.com/v1)",
            "client_id": auth.account_label,
            "default_ad_account_id": config.ad_account_id,
            "dry_run": config.dry_run,
            "read_only": config.read_only,
            "tool_groups": config.tool_groups or "all",
            "max_increase_pct": config.max_increase_pct,
            "audit_log": str(config.audit_log),
            "audit_retention_days": config.audit_retention_days,
            "page_size": config.page_size,
            "timeout": config.timeout,
            "transport": config.transport,
            "rate_limit": client.rate_limit or None,
        }

    @mcp.tool()
    def apple_ads_health_check() -> dict[str, Any]:
        """Check the credentials work: gets an access token, then calls /v1/me and
        /v1/acls (and the default ad account, if set). Lists the ad accounts and
        roles this API user has. Good first call after setup."""
        checks: list[dict[str, Any]] = []
        out: dict[str, Any] = {}

        def probe(name: str, fn) -> Any:
            t0 = time.time()
            try:
                value = fn()
                checks.append({"check": name, "ok": True, "ms": int((time.time() - t0) * 1000)})
                return value
            except Exception as e:
                checks.append(
                    {
                        "check": name,
                        "ok": False,
                        "ms": int((time.time() - t0) * 1000),
                        "error": redact_text(str(e))[:300],
                    }
                )
                return None

        if probe("access_token", lambda: bool(auth.access_token())):
            out["me"] = probe("me", lambda: client.get_result("me", context="none"))
            acls = probe("acls", lambda: client.get_result("acls", context="none"))
            if isinstance(acls, dict):
                out["ad_accounts"] = [
                    {
                        "ad_account_id": (a.get("adAccount") or {}).get("id"),
                        "name": (a.get("adAccount") or {}).get("name"),
                        "org_id": (a.get("adAccount") or {}).get("orgId"),
                        "roles": a.get("roles"),
                    }
                    for a in acls.get("acls") or []
                    if isinstance(a, dict)
                ]
            if config.ad_account_id:
                account = probe(
                    "default_ad_account",
                    lambda: client.get_result(f"ad-accounts/{config.ad_account_id}"),
                )
                if isinstance(account, dict):
                    out["default_ad_account"] = {
                        k: account.get(k)
                        for k in (
                            "id",
                            "name",
                            "currency",
                            "timezone",
                            "productFeatures",
                            "systemStatus",
                            "systemStatusReasons",
                        )
                    }
        ok = sum(1 for c in checks if c["ok"])
        return {
            "ok": ok == len(checks),
            "passed": ok,
            "total": len(checks),
            "checks": checks,
            "rate_limit": client.rate_limit or None,
            **out,
        }

    @mcp.tool()
    def apple_ads_audit_tail(limit: int = 20) -> dict[str, Any]:
        """Show the most recent audit log entries (writes and dry-runs only)."""
        entries = audit.tail(limit)
        return {"count": len(entries), "entries": entries}

    @mcp.tool()
    def apple_ads_audit_lookup(audit_id: str) -> dict[str, Any]:
        """Look up an audit log entry by ID, including the `before` snapshot of what changed."""
        entry = audit.find(audit_id)
        if not entry:
            return {"found": False, "audit_id": audit_id}
        return {"found": True, "entry": entry}

    @mcp.tool()
    def apple_ads_set_dry_run(enabled: bool) -> dict[str, Any]:
        """Turn dry-run on or off for this session. When on, writes are recorded in
        the audit log and returned as a preview but NOT sent to Apple Ads, and
        confirm strings aren't needed (the preview says which one the live call needs)."""
        client.config.dry_run = enabled
        logger.info("dry_run=%s (set via tool)", enabled)
        return {"dry_run": enabled}

    for group in groups:
        getattr(tools, group).register(mcp, client)

    logger.info(
        "registered %d tools (groups=%s read_only=%s)",
        len(mcp._tool_manager.list_tools()),
        ",".join(config.tool_groups) or "all",
        config.read_only,
    )
    return mcp
