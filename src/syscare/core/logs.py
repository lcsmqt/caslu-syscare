"""System log reader: Windows Event Log (wevtutil) or Linux journalctl."""
from __future__ import annotations

import platform
import shutil
import subprocess

IS_WINDOWS = platform.system() == "Windows"


def recent_errors(limit: int = 100) -> str:
    try:
        if IS_WINDOWS:
            cmd = ["wevtutil", "qe", "System", f"/c:{limit}", "/rd:true", "/f:text",
                   "/q:*[System[(Level=1 or Level=2)]]"]
        elif shutil.which("journalctl"):
            cmd = ["journalctl", "-p", "err", "-n", str(limit), "--no-pager"]
        else:
            return "Nenhum leitor de logs disponível (journalctl/wevtutil)."
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (r.stdout or r.stderr).strip() or "Nenhum erro recente encontrado."
    except (OSError, subprocess.SubprocessError) as e:
        return f"Não foi possível ler os logs: {e}"
