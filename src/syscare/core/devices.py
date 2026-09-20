"""Drivers and Device Health (Plug and Play).

Reports driver versions/dates and Device Manager problem codes with plain-language explanations.
Never downloads drivers: use Windows Update or the official manufacturer site.
"""
from __future__ import annotations

import datetime as dt
import logging

from . import config, winutil
from .issues import Issue
from .winutil import IS_WINDOWS, UNAVAILABLE, ensure_list, val

log = logging.getLogger("syscare.devices")

DEVICES_PS = (
    "[pscustomobject]@{"
    "Devices=@(Get-CimInstance Win32_PnPEntity | Select-Object Name,PNPClass,Manufacturer,Status,"
    "ConfigManagerErrorCode,PNPDeviceID);"
    "Drivers=@(Get-CimInstance Win32_PnPSignedDriver | Select-Object DeviceName,Manufacturer,DriverVersion,"
    "@{n='DriverDate';e={if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')}}},DeviceClass,IsSigned)}"
)

# Device Manager problem codes (CM_PROB_*): code -> explanation (pt-BR)
PROBLEM_CODES = {
    1: "O dispositivo não está configurado corretamente.",
    3: "O driver pode estar corrompido ou o sistema está com pouca memória.",
    10: "O dispositivo não pode iniciar. Atualize ou reinstale o driver.",
    12: "Recursos livres insuficientes para o dispositivo (conflito de recursos).",
    14: "O dispositivo só funcionará depois de reiniciar o computador.",
    16: "O Windows não consegue identificar todos os recursos do dispositivo.",
    18: "Reinstale os drivers deste dispositivo.",
    19: "Configuração do registro incompleta ou inválida.",
    21: "O Windows está removendo este dispositivo.",
    22: "O dispositivo está desativado.",
    24: "O dispositivo não está presente, não funciona corretamente ou faltam drivers.",
    28: "Os drivers deste dispositivo não estão instalados.",
    29: "O dispositivo foi desativado pelo firmware (BIOS/UEFI).",
    31: "O dispositivo não está funcionando corretamente: o Windows não consegue carregar o driver.",
    32: "O serviço/driver deste dispositivo foi desativado.",
    33: "O Windows não consegue determinar os recursos necessários.",
    34: "O dispositivo requer configuração manual.",
    35: "O firmware do computador não tem informações suficientes para configurar o dispositivo.",
    36: "O dispositivo está solicitando uma interrupção PCI, mas está configurado para ISA (conflito de IRQ).",
    37: "O Windows não conseguiu inicializar o driver deste dispositivo.",
    38: "O Windows não consegue carregar o driver porque uma instância anterior ainda está na memória.",
    39: "O driver está corrompido ou ausente.",
    40: "Informações de serviço ausentes no registro.",
    41: "O driver foi carregado, mas o dispositivo de hardware não foi encontrado.",
    42: "Dispositivo duplicado detectado.",
    43: "O Windows parou este dispositivo porque ele reportou problemas.",
    44: "Um aplicativo ou serviço encerrou este dispositivo.",
    45: "O dispositivo não está conectado ao computador no momento.",
    46: "O Windows não pode acessar o dispositivo (sistema em desligamento).",
    47: "O dispositivo foi preparado para remoção segura.",
    48: "O software deste dispositivo foi bloqueado por problemas conhecidos de compatibilidade.",
    49: "O registro do sistema excedeu o tamanho máximo.",
    50: "O Windows não consegue aplicar todas as propriedades do dispositivo.",
    51: "O dispositivo está aguardando outro dispositivo ou serviço.",
    52: "O Windows não consegue verificar a assinatura digital dos drivers.",
}

_CATEGORY = {
    "usb": "USB", "media": "Áudio", "audioendpoint": "Áudio", "net": "Rede", "bluetooth": "Bluetooth",
    "display": "Vídeo", "diskdrive": "Armazenamento", "scsiadapter": "Armazenamento", "hdc": "Armazenamento",
    "storagevolume": "Armazenamento", "keyboard": "Teclado/Mouse", "mouse": "Teclado/Mouse",
    "hidclass": "Teclado/Mouse", "camera": "Câmera", "image": "Câmera", "printer": "Impressora",
}

MANUFACTURER_SUPPORT = {
    "dell": "https://www.dell.com/support", "hp": "https://support.hp.com",
    "hewlett": "https://support.hp.com", "lenovo": "https://support.lenovo.com",
    "asus": "https://www.asus.com/support", "acer": "https://www.acer.com/support",
    "msi": "https://www.msi.com/support", "gigabyte": "https://www.gigabyte.com/Support",
    "samsung": "https://www.samsung.com/br/support",
}


def support_url(manufacturer: str) -> str | None:
    m = (manufacturer or "").lower()
    return next((u for k, u in MANUFACTURER_SUPPORT.items() if k in m), None)


def category(pnp_class: str | None) -> str:
    return _CATEGORY.get((pnp_class or "").lower(), "Outros")


def explain(code) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return ""
    return PROBLEM_CODES.get(c, f"Código de problema {c} (consulte a documentação da Microsoft).") if c else ""


def parse_devices(raw) -> list[dict]:
    out = []
    for d in ensure_list(raw):
        code = d.get("ConfigManagerErrorCode")
        code = int(code) if code not in (None, "") else 0
        name = d.get("Name")
        cls = d.get("PNPClass")
        if code == 22:
            state = "Desativado"
        elif code == 28:
            state = "Sem driver"
        elif code:
            state = "Erro"
        elif not name or str(cls or "").lower() in ("unknown", ""):
            state = "Desconhecido"
        else:
            state = "OK"
        out.append({"name": val(name, "Dispositivo desconhecido"), "class": val(cls), "category": category(cls),
                    "manufacturer": val(d.get("Manufacturer")), "state": state, "code": code,
                    "explanation": explain(code) if code else
                    ("Dispositivo sem nome/classe: pode faltar driver." if state == "Desconhecido" else ""),
                    "id": val(d.get("PNPDeviceID"))})
    return out


def _age_years(date_str: str | None, today: dt.date | None = None) -> float | None:
    try:
        d = dt.date.fromisoformat(str(date_str)[:10])
    except (TypeError, ValueError):
        return None
    return ((today or dt.date.today()) - d).days / 365.25


def parse_drivers(raw, today: dt.date | None = None) -> list[dict]:
    limit = config.threshold("driver_old_years")
    out = []
    for d in ensure_list(raw):
        if not d.get("DeviceName"):
            continue
        manuf = val(d.get("Manufacturer"))
        age = _age_years(d.get("DriverDate"), today)
        # Microsoft inbox drivers carry very old dates by design: never flag them.
        old = bool(age and age >= limit and "microsoft" not in manuf.lower() and "windows" not in manuf.lower())
        out.append({"device": d["DeviceName"], "manufacturer": manuf, "version": val(d.get("DriverVersion")),
                    "date": val(d.get("DriverDate")), "class": val(d.get("DeviceClass")),
                    "signed": d.get("IsSigned"), "old": old,
                    "age_years": round(age, 1) if age is not None else None})
    return sorted(out, key=lambda x: x["device"].lower())


def assess(devices: list[dict], drivers: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    errs = [d for d in devices if d["state"] in ("Erro", "Sem driver")]
    dis = [d for d in devices if d["state"] == "Desativado"]
    unk = [d for d in devices if d["state"] == "Desconhecido"]
    for d in errs:
        issues.append(Issue("Dispositivos", "medium", f"{d['name']}: código de erro {d['code']}", d["explanation"],
                            "Atualize o driver via Windows Update ou pelo site do fabricante; "
                            "se persistir, reinstale o dispositivo.", f"ConfigManagerErrorCode={d['code']}"))
    if unk:
        issues.append(Issue("Dispositivos", "low", f"{len(unk)} dispositivo(s) desconhecido(s)",
                            "Dispositivos sem nome/classe geralmente indicam driver ausente.",
                            "Execute o Windows Update e instale os drivers do fabricante do equipamento.",
                            ", ".join(d["id"][:40] for d in unk[:3])))
    if dis:
        issues.append(Issue("Dispositivos", "info", f"{len(dis)} dispositivo(s) desativado(s)",
                            "Pode ser intencional. Verifique se algum deveria estar ativo.", "",
                            ", ".join(d["name"] for d in dis[:5])))
    old = [d for d in drivers if d["old"]]
    if old:
        issues.append(Issue("Drivers", "info", f"{len(old)} driver(s) antigo(s) de terceiros",
                            "Data antiga não significa problema. Só atualize se houver falha ou recomendação "
                            "do fabricante.", "Use o Windows Update ou o site oficial do fabricante.",
                            ", ".join(d["device"] for d in old[:5])))
    return issues


def collect() -> dict:
    if not IS_WINDOWS:
        return {"devices": [], "drivers": [], "issues": [],
                "message": "Diagnóstico de dispositivos e drivers disponível apenas no Windows."}
    raw = winutil.ps_json(DEVICES_PS, 120)
    if not isinstance(raw, dict):
        return {"devices": [], "drivers": [], "issues": [],
                "message": "Não foi possível consultar dispositivos e drivers (detalhes no log técnico)."}
    devices, drivers = parse_devices(raw.get("Devices")), parse_drivers(raw.get("Drivers"))
    return {"devices": devices, "drivers": drivers, "issues": assess(devices, drivers), "message": ""}
