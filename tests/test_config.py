"""Configuration: per-user default locations and .env lookup."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from apple_ads_mcp.audit import AuditLog
from apple_ads_mcp.config import load_audit_settings, load_config

from .conftest import posix_only

VARS = (
    "APPLE_ADS_CLIENT_ID",
    "APPLE_ADS_TEAM_ID",
    "APPLE_ADS_KEY_ID",
    "APPLE_ADS_PRIVATE_KEY_PATH",
    "APPLE_ADS_AD_ACCOUNT_ID",
    "APPLE_ADS_AUDIT_LOG",
    "APPLE_ADS_TOOL_GROUPS",
    "APPLE_ADS_READ_ONLY",
    "APPLE_ADS_DRY_RUN",
    "APPLE_ADS_ALLOW_REMOTE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in VARS:
        monkeypatch.delenv(var, raising=False)


def _ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPLE_ADS_CLIENT_ID", "SEARCHADS.abc")
    monkeypatch.setenv("APPLE_ADS_TEAM_ID", "SEARCHADS.abc")
    monkeypatch.setenv("APPLE_ADS_KEY_ID", "kid")


def _env_lines(**values: str) -> str:
    return "".join(f"{k}={v}\n" for k, v in values.items())


def test_private_key_defaults_to_the_keygen_location(
    monkeypatch: pytest.MonkeyPatch, isolated_home: Path, key_file: Path
) -> None:
    _ids(monkeypatch)
    default = isolated_home / ".apple-ads-mcp" / "secrets" / "private-key.pem"
    default.parent.mkdir(parents=True)
    shutil.copy(key_file, default)
    config = load_config()
    assert config.private_key_path == default


def test_missing_private_key_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    _ids(monkeypatch)
    with pytest.raises(RuntimeError) as exc_info:
        load_config()
    message = str(exc_info.value)
    assert "APPLE_ADS_PRIVATE_KEY_PATH" in message
    assert "keygen" in message


def test_explicit_private_key_path_wins(
    monkeypatch: pytest.MonkeyPatch, isolated_home: Path, key_file: Path
) -> None:
    _ids(monkeypatch)
    default = isolated_home / ".apple-ads-mcp" / "secrets" / "private-key.pem"
    default.parent.mkdir(parents=True)
    default.write_text("not used", encoding="ascii")
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    assert load_config().private_key_path == key_file.resolve()


def test_audit_log_defaults_to_the_per_user_folder(isolated_home: Path) -> None:
    path, retention = load_audit_settings()
    assert path == isolated_home / ".apple-ads-mcp" / "logs" / "audit.jsonl"
    assert retention == 30


def test_env_file_in_the_per_user_folder_is_read(
    monkeypatch: pytest.MonkeyPatch, isolated_home: Path, key_file: Path
) -> None:
    app = isolated_home / ".apple-ads-mcp"
    app.mkdir()
    (app / ".env").write_text(
        _env_lines(
            APPLE_ADS_CLIENT_ID="SEARCHADS.home",
            APPLE_ADS_TEAM_ID="SEARCHADS.home",
            APPLE_ADS_KEY_ID="home-key",
            APPLE_ADS_PRIVATE_KEY_PATH=str(key_file),
            APPLE_ADS_AD_ACCOUNT_ID="42",
        ),
        encoding="utf-8",
    )
    config = load_config()
    assert config.client_id == "SEARCHADS.home"
    assert config.ad_account_id == "42"


def test_working_directory_env_wins_over_the_per_user_one(
    monkeypatch: pytest.MonkeyPatch, isolated_home: Path, key_file: Path
) -> None:
    _ids(monkeypatch)
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    app = isolated_home / ".apple-ads-mcp"
    app.mkdir()
    (app / ".env").write_text(
        _env_lines(APPLE_ADS_AD_ACCOUNT_ID="1", APPLE_ADS_DRY_RUN="true"), encoding="utf-8"
    )
    Path(".env").write_text(_env_lines(APPLE_ADS_AD_ACCOUNT_ID="2"), encoding="utf-8")
    config = load_config()
    assert config.ad_account_id == "2"
    assert config.dry_run is True  # still read from the per-user file


def test_real_environment_wins_over_env_files(
    monkeypatch: pytest.MonkeyPatch, key_file: Path
) -> None:
    _ids(monkeypatch)
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    monkeypatch.setenv("APPLE_ADS_AD_ACCOUNT_ID", "7")
    Path(".env").write_text(_env_lines(APPLE_ADS_AD_ACCOUNT_ID="2"), encoding="utf-8")
    assert load_config().ad_account_id == "7"


def test_explicit_env_file_is_the_only_one_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, isolated_home: Path, key_file: Path
) -> None:
    _ids(monkeypatch)
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    Path(".env").write_text(_env_lines(APPLE_ADS_READ_ONLY="true"), encoding="utf-8")
    explicit = tmp_path / "explicit.env"
    explicit.write_text(_env_lines(APPLE_ADS_AD_ACCOUNT_ID="3"), encoding="utf-8")
    config = load_config(env_file=explicit)
    assert config.ad_account_id == "3"
    assert config.read_only is False


def test_allow_remote_is_off_by_default(monkeypatch: pytest.MonkeyPatch, key_file: Path) -> None:
    _ids(monkeypatch)
    monkeypatch.setenv("APPLE_ADS_PRIVATE_KEY_PATH", str(key_file))
    assert load_config().allow_remote is False
    monkeypatch.setenv("APPLE_ADS_ALLOW_REMOTE", "true")
    assert load_config().allow_remote is True


@posix_only
def test_audit_log_folders_are_created_owner_only(isolated_home: Path) -> None:
    path, _ = load_audit_settings()
    AuditLog(path).record(op="x", resource="r", method="PUT", url="u")
    app = isolated_home / ".apple-ads-mcp"
    assert oct(app.stat().st_mode & 0o777) == "0o700"
    assert oct((app / "logs").stat().st_mode & 0o777) == "0o700"
    assert oct(path.stat().st_mode & 0o777) == "0o600"


@posix_only
def test_existing_audit_folder_permissions_are_left_alone(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    AuditLog(shared / "audit.jsonl").record(op="x", resource="r", method="PUT", url="u")
    assert oct(shared.stat().st_mode & 0o777) == "0o755"
