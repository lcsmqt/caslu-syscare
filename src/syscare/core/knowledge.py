"""Knowledge base: which processes are protected and which are commonly unnecessary.

Edit this file to teach SysCare new programs. Patterns are case-insensitive
regular expressions matched against the process name (without .exe).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Processes that must NEVER be flagged or terminated.
PROTECTED = {
    # Windows
    "system", "system idle process", "registry", "smss", "csrss", "wininit", "winlogon",
    "services", "lsass", "svchost", "explorer", "dwm", "fontdrvhost", "sihost",
    "taskhostw", "ctfmon", "runtimebroker", "searchhost", "startmenuexperiencehost",
    "shellexperiencehost", "audiodg", "spoolsv", "msmpeng", "securityhealthservice",
    "memory compression", "conhost", "dllhost", "wudfhost", "lsaiso", "python", "pythonw",
    # Linux
    "systemd", "init", "kthreadd", "dbus-daemon", "dbus-broker", "networkmanager",
    "sshd", "xorg", "xwayland", "gnome-shell", "kwin_x11", "kwin_wayland", "plasmashell",
    "pipewire", "pulseaudio", "wireplumber", "login", "agetty", "cron", "rsyslogd",
    "systemd-journald", "systemd-logind", "systemd-udevd", "systemd-resolved",
}


@dataclass(frozen=True)
class Rule:
    pattern: str
    category: str
    reason: str
    risk: str = "safe"  # safe | caution


RULES: list[Rule] = [
    # Auto-updaters / telemetry
    Rule(r"^(googleupdate|googlecrashhandler.*)$", "Atualizador", "Atualizador em segundo plano do Google; o navegador se atualiza sozinho."),
    Rule(r"^(adobeupdateservice|adobearm|adobegcclient|agsservice|armsvc|ccxprocess)$", "Atualizador", "Serviços Adobe de atualização/licença rodando o tempo todo."),
    Rule(r"^(jusched|javaupdater)$", "Atualizador", "Atualizador do Java."),
    Rule(r"^(microsoftedgeupdate|msedgeupdate)$", "Atualizador", "Atualizador do Edge em segundo plano."),
    Rule(r"^(compattelrunner|diagtrack)$", "Telemetria", "Coleta de telemetria do Windows; consome CPU/disco.", "caution"),
    # Launchers / chat clients that auto-start
    Rule(r"^(steamwebhelper|steam)$", "Launcher de jogos", "Launcher de jogos aberto sem uso ativo."),
    Rule(r"^(epicgameslauncher|epicwebhelper|origin|eadesktop|ubisoftconnect|upc|galaxyclient|battle\.net|riotclientservices|riotclient.*)$", "Launcher de jogos", "Launcher de jogos aberto sem uso ativo."),
    Rule(r"^(discord|discordptb|update)$", "Comunicação", "Cliente de chat que costuma iniciar com o sistema e usa bastante RAM."),
    Rule(r"^(spotify|spotifywebhelper)$", "Mídia", "Cliente de música em segundo plano."),
    Rule(r"^(teams|ms-teams|msteams)$", "Comunicação", "Microsoft Teams (clássico) é pesado; feche se não estiver em uso."),
    Rule(r"^(skype|skypehost|skypeapp)$", "Comunicação", "Skype em segundo plano."),
    Rule(r"^(onedrive|dropbox|googledrivefs|gdrive.*|megasync|box)$", "Sincronização", "Sincronização de nuvem contínua (I/O de disco). Mantenha só se usar.", "caution"),
    # Vendor bloat
    Rule(r"^(hpsupportassistant|hpsysinfo|hpsa.*|hp\.?smart.*|hpcommrecovery|hpqwmiex|hptouchpointanalytics.*)$", "Bloatware de fabricante", "Software HP pré-instalado."),
    Rule(r"^(dellsupportassist.*|supportassist.*|dellcommandupdate|dellupdate|dellsystemdetect)$", "Bloatware de fabricante", "Software Dell pré-instalado."),
    Rule(r"^(lenovovantage.*|lenovo.*service|lvtray|imcontroller)$", "Bloatware de fabricante", "Software Lenovo pré-instalado."),
    Rule(r"^(asusoptimization.*|armourycrate.*|asuslinkremote|asussystemanalysis)$", "Bloatware de fabricante", "Software ASUS pré-instalado.", "caution"),
    Rule(r"^(acerjumpstart|acerportal|acerquickaccess)$", "Bloatware de fabricante", "Software Acer pré-instalado."),
    # Toolbars / bundleware / misc
    Rule(r"^(mcafee.*|mcshield|mfemms|mfevtps|norton.*|nsbu|avgui|avgsvc|avastui|avastsvc|ccsvchst)$", "Antivírus terceiro", "Antivírus de terceiros costuma pesar; o Windows Defender é suficiente para uso comum.", "caution"),
    Rule(r"^(ask.*toolbar|babylon.*|conduit.*|searchprotect.*|wajam.*|opencandy.*)$", "Adware/PUP", "Programa potencialmente indesejado (adware/toolbar). Recomenda-se remover."),
    Rule(r"^(cortana|searchapp|yourphone|phoneexperiencehost|gamebar|gamebarftserver|widgets|widgetservice)$", "Recurso opcional do Windows", "Recurso opcional do Windows que pode ser desativado.", "caution"),
    Rule(r"^(itunes.*helper|applemobiledevice.*|ipodservice|applemobiledeviceservice)$", "Apple", "Serviço auxiliar do iTunes/Apple; só necessário ao conectar iPhone.", "caution"),
    Rule(r"^(zoom|zoomit|cptinstall|zoomopener)$", "Comunicação", "Zoom aberto em segundo plano."),
    # Linux desktop extras
    Rule(r"^(tracker-miner-fs.*|tracker-extract.*|baloo_file.*|baloo_file_extractor)$", "Indexador", "Indexador de arquivos; pode consumir CPU/disco em picos.", "caution"),
    Rule(r"^(snapd|snap-store|gnome-software|packagekitd|update-notifier|unattended-upgr.*)$", "Atualizador", "Serviço de atualização/loja em segundo plano.", "caution"),
    Rule(r"^(evolution-.*|geoclue|colord|cups-browsed|avahi-daemon|bluetoothd|modemmanager)$", "Serviço opcional", "Serviço opcional; desative se não usar o recurso correspondente.", "caution"),
]

_COMPILED = [(re.compile(r.pattern, re.I), r) for r in RULES]


def normalize(name: str) -> str:
    n = name.strip().lower()
    return n[:-4] if n.endswith(".exe") else n


def is_protected(name: str) -> bool:
    return normalize(name) in PROTECTED


def match_rule(name: str) -> Rule | None:
    n = normalize(name)
    for rx, rule in _COMPILED:
        if rx.match(n):
            return rule
    return None
