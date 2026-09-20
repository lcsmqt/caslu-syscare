"""Diagnostic pages: hardware, storage health, battery, security, devices, repair, reports, toolbox."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QTabWidget,
                               QVBoxLayout, QWidget)

from ..core import (analyzer, battery, config, devices, diagnostics, hardware, privilege, report, repair,
                    restore, safeaction, snapshots, security, shortcuts, startup, storage_health)
from ..core.issues import SEVERITY_LABEL
from .common import Card, ToolTile, fill_table, make_table, page_header, run_async
from .pages import _btn, _confirm, _page
from .theme import BAD, MUTED, OK, WARN

log = logging.getLogger("syscare.ui")
GRAY = MUTED
STATUS_COLOR = {"HEALTHY": OK, "ATTENTION": WARN, "CRITICAL": BAD, "UNKNOWN": GRAY}
SEV_COLOR = {"high": BAD, "medium": WARN, "low": "#60a5fa", "info": GRAY}
RESULT_LABEL = {"success": "Sucesso", "warning": "Aviso", "failed": "Falha", "blocked": "Bloqueado",
                "cancelled": "Cancelado"}
RESULT_COLOR = {"success": OK, "warning": WARN, "failed": BAD, "blocked": BAD, "cancelled": GRAY}


class DataPage(QWidget):
    """Header + status line + body. Subclasses implement load() -> data and render(data)."""
    title = ""
    subtitle = ""
    icon = ""
    auto_load = True

    def __init__(self):
        super().__init__()
        page, self.lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        self.lay.addWidget(page_header(self.title, self.subtitle, icon=self.icon))
        self.bar = QHBoxLayout()
        self.refresh_btn = _btn("Atualizar", self.refresh)
        self.bar.addWidget(self.refresh_btn)
        self.bar.addStretch()
        self.lay.addLayout(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.lay.addWidget(self.status)
        self.build()
        if self.auto_load:
            self.refresh()

    def build(self):  # pragma: no cover - overridden
        pass

    def load(self):  # runs in a worker thread
        raise NotImplementedError

    def render(self, data):
        raise NotImplementedError

    def refresh(self):
        self.refresh_btn.setEnabled(False)
        self.status.setText("Coletando informações…")
        run_async(self.load, self._ok, self._fail)

    def _ok(self, data):
        self.refresh_btn.setEnabled(True)
        self.status.setText("")
        try:
            self.render(data)
        except Exception:  # noqa: BLE001
            log.exception("render failed in %s", type(self).__name__)
            self.status.setText("Não foi possível exibir os dados desta seção.")

    def _fail(self, msg):
        self.refresh_btn.setEnabled(True)
        self.status.setText(msg)


# ---------------------------------------------------------------- Hardware
class HardwarePage(DataPage):
    title = "Hardware"
    icon = "cpu"
    subtitle = "CPU, memória, GPU e placa-mãe. Valores que o Windows não informa aparecem como “Indisponível”."

    def build(self):
        self.table = make_table(["Componente", "Item", "Valor"], stretch_col=2)
        self.lay.addWidget(self.table)

    def load(self):
        return hardware.collect()

    def render(self, hw):
        fill_table(self.table, hardware.flatten(hw), sortable=False)
        self.status.setText(" ".join(hw.get("notes", [])))


# ---------------------------------------------------------------- Storage health
class StorageHealthPage(DataPage):
    title = "Saúde dos discos"
    icon = "disk"
    subtitle = ("Leitura SMART/NVMe. Um indicador isolado não confirma falha; o Observer nunca executa "
                "operações destrutivas no disco.")

    def build(self):
        self.disks: list[storage_health.DiskHealth] = []
        self.table = make_table(["Disco", "Tipo", "Capacidade", "Estado", "Temp.", "Horas", "Desgaste", "Fonte"],
                                stretch_col=0)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.lay.addWidget(self.table, 2)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.lay.addWidget(self.detail, 1)

    def load(self):
        return storage_health.collect()

    def render(self, disks):
        self.disks = disks
        rows, colors = [], {}
        for i, d in enumerate(disks):
            m = d.metrics
            used, life = m.get("percentage_used"), m.get("remaining_life_pct")
            wear = f"{used:.0f}% usado" if isinstance(used, (int, float)) else \
                f"{life:.0f}% restante" if isinstance(life, (int, float)) else "Indisponível"
            rows.append([d.model, d.media_type, f"{d.capacity_gb or '?'} GB", storage_health.STATUS_LABEL[d.status],
                         f"{m['temperature_c']} °C" if m.get("temperature_c") is not None else "Indisponível",
                         f"{m['power_on_hours']} h" if m.get("power_on_hours") is not None else "Indisponível",
                         wear, d.source])
            colors[i] = STATUS_COLOR[d.status]
        fill_table(self.table, rows, colors, sortable=False)
        if disks:
            self.table.selectRow(0)
        else:
            self.detail.setPlainText("Nenhum disco reportado pelo sistema.")

    def show_detail(self):
        idx = self.table.currentRow()
        if not (0 <= idx < len(self.disks)):
            return
        d = self.disks[idx]
        lines = [f"{d.model} — {storage_health.STATUS_LABEL[d.status]}", f"Interface: {d.interface}   Origem: {d.source}"]
        lines += [f"• {r.text}" for r in d.reasons]
        if not d.reasons and d.status == "HEALTHY":
            lines.append("Nenhum indicador de problema encontrado nos dados disponíveis.")
        if d.note:
            lines.append(d.note)
        self.detail.setPlainText("\n".join(lines))


# ---------------------------------------------------------------- Battery
class BatteryPage(DataPage):
    title = "Bateria"
    icon = "battery"
    subtitle = "Capacidade atual comparada à capacidade original de projeto."

    def build(self):
        g = QGridLayout()
        self.c_charge, self.c_health = Card("Carga atual", with_bar=True, icon="battery"), Card("Saúde da bateria", with_bar=True, icon="health")
        self.c_cycles, self.c_state = Card("Ciclos de carga", icon="clock"), Card("Estado", icon="info")
        for i, c in enumerate((self.c_charge, self.c_health, self.c_cycles, self.c_state)):
            g.addWidget(c, 0, i)
        self.lay.addLayout(g)
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        self.lay.addWidget(self.info)

    def load(self):
        return battery.collect()

    def render(self, b):
        if not b.get("present"):
            self.info.setPlainText(b.get("message", ""))
            for c in (self.c_charge, self.c_health, self.c_cycles, self.c_state):
                c.set("—", 0)
            return
        self.c_charge.set(f"{b['charge_pct']}%", b["charge_pct"])
        h = b.get("health_pct")
        self.c_health.set("Indisponível" if h is None else f"{h:.0f}%", h or 0)
        self.c_cycles.set(str(b.get("cycle_count") or "Indisponível"))
        self.c_state.set(b["state"])
        lines = [f"Capacidade de projeto: {b.get('design_capacity_mwh') or 'Indisponível'} mWh",
                 f"Capacidade plena atual: {b.get('full_capacity_mwh') or 'Indisponível'} mWh",
                 f"Desgaste: {b['wear_pct']}%" if b.get("wear_pct") is not None else "Desgaste: Indisponível",
                 f"Autonomia estimada: {b['runtime']}", f"Química: {b['chemistry']}"]
        lines += [f"\nAtenção: {i.detail} {i.recommendation}" for i in battery.assess(b)]
        if b.get("message"):
            lines.append(b["message"])
        self.info.setPlainText("\n".join(lines))


# ---------------------------------------------------------------- Security
class SecurityPage(DataPage):
    title = "Central de segurança"
    icon = "shield"
    subtitle = "Diagnóstico somente leitura. O Observer não altera configurações de segurança."

    def build(self):
        self.bar.insertWidget(1, _btn("Abrir Segurança do Windows", lambda: self._open("security"), "ghost"))
        self.table = make_table(["Verificação", "Estado"], stretch_col=1)
        self.table.setMaximumHeight(300)
        self.lay.addWidget(self.table)
        self.lay.addWidget(QLabel("Riscos detectados"))
        self.issues = make_table(["Prioridade", "Achado", "Recomendação"], stretch_col=2)
        self.lay.addWidget(self.issues)

    def _open(self, key):
        ok, msg = shortcuts.launch(key)
        self.status.setText(msg)

    def load(self):
        return security.collect(portable_device=bool(battery.collect().get("present")))

    def render(self, data):
        fill_table(self.table, [[k, v] for k, v in data["summary"].items()], sortable=False)
        iss = data["issues"]
        fill_table(self.issues, [[SEVERITY_LABEL[i.severity], i.title, i.recommendation] for i in iss],
                   {n: SEV_COLOR[i.severity] for n, i in enumerate(iss)}, sortable=False)
        self.status.setText(f"{len(iss)} risco(s) detectado(s)." if iss else
                            "Nenhum risco óbvio detectado nas verificações disponíveis.")


# ---------------------------------------------------------------- Devices & drivers
class DevicesPage(DataPage):
    title = "Drivers e dispositivos"
    icon = "usb"
    subtitle = ("Problemas do Gerenciador de Dispositivos. Atualize drivers pelo Windows Update ou pelo site oficial "
                "do fabricante — o Observer não baixa drivers.")

    def build(self):
        self.bar.insertWidget(1, _btn("Windows Update", lambda: self._open("winupdate"), "ghost"))
        self.bar.insertWidget(2, _btn("Gerenciador de Dispositivos", lambda: self._open("devmgmt"), "ghost"))
        self.data = {"devices": [], "drivers": []}
        tabs = QTabWidget()
        self.lay.addWidget(tabs)
        self.problems = make_table(["Dispositivo", "Categoria", "Estado", "Código", "Explicação"], stretch_col=4)
        self.all_dev = make_table(["Dispositivo", "Categoria", "Fabricante", "Estado"], stretch_col=0)
        self.drivers = make_table(["Dispositivo", "Fabricante", "Versão", "Data", "Antigo?"], stretch_col=0)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.only_old = QCheckBox("Mostrar somente drivers antigos de terceiros (informativo)")
        self.only_old.stateChanged.connect(self.render_drivers)
        lay.addWidget(self.only_old)
        lay.addWidget(self.drivers)
        tabs.addTab(self.problems, "Problemas")
        tabs.addTab(self.all_dev, "Todos os dispositivos")
        tabs.addTab(w, "Drivers")

    def _open(self, key):
        self.status.setText(shortcuts.launch(key)[1])

    def load(self):
        return devices.collect()

    def render(self, data):
        self.data = data
        devs = data["devices"]
        bad = [d for d in devs if d["state"] != "OK"]
        fill_table(self.problems, [[d["name"], d["category"], d["state"], d["code"] or "", d["explanation"]]
                                   for d in bad], {i: WARN for i in range(len(bad))})
        fill_table(self.all_dev, [[d["name"], d["category"], d["manufacturer"], d["state"]] for d in devs],
                   {i: WARN for i, d in enumerate(devs) if d["state"] != "OK"})
        self.render_drivers()
        self.status.setText(data["message"] or (f"{len(devs)} dispositivos; {len(bad)} com problema, desativados ou desconhecidos."))

    def render_drivers(self):
        rows = [d for d in self.data["drivers"] if d["old"] or not self.only_old.isChecked()]
        fill_table(self.drivers, [[d["device"], d["manufacturer"], d["version"], d["date"],
                                   f"{d['age_years']:.0f} anos" if d["old"] else ""] for d in rows])


# ---------------------------------------------------------------- Repair center
class RepairPage(QWidget):
    def __init__(self):
        super().__init__()
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Reparo do Windows",
            "Nada é executado sem sua confirmação. Comandos destrutivos do CHKDSK (/f, /r) não são oferecidos.",
            icon="wrench"))
        adm = "sim" if privilege.is_admin() else "não — o Windows pedirá permissão (UAC) ao executar"
        self.admin = QLabel(f"Executando como administrador: {adm}")
        self.admin.setObjectName("muted")
        lay.addWidget(self.admin)
        self.table = make_table(["Ferramenta", "Risco", "Administrador", "Duração", "Impacto"], stretch_col=4)
        rows = [[c.title, safeaction.RISK_LABEL[c.risk], privilege.ADMIN_BADGE if c.needs_admin else "-",
                 c.duration, c.impact] for c in repair.CATALOG]
        fill_table(self.table, rows, sortable=False)
        self.table.setMaximumHeight(260)
        self.table.itemSelectionChanged.connect(self._sel)
        lay.addWidget(self.table)
        self.rp = QCheckBox("Criar ponto de restauração antes (recomendado para risco médio; a operação é "
                            "cancelada se o ponto não puder ser criado)")
        self.rp.setChecked(True)
        lay.addWidget(self.rp)
        bar = QHBoxLayout()
        self.run_btn = _btn("Executar…", self.run)
        self.run_btn.setEnabled(False)
        bar.addWidget(self.run_btn)
        self.info = QLabel("Selecione uma ferramenta.")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        bar.addWidget(self.info, 1)
        lay.addLayout(bar)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        lay.addWidget(self.out)

    def _cmd(self) -> repair.RepairCommand | None:
        r = self.table.currentRow()
        title = self.table.item(r, 0).text() if r >= 0 and self.table.item(r, 0) else None
        return next((c for c in repair.CATALOG if c.title == title), None)

    def _sel(self):
        c = self._cmd()
        self.run_btn.setEnabled(c is not None)
        if c:
            self.info.setText(c.explanation)

    def run(self):
        c = self._cmd()
        if not c:
            return
        action = repair.RepairAction(c)
        analysis, preview, err = safeaction.prepare(action)
        if err or preview is None:
            self.out.setPlainText(err.message if err else "Falha ao preparar a ação.")
            return
        if not _confirm(self, f"Confirmar: {c.title}", preview.as_text() + "\n\nExecutar agora?"):
            self.out.setPlainText("Cancelado.")
            return
        self.run_btn.setEnabled(False)
        self.out.setPlainText("Executando… isso pode levar vários minutos. Não desligue o computador.")
        want_rp = self.rp.isChecked() and c.risk != safeaction.Risk.LOW
        run_async(self._work, self._done, self._fail, action, analysis, preview, want_rp)

    @staticmethod
    def _work(action, analysis, preview, want_rp: bool):
        if want_rp:
            rp = restore.RestorePointAction("Caslu Observer - antes de reparo")
            a, pv, err = safeaction.prepare(rp)
            r = err or safeaction.commit(rp, a, pv)
            if r.status == "failed":
                return safeaction.ActionResult("cancelled", "Operação cancelada: não foi possível criar o ponto de "
                                               f"restauração. {r.message}")
        return safeaction.commit(action, analysis, preview)

    def _done(self, res: safeaction.ActionResult):
        self.run_btn.setEnabled(True)
        self.out.setPlainText(f"[{RESULT_LABEL.get(res.status, res.status)}] {res.message}\n\n{res.output}".strip())

    def _fail(self, msg):
        self.run_btn.setEnabled(True)
        self.out.setPlainText(msg)


# ---------------------------------------------------------------- Reports
class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Relatório profissional",
            "Executa o diagnóstico completo e gera HTML (imprimível em PDF) e JSON. Os dados ficam no seu computador.",
            icon="clipboard"))
        form = QFormLayout()
        self.f = {k: QLineEdit() for k in ("customer", "device", "technician", "ticket")}
        for k, lbl in report.TECH_FIELDS[:4]:
            form.addRow(lbl, self.f[k])
        self.f["reported_issue"] = QPlainTextEdit()
        self.f["actions"] = QPlainTextEdit()
        self.f["diagnosis"] = QPlainTextEdit()
        self.f["recommendations"] = QPlainTextEdit()
        for k, lbl in report.TECH_FIELDS[4:]:
            self.f[k].setMaximumHeight(70)
            form.addRow(lbl, self.f[k])
        lay.addLayout(form)
        self.inc = QCheckBox("Incluir análise de processos e inicialização")
        self.inc.setChecked(True)
        lay.addWidget(self.inc)
        bar = QHBoxLayout()
        self.btn = _btn("Executar diagnóstico e gerar relatório", self.generate)
        bar.addWidget(self.btn)
        bar.addStretch()
        lay.addLayout(bar)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch()

    def _tech(self) -> dict:
        return {k: (w.text() if isinstance(w, QLineEdit) else w.toPlainText()).strip() for k, w in self.f.items()}

    def generate(self):
        self.btn.setEnabled(False)
        self.status.setText("Executando diagnóstico completo… pode levar alguns instantes.")
        include = self.inc.isChecked()
        run_async(self._collect, self._done, self._fail, include)

    @staticmethod
    def _collect(include: bool):
        snap = diagnostics.collect_all()
        res = startup_items = None
        if include:
            res = analyzer.scan_processes(0.8)
            startup_items = startup.list_startup()
        diagnostics.finalize(snap, res, startup_items, None)
        return snap, res, startup_items

    def _fail(self, msg):
        self.btn.setEnabled(True)
        self.status.setText(msg)

    def _done(self, out):
        self.btn.setEnabled(True)
        snap, res, st = out
        tech = self._tech()
        default = str(config.reports_dir() / "relatorio.html")
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", default, "Relatório HTML (*.html)")
        if not path:
            self.status.setText("Diagnóstico concluído; relatório não salvo.")
            return
        p = Path(path)
        try:
            p.write_text(report.to_html_full(snap, res, st, tech), encoding="utf-8")
            p.with_suffix(".json").write_text(report.to_json_full(snap, res, st, tech), encoding="utf-8")
        except OSError as e:
            log.warning("could not save report: %s", e)
            self.status.setText("Não foi possível salvar o relatório nesse local.")
            return
        n = len(snap.get("issues", []))
        if any(tech.values()):
            snapshots.add_job({"customer": tech.get("customer", ""), "device": tech.get("device", ""),
                               "technician": tech.get("technician", ""), "ticket": tech.get("ticket", ""),
                               "score": snap.get("score", {}).get("score"), "report": p.name})
        self.status.setText(f"Relatório salvo: {p.name} (+ .json). {n} achado(s) registrado(s).")


# ---------------------------------------------------------------- Toolbox
_TOOL_ICONS = {
    "taskmgr": "activity", "devmgmt": "usb", "diskmgmt": "disk", "eventvwr": "list",
    "services": "gear", "regedit": "key", "msinfo32": "info", "control": "sliders",
    "settings": "gear", "winupdate": "update", "security": "shield", "cmd": "terminal",
    "powershell": "terminal", "ncpa": "wifi", "sysdm": "monitor", "resmon": "gauge",
}


class ToolboxPage(QWidget):
    def __init__(self):
        super().__init__()
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Caixa de ferramentas do Windows",
            "Atalhos para utilitários oficiais. Nada é instalado — só abre o que já está no Windows.",
            icon="toolbox"))
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (key, (label, _t, admin)) in enumerate(shortcuts.LAUNCHERS.items()):
            tile = ToolTile(label, _TOOL_ICONS.get(key, "wrench"),
                            "Pode pedir administrador" if admin else "")
            tile.clicked.connect(lambda k=key: self._go(k))
            grid.addWidget(tile, i // 4, i % 4)
        lay.addLayout(grid)
        self.status = QLabel("Só atalhos oficiais do Windows. O Observer não baixa nem instala programas.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch()

    def _go(self, key):
        self.status.setText(shortcuts.launch(key)[1])
