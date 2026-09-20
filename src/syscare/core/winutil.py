"""Safe command/PowerShell helpers. Nothing here raises: failures become CmdResult(ok=False)."""
from __future__ import annotations

import base64
import json
import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

IS_WINDOWS = platform.system() == "Windows"
UNAVAILABLE = "Indisponível"
log = logging.getLogger("syscare.winutil")

_PS_PREFIX = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
              "$ProgressPreference='SilentlyContinue';$ErrorActionPreference='Stop';")


@dataclass
class CmdResult:
    ok: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str = ""

    @property
    def text(self) -> str:
        return (self.stdout + ("\n" + self.stderr if self.stderr.strip() else "")).strip()


def _oem_encoding() -> str:
    if IS_WINDOWS:
        try:
            import ctypes
            return f"cp{ctypes.windll.kernel32.GetOEMCP()}"  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return "cp850"
    return "utf-8"


def decode_output(data: bytes) -> str:
    """Decode console output: UTF-16 (sfc.exe), UTF-8, or the OEM code page."""
    if not data:
        return ""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace").replace("\x00", "")
    if b"\x00" in data[:400]:  # UTF-16LE without BOM
        return data.decode("utf-16-le", errors="replace").replace("\x00", "")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(_oem_encoding(), errors="replace")


def run(cmd: list[str], timeout: float = 30, cwd: str | None = None) -> CmdResult:
    kwargs: dict[str, Any] = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd, **kwargs)
    except FileNotFoundError:
        return CmdResult(False, error=f"Comando não encontrado: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return CmdResult(False, timed_out=True, error=f"Tempo esgotado ({timeout:.0f}s): {cmd[0]}")
    except OSError as e:
        log.warning("run(%s) failed: %s", cmd[0], e)
        return CmdResult(False, error=str(e))
    return CmdResult(p.returncode == 0, p.returncode, decode_output(p.stdout), decode_output(p.stderr))


def encode_ps(script: str) -> str:
    return base64.b64encode((_PS_PREFIX + script).encode("utf-16-le")).decode("ascii")


def powershell_exe() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def powershell(script: str, timeout: float = 30) -> CmdResult:
    exe = powershell_exe()
    if not exe:
        return CmdResult(False, error="PowerShell não disponível neste sistema.")
    return run([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encode_ps(script)], timeout)


def ps_json(script: str, timeout: float = 30) -> Any | None:
    """Run a PowerShell pipeline and return parsed JSON. None on failure, [] when empty."""
    r = powershell(script + " | ConvertTo-Json -Depth 5 -Compress", timeout)
    if not r.ok:
        log.info("ps_json failed: %s", (r.error or r.stderr)[:300])
        return None
    out = r.stdout.strip()
    if not out:
        return []
    try:
        return json.loads(out)
    except ValueError as e:
        log.warning("ps_json parse error: %s", e)
        return None


def ensure_list(x: Any) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def val(x: Any, default: str = UNAVAILABLE) -> str:
    """Stringify a value, mapping None/empty to the 'unavailable' marker."""
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def fmt_gb(n: float | int | None, digits: int = 1) -> str:
    if not n:
        return UNAVAILABLE
    return f"{n / 1024**3:.{digits}f} GB"
