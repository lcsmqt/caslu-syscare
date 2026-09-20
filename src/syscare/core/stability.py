"""Stability diagnostics: unexpected shutdowns, bugchecks (BSOD), app crashes, service failures.

Language is deliberately cautious: without minidump analysis (WinDbg) a root cause cannot be
proven, so findings say 'possível componente relacionado' and list common causes.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import winutil
from .issues import Issue
from .winutil import IS_WINDOWS, UNAVAILABLE, ensure_list

log = logging.getLogger("syscare.stability")

EVENTS_PS = """
$since = (Get-Date).AddDays(-{days})
$f = {{ param($h) @(Get-WinEvent -FilterHashtable $h -MaxEvents 300 -ErrorAction SilentlyContinue |
  Select-Object @{{n='Time';e={{$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}}}},Id,ProviderName,
  @{{n='Message';e={{ if ($_.Message) {{ $_.Message.Substring(0,[Math]::Min(600,$_.Message.Length)) }} }}}}) }}
[pscustomobject]@{{
  System = (& $f @{{LogName='System';Id=41,6008,1001,7031,7034;StartTime=$since}});
  App = (& $f @{{LogName='Application';Id=1000;StartTime=$since}})
}}
"""

BUGCHECK_NAMES = {
    0x0A: "IRQL_NOT_LESS_OR_EQUAL", 0x1A: "MEMORY_MANAGEMENT", 0x1E: "KMODE_EXCEPTION_NOT_HANDLED",
    0x3B: "SYSTEM_SERVICE_EXCEPTION", 0x50: "PAGE_FAULT_IN_NONPAGED_AREA",
    0x7E: "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", 0x7F: "UNEXPECTED_KERNEL_MODE_TRAP",
    0x9F: "DRIVER_POWER_STATE_FAILURE", 0xC2: "BAD_POOL_CALLER", 0xD1: "DRIVER_IRQL_NOT_LESS_OR_EQUAL",
    0xEF: "CRITICAL_PROCESS_DIED", 0x116: "VIDEO_TDR_FAILURE", 0x117: "VIDEO_TDR_TIMEOUT_DETECTED",
    0x124: "WHEA_UNCORRECTABLE_ERROR", 0x133: "DPC_WATCHDOG_VIOLATION", 0x139: "KERNEL_SECURITY_CHECK_FAILURE",
    0x154: "UNEXPECTED_STORE_EXCEPTION",
}
_HEX = re.compile(r"0x[0-9a-fA-F]{4,8}")
_MODULE = re.compile(r"(?:Faulting module name|Nome do m[óo]dulo com falha):\s*([^,\s]+)", re.I)
_APP = re.compile(r"(?:Faulting application name|Nome do aplicativo com falha):\s*([^,\s]+)", re.I)
_SERVICE = re.compile(r"(?:The\s+(.+?)\s+service (?:terminated|entered)|O servi[çc]o\s+(.+?)\s+(?:foi encerrado|terminou))",
                      re.I)


def parse_bugcheck(msg: str) -> tuple[str, str]:
    """Return (code_hex, name) from a bugcheck event message; ('', '') when not found."""
    m = _HEX.search(msg or "")
    if not m:
        return "", ""
    code = int(m.group(0), 16)
    return f"0x{code:08X}", BUGCHECK_NAMES.get(code, "código não catalogado")


def parse_events(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {"unexpected_shutdowns": [], "bugchecks": [], "app_crashes": [], "service_failures": []}
    for e in ensure_list(raw.get("System")):
        eid, msg, prov = e.get("Id"), e.get("Message") or "", str(e.get("ProviderName") or "")
        if eid == 1001:
            if "SystemErrorReporting" not in prov and "bugcheck" not in msg.lower() and "verificação de erro" not in msg.lower():
                continue
            code, name = parse_bugcheck(msg)
            out["bugchecks"].append({"time": e.get("Time"), "code": code or UNAVAILABLE, "name": name or UNAVAILABLE})
        elif eid in (41, 6008):
            out["unexpected_shutdowns"].append({"time": e.get("Time"), "id": eid})
        elif eid in (7031, 7034):
            m = _SERVICE.search(msg)
            svc = next((g for g in (m.groups() if m else ()) if g), msg[:60] or UNAVAILABLE)
            out["service_failures"].append({"time": e.get("Time"), "service": svc.strip()})
    for e in ensure_list(raw.get("App")):
        msg = e.get("Message") or ""
        a, m = _APP.search(msg), _MODULE.search(msg)
        out["app_crashes"].append({"time": e.get("Time"), "app": a.group(1) if a else UNAVAILABLE,
                                   "module": m.group(1) if m else UNAVAILABLE})
    return out


def list_minidumps() -> list[dict]:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Minidump"
    out = []
    try:
        for f in sorted(root.glob("*.dmp"), reverse=True)[:20]:
            st = f.stat()
            out.append({"file": f.name, "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "size_kb": round(st.st_size / 1024)})
    except OSError:
        pass
    return out


def assess(rep: dict) -> list[Issue]:
    out: list[Issue] = []
    days = rep.get("days", 30)
    b = rep["bugchecks"]
    if b:
        codes = ", ".join(sorted({f"{x['code']} ({x['name']})" for x in b}))
        out.append(Issue("Estabilidade", "high" if len(b) >= 3 else "medium",
                         f"{len(b)} tela(s) azul(is) (bugcheck) nos últimos {days} dias",
                         "Causas comuns: drivers (vídeo, rede, armazenamento), memória RAM, disco ou superaquecimento. "
                         "Sem análise do minidump não é possível apontar a causa exata.",
                         "Atualize drivers pelo Windows Update/fabricante, rode o diagnóstico de memória do Windows e "
                         "verifique a saúde do disco. Para a causa exata, analise o minidump com o WinDbg.",
                         f"códigos: {codes}"))
    u = [x for x in rep["unexpected_shutdowns"]]
    if len(u) >= 2:
        out.append(Issue("Estabilidade", "medium", f"{len(u)} desligamentos inesperados nos últimos {days} dias",
                         "Possíveis causas: falta de energia, fonte/bateria, superaquecimento, driver ou falha de hardware.",
                         "Verifique temperaturas, fonte/bateria e o Visualizador de Eventos.",
                         f"eventos 41/6008 em {len(u)} ocasiões"))
    crashes = Counter((c["app"], c["module"]) for c in rep["app_crashes"])
    for (app, mod), n in crashes.items():
        if n >= 3:
            out.append(Issue("Estabilidade", "low", f"{app} travou {n} vezes",
                             f"Possível componente relacionado: {mod}. Isso não prova a causa, apenas o módulo "
                             "reportado nas falhas.", "Atualize ou reinstale o aplicativo e verifique se há atualizações do Windows.",
                             f"módulo com falha: {mod}"))
    svc = Counter(s["service"] for s in rep["service_failures"])
    for name, n in svc.items():
        if n >= 3:
            out.append(Issue("Estabilidade", "low", f"Serviço '{name}' falhou {n} vezes",
                             "Falhas repetidas de serviço podem indicar corrupção, conflito ou dependência ausente.",
                             "Verifique o Visualizador de Eventos e considere SFC/DISM em Reparo do Windows.",
                             f"{n} eventos 7031/7034"))
    return out


def collect(days: int = 30) -> dict:
    empty = {"days": days, "unexpected_shutdowns": [], "bugchecks": [], "app_crashes": [], "service_failures": [],
             "minidumps": list_minidumps(), "issues": [], "message": ""}
    if not IS_WINDOWS:
        empty["message"] = "Diagnóstico de estabilidade disponível apenas no Windows."
        return empty
    raw = winutil.ps_json(EVENTS_PS.format(days=int(days)), 90)
    if not isinstance(raw, dict):
        empty["message"] = "Não foi possível ler o Visualizador de Eventos (detalhes no log técnico)."
        return empty
    rep = parse_events(raw)
    rep.update({"days": days, "minidumps": empty["minidumps"], "message": ""})
    rep["issues"] = assess(rep)
    return rep
