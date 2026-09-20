"""Explainable, evidence-based recommendations. Every item states finding, reason and evidence."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import psutil

from .issues import SEVERITY_ORDER

PRIORITY_LABEL = {"high": "ALTA", "medium": "MÉDIA", "low": "BAIXA"}


@dataclass
class Recommendation:
    area: str
    finding: str
    recommendation: str
    priority: str          # high | medium | low
    reason: str            # the evidence behind it

    def to_dict(self) -> dict:
        return asdict(self)


def _from_issues(issues: list[dict]) -> list[Recommendation]:
    out = []
    for i in issues:
        if i["severity"] == "info" or not i.get("recommendation"):
            continue
        out.append(Recommendation(i["area"], i["title"], i["recommendation"], i["severity"],
                                  i.get("evidence") or i.get("detail", "")))
    return out


def _ram_upgrade(snap: dict, perf: dict | None, total_gb: float) -> list[Recommendation]:
    if not perf or not perf.get("sufficient") or not perf.get("mem") or total_gb > 8.5:
        return []
    mem = perf["mem"]
    if perf["mem_pct_over_90"] >= 30 or mem["avg"] >= 85:
        return [Recommendation(
            "Desempenho", f"Apenas {total_gb:.0f} GB de RAM instalada e pressão de memória frequente",
            "Considere ampliar para 16 GB de RAM (verifique se o modelo permite upgrade).", "medium",
            f"Uso de memória ≥ 90% em {perf['mem_pct_over_90']}% das amostras (média {mem['avg']}%, "
            f"pico {mem['max']}%) durante {perf['duration_s']:.0f} s.")]
    return []


def _ssd_upgrade(snap: dict, perf: dict | None) -> list[Recommendation]:
    hdds = [d for d in snap.get("storage", []) if d.get("media_type") == "HDD"]
    if not hdds or not perf or not perf.get("sufficient"):
        return []
    busy, q = perf.get("disk_busy"), perf.get("disk_queue")
    if (busy and busy["avg"] >= 70) or (q is not None and q >= 2):
        ev = f"disco ocupado {busy['avg']}% em média" if busy and busy["avg"] >= 70 else f"fila de disco {q}"
        return [Recommendation("Desempenho", "Disco mecânico (HDD) com atividade elevada",
                               "Migrar o sistema para um SSD costuma trazer o maior ganho de desempenho.", "medium",
                               f"{len(hdds)} HDD(s) detectado(s); {ev}.")]
    return []


def build(snap: dict, perf: dict | None = None) -> list[Recommendation]:
    total_gb = psutil.virtual_memory().total / 1024**3
    recs = _from_issues(snap.get("issues", [])) + _ram_upgrade(snap, perf, total_gb) + _ssd_upgrade(snap, perf)
    seen, uniq = set(), []
    for r in recs:
        if r.finding not in seen:
            seen.add(r.finding)
            uniq.append(r)
    return sorted(uniq, key=lambda r: SEVERITY_ORDER.get(r.priority, 9))
