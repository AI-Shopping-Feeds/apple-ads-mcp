from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .paths import default_audit_path, default_env_file, default_private_key_path

# "sse" (HTTP+SSE) is deprecated by the MCP spec; prefer "streamable-http".
TRANSPORTS = ("stdio", "streamable-http", "sse")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_tool_groups(raw: str | None) -> list[str]:
    """Split a comma-separated APPLE_ADS_TOOL_GROUPS value and check every name.

    Names are case-insensitive and may use '-' for '_'. Empty means all groups.
    """
    from .tools import resolve_tool_groups  # local: tools imports this module

    names = [p.strip().lower().replace("-", "_") for p in (raw or "").split(",")]
    names = [n for n in names if n]
    return resolve_tool_groups(names) if names else []


@dataclass
class Config:
    client_id: str
    team_id: str
    key_id: str
    private_key_path: Path
    # Default ad account for the X-AP-Context header. Tools can override it per
    # call with `ad_account_id`. Empty means "none": only account-less tools
    # (me, ACLs, org, app search) work until one is passed.
    ad_account_id: str | None
    audit_log: Path
    page_size: int
    timeout: float
    dry_run: bool
    audit_retention_days: int = 30
    # Budget and bid increases above this percentage need confirm='APPLY'.
    max_increase_pct: float = 20.0
    log_level: str = "INFO"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    # Tool modules to register; empty means all (see apple_ads_mcp.tools.TOOL_GROUPS).
    tool_groups: list[str] = field(default_factory=list)
    # Register only tools annotated read-only (plus the meta tools).
    read_only: bool = False
    # HTTP transports refuse non-loopback hosts unless this is set.
    allow_remote: bool = False


def _path_or_none(raw: str | None) -> Path | None:
    if not raw or not raw.strip():
        return None
    return Path(raw).expanduser().resolve()


def load_env_files(env_file: Path | None = None) -> list[Path]:
    """Load settings from .env files without overriding real environment variables.

    With `--env`, only that file is read. Otherwise ./.env, then
    ~/.apple-ads-mcp/.env; the first file to set a variable wins.
    """
    candidates = [env_file] if env_file is not None else [Path.cwd() / ".env", default_env_file()]
    loaded: list[Path] = []
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)
            loaded.append(candidate)
    return loaded


def _private_key_setting() -> Path | None:
    """APPLE_ADS_PRIVATE_KEY_PATH, or the keygen default if that file exists."""
    configured = _path_or_none(os.environ.get("APPLE_ADS_PRIVATE_KEY_PATH"))
    if configured is not None:
        return configured
    default = default_private_key_path()
    return default if default.is_file() else None


def _int(name: str, default: str) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer") from e


def _float(name: str, default: str) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError as e:
        raise RuntimeError(f"{name} must be a number") from e


def load_audit_settings(env_file: Path | None = None) -> tuple[Path, int]:
    """Audit path and retention only, without requiring credentials (used by `purge`)."""
    load_env_files(env_file)
    path = _path_or_none(os.environ.get("APPLE_ADS_AUDIT_LOG")) or default_audit_path()
    return path, _int("APPLE_ADS_AUDIT_RETENTION_DAYS", "30")


def load_config(env_file: Path | None = None) -> Config:
    """Read configuration from the environment and .env files (see `load_env_files`).

    Raises RuntimeError with actionable messages on misconfiguration."""
    load_env_files(env_file)

    key_path = _private_key_setting()
    missing = [
        name
        for name in ("APPLE_ADS_CLIENT_ID", "APPLE_ADS_TEAM_ID", "APPLE_ADS_KEY_ID")
        if not os.environ.get(name, "").strip()
    ]
    if key_path is None:
        missing.append("APPLE_ADS_PRIVATE_KEY_PATH")
    if missing or key_path is None:
        raise RuntimeError(
            f"Missing Apple Ads API credentials: {', '.join(missing)}.\n"
            "  - Generate a key pair with `apple-ads-mcp keygen` and upload the public key in\n"
            "    Apple Ads > Account Settings > API (signed in as the API user).\n"
            "  - Copy the clientId, teamId and keyId shown there into your MCP config or .env.\n"
            f"  - APPLE_ADS_PRIVATE_KEY_PATH defaults to {default_private_key_path()} when that\n"
            "    file exists."
        )

    client_id = os.environ["APPLE_ADS_CLIENT_ID"].strip()
    if not client_id.startswith("SEARCHADS."):
        raise RuntimeError(
            f"APPLE_ADS_CLIENT_ID should start with 'SEARCHADS.', got '{client_id[:20]}…'."
        )
    if not key_path.exists():
        raise RuntimeError(
            f"APPLE_ADS_PRIVATE_KEY_PATH points to a missing file: {key_path}\n"
            "Run `apple-ads-mcp keygen` to create one."
        )

    ad_account = os.environ.get("APPLE_ADS_AD_ACCOUNT_ID", "").strip() or None
    if ad_account and not ad_account.isdigit():
        raise RuntimeError(f"APPLE_ADS_AD_ACCOUNT_ID must be numeric, got '{ad_account}'.")

    audit_path = _path_or_none(os.environ.get("APPLE_ADS_AUDIT_LOG")) or default_audit_path()

    transport = os.environ.get("APPLE_ADS_TRANSPORT", "stdio").strip().lower()
    if transport not in TRANSPORTS:
        raise RuntimeError(
            f"APPLE_ADS_TRANSPORT must be one of {', '.join(TRANSPORTS)}, got '{transport}'."
        )

    page_size = _int("APPLE_ADS_PAGE_SIZE", "100")
    if not 1 <= page_size <= 1000:
        raise RuntimeError("APPLE_ADS_PAGE_SIZE must be between 1 and 1000")
    max_increase = _float("APPLE_ADS_MAX_INCREASE_PCT", "20")
    if max_increase < 0:
        raise RuntimeError("APPLE_ADS_MAX_INCREASE_PCT must be 0 or more")

    return Config(
        client_id=client_id,
        team_id=os.environ["APPLE_ADS_TEAM_ID"].strip(),
        key_id=os.environ["APPLE_ADS_KEY_ID"].strip(),
        private_key_path=key_path,
        ad_account_id=ad_account,
        audit_log=audit_path,
        page_size=page_size,
        timeout=_float("APPLE_ADS_TIMEOUT", "30"),
        dry_run=_truthy(os.environ.get("APPLE_ADS_DRY_RUN")),
        audit_retention_days=_int("APPLE_ADS_AUDIT_RETENTION_DAYS", "30"),
        max_increase_pct=max_increase,
        log_level=os.environ.get("APPLE_ADS_LOG_LEVEL", "INFO").upper(),
        transport=transport,
        host=os.environ.get("APPLE_ADS_HOST", "127.0.0.1"),
        port=_int("APPLE_ADS_PORT", "8000"),
        tool_groups=parse_tool_groups(os.environ.get("APPLE_ADS_TOOL_GROUPS")),
        read_only=_truthy(os.environ.get("APPLE_ADS_READ_ONLY")),
        allow_remote=_truthy(os.environ.get("APPLE_ADS_ALLOW_REMOTE")),
    )
