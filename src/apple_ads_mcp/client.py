"""Thin HTTP wrapper over the Apple Ads Platform API v1.

Handles the bearer token, the `X-AP-Context: adAccountId=...` header, retries,
Apple's documented rate-limit headers, offset pagination for `/query`
endpoints, dry-run and the audit log.

Only two hosts are ever contacted: appleid.apple.com (tokens, in auth.py) and
api.ads.apple.com (this module). There is no telemetry.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx

from . import __version__
from ._logging import get_logger
from .audit import AuditLog
from .auth import AppleAdsAuth
from .config import Config
from .redact import redact, redact_text

API_HOST = "api.ads.apple.com"
BASE_URL = f"https://{API_HOST}/v1"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
MAX_BACKOFF = 16.0
# Pause proactively when fewer than this many requests remain in the window.
RATE_LIMIT_LOW_WATER = 2
MAX_PROACTIVE_WAIT = 60.0
QUERY_MAX_PAGE_SIZE = 1000
# Hard ceilings so one call can't exhaust memory: bytes in a single response,
# and rows collected across the pages of one query or report.
MAX_RESPONSE_BYTES = 200 * 1024 * 1024
MAX_ROWS = 100_000
# Path characters allowed after normalising: RFC 3986 unreserved plus '/'.
_SAFE_PATH_RE = re.compile(r"[A-Za-z0-9._~/-]*")
_SAFE_SEGMENT_RE = re.compile(r"[A-Za-z0-9._~-]+")

ContextMode = Literal["account", "optional", "none"]

logger = get_logger("client")


class AppleAdsAPIError(Exception):
    def __init__(self, status: int, body: Any, message: str = ""):
        self.status = status
        self.body = redact(body)
        super().__init__(message or f"Apple Ads API error {status}: {_summarise_error(self.body)}")


class ResponseTooLargeError(AppleAdsAPIError):
    """A response was bigger than MAX_RESPONSE_BYTES; nothing more is read."""


def _summarise_error(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        parts = [str(err.get("code") or ""), str(err.get("message") or "")]
        for d in err.get("details") or []:
            if isinstance(d, dict):
                info = d.get("info")
                field = (
                    f" ({info.get('field')})"
                    if isinstance(info, dict) and info.get("field")
                    else ""
                )
                parts.append(f"{d.get('code')}: {d.get('message')}{field}")
        return redact_text(" | ".join(p for p in parts if p))
    return redact_text(str(body)[:500])


def normalise_path(path: str) -> str:
    """Accept 'campaigns/1', '/campaigns/1', '/v1/campaigns/1' or 'v1/campaigns/1'.

    Rejects absolute URLs, '.' and '..' segments, and anything outside letters,
    digits, '-', '_', '.', '~' and '/', so a path can't reach another host,
    smuggle a query string or escape /v1. Query parameters go in `params`.
    """
    p = path.strip()
    if "://" in p or p.startswith("//") or p.startswith("\\\\"):
        raise ValueError("Pass a path such as '/v1/campaigns/query', not a full URL.")
    p = p.lstrip("/")
    if p.startswith("v1/"):
        p = p[3:]
    elif p == "v1":
        p = ""
    segments = p.split("/")
    if ".." in segments or "." in segments:
        raise ValueError("Path may not contain '.' or '..' segments.")
    if "" in segments[:-1]:
        raise ValueError("Path may not contain empty segments ('//').")
    if not _SAFE_PATH_RE.fullmatch(p):
        raise ValueError(
            "Path may only contain letters, digits, '-', '_', '.', '~' and '/'. "
            "Pass query parameters separately."
        )
    return p


def path_segment(value: str | int, name: str = "id") -> str:
    """Check an ID is a single safe path segment before it's put into a path."""
    text = str(value).strip()
    if text in (".", "..") or not _SAFE_SEGMENT_RE.fullmatch(text):
        raise ValueError(
            f"{name} must be a single ID made of letters, digits, '-', '_', '.' or '~', "
            f"got {text[:40]!r}"
        )
    return text


def check_row_limit(requested: int | None, name: str = "max_items") -> int:
    """Rows to collect at most: `requested`, or MAX_ROWS when None. Refuses more than MAX_ROWS."""
    if requested is None:
        return MAX_ROWS
    if requested > MAX_ROWS:
        raise ValueError(
            f"{name} can be at most {MAX_ROWS}; narrow the request with filters or a "
            "shorter date range."
        )
    return requested


class AppleAdsClient:
    def __init__(
        self,
        config: Config,
        auth: AppleAdsAuth,
        audit: AuditLog,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.config = config
        self.auth = auth
        self.audit = audit
        self._sleep = sleep
        self._clock = clock
        self._http = httpx.Client(
            timeout=config.timeout,
            headers={"User-Agent": f"apple-ads-mcp/{__version__}"},
        )
        self.rate_limit: dict[str, Any] = {}
        self._rl_reset_at: float | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AppleAdsClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ context

    def resolve_account(self, ad_account_id: str | int | None) -> str | None:
        value = str(ad_account_id).strip() if ad_account_id not in (None, "") else None
        value = value or self.config.ad_account_id
        if value is not None and not str(value).isdigit():
            raise ValueError(f"ad_account_id must be numeric, got '{value}'")
        return value

    def _context_header(
        self, mode: ContextMode, ad_account_id: str | int | None
    ) -> tuple[dict[str, str], str | None]:
        if mode == "none":
            return {}, None
        account = self.resolve_account(ad_account_id)
        if account is None:
            if mode == "account":
                raise ValueError(
                    "No ad account selected. Pass ad_account_id, or set APPLE_ADS_AD_ACCOUNT_ID "
                    "(apple_ads_list_acls lists the ad accounts you can use)."
                )
            return {}, None
        return {"X-AP-Context": f"adAccountId={account}"}, account

    # ------------------------------------------------------------------ requests

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        op: str | None = None,
        before: Any | None = None,
        read_only: bool = False,
        ad_account_id: str | int | None = None,
        context: ContextMode = "account",
    ) -> Any:
        """Perform one API request and return the parsed JSON ({} for an empty body).

        read_only: set True for POST endpoints that don't change anything
        (`/query`, reports, insights). They then bypass dry-run and are never
        written to the audit log.
        """
        method = method.upper()
        rel = normalise_path(path)
        url = f"{BASE_URL}/{rel}" if rel else BASE_URL
        if httpx.URL(url).host != API_HOST:  # defence in depth; normalise_path already checks
            raise ValueError(f"Refusing to call a host other than {API_HOST}.")
        is_write = method in WRITE_METHODS and not read_only
        headers, account = self._context_header(context, ad_account_id)
        op_name = op or f"{method} /v1/{rel}"

        if is_write and self.config.dry_run:
            audit_id = self.audit.record(
                op=op_name,
                resource=f"/v1/{rel}",
                method=method,
                url=url,
                ad_account_id=account,
                request_body=json_body,
                dry_run=True,
                before=before,
            )
            logger.info("dry-run %s /v1/%s (audit=%s)", method, rel, audit_id)
            return {
                "_dry_run": True,
                "method": method,
                "url": url,
                "ad_account_id": account,
                "body": json_body,
                "audit_id": audit_id,
                "note": "Dry-run: nothing was sent to Apple Ads.",
            }

        resp, content = self._send(
            method, url, rel, params=params, json_body=json_body, headers=headers
        )
        payload: Any = _parse_json(content) if content else {}

        if not (200 <= resp.status_code < 300):
            if is_write:
                self.audit.record(
                    op=op_name,
                    resource=f"/v1/{rel}",
                    method=method,
                    url=url,
                    ad_account_id=account,
                    request_body=json_body,
                    response_status=resp.status_code,
                    response_body=payload,
                    before=before,
                    error=f"HTTP {resp.status_code}",
                )
            logger.error(
                "api error %d %s /v1/%s: %s",
                resp.status_code,
                method,
                rel,
                _summarise_error(payload),
            )
            raise AppleAdsAPIError(resp.status_code, payload)

        if is_write:
            audit_id = self.audit.record(
                op=op_name,
                resource=f"/v1/{rel}",
                method=method,
                url=url,
                ad_account_id=account,
                request_body=json_body,
                response_status=resp.status_code,
                response_body=payload,
                before=before,
            )
            logger.info("write %s /v1/%s -> %d (audit=%s)", method, rel, resp.status_code, audit_id)
            if isinstance(payload, dict):
                payload = {**payload, "audit_id": audit_id}
        else:
            logger.debug("read  %s /v1/%s -> %d", method, rel, resp.status_code)
        return payload

    def _send(
        self,
        method: str,
        url: str,
        rel: str,
        *,
        params: dict[str, Any] | None,
        json_body: Any | None,
        headers: dict[str, str],
    ) -> tuple[httpx.Response, bytes]:
        backoff = 2.0
        refreshed = False
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            self._pace()
            try:
                request = self._http.build_request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={**headers, "Authorization": f"Bearer {self.auth.access_token()}"},
                )
                resp = self._http.send(request, stream=True)
                try:
                    content = _read_capped(resp, MAX_RESPONSE_BYTES)
                finally:
                    resp.close()
            except httpx.RequestError as e:
                last_exc = e
                logger.warning(
                    "transport error attempt=%d %s /v1/%s: %s",
                    attempt + 1,
                    method,
                    rel,
                    redact_text(str(e)),
                )
                self._sleep(backoff + random.uniform(0, 0.5))
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue

            self._note_rate_limit(resp)

            if resp.status_code == 401 and not refreshed:
                # Token revoked or expired early: get a fresh one and retry once.
                refreshed = True
                self.auth.invalidate()
                continue

            if resp.status_code in RETRYABLE_STATUSES and attempt < MAX_ATTEMPTS - 1:
                wait: float = backoff
                if resp.status_code == 429:
                    # Apple: prefer Retry-After, then RateLimit-Reset, then backoff.
                    told = _header_seconds(resp, "Retry-After")
                    if told is None:
                        told = _header_seconds(resp, "RateLimit-Reset")
                    wait = told if told is not None else backoff
                logger.warning(
                    "retryable status=%d attempt=%d %s /v1/%s; waiting %.1fs",
                    resp.status_code,
                    attempt + 1,
                    method,
                    rel,
                    wait,
                )
                self._sleep(min(wait, 120.0))
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            return resp, content

        if last_exc is not None:
            raise AppleAdsAPIError(0, redact_text(str(last_exc)), "Apple Ads API unreachable")
        raise AppleAdsAPIError(0, "exhausted retries", "Apple Ads API: exhausted retries")

    def _note_rate_limit(self, resp: httpx.Response) -> None:
        limit = _header_int(resp, "RateLimit-Limit")
        remaining = _header_int(resp, "RateLimit-Remaining")
        reset = _header_int(resp, "RateLimit-Reset")
        if limit is None and remaining is None and reset is None:
            return
        self.rate_limit = {"limit": limit, "remaining": remaining, "reset_seconds": reset}
        if remaining is not None and reset is not None and remaining < RATE_LIMIT_LOW_WATER:
            self._rl_reset_at = self._clock() + reset
        else:
            self._rl_reset_at = None

    def _pace(self) -> None:
        """Wait for the rate-limit window to reset when the last response said we're nearly out."""
        if self._rl_reset_at is None:
            return
        wait = self._rl_reset_at - self._clock()
        self._rl_reset_at = None
        if wait > 0:
            wait = min(wait, MAX_PROACTIVE_WAIT)
            logger.info("rate limit nearly used up; pausing %.1fs", wait)
            self._sleep(wait)

    # ------------------------------------------------------------------ helpers

    def query(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        max_items: int | None = None,
        page_size: int | None = None,
        ad_account_id: str | int | None = None,
        context: ContextMode = "account",
        max_page_size: int = QUERY_MAX_PAGE_SIZE,
        fetch_total: bool = True,
    ) -> dict[str, Any]:
        """POST a `/query`-style request and follow offset pagination.

        Returns {"result": [...], "pagination": {...}, "truncated": bool}.
        Collects at most `max_items` rows (MAX_ROWS when None).
        """
        max_items = check_row_limit(max_items)
        body = dict(body or {})
        size = max(1, min(page_size or self.config.page_size, max_page_size, max_items))
        pagination = dict(body.get("pagination") or {})
        offset = int(pagination.get("offset", 0))
        rows: list[Any] = []
        total: int | None = None
        truncated = False
        while True:
            body["pagination"] = {**pagination, "offset": offset, "pageSize": size}
            if fetch_total and "fetchTotalCount" not in pagination:
                body["pagination"]["fetchTotalCount"] = True
            payload = self.request(
                "POST",
                path,
                json_body=body,
                read_only=True,
                ad_account_id=ad_account_id,
                context=context,
            )
            page = _rows(payload)
            rows.extend(page)
            pag = payload.get("pagination") if isinstance(payload, dict) else None
            if isinstance(pag, dict) and pag.get("totalCount") is not None:
                total = int(pag["totalCount"])
            offset += len(page)
            if len(rows) >= max_items:
                truncated = total is None or total > max_items
                rows = rows[:max_items]
                break
            if not page or len(page) < size or (total is not None and offset >= total):
                break
        return {
            "result": rows,
            "pagination": {"returned": len(rows), "totalCount": total},
            "truncated": truncated,
        }

    def get_result(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        ad_account_id: str | int | None = None,
        context: ContextMode = "account",
    ) -> Any:
        payload = self.request(
            "GET", path, params=params, ad_account_id=ad_account_id, context=context
        )
        return payload.get("result", payload) if isinstance(payload, dict) else payload

    def snapshot(
        self, path: str, *, ad_account_id: str | int | None = None, context: ContextMode = "account"
    ) -> Any | None:
        """Best-effort GET for an audit `before` snapshot. Never raises."""
        try:
            return self.get_result(path, ad_account_id=ad_account_id, context=context)
        except Exception:
            return None


def _parse_json(content: bytes) -> Any:
    try:
        return json.loads(content)
    except ValueError:
        return {"_raw": content[:2000].decode("utf-8", errors="replace")}


def _read_capped(resp: httpx.Response, limit: int) -> bytes:
    """Read a streamed response body, refusing anything over `limit` bytes."""
    too_large = ResponseTooLargeError(
        resp.status_code,
        "response too large",
        f"Apple Ads API response is larger than {limit // (1024 * 1024)} MB, so it was "
        "not read. Ask for less: fewer rows, a shorter date range or more filters.",
    )
    declared = resp.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    for chunk in resp.iter_bytes():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def _rows(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("rows", "data", "items"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


def _header_int(resp: httpx.Response, name: str) -> int | None:
    raw = resp.headers.get(name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _header_seconds(resp: httpx.Response, name: str) -> float | None:
    raw = resp.headers.get(name)
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
