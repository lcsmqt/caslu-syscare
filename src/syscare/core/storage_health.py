"""SSD/HDD/NVMe health (SMART).

Sources, best first:
  1. smartctl --json (smartmontools, optional external tool — never bundled or downloaded)
  2. Windows Storage reliability counters (Get-PhysicalDisk | Get-StorageReliabilityCounter)
Classification is conservative: one ambiguous metric alone never yields CRITICAL.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field, asdict

from . import config, privilege, winutil
from .winutil import IS_WINDOWS, UNAVAILABLE, ensure_list

log = logging.getLogger("syscare.storage")

HEALTHY, ATTENTION, CRITICAL, UNKNOWN = "HEALTHY", "ATTENTION", "CRITICAL", "UNKNOWN"
STATUS_LABEL = {HEALTHY: "Saudável", ATTENTION: "Atenção", CRITICAL: "Crítico", UNKNOWN: "Desconhecido"}

NO_DATA_NOTE = ("Dados de saúde indisponíveis. Para leitura SMART completa, instale o smartmontools "
                "(smartctl) e execute o Observer como administrador.")


@dataclass
class Reason:
    severity: str    # info | attention | critical
    text: str


@dataclass
class DiskHealth:
    device: str
    model: str
    media_type: str          # HDD | SSD | NVMe | Desconhecido
    interface: str
    capacity_gb: float | None
    status: str
    reasons: list[Reason] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    source: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# metrics that say something about health (vs. purely informative ones)
_HEALTH_KEYS = ("smart_passed", "os_health", "nvme_critical_warning", "percentage_used", "remaining_life_pct",
                "reallocated", "pending", "uncorrectable", "media_errors", "read_errors", "write_errors",
                "spare_pct")

_NVME_WARN_BITS = {
    0: "capacidade reserva (spare) abaixo do limite",
    1: "temperatura fora do limite",
    2: "confiabilidade degradada",
    3: "mídia em modo somente leitura",
    4: "falha no backup de memória volátil",
    5: "região de memória persistente não confiável",
}


def decode_nvme_warning(code: int) -> list[str]:
    return [t for bit, t in _NVME_WARN_BITS.items() if code & (1 << bit)]


def assess(m: dict, media_type: str) -> tuple[str, list[Reason]]:
    reasons: list[Reason] = []
    serious = 0
    add = lambda sev, text: reasons.append(Reason(sev, text))  # noqa: E731

    if m.get("smart_passed") is False:
        add("critical", "O disco reporta falha na autoavaliação SMART. Faça backup imediato dos dados importantes.")
    oh = str(m.get("os_health") or "").lower()
    if oh == "unhealthy":
        add("critical", "O Windows classifica este disco como não íntegro (Unhealthy). "
                        "Faça backup e execute o diagnóstico do fabricante.")
    elif oh == "warning":
        add("attention", "O Windows reporta estado de aviso (Warning) para este disco. Faça backup e monitore.")

    cw = m.get("nvme_critical_warning")
    if cw:
        what = ", ".join(decode_nvme_warning(int(cw))) or "alerta não especificado"
        add("critical", f"O controlador NVMe reporta alerta crítico (0x{int(cw):02x}): {what}. "
                        "Faça backup e verifique com a ferramenta do fabricante.")

    sp, spt = m.get("spare_pct"), m.get("spare_threshold")
    if sp is not None and spt is not None and sp < spt:
        add("critical", f"Capacidade reserva do SSD ({sp}%) abaixo do limite do fabricante ({spt}%).")

    def positive(k):
        v = m.get(k)
        return isinstance(v, (int, float)) and v > 0

    if positive("reallocated"):
        serious += 1
        add("attention", f"Setores realocados detectados ({int(m['reallocated'])}). Isso pode indicar degradação "
                         "física do disco. Faça backup dos arquivos importantes e execute diagnósticos adicionais.")
    if positive("pending"):
        serious += 1
        add("attention", f"Setores pendentes de realocação ({int(m['pending'])}). O disco encontrou áreas difíceis "
                         "de ler. Faça backup e reavalie; se o número crescer, o disco pode estar em degradação.")
    if positive("uncorrectable"):
        serious += 1
        add("attention", f"Erros não corrigíveis offline ({int(m['uncorrectable'])}). Faça backup e "
                         "execute o teste estendido do fabricante.")
    if positive("media_errors"):
        serious += 1
        add("attention", f"Erros de integridade de mídia reportados pelo NVMe ({int(m['media_errors'])}). "
                         "Faça backup e monitore.")
    if positive("read_errors") or positive("write_errors"):
        serious += 1
        add("attention", "Erros de leitura/escrita não corrigidos reportados pelo Windows. "
                         "Faça backup e execute diagnósticos adicionais.")
    if serious >= 2:
        add("critical", "Vários indicadores independentes de degradação estão presentes ao mesmo tempo. "
                        "Recomenda-se backup imediato e substituição planejada do disco.")

    used = m.get("percentage_used")
    if used is None and m.get("remaining_life_pct") is not None:
        used = 100 - m["remaining_life_pct"]
    wear_limit = config.threshold("disk_wear_attention_pct")
    if used is not None and used >= wear_limit:
        add("attention", f"Cerca de {used:.0f}% da vida útil nominal do SSD foi consumida. "
                         "Isso é desgaste esperado, mas planeje a substituição e mantenha backup.")

    t = m.get("temperature_c")
    limit = config.threshold("disk_temp_attention_hdd_c" if media_type == "HDD" else "disk_temp_attention_ssd_c")
    if isinstance(t, (int, float)) and t >= limit:
        add("attention", f"Temperatura elevada ({t:.0f} °C). Verifique ventilação e fluxo de ar do gabinete.")

    if positive("crc_errors"):
        add("info", f"Erros de CRC na interface ({int(m['crc_errors'])}): costuma indicar problema de cabo/conexão, "
                    "não necessariamente do disco.")
    if isinstance(m.get("unsafe_shutdowns"), (int, float)) and m["unsafe_shutdowns"] > 0:
        add("info", f"{int(m['unsafe_shutdowns'])} desligamentos inesperados registrados (informativo).")

    has_data = any(m.get(k) is not None for k in _HEALTH_KEYS)
    if any(r.severity == "critical" for r in reasons):
        status = CRITICAL
    elif any(r.severity == "attention" for r in reasons):
        status = ATTENTION
    elif has_data:
        status = HEALTHY
    else:
        status = UNKNOWN
    return status, reasons


# ------------------------------------------------------------------ smartctl
_LIFE_ATTRS = (231, 233, 202, 177)   # normalized value = % life remaining (vendor dependent)


def _parts_from_smartctl(js: dict) -> dict:
    dev = js.get("device", {}) or {}
    proto = str(dev.get("protocol", ""))
    m: dict = {}
    if isinstance(js.get("smart_status"), dict) and "passed" in js["smart_status"]:
        m["smart_passed"] = bool(js["smart_status"]["passed"])
    m["temperature_c"] = (js.get("temperature") or {}).get("current")
    m["power_on_hours"] = (js.get("power_on_time") or {}).get("hours")

    nvme = js.get("nvme_smart_health_information_log")
    rot = js.get("rotation_rate")
    if nvme:
        media, iface = "NVMe", "NVMe"
        m.update({
            "nvme_critical_warning": nvme.get("critical_warning"),
            "spare_pct": nvme.get("available_spare"),
            "spare_threshold": nvme.get("available_spare_threshold"),
            "percentage_used": nvme.get("percentage_used"),
            "unsafe_shutdowns": nvme.get("unsafe_shutdowns"),
            "media_errors": nvme.get("media_errors"),
        })
        m["temperature_c"] = nvme.get("temperature", m["temperature_c"])
        m["power_on_hours"] = nvme.get("power_on_hours", m["power_on_hours"])
    else:
        media = "HDD" if isinstance(rot, int) and rot > 0 else "SSD" if rot == 0 else "Desconhecido"
        iface = "SATA/ATA" if proto.upper() == "ATA" else proto or UNAVAILABLE
        table = {a.get("id"): a for a in (js.get("ata_smart_attributes") or {}).get("table", []) if isinstance(a, dict)}

        def raw(i):
            a = table.get(i)
            return (a.get("raw") or {}).get("value") if a else None

        m["reallocated"] = raw(5)
        m["pending"] = raw(197)
        m["uncorrectable"] = raw(198)
        m["crc_errors"] = raw(199)
        if m["temperature_c"] is None and raw(194) is not None:
            m["temperature_c"] = raw(194) & 0xFF
        if media != "HDD":
            for i in _LIFE_ATTRS:
                if i in table and table[i].get("value") is not None:
                    m["remaining_life_pct"] = table[i]["value"]
                    m["life_source"] = table[i].get("name", str(i))
                    break
    cap = (js.get("user_capacity") or {}).get("bytes")
    return {
        "device": dev.get("name", ""), "model": js.get("model_name") or js.get("device_model") or UNAVAILABLE,
        "media_type": media, "interface": iface,
        "capacity_gb": round(cap / 1e9, 1) if cap else None, "metrics": m, "source": "smartctl",
    }


def _build(parts: dict, extra: dict | None = None, note: str = "") -> DiskHealth:
    metrics = dict(parts["metrics"])
    for k, v in (extra or {}).items():
        if metrics.get(k) is None and v is not None:
            metrics[k] = v
    status, reasons = assess(metrics, parts["media_type"])
    if status == UNKNOWN and not note:
        note = NO_DATA_NOTE
    return DiskHealth(parts["device"], parts["model"], parts["media_type"], parts["interface"],
                      parts["capacity_gb"], status, reasons, metrics, parts["source"], note)


def parse_smartctl(js: dict, extra: dict | None = None) -> DiskHealth:
    return _build(_parts_from_smartctl(js), extra)


# ------------------------------------------------------------------ Windows counters / inventory
_MEDIA = {"3": "HDD", "4": "SSD", "5": "SSD", "HDD": "HDD", "SSD": "SSD", "SCM": "SSD"}
_BUS = {"3": "ATA", "7": "USB", "8": "RAID", "10": "SAS", "11": "SATA", "17": "NVMe"}
_HEALTH = {"0": "Healthy", "1": "Warning", "2": "Unhealthy", "5": "Unknown"}

STORAGE_PS = r"""
$d = @(Get-PhysicalDisk | ForEach-Object {
  $pd = $_; $r = $null
  try { $r = $pd | Get-StorageReliabilityCounter } catch {}
  [pscustomobject]@{
    DeviceId=$pd.DeviceId; Name=$pd.FriendlyName; Media=[string]$pd.MediaType; Bus=[string]$pd.BusType;
    Size=$pd.Size; Health=[string]$pd.HealthStatus; Firmware=$pd.FirmwareVersion;
    Temp=$r.Temperature; Wear=$r.Wear; PowerOn=$r.PowerOnHours;
    ReadErr=$r.ReadErrorsUncorrected; WriteErr=$r.WriteErrorsUncorrected
  }
}); $d
"""


def parse_inventory(raw) -> list[tuple[dict, dict]]:
    """Windows PhysicalDisk rows -> [(parts-without-assessment, extra_metrics)]."""
    out = []
    for d in ensure_list(raw):
        bus = _BUS.get(str(d.get("Bus")), str(d.get("Bus") or UNAVAILABLE))
        media = "NVMe" if bus == "NVMe" else _MEDIA.get(str(d.get("Media")), "Desconhecido")
        size = d.get("Size")
        health = _HEALTH.get(str(d.get("Health")), str(d.get("Health") or ""))
        metrics = {
            "os_health": health if health in ("Healthy", "Warning", "Unhealthy") else None,
            "temperature_c": d.get("Temp"), "percentage_used": d.get("Wear"),
            "power_on_hours": d.get("PowerOn"), "read_errors": d.get("ReadErr"), "write_errors": d.get("WriteErr"),
        }
        parts = {"device": f"PhysicalDrive{d.get('DeviceId', '?')}", "model": winutil.val(d.get("Name")),
                 "media_type": media, "interface": bus, "capacity_gb": round(size / 1e9, 1) if size else None,
                 "metrics": metrics, "source": "Windows Storage"}
        out.append((parts, {}))
    return out


def _linux_inventory() -> list[tuple[dict, dict]]:
    exe = shutil.which("lsblk")
    if not exe:
        return []
    r = winutil.run([exe, "-J", "-b", "-d", "-o", "NAME,MODEL,SIZE,ROTA,TRAN,TYPE"], 10)
    try:
        devs = json.loads(r.stdout).get("blockdevices", [])
    except ValueError:
        return []
    out = []
    for d in devs:
        if d.get("type") != "disk" or str(d.get("name", "")).startswith(("loop", "zram", "ram")):
            continue
        tran = (d.get("tran") or "").lower()
        rota = str(d.get("rota")).lower() in ("1", "true")
        media = "NVMe" if tran == "nvme" or d["name"].startswith("nvme") else "HDD" if rota else "SSD"
        size = int(d["size"]) if d.get("size") else None
        parts = {"device": "/dev/" + d["name"], "model": (d.get("model") or UNAVAILABLE).strip(),
                 "media_type": media, "interface": (tran or "SATA/ATA").upper() if tran != "nvme" else "NVMe",
                 "capacity_gb": round(size / 1e9, 1) if size else None, "metrics": {}, "source": "lsblk"}
        out.append((parts, {}))
    return out


def smartctl_devices() -> list[DiskHealth]:
    exe = shutil.which("smartctl")
    if not exe:
        return []
    scan = winutil.run([exe, "--scan", "--json"], 20)
    try:
        devs = json.loads(scan.stdout).get("devices", [])
    except ValueError:
        return []
    out = []
    for d in devs:
        cmd = [exe, "-a", "--json", d.get("name", "")]
        if d.get("type"):
            cmd += ["-d", d["type"]]
        r = winutil.run(cmd, 40)
        try:
            js = json.loads(r.stdout)   # smartctl exit codes are bit flags; JSON is still valid
        except ValueError:
            continue
        out.append(_parts_from_smartctl(js))
    return out


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def collect() -> list[DiskHealth]:
    inventory = parse_inventory(winutil.ps_json(STORAGE_PS, 60)) if IS_WINDOWS else _linux_inventory()
    smart_parts = smartctl_devices()
    results: list[DiskHealth] = []
    used: set[int] = set()
    for parts, _ in inventory:
        match = None
        for i, sp in enumerate(smart_parts):
            a, b = _norm(parts["model"]), _norm(sp["model"])
            if i not in used and a and b and (a in b or b in a):
                match = sp
                used.add(i)
                break
        if match:
            extra = {k: v for k, v in parts["metrics"].items() if k in ("os_health",)}
            match = dict(match, capacity_gb=match["capacity_gb"] or parts["capacity_gb"])
            results.append(_build(match, extra))
        else:
            results.append(_build(parts))
    for i, sp in enumerate(smart_parts):
        if i not in used:
            results.append(_build(sp))
    if smart_parts == [] and shutil.which("smartctl") is None:
        for d in results:
            if d.status == UNKNOWN:
                d.note = NO_DATA_NOTE
    elif not privilege.is_admin() and not smart_parts and shutil.which("smartctl"):
        for d in results:
            if d.status == UNKNOWN:
                d.note = "smartctl não retornou dados. Execute o Observer como administrador."
    return results


def issues_for(disks: list["DiskHealth"]) -> list:
    """Convert per-disk reasons into report Issues (evidence-based, conservative wording)."""
    from .issues import Issue
    out = []
    for d in disks:
        label = f"{d.model} ({d.media_type}, {d.capacity_gb or '?'} GB)"
        for r in d.reasons:
            if r.severity == "info":
                out.append(Issue("Armazenamento", "info", label, r.text, "", d.source))
            else:
                sev = "high" if r.severity == "critical" else "medium"
                out.append(Issue("Armazenamento", sev, f"{label}: {STATUS_LABEL[d.status]}", r.text,
                                 "Faça backup dos dados importantes e execute o diagnóstico do fabricante.",
                                 f"fonte: {d.source}"))
    return out
