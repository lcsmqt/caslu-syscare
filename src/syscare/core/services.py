"""Windows Services manager. Conservative by design: no 'disable everything useless' feature.

Only third-party services can have their startup type changed, always with confirmation, admin
elevation and a recorded previous state for undo. Critical/Windows services are read-only.
"""
from __future__ import annotations

import json
import logging
import re

from . import knowledge, privilege, winutil
from .config import data_dir
from .safeaction import ActionResult, Preview, Risk, SafeAction

log = logging.getLogger("syscare.services")

CRITICAL = {
    "rpcss", "dcomlaunch", "rpceptmapper", "lsm", "eventlog", "winmgmt", "plugplay", "power", "profsvc",
    "samss", "cryptsvc", "bfe", "mpssvc", "windefend", "wdnissvc", "securityhealthservice", "wscsvc", "sense",
    "dhcp", "dnscache", "nsi", "lanmanworkstation", "lanmanserver", "trustedinstaller", "gpsvc", "schedule",
    "sens", "systemeventsbroker", "timebrokersvc", "themes", "audiosrv", "audioendpointbuilder", "keyiso",
    "sppsvc", "wuauserv", "bits", "usosvc", "appinfo", "staterepository", "userdatasvc", "cdpsvc", "netprofm",
    "nlasvc", "wlansvc", "bthserv", "spooler", "vss", "wersvc", "tokenbroker", "camsvc", "brokerinfrastructure",
}
CRITICAL_LABEL, WINDOWS_LABEL, THIRD_LABEL, REVIEW_LABEL = "Crítico do sistema", "Windows", "Terceiros", "Revisar"
CHANGEABLE = {THIRD_LABEL, REVIEW_LABEL}

_WIN_PATH = re.compile(r"(^|[\\\"'])(%systemroot%|%windir%|[a-z]:\\windows)\\", re.I)
_START = {"automatic": "auto", "manual": "demand", "disabled": "disabled"}
_TYPE_LABEL = {"auto": "Automático", "demand": "Manual", "disabled": "Desativado"}


def classify(name: str, display: str, binpath: str, start_type: str) -> tuple[str, str]:
    """Return (label, reason). Classifies only when the evidence is reliable."""
    if name.lower() in CRITICAL:
        return CRITICAL_LABEL, "Serviço essencial do Windows (lista de proteção)."
    if binpath and _WIN_PATH.search(binpath):
        return WINDOWS_LABEL, "Executável dentro da pasta do Windows."
    if not binpath:
        return REVIEW_LABEL, "Caminho do executável indisponível; não é seguro classificar."
    rule = knowledge.match_rule(name) or knowledge.match_rule(display)
    if rule and start_type == "automatic":
        return REVIEW_LABEL, rule.reason
    return THIRD_LABEL, "Executável fora da pasta do Windows."


def parse_service(d: dict) -> dict:
    name = d.get("name", "")
    label, reason = classify(name, d.get("display_name", ""), d.get("binpath", "") or "", d.get("start_type", ""))
    return {"name": name, "display_name": winutil.val(d.get("display_name")), "status": winutil.val(d.get("status")),
            "start_type": winutil.val(d.get("start_type")), "binpath": winutil.val(d.get("binpath")),
            "description": winutil.val((d.get("description") or "")[:200]), "class": label, "reason": reason,
            "changeable": label in CHANGEABLE}


def list_services() -> list[dict]:
    if not winutil.IS_WINDOWS:
        return []
    import psutil
    out = []
    try:
        for s in psutil.win_service_iter():
            try:
                out.append(parse_service(s.as_dict()))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        log.exception("win_service_iter failed")
    return sorted(out, key=lambda x: x["display_name"].lower())


# ------------------------------------------------------------------ undo store
def _undo_path():
    return data_dir() / "services_undo.json"


def _load_undo() -> list[dict]:
    try:
        return json.loads(_undo_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _record_undo(entry: dict) -> None:
    log_ = _load_undo()
    log_.append(entry)
    _undo_path().write_text(json.dumps(log_, indent=2, ensure_ascii=False), encoding="utf-8")


def _sc_config(name: str, start: str) -> winutil.CmdResult:
    cmd = ["sc", "config", name, "start=", start]
    return winutil.run(cmd) if privilege.is_admin() else privilege.run_elevated(cmd, 60)


def current_start_type(name: str) -> str | None:
    if not winutil.IS_WINDOWS:
        return None
    try:
        import psutil
        return _START.get(psutil.win_service_get(name).start_type())
    except Exception:  # noqa: BLE001
        return None


class ServiceStartTypeAction(SafeAction):
    can_elevate = True

    def __init__(self, svc: dict, new_type: str):
        self.svc, self.new = svc, new_type            # new_type: auto | demand | disabled
        self.name = f"service:{svc['name']}"

    def scan(self):
        return dict(self.svc, prev=_START.get(self.svc["start_type"]))

    def preview(self, analysis) -> Preview:
        s = self.svc
        block = "" if s["changeable"] else \
            f"\n\nBLOQUEADO: serviços da categoria '{s['class']}' não podem ser alterados pelo Observer."
        risk = Risk.LOW if self.new == "demand" else Risk.MEDIUM
        return Preview(
            title=f"Alterar inicialização de {s['display_name']}",
            description=(f"Serviço: {s['name']} ({s['class']})\nDe: {s['start_type']}  →  Para: {_TYPE_LABEL[self.new]}"
                         f"\n{s['reason']}{block}"),
            risk=risk, needs_admin=True, reversible=True,
            impact="O programa associado pode deixar de funcionar corretamente se depender deste serviço.",
            items=[f"sc config {s['name']} start= {self.new}"])

    def audit_target(self, analysis) -> str:
        return self.svc["name"]

    def previous_state(self, analysis):
        return {"start_type": self.svc["start_type"]}

    def execute(self, analysis) -> ActionResult:
        if not self.svc["changeable"]:
            return ActionResult("blocked", f"Serviços '{self.svc['class']}' são protegidos e não podem ser alterados.")
        prev = _START.get(self.svc["start_type"])
        if prev is None:
            return ActionResult("failed", "Tipo de inicialização atual desconhecido; alteração cancelada por segurança.")
        r = _sc_config(self.svc["name"], self.new)
        if not r.ok:
            return ActionResult("failed", r.error or "O comando sc falhou (verifique permissões de administrador).", r.text)
        _record_undo({"name": self.svc["name"], "previous": prev, "new": self.new, "undone": False})
        return ActionResult("success", f"Inicialização de {self.svc['display_name']} alterada para {_TYPE_LABEL[self.new]}.",
                            r.text)

    def verify(self, analysis, result):
        if result.status != "success":
            return None
        return current_start_type(self.svc["name"]) == self.new


def undo_last() -> str:
    log_ = _load_undo()
    for i in range(len(log_) - 1, -1, -1):
        e = log_[i]
        if e.get("undone"):
            continue
        r = _sc_config(e["name"], e["previous"])
        if not r.ok:
            return f"Não foi possível desfazer {e['name']}: {r.error or 'falha do comando sc'}."
        log_[i]["undone"] = True
        _undo_path().write_text(json.dumps(log_, indent=2, ensure_ascii=False), encoding="utf-8")
        from . import audit
        audit.record("undo_service_change", "success", e["name"], {"start_type": e["new"]}, {"start_type": e["previous"]})
        return f"Restaurado: {e['name']} → {_TYPE_LABEL.get(e['previous'], e['previous'])}."
    return "Nada para desfazer."
