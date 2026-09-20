"""Security Center: Defender, firewall, UAC, Secure Boot, TPM, BitLocker, OS support status.

Read-only diagnostics. Never changes security settings and never replaces antivirus software.
Checks that need administrator rights report 'Indisponível (requer administrador)' instead of guessing.
"""
from __future__ import annotations

import datetime as dt
import logging
import platform

from . import winutil
from .issues import Issue
from .winutil import IS_WINDOWS, UNAVAILABLE, ensure_list

log = logging.getLogger("syscare.security")
NEEDS_ADMIN = "Indisponível (requer administrador)"

SECURITY_PS = r"""
$r = [ordered]@{}
try { $r.Defender = Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,IsTamperProtected,AntivirusSignatureAge } catch { $r.Defender = $null }
try { $r.AntiVirus = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object displayName,productState) } catch { $r.AntiVirus = $null }
try { $r.Firewall = @(Get-NetFirewallProfile | Select-Object Name,@{n='Enabled';e={[string]$_.Enabled}}) } catch { $r.Firewall = $null }
try { $r.Tpm = Get-Tpm | Select-Object TpmPresent,TpmReady,TpmEnabled } catch { $r.Tpm = $null }
try { $r.BitLocker = @(Get-BitLockerVolume | Select-Object MountPoint,@{n='Status';e={[string]$_.VolumeStatus}},@{n='Protection';e={[string]$_.ProtectionStatus}},EncryptionPercentage) } catch { $r.BitLocker = $null }
[pscustomobject]$r
"""

# (build, name, end-of-support date for Home/Pro editions — indicative; Enterprise/LTSC differ)
_SUPPORT = {
    19045: ("Windows 10 22H2", dt.date(2025, 10, 14)),
    22000: ("Windows 11 21H2", dt.date(2023, 10, 10)),
    22621: ("Windows 11 22H2", dt.date(2024, 10, 8)),
    22631: ("Windows 11 23H2", dt.date(2025, 11, 11)),
    26100: ("Windows 11 24H2", dt.date(2026, 10, 13)),
}


def _truthy(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "enabled", "on"):
        return True
    if s in ("false", "0", "disabled", "off"):
        return False
    return None  # e.g. NotConfigured


def decode_product_state(state) -> dict:
    """Decode Security Center productState (estimated; layout is undocumented but stable)."""
    try:
        hx = format(int(state), "06x")
    except (TypeError, ValueError):
        return {"enabled": None, "up_to_date": None}
    rt, sig = hx[2:4], hx[4:6]
    return {"enabled": True if rt in ("10", "11") else False if rt in ("00", "01") else None,
            "up_to_date": True if sig == "00" else False if sig == "10" else None}


def os_support(build: int | None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    if build is None:
        return {"name": UNAVAILABLE, "status": UNAVAILABLE}
    if build in _SUPPORT:
        name, end = _SUPPORT[build]
        st = f"Suporte encerrado em {end:%d/%m/%Y}" if end < today else f"Suporte até {end:%d/%m/%Y}"
        return {"name": name, "status": st, "ended": end < today, "end": end.isoformat()}
    return {"name": f"Build {build}", "status": "Sem informação de suporte para esta build", "ended": None}


def _reg(hive_name: str, path: str, name: str):
    if not IS_WINDOWS:
        return None
    try:
        import winreg
        hive = getattr(winreg, hive_name)
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def windows_build() -> int | None:
    try:
        return int(platform.version().split(".")[2])
    except (IndexError, ValueError):
        return None


def summarize(raw: dict, uac: int | None, secure_boot: int | None, build: int | None) -> dict:
    """Pure: turn raw collector data into a display summary."""
    s: dict = {}
    d = raw.get("Defender")
    if isinstance(d, dict):
        s["Antivírus (Defender)"] = "Ativo" if _truthy(d.get("AntivirusEnabled")) else "Desativado/inativo"
        rt = _truthy(d.get("RealTimeProtectionEnabled"))
        s["Proteção em tempo real"] = "Ativa" if rt else "Desativada" if rt is False else UNAVAILABLE
        age = d.get("AntivirusSignatureAge")
        s["Assinaturas (idade)"] = f"{age} dia(s)" if age is not None else UNAVAILABLE
    else:
        s["Antivírus (Defender)"] = UNAVAILABLE
        s["Proteção em tempo real"] = UNAVAILABLE
    avs = []
    for av in ensure_list(raw.get("AntiVirus")):
        st = decode_product_state(av.get("productState"))
        avs.append({"name": av.get("displayName", UNAVAILABLE), **st})
    s["Produtos antivírus registrados"] = ", ".join(
        f"{a['name']} ({'ativo' if a['enabled'] else 'inativo' if a['enabled'] is False else 'estado desconhecido'})"
        for a in avs) or UNAVAILABLE
    fw = raw.get("Firewall")
    if fw is None:
        s["Firewall"] = UNAVAILABLE
    else:
        s["Firewall"] = "; ".join(
            f"{p.get('Name')}: {'ativo' if _truthy(p.get('Enabled')) else 'DESATIVADO' if _truthy(p.get('Enabled')) is False else 'não configurado'}"
            for p in ensure_list(fw)) or UNAVAILABLE
    s["UAC"] = UNAVAILABLE if uac is None else "Ativo" if uac == 1 else "DESATIVADO"
    s["Secure Boot"] = UNAVAILABLE if secure_boot is None else "Ativo" if secure_boot == 1 else "Desativado"
    t = raw.get("Tpm")
    if isinstance(t, dict):
        s["TPM"] = ("Presente e pronto" if t.get("TpmPresent") and t.get("TpmReady")
                    else "Presente" if t.get("TpmPresent") else "Não detectado")
    else:
        s["TPM"] = NEEDS_ADMIN
    bl = raw.get("BitLocker")
    if bl is None:
        s["BitLocker"] = NEEDS_ADMIN
    else:
        s["BitLocker"] = "; ".join(f"{v.get('MountPoint')}: {v.get('Status')}" for v in ensure_list(bl)) or "Sem volumes"
    sup = os_support(build)
    s["Sistema operacional"] = sup["name"]
    s["Suporte do Windows"] = sup["status"]
    return s


def assess(raw: dict, uac: int | None, secure_boot: int | None, build: int | None,
           portable_device: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    d = raw.get("Defender")
    avs = [decode_product_state(a.get("productState")) | {"name": a.get("displayName")}
           for a in ensure_list(raw.get("AntiVirus"))]
    any_av_on = any(a["enabled"] for a in avs) or (isinstance(d, dict) and _truthy(d.get("AntivirusEnabled")))
    if raw.get("Defender") is not None or raw.get("AntiVirus") is not None:
        if not any_av_on:
            issues.append(Issue("Segurança", "high", "Nenhum antivírus ativo detectado",
                                "Nem o Defender nem produtos registrados no Centro de Segurança parecem ativos.",
                                "Ative o Microsoft Defender ou instale/ative um antivírus confiável.",
                                "AntivirusEnabled=false; produtos ativos: 0"))
        elif isinstance(d, dict) and _truthy(d.get("RealTimeProtectionEnabled")) is False and \
                _truthy(d.get("AntivirusEnabled")):
            issues.append(Issue("Segurança", "high", "Proteção em tempo real desativada",
                                "O antivírus está presente, mas sem proteção em tempo real.",
                                "Reative a proteção em tempo real em Segurança do Windows.",
                                "RealTimeProtectionEnabled=false"))
        age = d.get("AntivirusSignatureAge") if isinstance(d, dict) else None
        if isinstance(age, (int, float)) and age > 7:
            issues.append(Issue("Segurança", "medium", "Assinaturas do antivírus desatualizadas",
                                f"As definições têm {int(age)} dias.", "Execute o Windows Update / atualize as assinaturas.",
                                f"AntivirusSignatureAge={int(age)}"))
    for p in ensure_list(raw.get("Firewall")):
        if _truthy(p.get("Enabled")) is False:
            issues.append(Issue("Segurança", "high", f"Firewall desativado (perfil {p.get('Name')})",
                                "O firewall do Windows está desligado neste perfil de rede.",
                                "Ative o firewall, salvo se houver outro firewall gerenciado.",
                                f"{p.get('Name')}=Disabled"))
    if uac == 0:
        issues.append(Issue("Segurança", "medium", "UAC desativado",
                            "O Controle de Conta de Usuário está desligado.",
                            "Reative o UAC; ele reduz o impacto de software malicioso.", "EnableLUA=0"))
    if portable_device:
        bl = raw.get("BitLocker")
        if bl and all(str(v.get("Protection")).lower() in ("0", "off") for v in ensure_list(bl)):
            issues.append(Issue("Segurança", "medium", "BitLocker desativado em dispositivo portátil",
                                "Se o notebook for perdido/roubado, os dados podem ser lidos.",
                                "Considere ativar a criptografia (BitLocker/Criptografia de dispositivo). "
                                "Guarde a chave de recuperação.", "ProtectionStatus=Off"))
    sup = os_support(build)
    if sup.get("ended"):
        issues.append(Issue("Segurança", "medium", "Versão do Windows fora do período de suporte",
                            f"{sup['name']}: {sup['status']} (datas para edições Home/Pro; confirme com a Microsoft).",
                            "Atualize para uma versão com suporte.", f"build={build}"))
    return issues


def collect(portable_device: bool = False) -> dict:
    if not IS_WINDOWS:
        return {"summary": {"Sistema": "Central de segurança do Windows indisponível neste sistema."},
                "issues": [], "raw": {}}
    raw = winutil.ps_json(SECURITY_PS, 60)
    raw = raw if isinstance(raw, dict) else {}
    uac = _reg("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA")
    sb = _reg("HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\SecureBoot\State", "UEFISecureBootEnabled")
    build = windows_build()
    return {"summary": summarize(raw, uac, sb, build),
            "issues": assess(raw, uac, sb, build, portable_device), "raw": raw}
