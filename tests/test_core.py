import json
from pathlib import Path

import pytest

from syscare.core import knowledge, analyzer, actions, startup, network, disk, report, sysinfo


def test_protected_never_flagged():
    f = analyzer.classify("svchost.exe", [1], 90.0, 5000.0, 16000.0)
    assert f.category == "Essencial"


def test_rule_match_flags_unnecessary():
    f = analyzer.classify("Discord.exe", [10], 1.0, 300.0, 16000.0)
    assert f.category == "Desnecessário"
    assert f.reason


def test_unknown_heavy_is_review_and_light_is_normal():
    assert analyzer.classify("mystery.exe", [1], 40.0, 100.0, 16000.0).category == "Revisar"
    assert analyzer.classify("mystery.exe", [1], 1.0, 2000.0, 16000.0).category == "Revisar"
    assert analyzer.classify("notepad.exe", [1], 0.1, 20.0, 16000.0).category == "Normal"


def test_scan_processes_runs():
    res = analyzer.scan_processes(sample_seconds=0.2)
    assert res.findings
    assert 0 <= res.health_score <= 100


def test_terminate_refuses_protected(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    killed, errs = actions.terminate_group("systemd", [1])
    assert killed == 0 and errs


def test_autostart_disable_and_undo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    auto = tmp_path / ".config" / "autostart"
    auto.mkdir(parents=True)
    f = auto / "foo.desktop"
    f.write_text("[Desktop Entry]\nName=Foo\nExec=foo\n")
    items = startup._linux_items()
    assert any(i.name == "Foo" for i in items)
    item = next(i for i in items if i.name == "Foo")
    actions.disable_startup(item)
    assert "Hidden=true" in f.read_text()
    assert not any(i.name == "Foo" for i in startup._linux_items())
    actions.undo_last()
    assert "Hidden=true" not in f.read_text()


def test_network_validation():
    with pytest.raises(ValueError):
        network.ping("-c 1; rm -rf /")
    assert network.interfaces()


def test_disk_clean_only_inside_temp(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(disk, "temp_locations", lambda: [temp])
    outside = tmp_path / "keep.txt"
    outside.write_text("x")
    inside = temp / "junk.tmp"
    inside.write_text("y")
    n, _ = disk.clean([(outside, 1), (inside, 1)])
    assert n == 1 and outside.exists() and not inside.exists()


def test_report_exports():
    res = analyzer.ScanResult(findings=[analyzer.classify("discord", [1], 1, 200, 16000)])
    res.health_score = 80
    assert json.loads(report.to_json(res))["health_score"] == 80
    assert "Relatório" in report.to_html(res)
    assert sysinfo.summary()["Host"]
