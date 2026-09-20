"""Process analyzer: finds programs that use resources and are likely unnecessary."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict

import psutil

from . import knowledge

# Unknown (unclassified) programs are flagged for review above these thresholds.
REVIEW_CPU = 15.0      # % of total CPU
REVIEW_MEM_MB = 800.0  # resident memory


@dataclass
class Finding:
    name: str
    pids: list[int]
    cpu: float          # % of total system CPU, summed over the group
    mem_mb: float
    category: str       # Essencial | Desnecessário | Revisar | Normal
    reason: str
    risk: str           # safe | caution | none
    exe: str = ""
    impact: float = 0.0  # 0-100 score used for sorting

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    cpu_total: float = 0.0
    mem_percent: float = 0.0
    duration_s: float = 0.0
    health_score: int = 100

    @property
    def unnecessary(self) -> list[Finding]:
        return [f for f in self.findings if f.category == "Desnecessário"]

    @property
    def review(self) -> list[Finding]:
        return [f for f in self.findings if f.category == "Revisar"]

    @property
    def reclaimable_mem_mb(self) -> float:
        return sum(f.mem_mb for f in self.unnecessary)


def _impact(cpu: float, mem_mb: float, total_mem_mb: float) -> float:
    mem_share = (mem_mb / total_mem_mb * 100) if total_mem_mb else 0
    return min(100.0, cpu * 1.5 + mem_share * 2.0)


def scan_processes(sample_seconds: float = 1.0) -> ScanResult:
    """Sample all processes and classify them. Blocks for ~sample_seconds."""
    t0 = time.time()
    ncpu = psutil.cpu_count() or 1
    total_mem_mb = psutil.virtual_memory().total / 1024 / 1024

    procs: dict[int, psutil.Process] = {}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p.cpu_percent(None)  # prime counters
            procs[p.pid] = p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(sample_seconds)

    groups: dict[str, dict] = defaultdict(lambda: {"pids": [], "cpu": 0.0, "mem": 0.0, "exe": ""})
    for pid, p in procs.items():
        try:
            name = p.name() or f"pid-{pid}"
            cpu = p.cpu_percent(None) / ncpu
            mem = p.memory_info().rss / 1024 / 1024
            g = groups[name]
            g["pids"].append(pid)
            g["cpu"] += cpu
            g["mem"] += mem
            if not g["exe"]:
                try:
                    g["exe"] = p.exe()
                except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    findings: list[Finding] = []
    for name, g in groups.items():
        f = classify(name, g["pids"], g["cpu"], g["mem"], total_mem_mb, g["exe"])
        findings.append(f)
    findings.sort(key=lambda f: (f.category != "Desnecessário", f.category != "Revisar", -f.impact))

    res = ScanResult(
        findings=findings,
        cpu_total=psutil.cpu_percent(None),
        mem_percent=psutil.virtual_memory().percent,
        duration_s=time.time() - t0,
    )
    res.health_score = health_score(res)
    return res


def classify(name: str, pids: list[int], cpu: float, mem_mb: float,
             total_mem_mb: float, exe: str = "") -> Finding:
    impact = _impact(cpu, mem_mb, total_mem_mb)
    if knowledge.is_protected(name):
        return Finding(name, pids, cpu, mem_mb, "Essencial",
                       "Processo crítico do sistema. Nunca encerrar.", "none", exe, impact)
    rule = knowledge.match_rule(name)
    if rule:
        return Finding(name, pids, cpu, mem_mb, "Desnecessário", rule.reason,
                       rule.risk, exe, impact)
    if cpu >= REVIEW_CPU or mem_mb >= REVIEW_MEM_MB:
        why = []
        if cpu >= REVIEW_CPU:
            why.append(f"usa {cpu:.0f}% da CPU")
        if mem_mb >= REVIEW_MEM_MB:
            why.append(f"usa {mem_mb:.0f} MB de RAM")
        return Finding(name, pids, cpu, mem_mb, "Revisar",
                       "Não classificado e " + " e ".join(why) + ". Verifique se é necessário.",
                       "caution", exe, impact)
    return Finding(name, pids, cpu, mem_mb, "Normal", "Sem indício de problema.", "none", exe, impact)


def health_score(res: ScanResult) -> int:
    """0-100. Penalizes reclaimable RAM, high load and unknown heavy processes."""
    total_mb = psutil.virtual_memory().total / 1024 / 1024 or 1
    score = 100.0
    score -= min(30.0, res.reclaimable_mem_mb / total_mb * 100 * 3)
    score -= min(15.0, len(res.unnecessary) * 1.5)
    score -= min(15.0, len(res.review) * 5)
    score -= max(0.0, res.cpu_total - 50) * 0.3
    score -= max(0.0, res.mem_percent - 70) * 0.5
    return max(0, min(100, round(score)))
