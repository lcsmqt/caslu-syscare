"""Safe actions with confirmation-friendly API and a persistent undo log.

Nothing here runs without an explicit call from the UI, which must confirm with
the user first. Every change is recorded so it can be reverted.
"""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path

import psutil

from . import audit, knowledge
from .config import data_dir  # noqa: F401  (re-exported for backward compatibility)

IS_WINDOWS = platform.system() == "Windows"


def _log_path() -> Path:
    return data_dir() / "undo_log.json"


def _load_log() -> list[dict]:
    try:
        return json.loads(_log_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_log(entries: list[dict]) -> None:
    _log_path().write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _record(entry: dict) -> None:
    entry["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log = _load_log()
    log.append(entry)
    _save_log(log)
    audit.record(entry.get("action", "action"), "success",
                 entry.get("name") or entry.get("target") or entry.get("src") or "",
                 previous=entry.get("original") or entry.get("value") and "enabled",
                 new={k: entry[k] for k in ("killed", "kind") if k in entry},
                 details=entry.get("undo", ""))


def history() -> list[dict]:
    return _load_log()


# --- Processes -----------------------------------------------------------
def terminate_group(name: str, pids: list[int]) -> tuple[int, list[str]]:
    """Gracefully terminate processes. Returns (killed, errors). Refuses protected ones."""
    if knowledge.is_protected(name):
        return 0, [f"'{name}' é um processo crítico e está protegido."]
    killed, errors = 0, []
    for pid in pids:
        try:
            p = psutil.Process(pid)
            if knowledge.is_protected(p.name()):
                errors.append(f"PID {pid}: protegido")
                continue
            p.terminate()
            try:
                p.wait(timeout=3)
            except psutil.TimeoutExpired:
                p.kill()
            killed += 1
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            errors.append(f"PID {pid}: acesso negado (execute como administrador)")
    _record({"action": "terminate", "name": name, "pids": pids, "killed": killed,
             "undo": "Reabra o programa manualmente."})
    return killed, errors


# --- Startup -------------------------------------------------------------
def disable_startup(item) -> str:
    """Disable a startup item reversibly. Returns a status message."""
    if item.kind == "registry":  # pragma: no cover - Windows only
        import winreg
        label, name = item.key.split("|", 1)
        hive = winreg.HKEY_CURRENT_USER if label == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
            value, vtype = winreg.QueryValueEx(k, name)
            winreg.DeleteValue(k, name)
        _record({"action": "disable_startup", "kind": "registry", "hive": label,
                 "name": name, "value": value, "vtype": vtype})
        return f"'{item.name}' removido da inicialização (reversível pelo histórico)."
    if item.kind == "folder":
        src = Path(item.key)
        dst = data_dir() / "disabled_startup" / src.name
        dst.parent.mkdir(exist_ok=True)
        src.replace(dst)
        _record({"action": "disable_startup", "kind": "folder", "src": str(src), "dst": str(dst)})
        return f"'{item.name}' movido para quarentena (reversível)."
    if item.kind == "autostart":
        src = Path(item.key)
        user_dir = Path.home() / ".config" / "autostart"
        user_dir.mkdir(parents=True, exist_ok=True)
        target = user_dir / src.name
        original = target.read_text() if target.exists() else None
        content = (src.read_text(errors="ignore") if src.exists() else "[Desktop Entry]\n")
        if "Hidden=" in content:
            content = "\n".join("Hidden=true" if l.startswith("Hidden=") else l
                                for l in content.splitlines()) + "\n"
        else:
            content = content.rstrip("\n") + "\nHidden=true\n"
        target.write_text(content)
        _record({"action": "disable_startup", "kind": "autostart", "target": str(target),
                 "original": original})
        return f"'{item.name}' desativado da inicialização (reversível)."
    raise ValueError(f"Tipo desconhecido: {item.kind}")


def undo_last() -> str:
    """Revert the most recent reversible action."""
    log = _load_log()
    for i in range(len(log) - 1, -1, -1):
        e = log[i]
        if e.get("action") != "disable_startup" or e.get("undone"):
            continue
        if e["kind"] == "folder":
            Path(e["src"]).parent.mkdir(parents=True, exist_ok=True)
            Path(e["dst"]).replace(e["src"])
        elif e["kind"] == "autostart":
            t = Path(e["target"])
            if e.get("original") is None:
                t.unlink(missing_ok=True)
            else:
                t.write_text(e["original"])
        elif e["kind"] == "registry":  # pragma: no cover - Windows only
            import winreg
            hive = winreg.HKEY_CURRENT_USER if e["hive"] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, e["name"], 0, e["vtype"], e["value"])
        log[i]["undone"] = True
        _save_log(log)
        audit.record("undo_disable_startup", "success", e.get("name") or e.get("target") or e.get("src") or "")
        return f"Desfeito: {e.get('name') or e.get('target') or e.get('src')}"
    return "Nada para desfazer."
