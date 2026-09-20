"""Professional health score: weighted categories with transparent deductions.

Score = 100 − Σ deductions. Categories without data are 'not evaluated' (no penalty, and the
result reports the coverage). Deductions come only from measured findings (Issues).
"""
from __future__ import annotations

from .issues import Issue

WEIGHTS = {
    "Armazenamento": 20, "Segurança": 20, "Estabilidade": 15, "Desempenho": 15,
    "Integridade do Windows": 10, "Inicialização": 8, "Hardware": 7, "Rede": 5,
}
AREA_TO_CATEGORY = {
    "Armazenamento": "Armazenamento", "Segurança": "Segurança", "Estabilidade": "Estabilidade",
    "Desempenho": "Desempenho", "Dispositivos": "Integridade do Windows", "Drivers": "Integridade do Windows",
    "Windows": "Integridade do Windows", "Windows Update": "Integridade do Windows",
    "Inicialização": "Inicialização", "Hardware": "Hardware", "Bateria": "Hardware", "Rede": "Rede",
}
SEVERITY_FRACTION = {"high": 0.60, "medium": 0.30, "low": 0.10, "info": 0.0}


def category_of(issue: Issue | dict) -> str:
    area = issue["area"] if isinstance(issue, dict) else issue.area
    return AREA_TO_CATEGORY.get(area, "Hardware")


def evaluated_categories(snap: dict, res=None, startup=None) -> set[str]:
    ev: set[str] = set()
    if any(d.get("status") != "UNKNOWN" for d in snap.get("storage", [])):
        ev.add("Armazenamento")
    if any("Indisponível" not in str(v) for v in snap.get("security", {}).get("summary", {}).values()):
        ev.add("Segurança")
    if snap.get("stability") and not snap["stability"].get("message"):
        ev.add("Estabilidade")
    if snap.get("free_space") or snap.get("performance"):
        ev.add("Desempenho")
    if (snap.get("devices") and snap["devices"].get("total_devices")) or snap.get("windows_update") or \
            snap.get("repair_history"):
        ev.add("Integridade do Windows")
    if startup is not None:
        ev.add("Inicialização")
    if snap.get("hardware") or snap.get("battery", {}).get("present"):
        ev.add("Hardware")
    if snap.get("network"):
        ev.add("Rede")
    return ev


def process_issues(res) -> list[Issue]:
    """Findings from the process analyzer that are evidence-based (reclaimable RAM)."""
    if res is None:
        return []
    mb = res.reclaimable_mem_mb
    if mb >= 1500:
        sev = "medium"
    elif mb >= 500:
        sev = "low"
    else:
        return []
    names = ", ".join(f.name for f in res.unnecessary[:5])
    return [Issue("Desempenho", sev, "Programas desnecessários consumindo memória",
                  f"Cerca de {mb:.0f} MB de RAM estão em programas classificados como desnecessários.",
                  "Feche-os quando não usar e revise a inicialização.", f"{mb:.0f} MB: {names}")]


def compute(issues: list[Issue | dict], evaluated: set[str]) -> dict:
    rows = []
    total = 0
    for cat, weight in WEIGHTS.items():
        mine = [i for i in issues if category_of(i) == cat]
        raw = sum(weight * SEVERITY_FRACTION.get(i["severity"] if isinstance(i, dict) else i.severity, 0)
                  for i in mine)
        ded = min(weight, round(raw)) if cat in evaluated else 0
        if cat in evaluated and raw > 0 and ded == 0:
            ded = 1
        total += ded
        rows.append({
            "category": cat, "max": weight, "evaluated": cat in evaluated, "deduction": ded,
            "reasons": [(i["title"] if isinstance(i, dict) else i.title) for i in mine
                        if (i["severity"] if isinstance(i, dict) else i.severity) != "info"],
        })
    coverage = sum(w for c, w in WEIGHTS.items() if c in evaluated)
    return {"score": max(0, 100 - total), "coverage_pct": coverage, "breakdown": rows,
            "not_evaluated": [c for c in WEIGHTS if c not in evaluated]}


def explain(result: dict) -> str:
    """Plain-text 'why points were deducted' (used in UI and reports)."""
    lines = [f"Saúde do sistema: {result['score']}/100 (cobertura da avaliação: {result['coverage_pct']}%)", ""]
    for r in result["breakdown"]:
        if not r["evaluated"]:
            lines.append(f"{r['category']}: não avaliado")
        else:
            lines.append(f"{r['category']}: -{r['deduction']}" + (f"  ({'; '.join(r['reasons'])})" if r["reasons"] else ""))
    return "\n".join(lines)
