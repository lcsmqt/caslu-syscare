from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMainWindow, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import APP_NAME, BRAND_SHORT, __version__
from ..core import privilege
from . import icons, pages, pages_diag, pages_p1
from .theme import ACCENT, MUTED

log = logging.getLogger("syscare.ui")


class _SearchFocus(QObject):
    def __init__(self, box: QWidget):
        super().__init__(box)
        self._box = box

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            self._box.setProperty("active", True)
        elif event.type() == QEvent.FocusOut:
            self._box.setProperty("active", False)
        if event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self._box.style().unpolish(self._box)
            self._box.style().polish(self._box)
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(icons.window_icon())
        self.resize(1280, 820)
        self.score: int | None = None

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(268)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 12, 0, 8)
        sl.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(16, 4, 16, 4)
        brand_row.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(icons.pixmap("app", 28, ACCENT))
        brand_col = QVBoxLayout()
        brand_col.setContentsMargins(0, 0, 0, 0)
        brand_col.setSpacing(0)
        brand = QLabel(BRAND_SHORT)
        brand.setObjectName("brand")
        tag = QLabel("monitoramento")
        tag.setObjectName("brandtag")
        brand_col.addWidget(brand)
        brand_col.addWidget(tag)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_col, 1)
        sl.addLayout(brand_row)

        search_box = QWidget()
        search_box.setObjectName("navsearchbox")
        search_lay = QHBoxLayout(search_box)
        search_lay.setContentsMargins(10, 0, 8, 0)
        search_lay.setSpacing(8)
        search_icon = QLabel()
        search_icon.setPixmap(icons.pixmap("search", 16, MUTED))
        search_icon.setFixedSize(16, 16)
        search_icon.setAlignment(Qt.AlignCenter)
        self.search = QLineEdit()
        self.search.setObjectName("navsearch")
        self.search.setPlaceholderText("Buscar ferramenta…")
        self.search.setClearButtonEnabled(True)
        self.search.setFrame(False)
        self.search.textChanged.connect(self._filter_nav)
        self.search.installEventFilter(_SearchFocus(search_box))
        search_lay.addWidget(search_icon)
        search_lay.addWidget(self.search, 1)
        sl.addWidget(search_box)

        self.nav = QTreeWidget()
        self.nav.setObjectName("nav")
        self.nav.setHeaderHidden(True)
        self.nav.setIndentation(12)
        self.nav.setRootIsDecorated(False)
        self.nav.setExpandsOnDoubleClick(False)
        self.nav.setAnimated(True)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setUniformRowHeights(True)
        sl.addWidget(self.nav, 1)
        admin = "administrador" if privilege.is_admin() else "usuário padrão"
        ver = QLabel(f"v{__version__}  ·  {admin}")
        ver.setObjectName("muted")
        ver.setContentsMargins(16, 4, 16, 8)
        sl.addWidget(ver)

        self.stack = QStackedWidget()
        self._factories: dict[str, Callable[[], QWidget]] = {}
        self._built: dict[str, int] = {}
        self._leaves: list[QTreeWidgetItem] = []

        D, P = pages_diag, pages_p1
        structure = [
            ("Painel", "dashboard", "dashboard", lambda: pages.DashboardPage(lambda: self.score)),
            ("Saúde", None, "pulse", [
                ("Visão geral e nota", "overview", "health", P.HealthOverviewPage),
                ("Hardware", "hardware", "cpu", D.HardwarePage),
                ("Discos (SMART)", "storage", "disk", D.StorageHealthPage),
                ("Bateria", "battery", "battery", D.BatteryPage),
                ("Desempenho", "performance", "gauge", P.PerformancePage),
                ("Estabilidade / BSOD", "stability", "warning", P.StabilityPage),
            ]),
            ("Windows", None, "monitor", [
                ("Windows Update", "winupdate", "update", P.WindowsUpdatePage),
                ("Reparo (SFC/DISM)", "repair", "wrench", D.RepairPage),
                ("Serviços", "services", "gear", P.ServicesPage),
                ("Drivers e dispositivos", "devices", "usb", D.DevicesPage),
                ("Software instalado", "inventory", "box", pages.InventoryPage),
                ("Logs", "logs", "document", pages.LogsPage),
            ]),
            ("Segurança", None, "shield", [
                ("Central de segurança", "security", "shield", D.SecurityPage),
            ]),
            ("Manutenção", None, "broom", [
                ("Processos", "analyzer", "activity", lambda: pages.AnalyzerPage(self._set_score)),
                ("Inicialização", "startup", "power", pages.StartupPage),
                ("Limpeza e armazenamento", "disk", "broom", pages.DiskPage),
            ]),
            ("Rede", None, "wifi", [
                ("Ferramentas de rede", "network", "network", pages.NetworkPage),
            ]),
            ("Técnico", None, "clipboard", [
                ("Relatório", "reports", "clipboard", D.ReportsPage),
                ("Antes e depois", "beforeafter", "compare", P.BeforeAfterPage),
                ("Histórico e auditoria", "history", "clock", P.HistoryPage),
                ("Segurança de operações", "safety", "lock", P.SafetyPage),
            ]),
            ("Ferramentas", None, "toolbox", [
                ("Caixa de ferramentas", "toolbox", "toolbox", D.ToolboxPage),
            ]),
        ]
        for label, key, ic, content in structure:
            top = QTreeWidgetItem(self.nav, [label])
            top.setIcon(0, icons.icon(ic, 18, MUTED))
            if key:  # leaf at top level
                self._register(top, key, content)
            else:
                top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
                for sub_label, sub_key, sub_ic, factory in content:
                    child = QTreeWidgetItem(top, [sub_label])
                    child.setIcon(0, icons.icon(sub_ic, 18, MUTED))
                    self._register(child, sub_key, factory)
                top.setExpanded(True)
        self.nav.itemClicked.connect(self._clicked)
        self.nav.currentItemChanged.connect(lambda cur, _prev: self._show(cur))

        lay.addWidget(side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.nav.setCurrentItem(self._leaves[0])

    def _register(self, item: QTreeWidgetItem, key: str, factory: Callable[[], QWidget]):
        item.setData(0, Qt.UserRole, key)
        self._factories[key] = factory
        self._leaves.append(item)

    def _clicked(self, item: QTreeWidgetItem):
        if item.childCount():
            item.setExpanded(not item.isExpanded())

    def _show(self, item: QTreeWidgetItem | None):
        key = item.data(0, Qt.UserRole) if item else None
        if not key:
            return
        if key not in self._built:  # lazy: pages (and their collectors) start on first visit
            try:
                w = self._factories[key]()
            except Exception:  # noqa: BLE001
                log.exception("could not build page %s", key)
                w = QLabel("Não foi possível abrir esta seção. Detalhes no log técnico.")
                w.setAlignment(Qt.AlignCenter)
            self._built[key] = self.stack.addWidget(w)
        self.stack.setCurrentIndex(self._built[key])

    def _filter_nav(self, text: str):
        q = text.strip().lower()
        for i in range(self.nav.topLevelItemCount()):
            top = self.nav.topLevelItem(i)
            if top.childCount() == 0:
                top.setHidden(bool(q) and q not in top.text(0).lower())
                continue
            visible = False
            group_hit = bool(q) and q in top.text(0).lower()
            for j in range(top.childCount()):
                child = top.child(j)
                hit = (not q) or group_hit or q in child.text(0).lower()
                child.setHidden(not hit)
                visible = visible or hit
            top.setHidden(bool(q) and not visible)
            if q and visible:
                top.setExpanded(True)

    def leaf_keys(self) -> list[str]:
        return [i.data(0, Qt.UserRole) for i in self._leaves]

    def go(self, key: str):
        for it in self._leaves:
            if it.data(0, Qt.UserRole) == key:
                self.nav.setCurrentItem(it)
                return

    def _set_score(self, res):
        self.score = res.health_score
