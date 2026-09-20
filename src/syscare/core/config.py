"""Configuration, portable data directory and logging setup."""
from __future__ import annotations

import copy
import json
import logging
import logging.handlers
import os
import platform
import sys
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
PORTABLE_MARKER = "syscare.portable"

DEFAULTS: dict = {
    "thresholds": {
        "disk_temp_attention_hdd_c": 55,
        "disk_temp_attention_ssd_c": 70,
        "disk_wear_attention_pct": 80,     # % of rated life used
        "battery_health_attention_pct": 80,
        "battery_health_poor_pct": 60,
        "driver_old_years": 5,
    },
    "report_dir": "",
}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def is_portable() -> bool:
    return os.environ.get("SYSCARE_PORTABLE") == "1" or (app_root() / PORTABLE_MARKER).exists()


def data_dir() -> Path:
    """Where logs, audit trail, config and reports live. Portable-aware."""
    env = os.environ.get("SYSCARE_DATA_DIR")
    if env:
        p = Path(env)
    elif is_portable():
        p = app_root() / "data"
    else:
        base = os.environ.get("APPDATA") if IS_WINDOWS else os.environ.get("XDG_DATA_HOME")
        p = (Path(base) if base else Path.home() / ".local" / "share") / "CasluSysCare"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _config_path() -> Path:
    return data_dir() / "config.json"


def load() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    try:
        user = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def save(cfg: dict) -> None:
    _config_path().write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def threshold(name: str):
    return load()["thresholds"].get(name, DEFAULTS["thresholds"][name])


def reports_dir() -> Path:
    custom = load().get("report_dir")
    p = Path(custom) if custom else data_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging() -> logging.Logger:
    """Technical details go to a rotating file; the UI shows friendly messages."""
    log = logging.getLogger("syscare")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    try:
        h = logging.handlers.RotatingFileHandler(data_dir() / "syscare.log", maxBytes=512_000,
                                                 backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        log.addHandler(h)
    except OSError:
        log.addHandler(logging.NullHandler())
    return log
