from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "data/audit.jsonl"))


def log_audit_event(event: str, actor: str = "system", **fields: Any) -> None:
    """Append one JSON line to the audit trail, kept physically separate from data/logs.jsonl.

    Only for events an incident reviewer would need without wading through
    request-level logs: incident enable/disable, config changes.
    """
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "actor": actor,
        **fields,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
