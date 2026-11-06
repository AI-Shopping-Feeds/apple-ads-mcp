"""Shared fixtures for the test suite.

All tests run fully offline: Apple's token and API endpoints are mocked with
respx, and the private key is a throwaway generated per test session.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from apple_ads_mcp.audit import AuditLog
from apple_ads_mcp.client import AppleAdsClient
from apple_ads_mcp.config import Config

ACCOUNT = "123456789"


class FakeAuth:
    """Stand-in for AppleAdsAuth in tests that don't exercise OAuth."""

    account_label = "SEARCHADS.test… key test…"
    token_requests = 0

    def access_token(self) -> str:
        return "fake-token"

    def invalidate(self) -> None:
        pass

    def clear(self) -> None:
        pass

    def status(self) -> dict[str, Any]:
        return {"has_token": True}


@pytest.fixture(scope="session")
def ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def key_file(tmp_path: Path, ec_key: ec.EllipticCurvePrivateKey) -> Path:
    path = tmp_path / "private-key.pem"
    path.write_bytes(
        ec_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    return path


@pytest.fixture
def tmp_audit_log(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


@pytest.fixture
def config(tmp_audit_log: Path, key_file: Path) -> Config:
    return Config(
        client_id="SEARCHADS.11111111-2222-3333-4444-555555555555",
        team_id="SEARCHADS.11111111-2222-3333-4444-555555555555",
        key_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        private_key_path=key_file,
        ad_account_id=ACCOUNT,
        audit_log=tmp_audit_log,
        page_size=50,
        timeout=5.0,
        dry_run=False,
    )


@pytest.fixture
def audit(tmp_audit_log: Path) -> AuditLog:
    return AuditLog(tmp_audit_log)


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(config: Config, audit: AuditLog, sleeps: list[float]) -> AppleAdsClient:
    c = AppleAdsClient(config, FakeAuth(), audit, sleep=sleeps.append)  # type: ignore[arg-type]
    yield c
    c.close()
