"""P1 tests: performance, scoring, recommendations, services, stability, Windows Update, restore, snapshots."""
import datetime as dt
import json

import pytest

from syscare.core import (diagnostics, performance, recommendations, restore, scoring, services, snapshots,
                          stability, startup, winupdate, winutil)
from syscare.core.issues import Issue
from syscare.core.safeaction import run_safe_action


def _samples(cpu=10, mem=40, n=10, busy=None):
    return [{"t": float(i), "cpu": cpu, "mem": mem, "disk_mbps": 1.0, "disk_busy": busy, "net_mbps": 0.1}
            for i in range(n)]


# ---------------------------------------------------------------- performance
def test_summarize_insufficient_makes_no_claims():
    st = performance.summarize(_samples(cpu=99, n=3))
    assert not st["sufficient"] and performance.assess(st) == []


def test_assess_cpu_and_memory():
    st = performance.summarize(_samples(cpu=95, mem=92))
    titles = [i.title for i in performance.assess(st)]
    assert any("CPU" in t for t in titles) and any("memória" in t for t in titles)


def test_assess_healthy_is_quiet():
    assert performance.assess(performance.summarize(_samples())) == []


def test_free_space_thresholds(monkeypatch):
    import shutil
    from collections import namedtuple
    U = namedtuple("U", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: U(500 * 1024**3, 460 * 1024**3, 40 * 1024**3))
    assert performance.free_space_issue("/")[1][0].severity == "medium"
    monkeypatch.setattr(shutil, "disk_usage", lambda p: U(500 * 1024**3, 497 * 1024**3, 3 * 1024**3))
    assert performance.free_space_issue("/")[1][0].severity == "high"
    monkeypatch.setattr(shutil, "disk_usage", lambda p: U(500 * 1024**3, 100 * 1024**3, 400 * 1024**3))
    assert performance.free_space_issue("/")[1] == []


def test_startup_load_issue():
    assert performance.startup_load_issue(5, 0) == []
    assert performance.startup_load_issue(16, 0)


# ---------------------------------------------------------------- scoring
def test_score_clean_is_100_and_unevaluated_not_penalized():
    r = scoring.compute([], {"Armazenamento"})
    assert r["score"] == 100 and r["coverage_pct"] == 20 and "Rede" in r["not_evaluated"]


def test_score_deduction_and_explain():
    r = scoring.compute([Issue("Armazenamento", "high", "Disco falhando")], {"Armazenamento"})
    assert r["score"] == 88          # 20 * 0.6
    assert "Disco falhando" in scoring.explain(r)


def test_score_ignores_unevaluated_category_issues():
    r = scoring.compute([Issue("Rede", "high", "x")], {"Armazenamento"})
    assert r["score"] == 100


def test_score_deduction_capped_by_weight():
    issues = [Issue("Rede", "high", f"x{i}") for i in range(10)]
    assert scoring.compute(issues, {"Rede"})["score"] == 95


# ---------------------------------------------------------------- recommendations
def test_ram_recommendation_requires_evidence(monkeypatch):
    import psutil
    from collections import namedtuple
    VM = namedtuple("VM", "total percent")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: VM(8 * 1024**3, 50))
    assert recommendations.build({"issues": []}, None) == []
    perf = performance.summarize(_samples(mem=95))
    perf["disk_queue"] = None
    recs = recommendations.build({"issues": []}, perf)
    assert any("RAM" in r.recommendation for r in recs)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: VM(32 * 1024**3, 50))
    assert recommendations.build({"issues": []}, perf) == []


def test_ssd_recommendation_only_with_hdd_and_load(monkeypatch):
    perf = performance.summarize(_samples(busy=90))
    hdd = {"issues": [], "storage": [{"media_type": "HDD"}]}
    assert any("SSD" in r.recommendation for r in recommendations.build(hdd, perf))
    ssd = {"issues": [], "storage": [{"media_type": "SSD"}]}
    assert not any("SSD" in r.recommendation for r in recommendations.build(ssd, perf))


# ---------------------------------------------------------------- services
def test_service_classification():
    assert services.classify("WinDefend", "Defender", r"C:\Windows\x.exe", "automatic")[0] == services.CRITICAL_LABEL
    assert services.classify("Foo", "Foo", r"C:\Windows\System32\svchost.exe -k x", "manual")[0] == services.WINDOWS_LABEL
    assert services.classify("Foo", "Foo", r"C:\Program Files\Foo\foo.exe", "manual")[0] == services.THIRD_LABEL
    assert services.classify("Foo", "Foo", "", "manual")[0] == services.REVIEW_LABEL


def _svc(name="FooSvc", binpath=r"C:\Program Files\Foo\foo.exe", start="Automatic"):
    return services.parse_service({"name": name, "display_name": name, "binpath": binpath,
                                   "start_type": start.lower(), "status": "running"})


def test_service_blocked_for_critical():
    s = _svc("WinDefend", r"C:\Windows\x.exe")
    assert not s["changeable"]
    r = run_safe_action(services.ServiceStartTypeAction(s, "disabled"), lambda p: True)
    assert r.status == "blocked"


def test_service_change_records_undo(monkeypatch):
    s = _svc()
    calls = []
    monkeypatch.setattr(services, "_sc_config", lambda n, t: (calls.append((n, t)) or winutil.CmdResult(True, 0, "ok", "")))
    monkeypatch.setattr(services, "current_start_type", lambda n: "demand")
    monkeypatch.setattr(services.privilege, "is_admin", lambda: True)
    r = run_safe_action(services.ServiceStartTypeAction(s, "demand"), lambda p: True)
    assert r.status == "success" and calls == [("FooSvc", "demand")]
    assert "Restaurado" in services.undo_last()
    assert calls[-1] == ("FooSvc", "auto")
    assert services.undo_last() == "Nada para desfazer."


def test_service_declined_does_not_run(monkeypatch):
    monkeypatch.setattr(services, "_sc_config", lambda n, t: pytest.fail("must not run"))
    r = run_safe_action(services.ServiceStartTypeAction(_svc(), "disabled"), lambda p: False)
    assert r.status != "success"


# ---------------------------------------------------------------- stability
def test_parse_bugcheck():
    code, name = stability.parse_bugcheck("O computador foi reiniciado. verificação de erro: 0x0000009f (0x3, ...)")
    assert code == "0x0000009F" and name == "DRIVER_POWER_STATE_FAILURE"
    assert stability.parse_bugcheck("nada") == ("", "")


RAW = {"System": [
    {"Time": "2026-09-01 10:00:00", "Id": 1001, "ProviderName": "Microsoft-Windows-WER-SystemErrorReporting",
     "Message": "The computer has rebooted from a bugcheck. The bugcheck was: 0x00000133 (0x0)"},
    {"Time": "2026-09-02 10:00:00", "Id": 41, "ProviderName": "Kernel-Power", "Message": ""},
    {"Time": "2026-09-03 10:00:00", "Id": 6008, "ProviderName": "EventLog", "Message": ""},
    {"Time": "2026-09-03 11:00:00", "Id": 1001, "ProviderName": "Windows Error Reporting", "Message": "Fault bucket"},
    ] + [{"Time": f"2026-09-0{i} 10:00:00", "Id": 7031, "ProviderName": "SCM",
          "Message": "The Foo Helper service terminated unexpectedly."} for i in range(1, 4)],
    "App": [{"Time": f"2026-09-0{i} 09:00:00", "Id": 1000,
             "Message": "Faulting application name: game.exe, version: 1\nFaulting module name: bad.dll, x"}
            for i in range(1, 4)]}


def test_parse_events_and_assess_cautious():
    rep = stability.parse_events(RAW)
    assert len(rep["bugchecks"]) == 1 and rep["bugchecks"][0]["name"] == "DPC_WATCHDOG_VIOLATION"
    assert len(rep["unexpected_shutdowns"]) == 2
    assert rep["service_failures"][0]["service"] == "Foo Helper"
    assert rep["app_crashes"][0]["module"] == "bad.dll"
    rep["days"] = 30
    issues = stability.assess(rep)
    assert {i.area for i in issues} == {"Estabilidade"}
    text = " ".join(i.detail for i in issues)
    assert "não é possível apontar a causa exata" in text and "Possível componente relacionado" in text


def test_stability_collect_non_windows_is_safe():
    rep = stability.collect()
    assert rep["message"] and rep["issues"] == []


# ---------------------------------------------------------------- windows update
def test_winupdate_assess():
    today = dt.date(2026, 9, 20)
    assert winupdate.assess({"last_install": "2026-09-01"}, today) == []
    assert winupdate.assess({"last_install": "2026-05-01"}, today)[0].severity == "medium"
    assert winupdate.assess({"last_install": "2026-01-01"}, today)[0].severity == "high"
    assert winupdate.assess({"reboot_reasons": ["Windows Update"]}, today)[0].title.startswith("Reinicialização")
    assert winupdate.assess({}, today) == []          # unknown date: no claim


# ---------------------------------------------------------------- restore
def test_parse_points_sorted():
    pts = restore.parse_points([{"SequenceNumber": 1, "Description": "a", "Created": "2026-01-01 10:00"},
                                {"SequenceNumber": 2, "Description": "b", "Created": "2026-02-01 10:00"}])
    assert pts[0]["id"] == 2


# ---------------------------------------------------------------- snapshots + startup impact
def test_compare_verdicts():
    b = {"score": 70, "ram_used_pct": 80, "startup_count": 20, "free_disk_gb": 10}
    a = {"score": 80, "ram_used_pct": 60, "startup_count": 20, "free_disk_gb": 9.8}
    rows = {r["metric"]: r["verdict"] for r in snapshots.compare(b, a)}
    assert rows["Pontuação de saúde"] == "melhorou"
    assert rows["RAM em uso (%)"] == "melhorou"
    assert rows["Itens de inicialização"] == "igual"
    assert rows["Espaço livre no sistema (GB)"] == "igual"
    assert rows["CPU média (%)"] == "não medido"


def test_snapshot_roundtrip_and_jobs():
    assert snapshots.load() is None
    snapshots.save({"score": 50})
    assert snapshots.load()["score"] == 50
    snapshots.clear()
    assert snapshots.load() is None
    snapshots.add_job({"client": "Fulano"})
    assert snapshots.read_jobs()[0]["client"] == "Fulano"


def test_startup_impact_estimates():
    it = startup.StartupItem("Foo", r'"C:\Apps\foo.exe" --x', "HKCU\\Run", "k", "registry")
    assert startup.estimate_impact(it, {})[0] == "Desconhecido"
    assert startup.estimate_impact(it, {"foo.exe": {"rss_mb": 400, "cpu_s": 1}})[0] == "Alto"
    assert startup.estimate_impact(it, {"foo.exe": {"rss_mb": 150, "cpu_s": 1}})[0] == "Médio"
    assert startup.estimate_impact(it, {"foo.exe": {"rss_mb": 20, "cpu_s": 1}})[0] == "Baixo"
    av = startup.StartupItem("Windows Defender notification", "SecurityHealthSystray.exe", "HKLM\\Run", "k", "registry")
    assert startup.estimate_impact(av, {"securityhealthsystray.exe": {"rss_mb": 900, "cpu_s": 900}})[0] == "Baixo"


# ---------------------------------------------------------------- finalize
def test_finalize_end_to_end(monkeypatch):
    snapshots.save({"score": 10, "issues_total": 9, "startup_count": 30})
    snap = diagnostics.collect_all()
    out = diagnostics.finalize(snap, None, [], None)
    assert 0 <= out["score"]["score"] <= 100 and "comparison" in out
    json.dumps(out, default=str)
    from syscare.core import report
    html = report.to_html_full(out, None, [])
    assert "Pontuação de saúde" in html and "Antes e depois" in html


def test_repair_aborts_when_restore_point_fails(monkeypatch):
    pytest.importorskip("PySide6")
    from syscare.core import repair, safeaction
    from syscare.ui.pages_diag import RepairPage
    monkeypatch.setattr(restore.RestorePointAction, "execute",
                        lambda self, a: safeaction.ActionResult("failed", "sem proteção"))
    monkeypatch.setattr(restore.privilege, "is_admin", lambda: True)
    monkeypatch.setattr(restore.winutil, "IS_WINDOWS", True)
    monkeypatch.setattr(restore, "list_points", lambda: {"points": [], "message": ""})
    cmd = next(c for c in repair.CATALOG if c.risk != safeaction.Risk.LOW)
    action = repair.RepairAction(cmd)
    monkeypatch.setattr(repair.RepairAction, "execute", lambda self, a: pytest.fail("must not execute"))
    a, pv, err = safeaction.prepare(action)
    r = RepairPage._work(action, a, pv, True)
    assert r.status == "cancelled"
