"""Battery diagnostics (laptops). Health = full-charge capacity / design capacity."""
from __future__ import annotations

import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil

from . import config, winutil
from .issues import Issue
from .winutil import IS_WINDOWS, UNAVAILABLE

log = logging.getLogger("syscare.battery")

CIM_PS = (
    "[pscustomobject]@{"
    "Static=@(Get-CimInstance -Namespace root/wmi -ClassName BatteryStaticData | Select-Object DesignedCapacity);"
    "Full=@(Get-CimInstance -Namespace root/wmi -ClassName BatteryFullChargedCapacity | Select-Object FullChargedCapacity);"
    "Cycles=@(Get-CimInstance -Namespace root/wmi -ClassName BatteryCycleCount | Select-Object CycleCount)}"
)


def health_pct(design: float | None, full: float | None) -> float | None:
    if not design or not full or design <= 0:
        return None
    return round(min(100.0, full / design * 100), 1)


def parse_powercfg_xml(xml_text: str) -> dict:
    """Parse `powercfg /batteryreport /xml` output (namespace-agnostic)."""
    out: dict = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("DesignCapacity", "FullChargeCapacity", "CycleCount", "Chemistry", "Manufacturer") \
                and tag not in out and el.text and el.text.strip():
            out[tag] = el.text.strip()
    return out


def parse_cim(raw) -> dict:
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    s, f, c = (winutil.ensure_list(raw.get(k)) for k in ("Static", "Full", "Cycles"))
    if s and s[0].get("DesignedCapacity"):
        out["DesignCapacity"] = s[0]["DesignedCapacity"]
    if f and f[0].get("FullChargedCapacity"):
        out["FullChargeCapacity"] = f[0]["FullChargedCapacity"]
    if c and c[0].get("CycleCount") is not None:
        out["CycleCount"] = c[0]["CycleCount"]
    return out


def _to_int(x) -> int | None:
    try:
        return int(str(x).replace(",", "").split()[0])
    except (ValueError, IndexError):
        return None


def _powercfg() -> dict:
    p = Path(tempfile.gettempdir()) / "syscare_battery.xml"
    r = winutil.run(["powercfg", "/batteryreport", "/xml", "/output", str(p)], 30)
    try:
        return parse_powercfg_xml(p.read_text(encoding="utf-8", errors="ignore")) if r.ok else {}
    except OSError:
        return {}
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def _sysfs() -> dict:
    """Linux dev fallback: /sys/class/power_supply/BAT*."""
    for bat in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        def rd(n):
            try:
                return int((bat / n).read_text().strip())
            except (OSError, ValueError):
                return None
        d = rd("energy_full_design") or rd("charge_full_design")
        f = rd("energy_full") or rd("charge_full")
        if d and f:
            return {"DesignCapacity": d, "FullChargeCapacity": f, "CycleCount": rd("cycle_count")}
    return {}


def collect() -> dict:
    batt = getattr(psutil, "sensors_battery", lambda: None)()
    if batt is None:
        return {"present": False, "message": "Nenhuma bateria detectada (desktop ou bateria não reportada)."}
    data = parse_cim(winutil.ps_json(CIM_PS, 30)) if IS_WINDOWS else _sysfs()
    if IS_WINDOWS and not (data.get("DesignCapacity") and data.get("FullChargeCapacity")):
        data.update({k: v for k, v in _powercfg().items() if k not in data})
    design, full = _to_int(data.get("DesignCapacity")), _to_int(data.get("FullChargeCapacity"))
    h = health_pct(design, full)
    cycles = _to_int(data.get("CycleCount"))
    secs = batt.secsleft
    runtime = UNAVAILABLE
    if not batt.power_plugged and isinstance(secs, int) and secs > 0:
        runtime = f"{secs // 3600}h {secs % 3600 // 60:02d}min (estimativa do sistema)"
    return {
        "present": True,
        "charge_pct": round(batt.percent),
        "state": "carregando / na tomada" if batt.power_plugged else "descarregando",
        "design_capacity_mwh": design, "full_capacity_mwh": full,
        "health_pct": h, "wear_pct": round(100 - h, 1) if h is not None else None,
        "cycle_count": cycles if cycles else None,
        "runtime": runtime,
        "chemistry": data.get("Chemistry", UNAVAILABLE),
        "message": "" if h is not None else "Capacidade de projeto/atual indisponível para esta bateria.",
    }


def assess(b: dict) -> list[Issue]:
    if not b.get("present") or b.get("health_pct") is None:
        return []
    h = b["health_pct"]
    ev = f"projeto {b['design_capacity_mwh']} / atual {b['full_capacity_mwh']} (mWh)"
    msg = f"A bateria retém aproximadamente {h:.0f}% da capacidade original de projeto."
    if h < config.threshold("battery_health_poor_pct"):
        return [Issue("Bateria", "medium", "Bateria bastante desgastada", msg,
                      "Considere substituir a bateria se a autonomia estiver insuficiente.", ev)]
    if h < config.threshold("battery_health_attention_pct"):
        return [Issue("Bateria", "low", "Desgaste da bateria acima do normal", msg,
                      "Autonomia reduzida é esperada; planeje a substituição no médio prazo.", ev)]
    return []
