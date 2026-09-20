"""Before/after snapshots and technician job history. Local files only; never fabricates improvements."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from .config import data_dir

log = logging.getLogger("syscare.snapshots")

# metric -> (label, better_when) ; better_when: "up" | "down"
METRICS = {
    "score": ("Pontuação de saúde", "up"),
    "ram_used_pct": ("RAM em uso (%)", "down"),
    "startup_count": ("Itens de inicialização", "down"),
    "free_disk_gb": ("Espaço livre no sistema (GB)", "up"),
    "issues_high": ("Problemas críticos", "down"),
    "issues_medium": ("Problemas médios", "down"),
    "issues_total": ("Total de problemas", "down"),
    "security_issues": ("Riscos de segurança", "down"),
    "disk_attention": ("Discos que exigem atenção", "down"),
    "perf_cpu_avg": ("CPU média (%)", "down"),
    "perf_ram_avg": ("RAM média (%)", "down"),
}
TOLERANCE = {"score": 1, "ram_used_pct": 2, "free_disk_gb": 0.5, "perf_cpu_avg": 3, "perf_ram_avg": 2}


def _path(name: str):
    return data_dir() / name


def make(snap: dict, res: dict | None = None, startup_count: int | None = None, perf: dict | None = None) -> dict:
    issues = snap.get("issues", [])
    out: dict = {"taken": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if res:
        out["score"] = res.get("score")
    import psutil
    out["ram_used_pct"] = psutil.virtual_memory().percent
    if startup_count is not None:
        out["startup_count"] = startup_count
    fs = snap.get("free_space") or {}
    if isinstance(fs.get("free_gb"), (int, float)):
        out["free_disk_gb"] = fs["free_gb"]
    for sev in ("high", "medium"):
        out[f"issues_{sev}"] = sum(1 for i in issues if i.get("severity") == sev)
    out["issues_total"] = sum(1 for i in issues if i.get("severity") != "info")
    out["security_issues"] = sum(1 for i in issues if i.get("area") == "Segurança" and i.get("severity") != "info")
    out["disk_attention"] = sum(1 for d in snap.get("storage", []) if d.get("status") in ("ATTENTION", "CRITICAL"))
    if perf and perf.get("sufficient"):
        out["perf_cpu_avg"] = perf["cpu"]["avg"]
        out["perf_ram_avg"] = perf["mem"]["avg"]
    return out


def save(state: dict, name: str = "before") -> None:
    try:
        _path(f"snapshot_{name}.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.exception("could not save snapshot")


def load(name: str = "before") -> dict | None:
    try:
        return json.loads(_path(f"snapshot_{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clear(name: str = "before") -> None:
    try:
        _path(f"snapshot_{name}.json").unlink()
    except OSError:
        pass


def compare(before: dict, after: dict) -> list[dict]:
    rows = []
    for key, (label, better) in METRICS.items():
        b, a = before.get(key), after.get(key)
        if not isinstance(b, (int, float)) or not isinstance(a, (int, float)):
            rows.append({"metric": label, "before": b, "after": a, "delta": None, "verdict": "não medido"})
            continue
        d = round(a - b, 2)
        if abs(d) <= TOLERANCE.get(key, 0):
            verdict = "igual"
        elif (d > 0) == (better == "up"):
            verdict = "melhorou"
        else:
            verdict = "piorou"
        rows.append({"metric": label, "before": b, "after": a, "delta": d, "verdict": verdict})
    return rows


# ------------------------------------------------------------------ technician job history
def add_job(job: dict) -> None:
    rec = dict(job, saved=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        with _path("jobs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        log.exception("could not save job")


def read_jobs(limit: int = 200) -> list[dict]:
    try:
        lines = _path("jobs.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return list(reversed(out))
