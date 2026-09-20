"""P1 pages: health overview, performance, services, stability, Windows Update, before/after, history, safety."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QVBoxLayout, QWidget)

from ..core import (analyzer, audit, diagnostics, performance, restore, safeaction, scoring, services,
                    snapshots, stability, startup, winupdate)
from ..core.issues import SEVERITY_LABEL
from . import icons
from .common import fill_table, make_table, page_header, run_async
from .pages import _btn, _confirm, _page
from .pages_diag import RESULT_LABEL, SEV_COLOR, DataPage
from .theme import BAD, OK, WARN

log = logging.getLogger("syscare.ui")
VERDICT_COLOR = {"melhorou": OK, "piorou": BAD, "igual": "#9ca3af", "não medido": "#9ca3af"}


def full_diagnosis(perf_seconds: float = 0):
    """Worker: complete diagnosis + finalize. Returns the snapshot."""
    snap = diagnostics.collect_all()
    res = analyzer.scan_processes(0.8)
    items = startup.list_startup()
    perf = performance.summarize(performance.sample(perf_seconds), performance.disk_queue_length()) \
        if perf_seconds else None
    return diagnostics.finalize(snap, res, items, perf), len(items), perf


# ---------------------------------------------------------------- Overview
class HealthOverviewPage(DataPage):
    title = "Visão geral da saúde"
    icon = "health"
    subtitle = ("Pontuação profissional com explicação das deduções e recomendações priorizadas. "
                "Áreas sem dados não penalizam a nota.")
    auto_load = False

    def build(self):
        self.refresh_btn.setText("Executar diagnóstico")
        self.refresh_btn.setIcon(icons.icon("scan", 16, "#062026"))
        self.score_lbl = QLabel("Clique em “Executar diagnóstico”.")
        self.score_lbl.setObjectName("title")
        self.lay.addWidget(self.score_lbl)
        self.cat = make_table(["Categoria", "Peso", "Dedução", "Motivos"], stretch_col=3)
        self.cat.setMaximumHeight(280)
        self.lay.addWidget(self.cat)
        self.lay.addWidget(QLabel("Recomendações priorizadas"))
        self.recs = make_table(["Prioridade", "Área", "Achado", "Recomendação", "Evidência"], stretch_col=3)
        self.lay.addWidget(self.recs, 1)

    def load(self):
        return full_diagnosis()[0]

    def render(self, snap):
        self.snap = snap
        sc = snap["score"]
        self.score_lbl.setText(f"Saúde do sistema: {sc['score']}/100  (cobertura: {sc['coverage_pct']}%)")
        fill_table(self.cat, [[r["category"], r["max"], ("-%d" % r["deduction"] if r["deduction"] else "0") if r["evaluated"] else "não avaliado",
                               "; ".join(r["reasons"])] for r in sc["breakdown"]], sortable=False)
        recs = snap["recommendations"]
        fill_table(self.recs, [[SEVERITY_LABEL.get(r["priority"], r["priority"]), r["area"], r["finding"],
                                r["recommendation"], r["reason"]] for r in recs],
                   {i: SEV_COLOR.get(r["priority"], "#9ca3af") for i, r in enumerate(recs)}, sortable=False)
        self.status.setText("" if recs else "Nenhum problema encontrado nas áreas avaliadas.")


# ---------------------------------------------------------------- Performance
class PerformancePage(QWidget):
    DURATION = 15

    def __init__(self):
        super().__init__()
        self._cancel = False
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Desempenho",
            f"Mede CPU, RAM, disco e rede por {self.DURATION} s. O resultado vale apenas para esse intervalo; "
            "com poucas amostras o Observer não faz afirmações.", icon="gauge"))
        bar = QHBoxLayout()
        self.start = _btn(f"Medir por {self.DURATION} s", self.run)
        self.stop = _btn("Cancelar", self.cancel, "ghost")
        self.stop.setEnabled(False)
        bar.addWidget(self.start)
        bar.addWidget(self.stop)
        bar.addStretch()
        lay.addLayout(bar)
        self.prog = QProgressBar()
        self.prog.setVisible(False)
        lay.addWidget(self.prog)
        self.table = make_table(["Indicador", "Média", "p95", "Máximo"], stretch_col=0)
        lay.addWidget(self.table)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        lay.addWidget(self.out)

    def run(self):
        self._cancel = False
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        self.prog.setVisible(True)
        self.prog.setRange(0, self.DURATION)
        self.prog.setValue(0)
        run_async(self._work, self._done, self._fail)

    def cancel(self):
        self._cancel = True

    def _work(self):
        samples = performance.sample(self.DURATION, 1.0, lambda: self._cancel)
        st = performance.summarize(samples, performance.disk_queue_length())
        fs_info, fs_issues = performance.free_space_issue()
        return st, fs_info, performance.assess(st) + fs_issues

    def _fail(self, msg):
        self._reset()
        self.out.setPlainText(msg)

    def _reset(self):
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        self.prog.setVisible(False)

    def _done(self, out):
        self._reset()
        st, fs, issues = out
        rows = []
        for key, lbl in (("cpu", "CPU (%)"), ("mem", "RAM (%)"), ("disk_mbps", "Disco (MB/s)"),
                         ("disk_busy", "Disco ocupado (%)"), ("net_mbps", "Rede (Mb/s)")):
            s = st.get(key)
            rows.append([lbl, s["avg"], s["p95"], s["max"]] if s else [lbl, "Indisponível", "", ""])
        fill_table(self.table, rows, sortable=False)
        lines = []
        if not st["sufficient"]:
            lines.append("Medição interrompida cedo: amostras insuficientes para concluir algo.")
        if fs:
            lines.append(f"Espaço livre em {fs['path']}: {fs['free_gb']} GB ({fs['free_pct']}%).")
        for i in issues:
            lines.append(f"[{SEVERITY_LABEL[i.severity]}] {i.title}: {i.detail}\n   → {i.recommendation}")
        if not issues and st["sufficient"]:
            lines.append("Nenhuma carga elevada detectada neste intervalo.")
        self.out.setPlainText("\n\n".join(lines))


# ---------------------------------------------------------------- Services
class ServicesPage(DataPage):
    title = "Serviços do Windows"
    icon = "gear"
    subtitle = ("Somente serviços de terceiros podem ter a inicialização alterada (com confirmação e Desfazer). "
                "Serviços do Windows e críticos são somente leitura.")

    def build(self):
        self.items: list[dict] = []
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrar por nome…")
        self.filter.textChanged.connect(self._apply)
        self.bar.insertWidget(1, self.filter)
        self.bar.addWidget(_btn("Desfazer último", self.undo, "ghost"))
        self.manual = _btn("Definir como Manual", lambda: self.change("demand"))
        self.disable = _btn("Desativar", lambda: self.change("disabled"), "danger")
        self.bar.addWidget(self.manual)
        self.bar.addWidget(self.disable)
        self.table = make_table(["Serviço", "Nome", "Estado", "Inicialização", "Classe", "Motivo"], stretch_col=5)
        self.lay.addWidget(self.table)

    def load(self):
        return services.list_services()

    def render(self, items):
        self.items = items
        if not items:
            self.status.setText("Lista de serviços disponível apenas no Windows.")
        self._apply()

    def _apply(self):
        q = self.filter.text().lower()
        self.shown = [s for s in self.items if q in s["name"].lower() or q in s["display_name"].lower()]
        fill_table(self.table, [[s["display_name"], s["name"], s["status"], s["start_type"], s["class"], s["reason"]]
                                for s in self.shown],
                   {i: WARN for i, s in enumerate(self.shown) if s["changeable"]})

    def _selected(self):
        r = self.table.currentRow()
        it = self.table.item(r, 1) if r >= 0 else None
        return next((s for s in self.items if it and s["name"] == it.text()), None)

    def change(self, new_type: str):
        svc = self._selected()
        if not svc:
            return
        action = services.ServiceStartTypeAction(svc, new_type)
        analysis, preview, err = safeaction.prepare(action)
        if err or preview is None:
            QMessageBox.information(self, "Serviços", err.message if err else "Falha ao preparar a ação.")
            return
        if not svc["changeable"]:
            QMessageBox.warning(self, "Bloqueado", preview.as_text())
            return
        if not _confirm(self, "Confirmar alteração de serviço", preview.as_text() + "\n\nExecutar agora?"):
            return
        run_async(safeaction.commit, self._done, self._fail_msg, action, analysis, preview)

    def _done(self, res):
        QMessageBox.information(self, "Resultado", f"[{RESULT_LABEL.get(res.status, res.status)}] {res.message}")
        self.refresh()

    def _fail_msg(self, msg):
        QMessageBox.warning(self, "Erro", msg)

    def undo(self):
        run_async(services.undo_last, lambda m: (QMessageBox.information(self, "Desfazer", m), self.refresh()),
                  self._fail_msg)


# ---------------------------------------------------------------- Stability
class StabilityPage(DataPage):
    title = "Estabilidade e telas azuis"
    icon = "warning"
    subtitle = ("Eventos dos últimos 30 dias. Sem analisar o minidump não é possível apontar a causa exata; "
                "os achados indicam causas comuns, não certezas.")

    def build(self):
        self.summary = QLabel("")
        self.lay.addWidget(self.summary)
        self.table = make_table(["Data/hora", "Tipo", "Detalhe"], stretch_col=2)
        self.lay.addWidget(self.table, 2)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.lay.addWidget(self.out, 1)

    def load(self):
        return stability.collect()

    def render(self, rep):
        if rep["message"]:
            self.status.setText(rep["message"])
        self.summary.setText(f"Telas azuis: {len(rep['bugchecks'])} • Desligamentos inesperados: "
                             f"{len(rep['unexpected_shutdowns'])} • Falhas de apps: {len(rep['app_crashes'])} • "
                             f"Falhas de serviços: {len(rep['service_failures'])} • Minidumps: {len(rep['minidumps'])}")
        rows = [[b["time"], "Tela azul", f"{b['code']} {b['name']}"] for b in rep["bugchecks"]]
        rows += [[u["time"], "Desligamento inesperado", f"evento {u['id']}"] for u in rep["unexpected_shutdowns"]]
        rows += [[c["time"], "Falha de aplicativo", f"{c['app']} (módulo {c['module']})"] for c in rep["app_crashes"]]
        rows += [[s["time"], "Falha de serviço", s["service"]] for s in rep["service_failures"]]
        fill_table(self.table, sorted(rows, key=lambda r: str(r[0]), reverse=True))
        self.out.setPlainText("\n\n".join(f"[{SEVERITY_LABEL[i.severity]}] {i.title}\n{i.detail}\n→ {i.recommendation}"
                                          for i in rep["issues"]) or "Nenhum padrão de instabilidade detectado.")


# ---------------------------------------------------------------- Windows Update
class WindowsUpdatePage(DataPage):
    title = "Windows Update"
    icon = "update"
    subtitle = "Diagnóstico somente leitura. A instalação de atualizações é feita pelo próprio Windows Update."

    def build(self):
        self.pending_btn = _btn("Verificar pendentes (usa a internet)", self.check_pending, "ghost")
        self.bar.addWidget(self.pending_btn)
        from ..core import shortcuts
        self.bar.addWidget(_btn("Abrir Windows Update", lambda: self.status.setText(shortcuts.launch("winupdate")[1]),
                                "ghost"))
        self.table = make_table(["Item", "Valor"], stretch_col=1)
        self.lay.addWidget(self.table, 1)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.lay.addWidget(self.out, 1)
        self._pending = False

    def check_pending(self):
        self._pending = True
        self.refresh()

    def load(self):
        want, self._pending = self._pending, False
        return winupdate.collect(check_pending=want)

    def render(self, st):
        rows = [[k, v] for k, v in st["version"].items()]
        rows += [["Última instalação", st["last_install"] or "Indisponível"],
                 ["Última verificação", st["last_search"] or "Indisponível"],
                 ["Reinicialização pendente", ", ".join(st["reboot_reasons"]) or "Não"],
                 ["Erros (30 dias)", len(st["errors"])]]
        if st["pending"] is not None:
            rows.append(["Atualizações pendentes", len(st["pending"])])
            rows += [["  •", p.get("Title", "")] for p in st["pending"][:20]]
        fill_table(self.table, rows, sortable=False)
        msgs = [st["message"]] if st["message"] else []
        msgs += [f"[{SEVERITY_LABEL[i.severity]}] {i.title}: {i.recommendation}" for i in st.get("issues", [])]
        self.out.setPlainText("\n\n".join(msgs))


# ---------------------------------------------------------------- Before / after
class BeforeAfterPage(QWidget):
    def __init__(self):
        super().__init__()
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)
        lay.addWidget(page_header(
            "Antes e depois",
            "Registre o estado ANTES da manutenção, faça o trabalho e meça DEPOIS. Só valores medidos entram "
            "na comparação; nada é estimado.", icon="compare"))
        bar = QHBoxLayout()
        self.b1 = _btn("1. Registrar ANTES", self.take_before)
        self.b2 = _btn("2. Medir DEPOIS e comparar", self.take_after)
        bar.addWidget(self.b1)
        bar.addWidget(self.b2)
        bar.addWidget(_btn("Limpar ANTES", self.clear, "ghost"))
        bar.addStretch()
        lay.addLayout(bar)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.table = make_table(["Indicador", "Antes", "Depois", "Variação", "Resultado"], stretch_col=0)
        lay.addWidget(self.table)
        self._refresh_status()

    def _refresh_status(self):
        b = snapshots.load("before")
        self.status.setText(f"ANTES registrado em {b['taken']}." if b else "Nenhum estado ANTES registrado.")

    def _busy(self, on: bool):
        self.b1.setEnabled(not on)
        self.b2.setEnabled(not on)
        if on:
            self.status.setText("Executando diagnóstico completo…")

    def take_before(self):
        self._busy(True)
        run_async(full_diagnosis, self._before_done, self._fail)

    def _before_done(self, out):
        snap, n, perf = out
        snapshots.save(snapshots.make(snap, snap["score"], n, perf), "before")
        self._busy(False)
        self._refresh_status()

    def take_after(self):
        if not snapshots.load("before"):
            self.status.setText("Registre primeiro o estado ANTES.")
            return
        self._busy(True)
        run_async(full_diagnosis, self._after_done, self._fail)

    def _after_done(self, out):
        snap, n, perf = out
        self._busy(False)
        cmp_ = snap.get("comparison")
        if not cmp_:
            self.status.setText("Sem dados ANTES para comparar.")
            return
        rows = cmp_["rows"]
        fill_table(self.table, [[r["metric"], "—" if r["before"] is None else r["before"],
                                 "—" if r["after"] is None else r["after"],
                                 "—" if r["delta"] is None else r["delta"], r["verdict"]] for r in rows],
                   sortable=False)
        for i, r in enumerate(rows):
            it = self.table.item(i, 4)
            if it:
                from PySide6.QtGui import QColor
                it.setForeground(QColor(VERDICT_COLOR.get(r["verdict"], "#9ca3af")))
        self.status.setText(f"Comparação: {cmp_['before_taken']} → {cmp_['after_taken']}. "
                            "Inclua no Relatório para entregar ao cliente.")

    def _fail(self, msg):
        self._busy(False)
        self.status.setText(msg)

    def clear(self):
        snapshots.clear("before")
        self._refresh_status()


# ---------------------------------------------------------------- History
class HistoryPage(DataPage):
    title = "Histórico e auditoria"
    icon = "clock"
    subtitle = "Registro local de tudo que o Observer alterou ou executou, e atendimentos gerados."

    def build(self):
        self.lay.addWidget(QLabel("Ações registradas (audit.jsonl)"))
        self.table = make_table(["Data/hora", "Ação", "Alvo", "Resultado", "Detalhe"], stretch_col=4)
        self.lay.addWidget(self.table, 2)
        self.lay.addWidget(QLabel("Atendimentos"))
        self.jobs = make_table(["Data", "Cliente", "Equipamento", "Técnico", "Chamado", "Pontuação"], stretch_col=1)
        self.lay.addWidget(self.jobs, 1)

    def load(self):
        return audit.read(300), snapshots.read_jobs()

    def render(self, data):
        entries, jobs = data
        rows = [[e.get("timestamp", ""), e.get("action", ""), e.get("target", ""), e.get("result", ""),
                 str(e.get("message", e.get("details", "")))[:200]] for e in reversed(entries)]
        fill_table(self.table, rows, {i: BAD for i, r in enumerate(rows) if r[3] in ("failed", "blocked")},
                   sortable=False)
        fill_table(self.jobs, [[j.get("saved", ""), j.get("customer", ""), j.get("device", ""),
                                j.get("technician", ""), j.get("ticket", ""), j.get("score", "")] for j in jobs],
                   sortable=False)


# ---------------------------------------------------------------- Safety
class SafetyPage(DataPage):
    title = "Central de segurança de operações"
    icon = "lock"
    subtitle = "Pontos de restauração e o guia de risco de cada tipo de operação."

    def build(self):
        self.bar.addWidget(_btn("Criar ponto de restauração…", self.create))
        self.table = make_table(["Operação", "Risco", "Observação"], stretch_col=2)
        fill_table(self.table, [list(r) for r in restore.RISK_GUIDE], sortable=False)
        self.table.setMaximumHeight(230)
        self.lay.addWidget(self.table)
        self.lay.addWidget(QLabel("Pontos de restauração existentes"))
        self.points = make_table(["Nº", "Descrição", "Criado em"], stretch_col=1)
        self.lay.addWidget(self.points, 1)

    def load(self):
        return restore.list_points()

    def render(self, data):
        self.status.setText(data["message"])
        fill_table(self.points, [[p["id"], p["description"], p["created"]] for p in data["points"]], sortable=False)

    def create(self):
        action = restore.RestorePointAction()
        analysis, preview, err = safeaction.prepare(action)
        if err or preview is None:
            self.status.setText(err.message if err else "Falha ao preparar a ação.")
            return
        if not _confirm(self, "Criar ponto de restauração", preview.as_text() + "\n\nExecutar agora?"):
            return
        self.status.setText("Criando ponto de restauração…")
        run_async(safeaction.commit, self._done, lambda m: self.status.setText(m), action, analysis, preview)

    def _done(self, res):
        self.status.setText(f"[{RESULT_LABEL.get(res.status, res.status)}] {res.message}")
        self.refresh()
