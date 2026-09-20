"""Shared UI helpers: background worker, cards, tables, tool tiles."""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Signal, Slot, Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QProgressBar, QSizePolicy, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import icons
from .theme import ACCENT


log = logging.getLogger("syscare.ui")


class _Bridge(QObject):
    """Delivers worker results to the UI thread (queued signal), never from the worker thread."""
    call = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._invoke)

    @Slot(object, object)
    def _invoke(self, fn, arg):
        try:
            fn(arg)
        except RuntimeError:
            pass  # target widget already destroyed
        except Exception:  # noqa: BLE001
            log.exception("UI callback failed")


_bridge: _Bridge | None = None


def _get_bridge() -> _Bridge:
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()
    return _bridge


def _noop(_arg):
    pass


class Worker(QRunnable):
    """Run fn() off the UI thread; on_done(result) / on_fail(message) run in the UI thread."""

    def __init__(self, fn: Callable, on_done: Callable, on_fail: Callable | None, args, kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.on_done, self.on_fail = on_done, on_fail or _noop
        self.bridge = _get_bridge()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001 - surfaced to the UI, technical detail to the log
            log.exception("background task failed")
            self.bridge.call.emit(self.on_fail, "A operação falhou. Detalhes no log técnico.")
            return
        self.bridge.call.emit(self.on_done, result)


def run_async(fn: Callable, on_done: Callable, on_fail: Callable | None = None, *args, **kwargs) -> Worker:
    w = Worker(fn, on_done, on_fail, args, kwargs)
    QThreadPool.globalInstance().start(w)
    return w


class Card(QFrame):
    def __init__(self, title: str, value: str = "-", with_bar: bool = False, icon: str | None = None):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        if icon:
            mark = QLabel()
            mark.setPixmap(icons.pixmap(icon, 18, ACCENT))
            head.addWidget(mark)
        t = QLabel(title)
        t.setObjectName("muted")
        head.addWidget(t, 1)
        self.value = QLabel(value)
        self.value.setObjectName("cardvalue")
        lay.addLayout(head)
        lay.addWidget(self.value)
        self.bar = None
        if with_bar:
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            lay.addWidget(self.bar)

    def set(self, text: str, pct: float | None = None):
        self.value.setText(text)
        if self.bar is not None and pct is not None:
            self.bar.setValue(int(pct))


def make_table(headers: list[str], stretch_col: int | None = None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeToContents)
    if stretch_col is not None:
        hh.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return t


def fill_table(t: QTableWidget, rows: list[list], colors: dict[int, str] | None = None,
               sortable: bool = True):
    """rows: list of lists of values; numeric values sort numerically."""
    t.setSortingEnabled(False)
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            it = QTableWidgetItem()
            if isinstance(v, (int, float)):
                it.setData(Qt.DisplayRole, float(v) if isinstance(v, float) else v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                it.setText(str(v))
            if colors and r in colors:
                from PySide6.QtGui import QColor
                it.setForeground(QColor(colors[r]))
            t.setItem(r, c, it)
    t.setSortingEnabled(sortable)


class ToolTile(QFrame):
    """Clickable icon + label tile used by Toolbox and dashboard shortcuts."""
    clicked = Signal()

    def __init__(self, label: str, icon: str, hint: str = ""):
        super().__init__()
        self.setObjectName("tool")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(104)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(8)
        mark = QLabel()
        mark.setAlignment(Qt.AlignCenter)
        mark.setPixmap(icons.pixmap(icon, 32, ACCENT))
        mark.setAttribute(Qt.WA_TransparentForMouseEvents)
        title = QLabel(label)
        title.setObjectName("tooltitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(mark)
        lay.addWidget(title)
        if hint:
            sub = QLabel(hint)
            sub.setObjectName("muted")
            sub.setAlignment(Qt.AlignCenter)
            sub.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(sub)
            self.setToolTip(hint)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def sizeHint(self):
        return QSize(160, 108)


def page_header(title: str, subtitle: str = "", icon: str = "") -> QWidget:
    w = QWidget()
    outer = QHBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 8)
    outer.setSpacing(12)
    if icon:
        mark = QLabel()
        mark.setPixmap(icons.pixmap(icon, 28, ACCENT))
        mark.setAlignment(Qt.AlignTop)
        outer.addWidget(mark)
    col = QVBoxLayout()
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(2)
    a = QLabel(title)
    a.setObjectName("title")
    col.addWidget(a)
    if subtitle:
        b = QLabel(subtitle)
        b.setObjectName("muted")
        b.setWordWrap(True)
        col.addWidget(b)
    outer.addLayout(col, 1)
    return w
