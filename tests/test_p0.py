"""P0 modules: parsers, classifiers, safety rules. Windows APIs are mocked; nothing touches the host."""
import datetime as dt
import json
import sys

import pytest

from syscare.core import (audit, battery, config, devices, diagnostics, hardware, privilege, report, repair,
                          safeaction, security, storage_health as sh, winutil)


# ------------------------------------------------------------------ winutil
def test_run_never_raises():
    r = winutil.run(["definitely-not-a-command-xyz"])
    assert not r.ok and r.error
    r = winutil.run([sys.executable, "-c", "import time; time.sleep(3)"], timeout=0.3)
    assert r.timed_out and not r.ok


def test_decode_output_utf16_and_utf8():
    assert winutil.decode_output("Verificação".encode("utf-16")) == "Verificação"
    assert "sfc" in winutil.decode_output("sfc /scannow".encode("utf-16-le"))
    assert winutil.decode_output("ação".encode("utf-8")) == "ação"


def test_val_and_ensure_list():
    assert winutil.val(None) == winutil.UNAVAILABLE and winutil.val("  ") == winutil.UNAVAILABLE
    assert winutil.ensure_list({"a": 1}) == [{"a": 1}] and winutil.ensure_list(None) == []


# ------------------------------------------------------------------ config / audit / safeaction
def test_config_threshold_override_and_data_dir(tmp_path, monkeypatch):
    assert config.data_dir().exists()
    assert config.threshold("driver_old_years") == 5
    config.save({"thresholds": {"driver_old_years": 9}})
    assert config.threshold("driver_old_years") == 9
    assert config.threshold("battery_health_poor_pct") == 60   # untouched default preserved


def test_audit_scrubs_secrets_and_reads_back():
    audit.record("x", "success", "t", previous={"password": "hunter2", "ok": 1}, new={"api_key": "abc"})
    e = audit.read()[-1]
    assert e["previous_state"]["password"] == "[redacted]" and e["new_state"]["api_key"] == "[redacted]"
    assert e["previous_state"]["ok"] == 1 and e["timestamp"]


class _Dummy(safeaction.SafeAction):
    name = "dummy"

    def __init__(self, fail=False, admin=False):
        self.executed, self.fail, self.admin = False, fail, admin

    def preview(self, analysis):
        return safeaction.Preview("t", "d", safeaction.Risk.MEDIUM, needs_admin=self.admin, items=["a"])

    def execute(self, analysis):
        if self.fail:
            raise RuntimeError("boom")
        self.executed = True
        return safeaction.ActionResult("success", "ok")

    def verify(self, analysis, result):
        return True


def test_safeaction_requires_confirmation():
    a = _Dummy()
    res = safeaction.run_safe_action(a, lambda p: False)
    assert res.status == "cancelled" and not a.executed
    res = safeaction.run_safe_action(a, lambda p: True)
    assert res.status == "success" and a.executed and res.verified is True
    assert [e["result"] for e in audit.read() if e["action"] == "dummy"] == ["cancelled", "success"]


def test_safeaction_failure_never_raises_and_admin_block(monkeypatch):
    assert safeaction.run_safe_action(_Dummy(fail=True), lambda p: True).status == "failed"
    monkeypatch.setattr(privilege, "is_admin", lambda: False)
    res = safeaction.run_safe_action(_Dummy(admin=True), lambda p: True)
    assert res.status == "blocked"


# ------------------------------------------------------------------ hardware
def test_hardware_parsers():
    cpu = hardware.parse_cpu([{"Name": "Ryzen 5", "NumberOfCores": 6, "NumberOfLogicalProcessors": 12,
                               "MaxClockSpeed": 3600}], 12, 6)
    assert cpu["Modelo"] == "Ryzen 5" and "3600" in cpu["Clock"] and cpu["Fabricante"] == winutil.UNAVAILABLE
    ram = hardware.parse_ram([{"DeviceLocator": "DIMM1", "Capacity": 8 * 1024**3, "ConfiguredClockSpeed": 3200,
                               "SMBIOSMemoryType": 26}, {"DeviceLocator": "DIMM2", "Capacity": 8 * 1024**3}],
                             {"MemoryDevices": 4})
    assert ram["Slots (total)"] == "4" and ram["Slots ocupados"] == "2"
    assert ram["Módulos"][0]["Tipo"] == "DDR4" and ram["Módulos"][1]["Tipo"] == winutil.UNAVAILABLE
    gpu = hardware.parse_gpu([{"Name": "NVIDIA RTX 3060", "AdapterRAM": 4294967295}])
    assert "4 GB" in gpu[0]["VRAM"] and gpu[0]["Temperatura"] == winutil.UNAVAILABLE
    gpu = hardware.parse_gpu([{"Name": "NVIDIA RTX 3060"}], {"NVIDIA RTX 3060": {"vram_mb": 12288, "util": 3, "temp": 41}})
    assert gpu[0]["VRAM"] == "12.0 GB" and gpu[0]["Temperatura"] == "41 °C"
    board = hardware.parse_board([{"Manufacturer": "ASUS", "Product": "B450"}], [{"SMBIOSBIOSVersion": "3001",
                                 "ReleaseDate": "2021-03-01"}], [])
    assert board["BIOS"] == "3001" and board["Modelo"] == "B450"


def test_hardware_collect_survives_failed_cim(monkeypatch):
    monkeypatch.setattr(hardware, "IS_WINDOWS", True)
    monkeypatch.setattr(winutil, "ps_json", lambda *a, **k: None)
    hw = hardware.collect()
    assert hw["cpu"]["Modelo"] == winutil.UNAVAILABLE and hw["notes"]
    assert hardware.flatten(hw)


# ------------------------------------------------------------------ SMART
ATA_OK = {"device": {"name": "/dev/sda", "protocol": "ATA"}, "model_name": "Samsung SSD 860",
          "user_capacity": {"bytes": 500107862016}, "rotation_rate": 0, "smart_status": {"passed": True},
          "temperature": {"current": 34}, "power_on_time": {"hours": 12000},
          "ata_smart_attributes": {"table": [
              {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100, "raw": {"value": 0}},
              {"id": 177, "name": "Wear_Leveling_Count", "value": 97, "raw": {"value": 30}},
              {"id": 197, "name": "Current_Pending_Sector", "value": 100, "raw": {"value": 0}},
              {"id": 199, "name": "UDMA_CRC_Error_Count", "value": 100, "raw": {"value": 0}}]}}


def _ata(raw_overrides=None):
    raw_overrides = raw_overrides or {}
    js = json.loads(json.dumps(ATA_OK))
    for a in js["ata_smart_attributes"]["table"]:
        if a["id"] in raw_overrides:
            a["raw"]["value"] = raw_overrides[a["id"]]
    return js


def test_smart_healthy_ata():
    d = sh.parse_smartctl(ATA_OK)
    assert d.status == sh.HEALTHY and d.media_type == "SSD" and d.metrics["remaining_life_pct"] == 97


def test_single_ambiguous_metric_never_critical():
    d = sh.parse_smartctl(_ata({5: 8}))
    assert d.status == sh.ATTENTION
    assert any("Setores realocados" in r.text and "backup" in r.text.lower() for r in d.reasons)


def test_multiple_signals_escalate_to_critical():
    d = sh.parse_smartctl(_ata({5: 8, 197: 3}))
    assert d.status == sh.CRITICAL


def test_smart_failed_is_critical():
    js = _ata()
    js["smart_status"]["passed"] = False
    assert sh.parse_smartctl(js).status == sh.CRITICAL


def test_crc_errors_are_informational_only():
    d = sh.parse_smartctl(_ata({199: 40}))
    assert d.status == sh.HEALTHY and any(r.severity == "info" for r in d.reasons)


NVME = {"device": {"name": "/dev/nvme0", "protocol": "NVMe"}, "model_name": "WD Black SN770",
        "user_capacity": {"bytes": 1000204886016}, "smart_status": {"passed": True},
        "nvme_smart_health_information_log": {"critical_warning": 0, "temperature": 41, "available_spare": 100,
                                              "available_spare_threshold": 10, "percentage_used": 3,
                                              "power_on_hours": 900, "unsafe_shutdowns": 14, "media_errors": 0}}


def test_nvme_healthy_and_warning_decode():
    d = sh.parse_smartctl(NVME)
    assert d.status == sh.HEALTHY and d.media_type == "NVMe" and d.metrics["percentage_used"] == 3
    bad = json.loads(json.dumps(NVME))
    bad["nvme_smart_health_information_log"]["critical_warning"] = 4
    d = sh.parse_smartctl(bad)
    assert d.status == sh.CRITICAL and "confiabilidade" in d.reasons[0].text
    assert sh.decode_nvme_warning(0b1001) == [sh._NVME_WARN_BITS[0], sh._NVME_WARN_BITS[3]]


def test_nvme_wear_and_low_spare():
    worn = json.loads(json.dumps(NVME))
    worn["nvme_smart_health_information_log"]["percentage_used"] = 91
    assert sh.parse_smartctl(worn).status == sh.ATTENTION
    spare = json.loads(json.dumps(NVME))
    spare["nvme_smart_health_information_log"]["available_spare"] = 5
    assert sh.parse_smartctl(spare).status == sh.CRITICAL


def test_temperature_threshold_depends_on_media():
    assert sh.assess({"smart_passed": True, "temperature_c": 56}, "HDD")[0] == sh.ATTENTION
    assert sh.assess({"smart_passed": True, "temperature_c": 56}, "SSD")[0] == sh.HEALTHY


def test_no_data_is_unknown_not_healthy():
    st, _ = sh.assess({"temperature_c": 30, "power_on_hours": 5}, "SSD")
    assert st == sh.UNKNOWN


def test_windows_inventory_parsing_and_status(monkeypatch):
    rows = [{"DeviceId": "0", "Name": "KINGSTON SA400", "Media": "SSD", "Bus": "SATA", "Size": 480103981056,
             "Health": "Healthy", "Temp": 30, "Wear": 4, "PowerOn": 2000, "ReadErr": 0, "WriteErr": 0},
            {"DeviceId": "1", "Name": "WDC HDD", "Media": "3", "Bus": "11", "Size": 1000204886016,
             "Health": "Warning", "Temp": None, "Wear": None, "PowerOn": None, "ReadErr": None, "WriteErr": None},
            {"DeviceId": "2", "Name": "Mystery", "Media": "Unspecified", "Bus": "USB", "Size": None,
             "Health": "Unknown"}]
    monkeypatch.setattr(sh, "IS_WINDOWS", True)
    monkeypatch.setattr(winutil, "ps_json", lambda *a, **k: rows)
    monkeypatch.setattr(sh.shutil, "which", lambda _n: None)
    d = sh.collect()
    assert [x.status for x in d] == [sh.HEALTHY, sh.ATTENTION, sh.UNKNOWN]
    assert d[1].media_type == "HDD" and d[2].note
    assert sh.issues_for(d)


# ------------------------------------------------------------------ repair
def test_repair_catalog_is_safe():
    assert len({c.id for c in repair.CATALOG}) == len(repair.CATALOG)
    for c in repair.CATALOG:
        assert not ({"/f", "/r", "/x", "/b"} & {a.lower() for a in c.command}), c.id
        assert c.explanation and c.impact and c.duration


@pytest.mark.parametrize("cid,rc,text,expected", [
    ("sfc_scannow", 0, "Windows Resource Protection did not find any integrity violations.", "success"),
    ("sfc_scannow", 0, "A Proteção de Recursos do Windows não encontrou nenhuma violação de integridade.", "success"),
    ("sfc_scannow", 0, "Windows Resource Protection found corrupt files and successfully repaired them.", "warning"),
    ("sfc_scannow", 1, "Windows Resource Protection found corrupt files but was unable to fix some of them.", "failed"),
    ("dism_scan", 0, "No component store corruption detected. The operation completed successfully.", "success"),
    ("dism_scan", 0, "The component store is repairable.", "warning"),
    ("dism_restore", 0, "The restore operation completed successfully.", "success"),
    ("dism_restore", 740, "Error: 740 Elevated permissions are required to run DISM.", "failed"),
    ("chkdsk_ro", 0, "Windows has scanned the file system and found no problems.", "success"),
    ("chkdsk_ro", 0, "Errors found. CHKDSK cannot continue in read-only mode.", "warning"),
    ("dism_check", 5, "unknown output", "failed"),
    ("dism_check", None, "", "failed"),
])
def test_repair_classification(cid, rc, text, expected):
    assert repair.classify_result(cid, rc, text)[0] == expected


def test_repair_action_on_non_windows_never_runs_anything(monkeypatch):
    monkeypatch.setattr(winutil, "IS_WINDOWS", False)
    ran = []
    monkeypatch.setattr(winutil, "run", lambda *a, **k: ran.append(a))
    res = safeaction.run_safe_action(repair.RepairAction(repair.BY_ID["sfc_scannow"]), lambda p: True)
    assert res.status == "failed" and not ran
    assert repair.recent_results()[-1]["target"] == "sfc /scannow"


# ------------------------------------------------------------------ battery
BAT_XML = ('<BatteryReport xmlns="http://schemas.microsoft.com/battery/2012"><Batteries><Battery><Id>X</Id>'
           '<Manufacturer>Foo</Manufacturer><Chemistry>LION</Chemistry><DesignCapacity>50000</DesignCapacity>'
           '<FullChargeCapacity>34000</FullChargeCapacity><CycleCount>412</CycleCount></Battery></Batteries>'
           '</BatteryReport>')


def test_battery_parse_and_assess():
    d = battery.parse_powercfg_xml(BAT_XML)
    assert d["DesignCapacity"] == "50000" and d["CycleCount"] == "412"
    h = battery.health_pct(50000, 34000)
    assert h == 68.0
    issues = battery.assess({"present": True, "health_pct": h, "design_capacity_mwh": 50000,
                             "full_capacity_mwh": 34000})
    assert issues and "68%" in issues[0].detail
    assert battery.assess({"present": True, "health_pct": 95, "design_capacity_mwh": 1, "full_capacity_mwh": 1}) == []
    assert battery.health_pct(0, 10) is None and battery.parse_powercfg_xml("not xml") == {}


def test_battery_cim_parse():
    d = battery.parse_cim({"Static": [{"DesignedCapacity": 40000}], "Full": {"FullChargedCapacity": 30000},
                           "Cycles": [{"CycleCount": 0}]})
    assert d["DesignCapacity"] == 40000 and d["CycleCount"] == 0


# ------------------------------------------------------------------ security
def test_product_state_decode():
    assert security.decode_product_state(397568) == {"enabled": True, "up_to_date": True}
    assert security.decode_product_state(393472)["enabled"] is False
    assert security.decode_product_state(397584) == {"enabled": True, "up_to_date": False}
    assert security.decode_product_state("x") == {"enabled": None, "up_to_date": None}


def test_os_support():
    today = dt.date(2026, 9, 20)
    assert security.os_support(19045, today)["ended"] is True
    assert security.os_support(26100, today)["ended"] is False
    assert security.os_support(12345, today)["ended"] is None and security.os_support(None)["name"]


GOOD = {"Defender": {"AntivirusEnabled": True, "RealTimeProtectionEnabled": True, "AntivirusSignatureAge": 1},
        "AntiVirus": [{"displayName": "Windows Defender", "productState": 397568}],
        "Firewall": [{"Name": "Domain", "Enabled": "True"}, {"Name": "Private", "Enabled": "True"},
                     {"Name": "Public", "Enabled": "True"}],
        "Tpm": {"TpmPresent": True, "TpmReady": True}, "BitLocker": [{"MountPoint": "C:", "Status": "FullyEncrypted",
                                                                      "Protection": "On"}]}


def test_security_clean_config_has_no_issues():
    assert security.assess(GOOD, 1, 1, 26100, portable_device=True) == []
    s = security.summarize(GOOD, 1, 1, 26100)
    assert s["UAC"] == "Ativo" and "Public: ativo" in s["Firewall"]


def test_security_detects_risky_config():
    bad = json.loads(json.dumps(GOOD))
    bad["Firewall"][2]["Enabled"] = "False"
    bad["Defender"]["RealTimeProtectionEnabled"] = False
    bad["BitLocker"][0]["Protection"] = "Off"
    titles = [i.title for i in security.assess(bad, 0, 1, 19045, portable_device=True)]
    assert any("Firewall desativado" in t for t in titles)
    assert any("tempo real" in t for t in titles)
    assert any("UAC" in t for t in titles) and any("BitLocker" in t for t in titles)
    assert any("fora do período" in t for t in titles)
    none_av = {"Defender": {"AntivirusEnabled": False}, "AntiVirus": []}
    assert any(i.severity == "high" for i in security.assess(none_av, 1, 1, 26100))


def test_security_unavailable_when_admin_only_data_missing():
    s = security.summarize({"Defender": None, "Firewall": None, "Tpm": None, "BitLocker": None}, None, None, None)
    assert "administrador" in s["BitLocker"] and s["Firewall"] == winutil.UNAVAILABLE
    assert security.assess({"Defender": None, "Firewall": None}, None, None, None) == []


# ------------------------------------------------------------------ devices / drivers
def test_devices_problem_codes():
    devs = devices.parse_devices([
        {"Name": "Wi-Fi", "PNPClass": "Net", "ConfigManagerErrorCode": 10},
        {"Name": "Old Cam", "PNPClass": "Camera", "ConfigManagerErrorCode": 22},
        {"Name": None, "PNPClass": None, "ConfigManagerErrorCode": 28, "PNPDeviceID": "PCI\\VEN_1234"},
        {"Name": "USB Hub", "PNPClass": "USB", "ConfigManagerErrorCode": 0},
        {"Name": None, "PNPClass": None, "ConfigManagerErrorCode": 0}])
    assert [d["state"] for d in devs] == ["Erro", "Desativado", "Sem driver", "OK", "Desconhecido"]
    assert devs[0]["category"] == "Rede" and "driver" in devs[0]["explanation"].lower()
    assert devices.explain(0) == "" and "999" in devices.explain(999)
    assert len(devices.PROBLEM_CODES) >= 30
    issues = devices.assess(devs, [])
    assert any(i.title.startswith("Wi-Fi") for i in issues)


def test_old_driver_rules_skip_microsoft_inbox_drivers():
    today = dt.date(2026, 9, 20)
    drv = devices.parse_drivers([
        {"DeviceName": "Realtek Audio", "Manufacturer": "Realtek", "DriverVersion": "6.0", "DriverDate": "2015-01-01"},
        {"DeviceName": "PCI Bus", "Manufacturer": "Microsoft", "DriverVersion": "10", "DriverDate": "2006-06-21"},
        {"DeviceName": "New GPU", "Manufacturer": "NVIDIA", "DriverVersion": "5", "DriverDate": "2026-05-01"},
        {"DeviceName": None}], today)
    assert {d["device"]: d["old"] for d in drv} == {"Realtek Audio": True, "PCI Bus": False, "New GPU": False}
    assert devices.support_url("Dell Inc.") == "https://www.dell.com/support" and devices.support_url("NoName") is None


# ------------------------------------------------------------------ diagnostics + report
def test_collect_all_isolates_failures(monkeypatch):
    def boom():
        raise RuntimeError("cim exploded")
    monkeypatch.setattr(hardware, "collect", boom)
    snap = diagnostics.collect_all()
    assert "hardware" in snap["errors"] and "cim" not in json.dumps(snap["errors"]).lower()
    assert snap["storage"] is not None and "system" in snap


def test_full_report_escapes_and_contains_sections():
    snap = {"generated": "2026-09-20T10:00:00", "app_version": "0.1.0", "system": {"Host": "<script>x</script>"},
            "hardware": None, "storage": [sh.parse_smartctl(_ata({5: 8})).to_dict()],
            "battery": {"present": True, "charge_pct": 80, "state": "descarregando", "health_pct": 68.0,
                        "wear_pct": 32.0, "cycle_count": 412, "runtime": "2h"},
            "security": {"summary": {"UAC": "Ativo"}}, "devices": {"problems": [], "message": "",
                                                                      "total_devices": 3, "total_drivers": 3},
            "issues": [{"severity": "high", "area": "Segurança", "title": "T", "detail": "D",
                        "recommendation": "R", "evidence": ""}],
            "errors": {}, "repair_history": [], "recent_actions": []}
    html = report.to_html_full(snap, technician={"customer": "Ana <b>", "reported_issue": "lento"})
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html and "Ana &lt;b&gt;" in html
    for s in ("Saúde dos discos", "Bateria", "Segurança", "Problemas detectados", "@media print"):
        assert s in html
    data = json.loads(report.to_json_full(snap, technician={"customer": "x"}))
    assert data["technician"]["customer"] == "x" and data["issues"]
