"""Full diagnostic snapshot: runs every collector, isolates failures, aggregates issues."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Callable

from .. import __version__
from . import (audit, battery, devices, hardware, performance, recommendations, repair, scoring, security,
               snapshots, stability, storage_health, sysinfo, winupdate)
from .issues import Issue, sort_issues

log = logging.getLogger("syscare.diagnostics")

STEPS = ("system", "hardware", "storage", "battery", "security", "devices", "stability", "windows_update", "free_space")


def collect_all(progress: Callable[[str], None] | None = None) -> dict:
    """Never raises: a failing module lands in snapshot['errors'] and the rest continues."""
    snap: dict = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "app_version": __version__,
                  "errors": {}}
    issues: list[Issue] = []

    def step(name: str, fn: Callable):
        if progress:
            progress(name)
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            log.exception("diagnostic step %s failed", name)
            snap["errors"][name] = "Não foi possível coletar esta seção (detalhes no log técnico)."
            return None

    snap["system"] = step("system", sysinfo.summary) or {}
    snap["hardware"] = step("hardware", hardware.collect)
    disks = step("storage", storage_health.collect) or []
    snap["storage"] = [d.to_dict() for d in disks]
    issues += storage_health.issues_for(disks)
    bat = step("battery", battery.collect) or {"present": False}
    snap["battery"] = bat
    issues += battery.assess(bat)
    sec = step("security", lambda: security.collect(portable_device=bool(bat.get("present")))) or \
        {"summary": {}, "issues": []}
    snap["security"] = {"summary": sec["summary"]}
    issues += sec["issues"]
    dev = step("devices", devices.collect) or {"devices": [], "drivers": [], "issues": [], "message": ""}
    snap["devices"] = {"message": dev["message"],
                       "problems": [d for d in dev["devices"] if d["state"] != "OK"],
                       "total_devices": len(dev["devices"]), "old_drivers": [d for d in dev["drivers"] if d["old"]],
                       "total_drivers": len(dev["drivers"])}
    issues += dev["issues"]
    stab = step("stability", stability.collect)
    if stab:
        snap["stability"] = {k: v for k, v in stab.items() if k != "issues"}
        issues += stab["issues"]
    wu = step("windows_update", winupdate.collect)
    if wu:
        snap["windows_update"] = {k: v for k, v in wu.items() if k != "issues"}
        issues += wu.get("issues", [])
    fs = step("free_space", performance.free_space_issue)
    if fs:
        snap["free_space"], fs_issues = fs
        issues += fs_issues
    snap["issues"] = [i.to_dict() for i in sort_issues(issues)]
    snap["repair_history"] = repair.recent_results()
    snap["recent_actions"] = [e for e in audit.read(50) if not str(e.get("action", "")).startswith("repair:")][-15:]
    return snap


def finalize(snap: dict, res=None, startup: list | None = None, perf: dict | None = None) -> dict:
    """Add process/startup/performance findings, then score, recommendations and before/after comparison.

    Mutates and returns `snap`. Only measured data feeds the score; unmeasured areas are 'not evaluated'.
    """
    extra: list[Issue] = []
    if res is not None:
        extra += scoring.process_issues(res)
    if startup is not None:
        high = sum(1 for i in startup if i.impact == "Alto")
        snap["startup_summary"] = {"count": len(startup), "high_impact": high,
                                   "flagged": sum(1 for i in startup if i.flagged)}
        extra += performance.startup_load_issue(len(startup), high)
    if perf:
        snap["performance"] = perf
        extra += performance.assess(perf)
    base = list(snap.get("issues", []))
    known = {(i["area"], i["title"]) for i in base}
    merged = base + [i.to_dict() for i in extra if (i.area, i.title) not in known]
    snap["issues"] = [i.to_dict() for i in sort_issues([Issue(**{k: i[k] for k in
                      ("area", "severity", "title", "detail", "recommendation", "evidence")}) for i in merged])]
    ev = scoring.evaluated_categories(snap, res, startup)
    snap["score"] = scoring.compute(snap["issues"], ev)
    snap["recommendations"] = [r.to_dict() for r in recommendations.build(snap, perf)]
    before = snapshots.load("before")
    if before:
        now = snapshots.make(snap, snap["score"], len(startup) if startup is not None else None, perf)
        snap["comparison"] = {"before_taken": before.get("taken"), "after_taken": now["taken"],
                              "rows": snapshots.compare(before, now)}
    return snap
