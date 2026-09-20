"""Windows Update diagnostics (read-only). Uses official Windows APIs only; no bypass mechanisms."""
from __future__ import annotations

import datetime as dt
import logging

from . import winutil
from .issues import Issue
from .winutil import IS_WINDOWS, UNAVAILABLE, ensure_list

log = logging.getLogger("syscare.winupdate")

STATUS_PS = r"""
$r = (New-Object -ComObject Microsoft.Update.AutoUpdate).Results
$d = { param($x) if ($x -and $x.Year -gt 2000) { $x.ToString('yyyy-MM-dd') } else { $null } }
[pscustomobject]@{
  LastSearch = (& $d $r.LastSearchSuccessDate)
  LastInstall = (& $d $r.LastInstallationSuccessDate)
}
"""
PENDING_PS = r"""
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0")
@($r.Updates | ForEach-Object { [pscustomobject]@{ Title=$_.Title; Severity=[string]$_.MsrcSeverity; Reboot=[bool]$_.RebootRequired } })
"""
ERRORS_PS = """
@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WindowsUpdateClient/Operational';Level=2;
  StartTime=(Get-Date).AddDays(-30)} -MaxEvents 20 -ErrorAction SilentlyContinue |
  Select-Object @{n='Time';e={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm')}},Id,
  @{n='Message';e={ if ($_.Message) { $_.Message.Substring(0,[Math]::Min(200,$_.Message.Length)) } }})
"""

_REBOOT_KEYS = [
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
     "Windows Update"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
     "Manutenção de componentes"),
]


def _key_exists(hive: str, path: str) -> bool:
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(getattr(winreg, hive), path))
        return True
    except OSError:
        return False


def pending_reboot_reasons(flags: dict[str, bool]) -> list[str]:
    return [name for name, on in flags.items() if on]


def os_version() -> dict:
    info = {"Produto": UNAVAILABLE, "Versão": UNAVAILABLE, "Build": UNAVAILABLE}
    if not IS_WINDOWS:
        return info
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            def rd(n):
                try:
                    return str(winreg.QueryValueEx(k, n)[0])
                except OSError:
                    return ""
            build = rd("CurrentBuild")
            product = rd("ProductName")
            if build.isdigit() and int(build) >= 22000 and "Windows 10" in product:
                product = product.replace("Windows 10", "Windows 11")   # registry keeps the old name
            info = {"Produto": product or UNAVAILABLE, "Versão": rd("DisplayVersion") or rd("ReleaseId") or UNAVAILABLE,
                    "Build": f"{build}.{rd('UBR')}" if build else UNAVAILABLE}
    except OSError:
        pass
    return info


def days_since(date_str: str | None, today: dt.date | None = None) -> int | None:
    try:
        return ((today or dt.date.today()) - dt.date.fromisoformat(str(date_str)[:10])).days
    except (TypeError, ValueError):
        return None


def assess(st: dict, today: dt.date | None = None) -> list[Issue]:
    out: list[Issue] = []
    if st.get("reboot_reasons"):
        out.append(Issue("Windows Update", "medium", "Reinicialização pendente",
                         "O Windows aguarda reiniciar para concluir alterações/atualizações.",
                         "Salve seu trabalho e reinicie o computador.", "; ".join(st["reboot_reasons"])))
    d = days_since(st.get("last_install"), today)
    if d is not None and d > 90:
        out.append(Issue("Windows Update", "high" if d > 180 else "medium",
                         f"Última atualização instalada há {d} dias",
                         "Atualizações contêm correções de segurança e estabilidade.",
                         "Abra o Windows Update e verifique atualizações pendentes.", f"última instalação: {st['last_install']}"))
    errs = st.get("errors", [])
    if len(errs) >= 3:
        out.append(Issue("Windows Update", "low", f"{len(errs)} erros do Windows Update nos últimos 30 dias",
                         "Falhas repetidas podem indicar componentes corrompidos ou falta de espaço/conectividade.",
                         "Use a solução de problemas do Windows Update; se persistir, DISM RestoreHealth e SFC em Reparo.",
                         f"último erro: {errs[0].get('Time', '?')}"))
    return out


def collect(check_pending: bool = False) -> dict:
    """Fast by default. `check_pending=True` queries Microsoft (needs internet, can take a minute)."""
    st: dict = {"version": os_version(), "last_search": None, "last_install": None, "reboot_reasons": [],
                "errors": [], "pending": None, "message": ""}
    if not IS_WINDOWS:
        st["message"] = "Diagnóstico do Windows Update disponível apenas no Windows."
        return st
    raw = winutil.ps_json(STATUS_PS, 30)
    if isinstance(raw, dict):
        st["last_search"], st["last_install"] = raw.get("LastSearch"), raw.get("LastInstall")
    st["reboot_reasons"] = pending_reboot_reasons({n: _key_exists(h, p) for h, p, n in _REBOOT_KEYS})
    st["errors"] = ensure_list(winutil.ps_json(ERRORS_PS, 30))
    if check_pending:
        p = winutil.ps_json(PENDING_PS, 180)
        st["pending"] = ensure_list(p) if p is not None else None
        if p is None:
            st["message"] = "Não foi possível consultar atualizações pendentes (sem internet ou serviço indisponível)."
    st["issues"] = assess(st)
    return st
