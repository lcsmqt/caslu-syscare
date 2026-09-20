"""System information and software inventory."""
from __future__ import annotations

import datetime as dt
import getpass
import platform
import shutil
import socket
import subprocess

import psutil

IS_WINDOWS = platform.system() == "Windows"


def _gb(n: float) -> float:
    return round(n / 1024**3, 1)


def summary() -> dict:
    vm = psutil.virtual_memory()
    boot = dt.datetime.fromtimestamp(psutil.boot_time())
    freq = psutil.cpu_freq()
    info = {
        "Host": socket.gethostname(),
        "Usuário": getpass.getuser(),
        "Sistema": f"{platform.system()} {platform.release()}",
        "Versão": platform.version()[:80],
        "Arquitetura": platform.machine(),
        "CPU": platform.processor() or platform.machine(),
        "Núcleos (físicos/lógicos)": f"{psutil.cpu_count(logical=False)}/{psutil.cpu_count()}",
        "Frequência CPU": f"{freq.current:.0f} MHz" if freq else "n/d",
        "RAM total": f"{_gb(vm.total)} GB",
        "RAM em uso": f"{vm.percent}%",
        "Ligado desde": boot.strftime("%d/%m/%Y %H:%M"),
        "Uptime": str(dt.datetime.now() - boot).split(".")[0],
    }
    bat = getattr(psutil, "sensors_battery", lambda: None)()
    if bat:
        info["Bateria"] = f"{bat.percent:.0f}% ({'carregando' if bat.power_plugged else 'descarregando'})"
    return info


def disks() -> list[dict]:
    out = []
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        out.append({"mount": p.mountpoint, "fs": p.fstype, "total_gb": _gb(u.total),
                    "used_gb": _gb(u.used), "percent": u.percent})
    return out


def installed_software() -> list[dict]:
    """Installed programs: Windows registry Uninstall keys, Linux dpkg/rpm."""
    return _software_windows() if IS_WINDOWS else _software_linux()


def _software_windows() -> list[dict]:  # pragma: no cover - Windows only
    import winreg
    out, seen = [], set()
    paths = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, path in paths:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                    def val(n):
                        try:
                            return str(winreg.QueryValueEx(k, n)[0])
                        except OSError:
                            return ""
                    name = val("DisplayName")
                    if name and name not in seen:
                        seen.add(name)
                        out.append({"name": name, "version": val("DisplayVersion"),
                                    "publisher": val("Publisher")})
            except OSError:
                continue
    return sorted(out, key=lambda x: x["name"].lower())


def _software_linux() -> list[dict]:
    cmds = []
    if shutil.which("dpkg-query"):
        cmds.append((["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\n"], "\t"))
    elif shutil.which("rpm"):
        cmds.append((["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}\t%{VENDOR}\n"], "\t"))
    out = []
    for cmd, sep in cmds:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        for line in res.stdout.splitlines():
            parts = line.split(sep)
            if parts and parts[0]:
                out.append({"name": parts[0], "version": parts[1] if len(parts) > 1 else "",
                            "publisher": parts[2] if len(parts) > 2 else ""})
    return sorted(out, key=lambda x: x["name"].lower())
