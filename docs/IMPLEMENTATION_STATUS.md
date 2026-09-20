# Caslu SysCare — Implementation Status

Legend: `[ ]` pending · `[~]` in progress / partial · `[x]` completed · `[!]` blocked
Read this file first in every new session, then only the files of the next task.

## 0. Audit (Phase 0) — completed

**Stack:** Python 3.10+, PySide6 (Qt, Fusion + QSS dark theme), psutil. No other runtime deps.
**Layout:** `src/syscare/core/` (UI-free logic) · `src/syscare/ui/` (PySide6) · `tests/` (pytest, UI offscreen).
**Baseline (before this work):** ~1,600 LOC, 10 tests passing, flat 7-item sidebar, no logging, no config,
no audit log (only `undo_log.json` for startup changes), Windows-only code isolated with lazy `winreg` imports.

| Area | Existing modules | State |
|---|---|---|
| Process analyzer / health score | `core/analyzer.py`, `core/knowledge.py` | works; score only uses process/RAM/CPU (Phase 24 will fix) |
| Startup manager + undo | `core/startup.py`, `core/actions.py` | works; no impact rating |
| Network basics | `core/network.py` | works; no gateway/traceroute/loss/routing |
| Disk tools | `core/disk.py` | temp cleaner (2 locations) + largest files |
| Software inventory | `core/sysinfo.py` | name/version/publisher only |
| Windows logs | `core/logs.py` | raw text of recent errors |
| Reports | `core/report.py` | basic HTML/JSON (analyzer + startup) |
| Error handling | `ui/common.py Worker` | exceptions caught in worker; subprocess wrappers were ad hoc |
| Permissions | — | no privilege awareness (Phase 29) |

**Key architectural decisions**
1. Every Windows collector = one PowerShell/CIM call (`winutil.ps_json`, `-EncodedCommand`, UTF-8) → **pure parse
   functions** that take plain dicts. Parsers are unit-tested with fixtures; collectors are mocked in tests.
2. No collector raises. Missing data is the string `Indisponível` (`winutil.UNAVAILABLE`); never invented.
3. `core/safeaction.py` implements SCAN → ANALYZE → PREVIEW → CONFIRM → EXECUTE → VERIFY → LOG. New maintenance
   actions must use it. Legacy actions (terminate, disable startup, temp clean) already confirm in the UI and log
   to the audit; migrating them onto `SafeAction` is tracked below.
4. Audit trail = `audit.jsonl` (append-only) in the data dir; `undo_log.json` is kept for undo mechanics.
5. Data dir is portable-aware (`SYSCARE_DATA_DIR`, or a `syscare.portable` marker next to the app).
6. External tools are optional: `smartctl` (smartmontools) enriches SMART data if installed; never bundled/downloaded.

**Risks**
- Windows code paths (CIM/PowerShell/winreg/UAC elevation) were developed on Linux with mocks: **must be validated on
  real Windows 10/11** (admin and non-admin). Items marked `(needs Windows validation)` below.
- PowerShell output/encoding differs by locale (handled: UTF-8 forcing + UTF-16 detection for `sfc`).
- SMART via Windows storage counters is coarse; `smartctl` is the reliable source for ATA attributes.

## Phase matrix

| # | Phase | Status | Notes |
|---|---|---|---|
| 0 | Audit | [x] | this file |
| 1 | Hardware Health | [~] | implemented (`core/hardware.py`, `core/sensors.py`) — needs Windows validation |
| 2 | SMART / storage health | [~] | `core/storage_health.py` (smartctl JSON + Windows storage counters) — needs Windows validation |
| 3 | Temperature monitor | [ ] | sensor reader exists; history/thresholds UI pending |
| 4 | Battery health | [~] | `core/battery.py` (CIM + powercfg XML) — needs Windows validation |
| 5 | Repair center | [~] | `core/repair.py` (SFC/DISM/CHKDSK read-only modes) — needs Windows validation |
| 6 | Windows Update | [~] | `core/winupdate.py` (read-only: last install, reboot pending, errors, optional pending check) — needs Windows validation |
| 7 | Driver center | [~] | `core/devices.py` |
| 8 | Device health | [~] | `core/devices.py` (problem codes 1–52) |
| 9 | Services manager | [~] | `core/services.py`: critical/Windows read-only; third-party start type via SafeAction + undo — needs Windows validation |
| 10 | Security center | [~] | `core/security.py` — needs Windows validation |
| 11 | Restore point / Safety center | [~] | `core/restore.py` + Safety page; Repair page creates a restore point first (aborts if it fails) — needs Windows validation |
| 12 | BSOD / stability | [~] | `core/stability.py` (events 41/6008/1001/7031/7034/1000, minidump list, cautious wording) — needs Windows validation |
| 13 | Performance | [x] | `core/performance.py` (15 s cancellable sampling, avg/p95/max, free space); no claims with <5 samples |
| 14 | Benchmark | [ ] | |
| 15 | Advanced network | [ ] | |
| 16 | Cleanup center | [~] | temp cleaner exists (now audited); categories pending |
| 17 | Storage analyzer | [~] | largest files exists |
| 18 | Duplicate finder | [ ] | |
| 19 | Software audit | [~] | inventory exists; install date/arch pending |
| 20 | Startup impact | [~] | estimate from running process RAM/CPU (Alto/Médio/Baixo/Desconhecido); security tools always Baixo |
| 21 | Toolbox | [~] | `core/shortcuts.py` whitelist + page |
| 22 | Technician mode | [x] | form fields feed report; job history `jobs.jsonl` + History page |
| 23 | Before/After | [x] | `core/snapshots.py` + page; verdict melhorou/piorou/igual/não medido with tolerances |
| 24 | Professional health score | [x] | `core/scoring.py` weighted categories, coverage %, explained deductions; old process score kept in Processes page |
| 25 | Recommendations engine | [x] | `core/recommendations.py` (evidence-based; RAM/SSD upgrade rules need measured load) |
| 26 | Professional reports | [~] | HTML/JSON now include score breakdown, recommendations, performance, stability, Windows Update, before/after |
| 27 | Portable edition | [~] | portable data dir marker implemented; packaging pending |
| 28 | UX/UI | [~] | grouped lazy navigation; remaining leaves added per phase |
| 29 | Admin privileges | [~] | `core/privilege.py` (badges + per-operation UAC elevation) — needs Windows validation |
| 30 | Audit log | [x] | `core/audit.py` |
| 31 | Safe action architecture | [~] | framework done; repair uses it; legacy actions to migrate |
| 32 | Testing | [~] | grows with each phase; all Windows APIs mocked |
| 33 | Error handling | [~] | `winutil` never raises; logging to file added |
| 34 | Dependency policy | [x] | still only PySide6 + psutil |
| 35 | Privacy | [x] | local-first, no telemetry, no network calls except user-triggered ping/DNS/port tests |

## Recommended sequence
P0 (this session): foundations → hardware → SMART → repair → security → drivers/devices → battery → reports/UI.
P1 next: performance → health score v2 + recommendations engine → services → stability/BSOD → Windows Update →
technician history → before/after.
P2: duplicates → benchmark → advanced network → portable packaging → the rest.

## Change log

### Session 1 — P0 (foundations + hardware, SMART, repair, security, drivers/devices, battery, reports, navigation)
Tests: 54 passing (`tests/test_core.py`, `test_p0.py`, `test_ui.py`); all Windows calls mocked, tests use an isolated data dir.

**New files (core):** `config.py` (thresholds, portable data dir, log setup) · `winutil.py` (never-raising command/PowerShell
runner, UTF-16/OEM decoding, `Indisponível` helpers) · `privilege.py` (`is_admin`, per-operation UAC `run_elevated`) ·
`audit.py` (JSONL audit, secret scrubbing) · `issues.py` (shared finding type) · `safeaction.py` (pipeline, `Risk`,
`Preview`, `prepare`/`commit`) · `hardware.py` · `sensors.py` · `storage_health.py` · `repair.py` · `battery.py` ·
`security.py` · `devices.py` (drivers + device problem codes) · `diagnostics.py` (full snapshot, per-section failure
isolation) · `shortcuts.py` (whitelisted Windows utilities).
**New files (ui):** `pages_diag.py` (Hardware, Storage health, Battery, Security, Devices/Drivers, Repair, Reports, Toolbox).
**Modified:** `report.py` (+`to_html_full`/`to_json_full`, print CSS; old functions untouched) · `actions.py` and `disk.py`
(now write to the audit trail) · `ui/common.py` (worker results delivered via queued signal to the UI thread) ·
`ui/main_window.py` (grouped, lazily-built navigation) · `ui/theme.py` · `app.py` (logging).
**Preserved unchanged:** analyzer, knowledge base, startup, network, sysinfo, logs and their pages.

**Decisions**
- Storage classification: CRITICAL only for explicit failure signals (SMART FAILED, NVMe critical warning, spare below
  threshold, Windows `Unhealthy`) or ≥2 independent degradation signals. Single metrics (e.g. reallocated sectors) → ATTENTION.
- Wear ≥ 80% used, temperature (HDD ≥55 °C, SSD ≥70 °C) → ATTENTION only. CRC errors → informational (cable).
- Repair Center exposes only DISM Check/Scan/Restore, SFC verify/scannow, CHKDSK read-only and `/scan`. `/f /r /x` are
  deliberately excluded; a test enforces it.
- Windows support end dates are a small indicative table (Home/Pro) and are worded as such in the UI/report.
- Old-driver flag ignores Microsoft inbox drivers (their dates are old by design) and is informational.

**Needs Windows validation (developed on Linux with mocks)**
1. `Get-CimInstance` field names/JSON shape for `HARDWARE_PS`, `STORAGE_PS`, `SECURITY_PS`, `DEVICES_PS`, `CIM_PS`.
2. `Get-StorageReliabilityCounter` availability without admin; `smartctl --scan --json` device naming on Windows.
3. `privilege.run_elevated` (UAC prompt + output file capture) and `sfc` UTF-16 decoding.
4. Security Center `productState` decoding (estimated) and admin-only checks (TPM, BitLocker).
5. `powercfg /batteryreport /xml` parsing on a real laptop.
Suggested manual check: run each PowerShell script from the modules in a normal and an elevated PowerShell and compare.

**Remaining for P0:** none blocking. Follow-ups: storage inventory rows inside the Hardware page; per-page admin badge on
Storage/Security when data needs elevation; migrate legacy actions (terminate/disable startup/temp clean) to `SafeAction`.

### Session 2 — P1 (performance, score v2, recommendations, services, stability, Windows Update, technician history, before/after, restore point, startup impact)
Tests: 79 passing (`tests/test_p1.py` added). Navigation now has 23 pages.

**New (core):** `performance.py` · `scoring.py` · `recommendations.py` · `services.py` · `stability.py` · `winupdate.py` · `restore.py` · `snapshots.py`.
**New (ui):** `pages_p1.py` (Overview/score, Performance, Services, Stability, Windows Update, Before/After, History, Safety).
**Modified:** `diagnostics.py` (+stability, windows_update, free_space steps; `finalize()` = score + recommendations + comparison) · `report.py` · `startup.py` (impact) · `ui/pages.py` (impact column) · `ui/pages_diag.py` (restore-point checkbox in Repair; Reports use `finalize` and save job history) · `ui/main_window.py`.

**Decisions:** only third-party/unknown services are changeable; score never penalizes unevaluated categories; recommendations for hardware upgrades require measured evidence; failed restore point aborts the repair (a warning = recent point exists, proceeds); performance uses no disk-busy on Windows unless typeperf queue is available (shown as Indisponível otherwise).

**Needs Windows validation:** `Get-WinEvent` shapes/message parsing (EN and PT-BR) in `stability.py`; `Microsoft.Update.AutoUpdate` COM in `winupdate.py`; `psutil.win_service_iter` fields + `sc config` under UAC; `Checkpoint-Computer`/`Get-ComputerRestorePoint`; `typeperf` disk queue; startup impact against real processes.

**Remaining:** Dashboard card for the new score; temperature history (Phase 3); migrate legacy actions to `SafeAction`.

### Session 3 — UX/UI modernization (Phase 28)
Tests: 82 passing. No new runtime deps.

Vector icons (`ui/icons.py`, QPainter) on nav, page headers, buttons, dashboard cards and Toolbox tiles.
Sidebar search filters tools; dashboard “Começar” tiles jump to diagnóstico/processos/limpeza/toolbox.
Theme: charcoal bench + oscilloscope cyan (`#3DB8C5`) + gold brand mark — replaces generic indigo.

### Next (P2)
Duplicates (18) → benchmark (14) → advanced network (15) → cleanup categories (16) → storage analyzer (17) → portable packaging (27).

### (old) Next (P1, done)
1. Performance module + session snapshot (Phase 13) → 2. Health score v2 with per-category deductions (24) and the
recommendations engine (25) on top of `Issue` → 3. Services manager (9) → 4. Stability/BSOD (12) → 5. Windows Update (6)
→ 6. Technician history + Before/After (22, 23) → 7. Restore point (11) and startup impact (20).
