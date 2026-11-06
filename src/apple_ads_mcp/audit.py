"""Append-only JSONL log of write operations.

What goes in: write requests, their `before` snapshots (the entity as it was),
and the write responses. What never goes in: read responses, report rows,
insights or anything else Apple Ads returns to a read. Apple's terms treat
reporting metrics as confidential, so those stay in memory only.

Every entry is passed through `redact.redact` so keys, client secrets and
tokens can't reach the file. Entries older than the retention period are
pruned when the server starts (`prune`).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import chmod_private, ensure_private_dir
from .redact import redact


class AuditLog:
    def __init__(self, path: Path, retention_days: int = 30):
        self.path = path
        self.retention_days = retention_days
        self._lock = threading.Lock()

    def record(
        self,
        *,
        op: str,
        resource: str,
        method: str,
        url: str,
        ad_account_id: str | None = None,
        request_body: Any | None = None,
        response_status: int | None = None,
        response_body: Any | None = None,
        before: Any | None = None,
        dry_run: bool = False,
        error: str | None = None,
    ) -> str:
        audit_id = uuid.uuid4().hex
        entry = {
            "audit_id": audit_id,
            "ts": time.time(),
            "op": op,
            "resource": resource,
            "method": method,
            "url": url,
            "ad_account_id": ad_account_id,
            "request_body": request_body,
            "response_status": response_status,
            "response_body": response_body,
            "before": before,
            "dry_run": dry_run,
            "error": error,
        }
        line = json.dumps(redact(entry), ensure_ascii=False, default=str)
        with self._lock:
            ensure_private_dir(self.path.parent)
            new_file = not self.path.exists()
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            if new_file:
                chmod_private(self.path)
        return audit_id

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.entries()[-limit:] if limit > 0 else []

    def find(self, audit_id: str) -> dict[str, Any] | None:
        for entry in self.entries():
            if entry.get("audit_id") == audit_id:
                return entry
        return None

    def prune(self, now: float | None = None) -> int:
        """Drop entries older than `retention_days`. Returns how many were removed.

        retention_days <= 0 keeps nothing (the file is emptied).
        """
        if not self.path.exists():
            return 0
        cutoff = (now if now is not None else time.time()) - self.retention_days * 86400
        with self._lock:
            entries = self.entries()
            keep = [e for e in entries if float(e.get("ts", 0)) >= cutoff]
            if self.retention_days <= 0:
                keep = []
            removed = len(entries) - len(keep)
            if removed:
                tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    for e in keep:
                        f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
                chmod_private(tmp)
                tmp.replace(self.path)
        return removed

    def purge(self) -> bool:
        """Delete the audit log file. Returns True if a file was removed."""
        with self._lock:
            if self.path.exists():
                self.path.unlink()
                return True
        return False
