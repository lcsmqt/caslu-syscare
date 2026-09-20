"""Disk tools: temp cleaner (preview + confirm) and largest-files finder."""
from __future__ import annotations

import os
import platform
import tempfile
import time
from pathlib import Path

from . import audit

IS_WINDOWS = platform.system() == "Windows"


def temp_locations() -> list[Path]:
    locs = [Path(tempfile.gettempdir())]
    if IS_WINDOWS:
        win = os.environ.get("WINDIR")
        if win:
            locs.append(Path(win) / "Temp")
    else:
        locs.append(Path.home() / ".cache" / "thumbnails")
    return [p for p in dict.fromkeys(locs) if p.is_dir()]


def scan_temp(min_age_hours: float = 24) -> list[tuple[Path, int]]:
    """Files older than min_age_hours in temp folders, with sizes. Does NOT delete."""
    cutoff = time.time() - min_age_hours * 3600
    out = []
    for base in temp_locations():
        for root, _dirs, files in os.walk(base):
            for f in files:
                p = Path(root) / f
                try:
                    st = p.lstat()
                    if st.st_mtime < cutoff and not p.is_symlink():
                        out.append((p, st.st_size))
                except OSError:
                    continue
    return out


def clean(files: list[tuple[Path, int]]) -> tuple[int, int]:
    """Delete previously scanned temp files. Returns (deleted_count, freed_bytes)."""
    allowed = [b.resolve() for b in temp_locations()]
    n = freed = 0
    deleted: list[str] = []
    for p, size in files:
        try:
            rp = p.resolve()
            if not any(a in rp.parents for a in allowed):
                continue  # safety: never delete outside temp locations
            p.unlink()
            n += 1
            freed += size
            deleted.append(str(p))
        except OSError:
            continue
    audit.record("cleanup_temp", "success" if n else "warning", f"{n} arquivos temporários",
                 new={"freed_bytes": freed, "paths": deleted[:50]})
    return n, freed


def largest_files(root: str, top: int = 50, min_mb: float = 50) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    min_b = int(min_mb * 1024 * 1024)
    for r, _d, files in os.walk(root, onerror=lambda e: None):
        for f in files:
            p = os.path.join(r, f)
            try:
                if os.path.islink(p):
                    continue
                s = os.path.getsize(p)
                if s >= min_b:
                    out.append((p, s))
            except OSError:
                continue
    out.sort(key=lambda x: -x[1])
    return out[:top]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
