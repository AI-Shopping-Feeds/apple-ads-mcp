"""Client secret JWT and access token lifecycle."""

from __future__ import annotations

from pathlib import Path

import httpx
import jwt
import pytest
import respx

from apple_ads_mcp.auth import (
    AUDIENCE,
    MAX_SECRET_LIFETIME,
    TOKEN_URL,
    AppleAdsAuth,
    AuthError,
    build_client_secret,
)

# Obviously fake identifiers: never real Apple Ads values.
CLIENT_ID = "SEARCHADS.00000000-0000-0000-0000-00000000c1d0"
TEAM_ID = "SEARCHADS.00000000-0000-0000-0000-0000000007ea"
KEY_ID = "00000000-0000-0000-0000-0000000000ee"
# A fake JWT-shaped string that must be redacted.
FAKE_JWT = "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.sig"  # pragma: allowlist secret


def test_client_secret_claims_and_signature(ec_key) -> None:
    secret = build_client_secret(
        client_id=CLIENT_ID, team_id=TEAM_ID, key_id=KEY_ID, private_key=ec_key, now=1_700_000_000
    )
    header = jwt.get_unverified_header(secret)
    assert header == {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
    claims = jwt.decode(
        secret,
        ec_key.public_key(),
        algorithms=["ES256"],
        audience=AUDIENCE,
        options={"verify_exp": False},
    )
    assert claims["sub"] == CLIENT_ID
    assert claims["iss"] == TEAM_ID
    assert claims["aud"] == "https://appleid.apple.com"
    assert claims["iat"] == 1_700_000_000
    assert 0 < claims["exp"] - claims["iat"] <= 180 * 86400


def test_client_secret_rejects_wrong_key(ec_key) -> None:
    from cryptography.hazmat.primitives.asymmetric import ec

    secret = build_client_secret(
        client_id=CLIENT_ID, team_id=TEAM_ID, key_id=KEY_ID, private_key=ec_key
    )
    other = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(secret, other.public_key(), algorithms=["ES256"], audience=AUDIENCE)


def test_client_secret_lifetime_capped_at_180_days(ec_key) -> None:
    with pytest.raises(ValueError):
        build_client_secret(
            client_id=CLIENT_ID,
            team_id=TEAM_ID,
            key_id=KEY_ID,
            private_key=ec_key,
            lifetime=MAX_SECRET_LIFETIME + 1,
        )


class Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _auth(key_file: Path, clock: Clock) -> AppleAdsAuth:
    return AppleAdsAuth(
        client_id=CLIENT_ID,
        team_id=TEAM_ID,
        key_id=KEY_ID,
        private_key_path=key_file,
        clock=clock,
    )


@respx.mock
def test_token_is_cached_then_refreshed_before_expiry(key_file: Path, ec_key) -> None:
    seen: list[dict[str, str]] = []

    def token(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        seen.append(form)
        return httpx.Response(
            200,
            json={
                "access_token": f"tok-{len(seen)}",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "searchadsorg",
            },
        )

    route = respx.post(TOKEN_URL).mock(side_effect=token)
    clock = Clock()
    auth = _auth(key_file, clock)

    assert auth.access_token() == "tok-1"
    clock.t += 1000
    assert auth.access_token() == "tok-1"  # cached
    assert route.call_count == 1

    clock.t += 2500  # 3500s after issue: inside the refresh margin
    assert auth.access_token() == "tok-2"
    assert route.call_count == 2

    form = seen[0]
    assert form["grant_type"] == "client_credentials"
    assert form["scope"] == "searchadsorg"
    assert form["client_id"] == CLIENT_ID
    claims = jwt.decode(
        form["client_secret"],
        ec_key.public_key(),
        algorithms=["ES256"],
        audience=AUDIENCE,
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["sub"] == CLIENT_ID
    request = route.calls[0].request
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"


@respx.mock
def test_client_secret_is_re_signed_when_it_nears_expiry(key_file: Path) -> None:
    secrets: list[str] = []

    def token(request: httpx.Request) -> httpx.Response:
        secrets.append(dict(httpx.QueryParams(request.content.decode()))["client_secret"])
        return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})

    respx.post(TOKEN_URL).mock(side_effect=token)
    clock = Clock()
    auth = _auth(key_file, clock)
    auth.access_token()
    clock.t += 4000
    auth.access_token()  # new token, same secret (still valid for ~23h)
    clock.t += 86400
    auth.access_token()  # secret expired: re-signed
    assert secrets[0] == secrets[1]
    assert secrets[2] != secrets[1]


@respx.mock
def test_invalidate_forces_a_new_token(key_file: Path) -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )
    auth = _auth(key_file, Clock())
    auth.access_token()
    auth.invalidate()
    auth.access_token()
    assert route.call_count == 2


@respx.mock
def test_token_error_is_redacted_and_helpful(key_file: Path) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": "invalid_client", "echo": FAKE_JWT},
        )
    )
    auth = _auth(key_file, Clock())
    with pytest.raises(AuthError) as exc_info:
        auth.access_token()
    message = str(exc_info.value)
    assert "invalid_client" in message
    assert "eyJ" not in message
    assert "APPLE_ADS_KEY_ID" in message


def test_non_ec_key_is_rejected(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "rsa.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    auth = _auth(path, Clock())
    with pytest.raises(AuthError, match="P-256"):
        auth.access_token()
