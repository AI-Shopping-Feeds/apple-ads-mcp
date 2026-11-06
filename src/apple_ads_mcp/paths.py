"""Per-user file locations and owner-only file helpers.

Defaults never depend on where the package is installed (uvx installs into a
cache) or on the working directory (desktop clients often start servers in
'/'). Everything lives under ~/.apple-ads-mcp/:

    ~/.apple-ads-mcp/.env                  optional settings
    ~/.apple-ads-mcp/secrets/              0700: private-key.pem (0600), public-key.pem
    ~/.apple-ads-mcp/logs/audit.jsonl      0600: the audit log

Each location can be overridden with an environment variable.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

APP_DIR_NAME = ".apple-ads-mcp"
PRIVATE_KEY_NAME = "private-key.pem"
PUBLIC_KEY_NAME = "public-key.pem"
AUDIT_LOG_NAME = "audit.jsonl"


def app_home() -> Path:
    """The per-user folder, ~/.apple-ads-mcp."""
    return Path.home() / APP_DIR_NAME


def default_secrets_dir() -> Path:
    return app_home() / "secrets"


def default_private_key_path() -> Path:
    return default_secrets_dir() / PRIVATE_KEY_NAME


def default_audit_path() -> Path:
    return app_home() / "logs" / AUDIT_LOG_NAME


def default_env_file() -> Path:
    return app_home() / ".env"


def chmod_private(path: Path, mode: int = 0o600) -> None:
    """Owner-only permissions on POSIX. Windows has no equivalent mode bits."""
    if os.name == "posix":
        with contextlib.suppress(OSError):
            path.chmod(mode)


def ensure_private_dir(path: Path) -> Path:
    """Create `path` and any missing parents as owner-only (0700) folders.

    Folders that already exist are left as they are, so pointing a setting at
    an existing shared folder never changes its permissions.
    """
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for folder in reversed(missing):
        folder.mkdir(mode=0o700, exist_ok=True)
        chmod_private(folder, 0o700)
    return path


def write_private(path: Path, data: bytes) -> None:
    """Write `path` with mode 0600 from the start (no window where it's world-readable)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    chmod_private(path)
