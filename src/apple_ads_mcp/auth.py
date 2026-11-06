"""OAuth 2 client credentials for the Apple Ads Platform API.

Flow (developer.apple.com/documentation/apple-ads-platform-api,
"Implementing OAuth for the Apple Ads Platform API"):

1. Build a client secret: a JWT signed ES256 with the API user's EC P-256
   private key. Header `kid` = keyId. Claims `sub` = clientId, `iss` = teamId,
   `aud` = https://appleid.apple.com, `iat`, `exp` (at most 180 days after iat).
2. POST it to https://appleid.apple.com/auth/oauth2/token with
   grant_type=client_credentials, client_id, client_secret, scope=searchadsorg.
3. Use the returned access token (valid `expires_in` seconds, usually 3600) as
   `Authorization: Bearer ...`.

Both the client secret and the access token live in memory only. Neither is
ever logged, written to disk or returned by a tool.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from . import __version__
from ._logging import get_logger
from .redact import redact_text

TOKEN_URL = "https://appleid.apple.com/auth/oauth2/token"
AUDIENCE = "https://appleid.apple.com"
SCOPE = "searchadsorg"
MAX_SECRET_LIFETIME = 180 * 86400
# We sign short-lived client secrets; Apple allows up to 180 days.
DEFAULT_SECRET_LIFETIME = 86400
# Refresh the access token this many seconds before it expires.
TOKEN_REFRESH_MARGIN = 120
# Re-sign the client secret when it has less than this left.
SECRET_REFRESH_MARGIN = 600

logger = get_logger("auth")


class AuthError(RuntimeError):
    """Token exchange failed. The message never contains secrets."""


def load_private_key(path: Path) -> ec.EllipticCurvePrivateKey:
    data = path.read_bytes()
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except (ValueError, TypeError) as e:
        raise AuthError(
            f"Could not read the private key at {path}: not an unencrypted PEM key"
        ) from e
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise AuthError(f"The private key at {path} must be an EC P-256 (prime256v1) key")
    _warn_if_world_readable(path)
    return key


def _warn_if_world_readable(path: Path) -> None:
    if os.name != "posix":
        return
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        logger.warning(
            "private key %s is readable by other users (mode %o); run: chmod 600 %s",
            path,
            stat.S_IMODE(mode),
            path,
        )


def build_client_secret(
    *,
    client_id: str,
    team_id: str,
    key_id: str,
    private_key: ec.EllipticCurvePrivateKey,
    lifetime: int = DEFAULT_SECRET_LIFETIME,
    now: float | None = None,
) -> str:
    """Sign the client secret JWT Apple's token endpoint expects."""
    if not 0 < lifetime <= MAX_SECRET_LIFETIME:
        raise ValueError("client secret lifetime must be between 1 second and 180 days")
    iat = int(now if now is not None else time.time())
    payload = {
        "sub": client_id,
        "iss": team_id,
        "aud": AUDIENCE,
        "iat": iat,
        "exp": iat + lifetime,
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": key_id})


class AppleAdsAuth:
    """Caches an access token and refreshes it (and the client secret) before expiry."""

    def __init__(
        self,
        *,
        client_id: str,
        team_id: str,
        key_id: str,
        private_key_path: Path,
        timeout: float = 30.0,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
        secret_lifetime: int = DEFAULT_SECRET_LIFETIME,
    ):
        self.client_id = client_id
        self.team_id = team_id
        self.key_id = key_id
        self.private_key_path = private_key_path
        self._clock = clock
        self._secret_lifetime = secret_lifetime
        self._http = http or httpx.Client(
            timeout=timeout, headers={"User-Agent": f"apple-ads-mcp/{__version__}"}
        )
        self._lock = threading.Lock()
        self._private_key: ec.EllipticCurvePrivateKey | None = None
        self._secret: str | None = None
        self._secret_exp = 0.0
        self._token: str | None = None
        self._token_exp = 0.0
        self.token_requests = 0

    @property
    def account_label(self) -> str:
        return f"{self.client_id[:18]}… key {self.key_id[:8]}…"

    def _client_secret(self) -> str:
        now = self._clock()
        if self._secret is None or now >= self._secret_exp - SECRET_REFRESH_MARGIN:
            if self._private_key is None:
                self._private_key = load_private_key(self.private_key_path)
            self._secret = build_client_secret(
                client_id=self.client_id,
                team_id=self.team_id,
                key_id=self.key_id,
                private_key=self._private_key,
                lifetime=self._secret_lifetime,
                now=now,
            )
            self._secret_exp = now + self._secret_lifetime
        return self._secret

    def access_token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token and now < self._token_exp - TOKEN_REFRESH_MARGIN:
                return self._token
            self._token, expires_in = self._fetch_token()
            self._token_exp = self._clock() + expires_in
            logger.info("obtained Apple Ads access token (expires in %ss)", expires_in)
            return self._token

    def invalidate(self) -> None:
        """Forget the cached access token (e.g. after a 401)."""
        with self._lock:
            self._token = None
            self._token_exp = 0.0

    def clear(self) -> None:
        """Forget every cached credential (token, client secret, loaded key)."""
        with self._lock:
            self._token = None
            self._token_exp = 0.0
            self._secret = None
            self._secret_exp = 0.0
            self._private_key = None

    def status(self) -> dict[str, Any]:
        now = self._clock()
        return {
            "has_token": bool(self._token) and now < self._token_exp,
            "token_expires_in": max(0, int(self._token_exp - now)) if self._token else None,
        }

    def _fetch_token(self) -> tuple[str, int]:
        self.token_requests += 1
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self._client_secret(),
            "scope": SCOPE,
        }
        try:
            resp = self._http.post(
                TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as e:
            raise AuthError(
                f"Could not reach the Apple token endpoint: {redact_text(str(e))}"
            ) from e
        if resp.status_code != 200:
            detail = redact_text(resp.text[:300])
            hint = ""
            if resp.status_code in (400, 401):
                hint = (
                    " Check APPLE_ADS_CLIENT_ID, APPLE_ADS_TEAM_ID and APPLE_ADS_KEY_ID match "
                    "Apple Ads > Account Settings > API, and that the uploaded public key "
                    "belongs to this private key."
                )
            raise AuthError(
                f"Apple token request failed (HTTP {resp.status_code}): {detail}.{hint}"
            )
        try:
            body = resp.json()
            token = body["access_token"]
            expires_in = int(body.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError) as e:
            raise AuthError("Apple token response had no access_token") from e
        return token, expires_in
