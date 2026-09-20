"""Hardware Health: CPU, RAM, GPU, motherboard/BIOS, storage inventory.

One PowerShell/CIM call feeds pure parse functions (unit-tested). Missing data is
shown as 'Indisponível' — values are never guessed.
"""
from __future__ import annotations

import logging
import platform
import shutil
from pathlib import Path

import psutil

from . import sensors, winutil
from .winutil import UNAVAILABLE, IS_WINDOWS, ensure_list, fmt_gb, val

log = logging.getLogger("syscare.hardware")

_DT = "@{n='%s';e={if($_.%s){$_.%s.ToString('yyyy-MM-dd')}}}"

HARDWARE_PS = (
    "[pscustomobject]@{"
    "Cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores,"
    "NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed,L3CacheSize);"
    "Memory=@(Get-CimInstance Win32_PhysicalMemory | Select-Object DeviceLocator,Capacity,Speed,"
    "ConfiguredClockSpeed,Manufacturer,PartNumber,SMBIOSMemoryType);"
    "MemArray=@(Get-CimInstance Win32_PhysicalMemoryArray | Select-Object MemoryDevices);"
    "Gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion,"
    + (_DT % ("DriverDate", "DriverDate", "DriverDate")) + ");"
    "Board=@(Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product);"
    "Bios=@(Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,"
    + (_DT % ("ReleaseDate", "ReleaseDate", "ReleaseDate")) + ");"
    "System=@(Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model)}"
)

_MEM_TYPE = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}


def _first(x):
    l = ensure_list(x)
    return l[0] if l else {}


# ------------------------------------------------------------------ parsers
def parse_cpu(raw_cpu, logical: int, physical: int | None) -> dict:
    c = _first(raw_cpu)
    cur, mx = c.get("CurrentClockSpeed"), c.get("MaxClockSpeed")
    clock = UNAVAILABLE
    if cur or mx:
        clock = f"{cur or '?'} MHz atual / {mx or '?'} MHz máx."
    return {
        "Modelo": val(c.get("Name")),
        "Fabricante": val(c.get("Manufacturer")),
        "Arquitetura": platform.machine() or UNAVAILABLE,
        "Núcleos físicos": val(c.get("NumberOfCores") or physical),
        "Núcleos lógicos": val(c.get("NumberOfLogicalProcessors") or logical),
        "Clock": clock,
    }


def parse_ram(raw_mem, raw_array) -> dict:
    mods = []
    for m in ensure_list(raw_mem):
        speed = m.get("ConfiguredClockSpeed") or m.get("Speed")
        mods.append({
            "Slot": val(m.get("DeviceLocator")),
            "Capacidade": fmt_gb(m.get("Capacity"), 0),
            "Velocidade": f"{speed} MHz" if speed else UNAVAILABLE,
            "Tipo": _MEM_TYPE.get(m.get("SMBIOSMemoryType"), UNAVAILABLE),
            "Fabricante": val(m.get("Manufacturer")),
            "Modelo": val(m.get("PartNumber")),
        })
    slots = sum(int(a.get("MemoryDevices") or 0) for a in ensure_list(raw_array)) or None
    return {"Slots (total)": val(slots), "Slots ocupados": str(len(mods)) if mods else UNAVAILABLE,
            "Módulos": mods}


def parse_gpu(raw_gpu, nvidia: dict[str, dict] | None = None) -> list[dict]:
    out = []
    nvidia = nvidia or {}
    for g in ensure_list(raw_gpu):
        name = val(g.get("Name"))
        nv = next((v for k, v in nvidia.items() if k and k.lower() in name.lower()), None)
        vram = UNAVAILABLE
        if nv and nv.get("vram_mb"):
            vram = f"{nv['vram_mb'] / 1024:.1f} GB"
        elif g.get("AdapterRAM"):
            ram = int(g["AdapterRAM"])
            vram = ("≥ 4 GB (a API do Windows limita a 4 GB; valor real pode ser maior)"
                    if ram >= 4294967295 else fmt_gb(ram, 1 if ram >= 1024**3 else 2))
        out.append({
            "Modelo": name,
            "VRAM": vram,
            "Driver": val(g.get("DriverVersion")),
            "Data do driver": val(g.get("DriverDate")),
            "Uso": f"{nv['util']:.0f}%" if nv and nv.get("util") is not None else UNAVAILABLE,
            "Temperatura": f"{nv['temp']:.0f} °C" if nv and nv.get("temp") is not None else UNAVAILABLE,
        })
    return out


def parse_board(raw_board, raw_bios, raw_system) -> dict:
    b, bi, s = _first(raw_board), _first(raw_bios), _first(raw_system)
    return {
        "Fabricante": val(b.get("Manufacturer") or s.get("Manufacturer")),
        "Modelo": val(b.get("Product")),
        "Sistema (modelo)": val(s.get("Model")),
        "BIOS": val(bi.get("SMBIOSBIOSVersion")),
        "Data da BIOS": val(bi.get("ReleaseDate")),
    }


def nvidia_info() -> dict[str, dict]:
    """Optional: richer GPU data when nvidia-smi is present (VRAM, load, temperature)."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {}
    r = winutil.run([exe, "--query-gpu=name,memory.total,utilization.gpu,temperature.gpu",
                     "--format=csv,noheader,nounits"], 10)
    out: dict[str, dict] = {}
    for line in r.stdout.splitlines() if r.ok else []:
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 4:
            def num(x):
                try:
                    return float(x)
                except ValueError:
                    return None
            out[p[0]] = {"vram_mb": num(p[1]), "util": num(p[2]), "temp": num(p[3])}
    return out


# ------------------------------------------------------------------ linux (dev/test) fallbacks
def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(errors="ignore").strip() or None
    except OSError:
        return None


def _linux_raw() -> dict:
    model = None
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.lower().startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    dmi = "/sys/class/dmi/id/"
    return {
        "Cpu": [{"Name": model}],
        "Board": [{"Manufacturer": _read(dmi + "board_vendor"), "Product": _read(dmi + "board_name")}],
        "Bios": [{"SMBIOSBIOSVersion": _read(dmi + "bios_version"), "ReleaseDate": _read(dmi + "bios_date")}],
        "System": [{"Manufacturer": _read(dmi + "sys_vendor"), "Model": _read(dmi + "product_name")}],
        "Memory": [], "MemArray": [], "Gpu": [],
    }


# ------------------------------------------------------------------ collector
def collect() -> dict:
    notes: list[str] = []
    raw = winutil.ps_json(HARDWARE_PS, 60) if IS_WINDOWS else _linux_raw()
    if not isinstance(raw, dict):
        notes.append("Não foi possível consultar o Windows (CIM). Exibindo apenas dados locais.")
        raw = _linux_raw() if not IS_WINDOWS else {}
    vm = psutil.virtual_memory()
    cpu = parse_cpu(raw.get("Cpu"), psutil.cpu_count() or 0, psutil.cpu_count(logical=False))
    cpu["Uso atual"] = f"{psutil.cpu_percent(interval=0.3):.0f}%"
    if cpu["Clock"] == UNAVAILABLE:
        f = psutil.cpu_freq()
        if f:
            cpu["Clock"] = f"{f.current:.0f} MHz atual / {f.max:.0f} MHz máx."
    temps = sensors.read_temperatures()
    t = sensors.pick(temps, "cpu", "package", "coretemp", "k10temp", "tctl")
    cpu["Temperatura"] = f"{t.celsius} °C ({t.source})" if t else UNAVAILABLE
    ram = parse_ram(raw.get("Memory"), raw.get("MemArray"))
    ram.update({"Instalada": fmt_gb(vm.total), "Disponível": fmt_gb(vm.available),
                "Em uso": f"{vm.percent:.0f}%"})
    gpus = parse_gpu(raw.get("Gpu"), nvidia_info())
    if not gpus:
        notes.append("Nenhuma GPU reportada pelo sistema.")
    return {
        "cpu": cpu, "ram": ram, "gpu": gpus,
        "board": parse_board(raw.get("Board"), raw.get("Bios"), raw.get("System")),
        "notes": notes,
    }


def flatten(hw: dict) -> list[list[str]]:
    """[category, item, value] rows for tables and reports."""
    rows: list[list[str]] = []
    for k, v in hw["cpu"].items():
        rows.append(["CPU", k, v])
    for k, v in hw["ram"].items():
        if k != "Módulos":
            rows.append(["Memória RAM", k, v])
    for m in hw["ram"].get("Módulos", []):
        rows.append(["Memória RAM", f"Módulo {m['Slot']}",
                     f"{m['Capacidade']} {m['Tipo']} {m['Velocidade']} — {m['Fabricante']} {m['Modelo']}"])
    for i, g in enumerate(hw["gpu"], 1):
        for k, v in g.items():
            rows.append([f"GPU {i}", k, v])
    for k, v in hw["board"].items():
        rows.append(["Placa-mãe / BIOS", k, v])
    return rows
