"""All application pages."""
from __future__ import annotations

import csv

import psutil
from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from ..core import actions, analyzer, disk, logs, network, report, startup, sysinfo
from . import icons
from .common import Card, ToolTile, fill_table, make_table, page_header, run_async
from .theme import BAD, OK, WARN

_BTN_ICONS = {
    "Analisar agora": "scan",
    "Encerrar selecionados": "stop",
    "Exportar HTML": "export",
    "Exportar JSON": "export",
    "Atualizar": "refresh",
    "Desfazer último": "undo",
    "Desativar selecionado": "stop",
    "Ping": "activity",
    "DNS": "wifi",
    "Portas comuns": "network",
    "Buscar temporários (>24h)": "scan",
    "Limpar temporários": "broom",
    "Maiores arquivos": "disk",
    "Carregar": "refresh",
    "Exportar CSV": "export",
    "Carregar erros recentes": "document",
    "Executar diagnóstico": "scan",
    "Abrir Segurança do Windows": "shield",
    "Windows Update": "update",
    "Gerenciador de Dispositivos": "usb",
    "Executar…": "play",
    "Executar diagnóstico e gerar relatório": "clipboard",
    "Cancelar": "stop",
    "Definir como Manual": "sliders",
    "Desativar": "stop",
    "Verificar pendentes (usa a internet)": "scan",
    "Abrir Windows Update": "update",
    "1. Registrar ANTES": "clock",
    "2. Medir DEPOIS e comparar": "compare",
    "Limpar ANTES": "broom",
    "Criar ponto de restauração…": "lock",
}


def _page() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    w.setObjectName("page")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(12)
    return w, lay


def _btn(text: str, cb, kind: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    name = _BTN_ICONS.get(text)
    if name is None and text.startswith("Medir por"):
        name = "gauge"
    if name:
        color = "#fff" if kind == "danger" else ("#E8F0F4" if kind == "ghost" else "#062026")
        b.setIcon(icons.icon(name, 16, color))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(cb)
    return b


def _confirm(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.Yes


def _score_color(s: int) -> str:
    return OK if s >= 75 else WARN if s >= 50 else BAD


# ---------------------------------------------------------------- Dashboard
class DashboardPage(QWidget):
    def __init__(self, get_score):
        super().__init__()
        self.get_score = get_score
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header("Painel", "Visão em tempo real da máquina.", icon="dashboard"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self.cpu = Card("CPU", with_bar=True, icon="cpu")
        self.ram = Card("Memória", with_bar=True, icon="activity")
        self.dsk = Card("Disco principal", with_bar=True, icon="disk")
        self.score = Card("Saúde do sistema", icon="health")
        for i, c in enumerate((self.cpu, self.ram, self.dsk, self.score)):
            grid.addWidget(c, 0, i)
        lay.addLayout(grid)
        shortcuts_lbl = QLabel("Começar")
        shortcuts_lbl.setObjectName("muted")
        lay.addWidget(shortcuts_lbl)
        tiles = QGridLayout()
        tiles.setSpacing(10)
        for i, (label, ic, key, hint) in enumerate((
            ("Diagnóstico", "scan", "overview", "Nota profissional de saúde"),
            ("Processos", "activity", "analyzer", "O que está consumindo a máquina"),
            ("Limpeza", "broom", "disk", "Temporários e espaço em disco"),
            ("Ferramentas", "toolbox", "toolbox", "Atalhos oficiais do Windows"),
        )):
            tile = ToolTile(label, ic, hint)
            tile.clicked.connect(lambda k=key: self._go(k))
            tiles.addWidget(tile, 0, i)
        lay.addLayout(tiles)
        info = QLabel("Informações do sistema")
        info.setObjectName("muted")
        lay.addWidget(info)
        self.table = make_table(["Item", "Valor"], stretch_col=1)
        lay.addWidget(self.table)
        fill_table(self.table, [[k, v] for k, v in sysinfo.summary().items()], sortable=False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        psutil.cpu_percent(None)
        self.refresh()

    def refresh(self):
        c = psutil.cpu_percent(None)
        m = psutil.virtual_memory().percent
        self.cpu.set(f"{c:.0f}%", c)
        self.ram.set(f"{m:.0f}%", m)
        try:
            d = psutil.disk_usage("C:\\" if sysinfo.IS_WINDOWS else "/")
            self.dsk.set(f"{d.percent:.0f}%", d.percent)
        except OSError:
            pass
        s = self.get_score()
        self.score.set("—" if s is None else f"{s}/100")
        if s is not None:
            self.score.value.setStyleSheet(f"color:{_score_color(s)}")

    def _go(self, key: str):
        w = self.window()
        if hasattr(w, "go"):
            w.go(key)


# ---------------------------------------------------------------- Analyzer
class AnalyzerPage(QWidget):
    def __init__(self, on_result):
        super().__init__()
        self.on_result = on_result
        self.result: analyzer.ScanResult | None = None
        self.rows: list[analyzer.Finding] = []
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Analisador de desempenho",
            "Encontra programas desnecessários que consomem CPU/RAM. Nada é encerrado sem a sua confirmação; "
            "processos críticos do sistema são protegidos.", icon="activity"))
        bar = QHBoxLayout()
        self.scan_btn = _btn("Analisar agora", self.scan)
        self.only = QCheckBox("Mostrar só desnecessários e a revisar")
        self.only.setChecked(True)
        self.only.stateChanged.connect(self.render)
        self.kill_btn = _btn("Encerrar selecionados", self.kill, "danger")
        self.kill_btn.setEnabled(False)
        bar.addWidget(self.scan_btn)
        bar.addWidget(self.only)
        bar.addStretch()
        bar.addWidget(_btn("Exportar HTML", lambda: self.export("html"), "ghost"))
        bar.addWidget(_btn("Exportar JSON", lambda: self.export("json"), "ghost"))
        bar.addWidget(self.kill_btn)
        lay.addLayout(bar)
        self.summary = QLabel("Clique em “Analisar agora”.")
        self.summary.setObjectName("muted")
        lay.addWidget(self.summary)
        self.table = make_table(["Programa", "Categoria", "CPU %", "RAM MB", "Proc.", "Risco", "Motivo"], stretch_col=6)
        self.table.itemSelectionChanged.connect(self._sel)
        lay.addWidget(self.table)

    def scan(self):
        self.scan_btn.setEnabled(False)
        self.summary.setText("Analisando processos...")
        run_async(analyzer.scan_processes, self._done, self._fail)

    def _fail(self, msg):
        self.scan_btn.setEnabled(True)
        self.summary.setText(f"Erro: {msg}")

    def _done(self, res: analyzer.ScanResult):
        self.scan_btn.setEnabled(True)
        self.result = res
        self.on_result(res)
        self.summary.setText(
            f"Saúde: {res.health_score}/100  •  {len(res.unnecessary)} desnecessários  •  "
            f"{len(res.review)} para revisar  •  RAM recuperável: {res.reclaimable_mem_mb:.0f} MB  •  "
            f"análise em {res.duration_s:.1f}s")
        self.render()

    def render(self):
        if not self.result:
            return
        fs = self.result.findings
        if self.only.isChecked():
            fs = [f for f in fs if f.category in ("Desnecessário", "Revisar")]
        self.rows = fs
        risk = {"safe": "baixo", "caution": "atenção", "none": "-"}
        colors = {i: (WARN if f.category == "Revisar" else BAD if f.category == "Desnecessário" else "#e5e7eb")
                  for i, f in enumerate(fs)}
        fill_table(self.table, [[f.name, f.category, round(f.cpu, 1), round(f.mem_mb),
                                 len(f.pids), risk[f.risk], f.reason] for f in fs], colors)

    def _selected(self) -> list[analyzer.Finding]:
        names = {self.table.item(i.row(), 0).text() for i in self.table.selectedIndexes()}
        return [f for f in self.rows if f.name in names]

    def _sel(self):
        self.kill_btn.setEnabled(bool(self._selected()))

    def kill(self):
        sel = [f for f in self._selected() if f.category != "Essencial"]
        if not sel:
            return
        listing = "\n".join(f"• {f.name} ({f.mem_mb:.0f} MB)" for f in sel[:15])
        if not _confirm(self, "Encerrar programas",
                        f"Encerrar estes programas?\n\n{listing}\n\nTrabalho não salvo neles será perdido."):
            return
        total, errs = 0, []
        for f in sel:
            k, e = actions.terminate_group(f.name, f.pids)
            total += k
            errs += e
        msg = f"{total} processo(s) encerrado(s)."
        if errs:
            msg += "\n\n" + "\n".join(errs[:8])
        QMessageBox.information(self, "Concluído", msg)
        self.scan()

    def export(self, kind: str):
        if not self.result:
            QMessageBox.information(self, "Exportar", "Faça uma análise primeiro.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", f"relatorio.{kind}", f"*.{kind}")
        if not path:
            return
        st = startup.list_startup()
        data = report.to_html(self.result, st) if kind == "html" else report.to_json(self.result, st)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(data)
        QMessageBox.information(self, "Exportar", f"Relatório salvo em:\n{path}")


# ---------------------------------------------------------------- Startup
class StartupPage(QWidget):
    def __init__(self):
        super().__init__()
        self.items: list[startup.StartupItem] = []
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header("Programas de inicialização",
                                  "O que abre junto com o sistema. Desativar é reversível (botão Desfazer).",
                                  icon="power"))
        bar = QHBoxLayout()
        bar.addWidget(_btn("Atualizar", self.load, "ghost"))
        bar.addStretch()
        bar.addWidget(_btn("Desfazer último", self.undo, "ghost"))
        self.dis = _btn("Desativar selecionado", self.disable, "danger")
        bar.addWidget(self.dis)
        lay.addLayout(bar)
        self.table = make_table(["Nome", "Origem", "Impacto (estim.)", "Sinalizado", "Comando", "Motivo"], stretch_col=5)
        lay.addWidget(self.table)
        self.load()

    def load(self):
        run_async(startup.list_startup, self._loaded, lambda m: None)

    def _loaded(self, items):
        self.items = items
        fill_table(self.table, [[i.name, i.location, i.impact, "sim" if i.flagged else "", i.command[:120],
                                 i.reason or i.impact_reason]
                                for i in items], {n: WARN for n, i in enumerate(items) if i.flagged})

    def disable(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        names = {self.table.item(r, 0).text() for r in rows}
        sel = [i for i in self.items if i.name in names]
        if not sel or not _confirm(self, "Desativar", "Desativar " + ", ".join(names) + " na inicialização?"):
            return
        msgs = []
        for i in sel:
            try:
                msgs.append(actions.disable_startup(i))
            except Exception as e:  # noqa: BLE001
                msgs.append(f"{i.name}: {e}")
        QMessageBox.information(self, "Resultado", "\n".join(msgs))
        self.load()

    def undo(self):
        QMessageBox.information(self, "Desfazer", actions.undo_last())
        self.load()


# ---------------------------------------------------------------- Network
class NetworkPage(QWidget):
    def __init__(self):
        super().__init__()
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Rede", "Diagnóstico para suporte. Teste portas apenas em máquinas suas ou autorizadas.",
            icon="network"))
        tabs = QTabWidget()
        lay.addWidget(tabs)

        self.ifaces = make_table(["Interface", "IPv4", "IPv6", "MAC", "Ativa", "Mbps"], stretch_col=2)
        w1, l1 = QWidget(), QVBoxLayout()
        w1.setLayout(l1)
        l1.addWidget(_btn("Atualizar", self.load_ifaces, "ghost"))
        l1.addWidget(self.ifaces)
        tabs.addTab(w1, "Interfaces")

        w2, l2 = QWidget(), QVBoxLayout()
        w2.setLayout(l2)
        row = QHBoxLayout()
        self.host = QLineEdit("8.8.8.8")
        self.host.setPlaceholderText("host ou IP")
        row.addWidget(self.host, 1)
        row.addWidget(_btn("Ping", self.do_ping))
        row.addWidget(_btn("DNS", self.do_dns, "ghost"))
        row.addWidget(_btn("Portas comuns", self.do_ports, "ghost"))
        l2.addLayout(row)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        l2.addWidget(self.out)
        tabs.addTab(w2, "Ping / DNS / Portas")

        self.listen = make_table(["Porta", "Endereço", "PID", "Processo"], stretch_col=3)
        w3, l3 = QWidget(), QVBoxLayout()
        w3.setLayout(l3)
        l3.addWidget(_btn("Atualizar", self.load_listen, "ghost"))
        l3.addWidget(self.listen)
        tabs.addTab(w3, "Portas em escuta")
        self.load_ifaces()
        self.load_listen()

    def load_ifaces(self):
        fill_table(self.ifaces, [[i["name"], i["ipv4"], i["ipv6"], i["mac"], "sim" if i["up"] else "não", i["speed"]]
                                 for i in network.interfaces()])

    def load_listen(self):
        run_async(network.listening_ports, lambda r: fill_table(
            self.listen, [[x["port"], x["address"], x["pid"], x["process"]] for x in r]))

    def _run(self, fn, fmt):
        h = self.host.text().strip()
        self.out.setPlainText("Executando...")
        run_async(fn, lambda r: self.out.setPlainText(fmt(r)), lambda m: self.out.setPlainText(f"Erro: {m}"), h)

    def do_ping(self):
        self._run(network.ping, str)

    def do_dns(self):
        self._run(network.dns_lookup, str)

    def do_ports(self):
        self._run(network.check_ports, lambda r: "\n".join(
            f"{x['port']:>5}  {x['service']:<10} {x['state']:<18} {x['ms']} ms" for x in r))


# ---------------------------------------------------------------- Disk
class DiskPage(QWidget):
    def __init__(self):
        super().__init__()
        self.temp_files: list = []
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header("Disco", "Espaço, limpeza de temporários (com prévia) e maiores arquivos.",
                                  icon="broom"))
        self.parts = make_table(["Ponto", "Sistema", "Total GB", "Usado GB", "Uso %"])
        self.parts.setMaximumHeight(160)
        lay.addWidget(self.parts)
        fill_table(self.parts, [[d["mount"], d["fs"], d["total_gb"], d["used_gb"], d["percent"]] for d in sysinfo.disks()])
        row = QHBoxLayout()
        self.scan_btn = _btn("Buscar temporários (>24h)", self.scan_temp)
        self.clean_btn = _btn("Limpar temporários", self.clean, "danger")
        self.clean_btn.setEnabled(False)
        row.addWidget(self.scan_btn)
        row.addWidget(self.clean_btn)
        row.addStretch()
        self.path = QLineEdit(str(__import__("pathlib").Path.home()))
        row.addWidget(self.path, 1)
        row.addWidget(_btn("Maiores arquivos", self.big, "ghost"))
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        lay.addWidget(self.status)
        self.table = make_table(["Arquivo", "Tamanho"], stretch_col=0)
        lay.addWidget(self.table)

    def scan_temp(self):
        self.status.setText("Buscando...")
        run_async(disk.scan_temp, self._temp_done)

    def _temp_done(self, files):
        self.temp_files = files
        total = sum(s for _, s in files)
        self.status.setText(f"{len(files)} arquivos temporários, {disk.human(total)} recuperáveis.")
        fill_table(self.table, [[str(p), disk.human(s)] for p, s in sorted(files, key=lambda x: -x[1])[:200]])
        self.clean_btn.setEnabled(bool(files))

    def clean(self):
        total = sum(s for _, s in self.temp_files)
        if not _confirm(self, "Limpar", f"Apagar {len(self.temp_files)} arquivos ({disk.human(total)})? Não vai para a lixeira."):
            return
        n, freed = disk.clean(self.temp_files)
        self.status.setText(f"{n} arquivos apagados, {disk.human(freed)} liberados.")
        self.temp_files = []
        self.clean_btn.setEnabled(False)

    def big(self):
        self.status.setText("Procurando arquivos grandes...")
        run_async(disk.largest_files, lambda r: (
            self.status.setText(f"{len(r)} arquivos ≥ 50 MB encontrados."),
            fill_table(self.table, [[p, disk.human(s)] for p, s in r])), None, self.path.text())


# ---------------------------------------------------------------- Inventory
class InventoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.data: list[dict] = []
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header("Inventário de software", "Programas instalados — útil para auditoria e licenças.",
                                  icon="box"))
        row = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrar por nome...")
        self.filter.textChanged.connect(self.render)
        row.addWidget(self.filter, 1)
        row.addWidget(_btn("Carregar", self.load))
        row.addWidget(_btn("Exportar CSV", self.export, "ghost"))
        lay.addLayout(row)
        self.table = make_table(["Nome", "Versão", "Fabricante"], stretch_col=0)
        lay.addWidget(self.table)

    def load(self):
        run_async(sysinfo.installed_software, self._loaded, lambda m: None)

    def _loaded(self, data):
        self.data = data
        self.render()

    def render(self):
        q = self.filter.text().lower()
        rows = [d for d in self.data if q in d["name"].lower()]
        fill_table(self.table, [[d["name"], d["version"], d["publisher"]] for d in rows])

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salvar CSV", "inventario.csv", "*.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["name", "version", "publisher"])
            w.writeheader()
            w.writerows(self.data)


# ---------------------------------------------------------------- Logs
class LogsPage(QWidget):
    def __init__(self):
        super().__init__()
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header("Logs do sistema", "Erros recentes (Event Viewer no Windows, journalctl no Linux).",
                                  icon="document"))
        lay.addWidget(_btn("Carregar erros recentes", self.load))
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        lay.addWidget(self.out)

    def load(self):
        self.out.setPlainText("Carregando...")
        run_async(logs.recent_errors, self.out.setPlainText)
