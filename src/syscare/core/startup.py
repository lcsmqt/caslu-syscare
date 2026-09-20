"""Startup program discovery (Windows registry / startup folder, Linux autostart)."""
from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from . import knowledge

IS_WINDOWS = platform.system() == "Windows"


@dataclass
class StartupItem:
    name: str
    command: str
    location: str        # human-readable source
    key: str             # opaque handle used by actions.disable_startup
    kind: str            # registry | folder | autostart
    flagged: bool = False
    reason: str = ""
    impact: str = "Desconhecido"      # Alto | Médio | Baixo | Desconhecido (estimate, not a boot-time measurement)
    impact_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _flag(item: StartupItem) -> StartupItem:
    base = re.split(r"[\\/]", item.command.strip().strip('"').split('"')[0] or item.command)[-1]
    for candidate in (item.name, base.split(" ")[0]):
        rule = knowledge.match_rule(candidate)
        if rule:
            item.flagged, item.reason = True, rule.reason
            break
    return item


def _exe_name(command: str) -> str:
    cmd = command.strip()
    if cmd.startswith('"'):
        cmd = cmd[1:].split('"')[0]
    else:
        m = re.match(r"(.+?\.(?:exe|bat|cmd|lnk))", cmd, re.I)
        cmd = m.group(1) if m else cmd.split(" ")[0]
    return re.split(r"[\\/]", cmd)[-1].lower()


def estimate_impact(item: StartupItem, running: dict[str, dict]) -> tuple[str, str]:
    """Estimate startup impact from the CURRENT footprint of the running process.

    `running` maps lower-case exe name -> {"rss_mb": float, "cpu_s": float}. This is an estimate,
    not a boot measurement; unknown when the program is not running. Security tools are never
    suggested for disabling.
    """
    exe = _exe_name(item.command)
    rule = knowledge.match_rule(item.name) or knowledge.match_rule(exe)
    if rule and rule.category == "Essencial":
        return "Baixo", "Componente essencial/segurança: não recomendado desativar."
    if any(w in item.name.lower() or w in exe for w in ("defender", "antivirus", "security", "kaspersky", "avast", "eset")):
        return "Baixo", "Ferramenta de segurança: não recomendado desativar."
    p = running.get(exe)
    if not p:
        return "Desconhecido", "Programa não está em execução; impacto não medido."
    rss, cpu = p.get("rss_mb", 0), p.get("cpu_s", 0)
    if rss >= 300 or cpu >= 60:
        level = "Alto"
    elif rss >= 100 or cpu >= 15:
        level = "Médio"
    else:
        level = "Baixo"
    return level, f"Em execução agora: {rss:.0f} MB de RAM, {cpu:.0f} s de CPU acumulada (estimativa)."


def running_footprint() -> dict[str, dict]:
    import psutil
    out: dict[str, dict] = {}
    for p in psutil.process_iter(["name", "memory_info", "cpu_times"]):
        try:
            n = (p.info["name"] or "").lower()
            mi, ct = p.info["memory_info"], p.info["cpu_times"]
            e = out.setdefault(n, {"rss_mb": 0.0, "cpu_s": 0.0})
            e["rss_mb"] += (mi.rss / 1048576) if mi else 0
            e["cpu_s"] += (ct.user + ct.system) if ct else 0
        except (psutil.Error, AttributeError):
            continue
    return out


def list_startup() -> list[StartupItem]:
    items = _windows_items() if IS_WINDOWS else _linux_items()
    try:
        running = running_footprint()
    except Exception:  # noqa: BLE001
        running = {}
    for i in items:
        _flag(i)
        i.impact, i.impact_reason = estimate_impact(i, running)
    return items


# --- Windows -------------------------------------------------------------
def _windows_items() -> list[StartupItem]:  # pragma: no cover - Windows only
    import winreg

    items: list[StartupItem] = []
    roots = [(winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")]
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    for hive, label in roots:
        try:
            with winreg.OpenKey(hive, path) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    items.append(StartupItem(name, str(value), f"{label}\\Run",
                                             f"{label}|{name}", "registry"))
                    i += 1
        except OSError:
            continue
    folders = [Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"]
    for folder in folders:
        if folder.is_dir():
            for f in folder.iterdir():
                if f.is_file() and f.name.lower() != "desktop.ini":
                    items.append(StartupItem(f.stem, str(f), "Pasta Inicializar", str(f), "folder"))
    return items


# --- Linux ---------------------------------------------------------------
def _autostart_dirs() -> list[Path]:
    dirs = [Path.home() / ".config" / "autostart"]
    dirs.append(Path("/etc/xdg/autostart"))
    return dirs


def _parse_desktop(path: Path) -> dict:
    data: dict[str, str] = {}
    try:
        for line in path.read_text(errors="ignore").splitlines():
            if "=" in line and not line.startswith("#") and not line.startswith("["):
                k, v = line.split("=", 1)
                data.setdefault(k.strip(), v.strip())
    except OSError:
        pass
    return data


def _linux_items() -> list[StartupItem]:
    items: list[StartupItem] = []
    seen: set[str] = set()
    for d in _autostart_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.desktop")):
            if f.name in seen:
                continue
            seen.add(f.name)
            data = _parse_desktop(f)
            if data.get("Hidden", "false").lower() == "true":
                continue
            items.append(StartupItem(data.get("Name", f.stem), data.get("Exec", ""),
                                     str(d), str(f), "autostart"))
    return items
