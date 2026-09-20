"""Append-only audit trail (JSON Lines). Never stores secrets or file contents."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from .config import data_dir

log = logging.getLogger("syscare.audit")
_SECRET = re.compile(r"pass(word|wd)?|token|secret|credential|api[_-]?key", re.I)
_MAX = 500


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("[redacted]" if _SECRET.search(str(k)) else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub(x) for x in list(obj)[:100]]
    if isinstance(obj, str):
        return obj if len(obj) <= _MAX else obj[:_MAX] + "…"
    return obj


def _path():
    return data_dir() / "audit.jsonl"


def record(action: str, result: str, target: str = "", previous: Any = None,
           new: Any = None, details: str = "") -> dict:
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "result": result,          # success | warning | failed | cancelled | blocked
        "target": _scrub(target),
        "previous_state": _scrub(previous),
        "new_state": _scrub(new),
        "details": _scrub(details),
    }
    try:
        with _path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("could not write audit entry: %s", e)
    return entry


def read(limit: int = 200) -> list[dict]:
    try:
        lines = _path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
