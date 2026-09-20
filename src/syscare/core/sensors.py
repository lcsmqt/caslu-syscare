"""Temperature sensors. Only returns readings the OS exposes reliably; never invents values."""
from __future__ import annotations

import shutil
from dataclasses import dataclass

import psutil

from . import winutil
from .winutil import IS_WINDOWS


@dataclass
class Reading:
    label: str
    celsius: float
    source: str
    note: str = ""


def _sane(c: float) -> bool:
    return -10 <= c <= 150


def parse_acpi(raw) -> list[Reading]:
    """MSAcpi_ThermalZoneTemperature: CurrentTemperature is in tenths of Kelvin."""
    out = []
    for r in winutil.ensure_list(raw):
        try:
            c = float(r["CurrentTemperature"]) / 10.0 - 273.15
        except (KeyError, TypeError, ValueError):
            continue
        if _sane(c):
            out.append(Reading(str(r.get("InstanceName", "ACPI")), round(c, 1), "ACPI",
                               "Zona térmica ACPI: pode não representar a temperatura real da CPU."))
    return out


def gpu_readings() -> list[Reading]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    r = winutil.run([exe, "--query-gpu=name,temperature.gpu", "--format=csv,noheader,nounits"], 10)
    out = []
    for line in r.stdout.splitlines() if r.ok else []:
        name, _, t = line.partition(",")
        try:
            c = float(t.strip())
        except ValueError:
            continue
        if _sane(c):
            out.append(Reading(name.strip(), c, "nvidia-smi"))
    return out


def read_temperatures() -> list[Reading]:
    out: list[Reading] = []
    fn = getattr(psutil, "sensors_temperatures", None)
    if fn:  # Linux/BSD
        try:
            for chip, entries in fn().items():
                for e in entries:
                    if e.current is not None and _sane(e.current):
                        out.append(Reading(f"{chip} {e.label}".strip(), round(e.current, 1), "psutil"))
        except Exception:  # noqa: BLE001
            pass
    if IS_WINDOWS:
        raw = winutil.ps_json("Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
                              "| Select-Object InstanceName,CurrentTemperature", 20)
        out += parse_acpi(raw)
    out += gpu_readings()
    return out


def pick(readings: list[Reading], *keywords: str) -> Reading | None:
    for r in readings:
        if any(k in r.label.lower() for k in keywords):
            return r
    return None
