"""CLI: transports, keygen and purge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from apple_ads_mcp import cli


class _FakeServer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, transport: str, **kwargs: Any) -> None:
        self.calls.append((transport, kwargs))


@pytest.fixture
def fake_run(tmp_path: Path, key_file: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPLE_ADS_CLIENT_ID", "SEARCHADS.abc")
    monkeypatch.setenv("APPLE_ADS_TEAM_ID", "SEARCHADS.abc")
    monkeypatch.setenv("APPLE_ADS_KEY_ID", "kid")
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    monkeypatch.setenv("APPLE_ADS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    for var in ("APPLE_ADS_TRANSPORT", "APPLE_ADS_HOST", "APPLE_ADS_PORT", "APPLE_ADS_TOOL_GROUPS"):
        monkeypatch.delenv(var, raising=False)
    server = _FakeServer()
    monkeypatch.setattr(cli, "build_server", lambda config: server)
    warnings: list[str] = []
    monkeypatch.setattr(cli.logger, "warning", lambda msg, *args: warnings.append(msg % args))

    def invoke(*args: str):
        env_file = str(tmp_path / "missing.env")
        result = CliRunner().invoke(cli.cli, ["--env", env_file, *args, "run"], obj={})
        assert result.exit_code == 0, result.output
        return server.calls, warnings

    return invoke


def test_stdio_is_the_default(fake_run) -> None:
    calls, warnings = fake_run()
    assert calls == [("stdio", {})]
    assert warnings == []


def test_streamable_http_gets_host_and_port(fake_run) -> None:
    calls, _ = fake_run("--transport", "streamable-http", "--port", "9123")
    assert calls == [("streamable-http", {"host": "127.0.0.1", "port": 9123})]


def test_non_loopback_host_warns(fake_run) -> None:
    calls, warnings = fake_run("--transport", "streamable-http", "--host", "0.0.0.0")
    assert calls[0][1]["host"] == "0.0.0.0"
    assert any("no authentication" in w for w in warnings)


def test_keygen_writes_a_private_p256_key_with_0600(tmp_path: Path) -> None:
    out = tmp_path / "secrets"
    result = CliRunner().invoke(cli.cli, ["keygen", "--dir", str(out)], obj={})
    assert result.exit_code == 0, result.output
    private = out / "private-key.pem"
    public = out / "public-key.pem"
    assert oct(private.stat().st_mode & 0o777) == "0o600"
    assert oct(out.stat().st_mode & 0o777) == "0o700"
    key = serialization.load_pem_private_key(private.read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    assert key.curve.name == "secp256r1"
    # Prints the public key, never the private one.
    assert "-----BEGIN PUBLIC KEY-----" in result.output
    assert public.read_text().strip() in result.output
    assert "PRIVATE KEY-----" not in result.output

    again = CliRunner().invoke(cli.cli, ["keygen", "--dir", str(out)], obj={})
    assert again.exit_code != 0
    assert "already exists" in again.output


def test_purge_deletes_the_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "audit.jsonl"
    log.write_text(json.dumps({"audit_id": "x", "ts": 0}) + "\n")
    monkeypatch.setenv("APPLE_ADS_AUDIT_LOG", str(log))
    env_file = str(tmp_path / "missing.env")
    result = CliRunner().invoke(cli.cli, ["--env", env_file, "purge", "--yes"], obj={})
    assert result.exit_code == 0, result.output
    assert not log.exists()
    assert "memory-only" in result.output


def test_unknown_transport_is_rejected() -> None:
    result = CliRunner().invoke(cli.cli, ["--transport", "websocket", "run"], obj={})
    assert result.exit_code != 0
    assert "streamable-http" in result.output
