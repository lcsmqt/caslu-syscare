"""Performance diagnostics: short, cancellable, session-based sampling (never records continuously)."""
from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Callable

import psutil

from . import winutil
from .issues import Issue

log = logging.getLogger("syscare.performance")

MIN_SAMPLES = 5   # below this we make no claim about "sustained" behavior


def system_drive() -> str:
    if winutil.IS_WINDOWS:
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def disk_queue_length() -> float | None:
    """Windows only: current disk queue length via typeperf (None when unavailable)."""
    if not winutil.IS_WINDOWS:
        return None
    r = winutil.run(["typeperf", r"\PhysicalDisk(_Total)\Current Disk Queue Length", "-sc", "1"], 15)
    if not r.ok:
        return None
    for line in r.stdout.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2:
            try:
                return float(parts[-1])
            except ValueError:
                continue
    return None


def sample(duration: float = 15, interval: float = 1.0, cancel: Callable[[], bool] | None = None,
           on_progress: Callable[[int, int], None] | None = None) -> list[dict]:
    """Collect samples for `duration` seconds. Stops early when cancel() is true."""
    total = max(1, int(duration / interval))
    out: list[dict] = []
    psutil.cpu_percent(None)
    prev_disk, prev_net = psutil.disk_io_counters(), psutil.net_io_counters()
    prev_t = time.time()
    for i in range(total):
        if cancel and cancel():
            break
        time.sleep(interval)
        now = time.time()
        dt_s = max(now - prev_t, 1e-6)
        disk, net = psutil.disk_io_counters(), psutil.net_io_counters()
        s = {"t": round(i * interval, 1), "cpu": psutil.cpu_percent(None),
             "mem": psutil.virtual_memory().percent, "disk_mbps": None, "disk_busy": None, "net_mbps": None}
        if disk and prev_disk:
            s["disk_mbps"] = ((disk.read_bytes - prev_disk.read_bytes) +
                              (disk.write_bytes - prev_disk.write_bytes)) / dt_s / 1e6
            busy = getattr(disk, "busy_time", None)   # Linux only (ms)
            if busy is not None and getattr(prev_disk, "busy_time", None) is not None:
                s["disk_busy"] = min(100.0, (busy - prev_disk.busy_time) / (dt_s * 10))
        if net and prev_net:
            s["net_mbps"] = ((net.bytes_recv - prev_net.bytes_recv) + (net.bytes_sent - prev_net.bytes_sent)) \
                * 8 / dt_s / 1e6
        prev_disk, prev_net, prev_t = disk, net, now
        out.append(s)
        if on_progress:
            on_progress(i + 1, total)
    return out


def _pct(values: list[float], p: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def _series(samples: list[dict], key: str) -> dict | None:
    v = [s[key] for s in samples if s.get(key) is not None]
    if not v:
        return None
    return {"avg": round(sum(v) / len(v), 1), "max": round(max(v), 1), "p95": round(_pct(v, 95), 1)}


def summarize(samples: list[dict], queue: float | None = None) -> dict:
    n = len(samples)
    cpu = [s["cpu"] for s in samples]
    return {
        "samples": n,
        "duration_s": round(samples[-1]["t"] + 1, 1) if samples else 0,
        "cpu": _series(samples, "cpu"),
        "cpu_pct_over_90": round(sum(1 for c in cpu if c >= 90) / n * 100) if n else 0,
        "mem": _series(samples, "mem"),
        "mem_pct_over_90": round(sum(1 for s in samples if s["mem"] >= 90) / n * 100) if n else 0,
        "disk_mbps": _series(samples, "disk_mbps"),
        "disk_busy": _series(samples, "disk_busy"),
        "net_mbps": _series(samples, "net_mbps"),
        "disk_queue": queue,
        "sufficient": n >= MIN_SAMPLES,
    }


def free_space_issue(path: str | None = None) -> tuple[dict, list[Issue]]:
    path = path or system_drive()
    try:
        u = shutil.disk_usage(path)
    except OSError:
        return {}, []
    free_gb, pct = u.free / 1024**3, u.free / u.total * 100
    info = {"path": path, "free_gb": round(free_gb, 1), "free_pct": round(pct, 1),
            "total_gb": round(u.total / 1024**3, 1)}
    ev = f"{free_gb:.1f} GB livres ({pct:.0f}%) em {path}"
    if pct < 5 or free_gb < 5:
        return info, [Issue("Desempenho", "high", "Espaço livre crítico no disco do sistema",
                            "Pouco espaço livre degrada o Windows (atualizações, arquivo de paginação, temporários).",
                            "Libere espaço com a Limpeza e o Analisador de armazenamento.", ev)]
    if pct < 10 or free_gb < 15:
        return info, [Issue("Desempenho", "medium", "Pouco espaço livre no disco do sistema",
                            "Recomenda-se manter pelo menos 10–15% livres.",
                            "Use a Limpeza de temporários e revise os maiores arquivos.", ev)]
    return info, []


def assess(stats: dict | None) -> list[Issue]:
    """Issues from a measured session. Makes no 'sustained' claim from too few samples."""
    if not stats or not stats.get("sufficient"):
        return []
    out: list[Issue] = []
    win = f"em {stats['duration_s']:.0f} s de medição"
    cpu = stats["cpu"]
    if cpu and (cpu["avg"] >= 85 or stats["cpu_pct_over_90"] >= 60):
        out.append(Issue("Desempenho", "medium", "CPU sob carga elevada e contínua",
                         f"Média de {cpu['avg']:.0f}% {win}.",
                         "Verifique os processos que mais consomem CPU (Manutenção › Processos) e o antivírus/atualizações.",
                         f"CPU média {cpu['avg']}%, máx. {cpu['max']}%, {stats['cpu_pct_over_90']}% das amostras ≥ 90%"))
    mem = stats["mem"]
    if mem and (mem["avg"] >= 85 or mem["max"] >= 95):
        out.append(Issue("Desempenho", "medium", "Pressão de memória",
                         f"Uso de RAM médio de {mem['avg']:.0f}% (pico {mem['max']:.0f}%) {win}.",
                         "Feche programas pesados, reduza itens de inicialização ou considere mais RAM.",
                         f"RAM média {mem['avg']}%, máx. {mem['max']}%, {stats['mem_pct_over_90']}% das amostras ≥ 90%"))
    busy, q = stats.get("disk_busy"), stats.get("disk_queue")
    if (busy and busy["avg"] >= 80) or (q is not None and q >= 2):
        ev = (f"disco ocupado {busy['avg']}% em média" if busy and busy["avg"] >= 80 else f"fila de disco {q}")
        out.append(Issue("Desempenho", "medium", "Atividade de disco elevada",
                         f"O disco esteve muito ocupado {win}.",
                         "Verifique indexação, antivírus e atualizações; em HDD, considere migrar para SSD.", ev))
    return out


def startup_load_issue(count: int, high_impact: int) -> list[Issue]:
    if count >= 15 or high_impact >= 3:
        return [Issue("Inicialização", "low", "Carga de inicialização elevada",
                      f"{count} programas iniciam com o Windows ({high_impact} de impacto estimado alto).",
                      "Revise a aba Inicialização e desative apenas o que não usa (nunca ferramentas de segurança).",
                      f"itens={count}, impacto alto={high_impact}")]
    return []
