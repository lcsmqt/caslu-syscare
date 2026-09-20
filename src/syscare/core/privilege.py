"""Privilege awareness and per-operation elevation (no need to run the whole app elevated)."""
from __future__ import annotations

import json
import os
import platform
import tempfile
import uuid
from pathlib import Path

from . import winutil

IS_WINDOWS = platform.system() == "Windows"
ADMIN_BADGE = "Requer administrador"


def is_admin() -> bool:
    try:
        if IS_WINDOWS:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        return os.geteuid() == 0
    except Exception:  # noqa: BLE001
        return False


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def run_elevated(cmd: list[str], timeout: float = 3600) -> winutil.CmdResult:
    """Run one command elevated via UAC (Windows). Output is captured through a temp file.

    The user sees the standard Windows UAC prompt; declining returns ok=False.
    (needs Windows validation)
    """
    if not IS_WINDOWS:
        return winutil.CmdResult(False, error="Elevação por UAC só existe no Windows.")
    out = Path(tempfile.gettempdir()) / f"syscare_{uuid.uuid4().hex}.log"
    inner = ("& " + " ".join(_ps_quote(c) for c in cmd) + f" *> {_ps_quote(str(out))}; exit $LASTEXITCODE")
    outer = (
        f"$p = Start-Process -FilePath powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
        f"-ArgumentList '-NoProfile','-EncodedCommand',{_ps_quote(winutil.encode_ps(inner))}; "
        "[pscustomobject]@{ExitCode=$p.ExitCode}"
    )
    r = winutil.powershell(outer + " | ConvertTo-Json -Compress", timeout)
    if not r.ok:
        msg = "Permissão de administrador negada ou operação cancelada." if "canceled" in r.text.lower() \
            or "cancelad" in r.text.lower() else (r.error or r.text[:300])
        return winutil.CmdResult(False, error=msg, stderr=r.stderr)
    try:
        code = json.loads(r.stdout.strip()).get("ExitCode")
    except (ValueError, AttributeError):
        code = None
    try:
        text = winutil.decode_output(out.read_bytes())
    except OSError:
        text = ""
    finally:
        try:
            out.unlink()
        except OSError:
            pass
    return winutil.CmdResult(code == 0, code, text)
