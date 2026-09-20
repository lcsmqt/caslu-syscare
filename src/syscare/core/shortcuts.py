"""Whitelisted shortcuts to legitimate Windows utilities (Toolbox)."""
from __future__ import annotations

import logging
import os
import platform

log = logging.getLogger("syscare.shortcuts")
IS_WINDOWS = platform.system() == "Windows"

# id -> (label, target, needs_admin_hint)
LAUNCHERS: dict[str, tuple[str, str, bool]] = {
    "taskmgr": ("Gerenciador de Tarefas", "taskmgr", False),
    "devmgmt": ("Gerenciador de Dispositivos", "devmgmt.msc", False),
    "diskmgmt": ("Gerenciamento de Disco", "diskmgmt.msc", True),
    "eventvwr": ("Visualizador de Eventos", "eventvwr.msc", False),
    "services": ("Serviços", "services.msc", False),
    "regedit": ("Editor do Registro", "regedit", True),
    "msinfo32": ("Informações do Sistema", "msinfo32", False),
    "control": ("Painel de Controle", "control", False),
    "settings": ("Configurações do Windows", "ms-settings:", False),
    "winupdate": ("Windows Update", "ms-settings:windowsupdate", False),
    "security": ("Segurança do Windows", "windowsdefender:", False),
    "cmd": ("Prompt de Comando", "cmd", False),
    "powershell": ("PowerShell", "powershell", False),
    "ncpa": ("Conexões de Rede", "ncpa.cpl", False),
    "sysdm": ("Propriedades do Sistema", "sysdm.cpl", False),
    "resmon": ("Monitor de Recursos", "resmon", False),
}


def launch(key: str) -> tuple[bool, str]:
    if key not in LAUNCHERS:
        return False, "Atalho desconhecido."
    label, target, _ = LAUNCHERS[key]
    if not IS_WINDOWS:
        return False, f"{label} só está disponível no Windows."
    try:
        os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606 - fixed whitelist only
        return True, f"{label} aberto."
    except OSError as e:
        log.warning("launch %s failed: %s", key, e)
        return False, f"Não foi possível abrir {label}."
