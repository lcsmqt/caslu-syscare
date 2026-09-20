import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QApplication

from syscare.ui.common import ToolTile
from syscare.ui.icons import NAMES, icon, pixmap, window_icon
from syscare.ui.main_window import MainWindow
from syscare.ui.pages_diag import ToolboxPage
from syscare.ui.theme import QSS


def _app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    return app


def test_every_page_builds_and_shows():
    app = _app()
    w = MainWindow()
    keys = w.leaf_keys()
    assert len(keys) == 23
    for k in keys:
        w.go(k)
        assert w.stack.currentWidget() is not None
        assert "Não foi possível abrir" not in getattr(w.stack.currentWidget(), "text", lambda: "")()
    QThreadPool.globalInstance().waitForDone(15000)
    for _ in range(50):
        app.processEvents()
    w.close()


def test_icons_render_and_window_icon():
    _app()
    assert "toolbox" in NAMES and "dashboard" in NAMES
    for name in NAMES:
        px = pixmap(name, 24)
        assert not px.isNull()
        assert px.width() >= 24
        assert not icon(name, 18).isNull()
    assert not window_icon().isNull()
    fallback = pixmap("not-a-real-icon", 16)
    assert not fallback.isNull()


def test_nav_has_icons_and_search_filters():
    _app()
    w = MainWindow()
    assert w.nav.topLevelItemCount() >= 8
    for i in range(w.nav.topLevelItemCount()):
        assert not w.nav.topLevelItem(i).icon(0).isNull()
    leaves_with_icons = sum(1 for it in w._leaves if not it.icon(0).isNull())
    assert leaves_with_icons == len(w._leaves)

    w._filter_nav("rede")
    hidden_groups = [w.nav.topLevelItem(i).text(0)
                     for i in range(w.nav.topLevelItemCount())
                     if w.nav.topLevelItem(i).isHidden()]
    assert "Painel" in hidden_groups
    visible = [w.nav.topLevelItem(i).text(0)
               for i in range(w.nav.topLevelItemCount())
               if not w.nav.topLevelItem(i).isHidden()]
    assert "Rede" in visible

    w._filter_nav("")
    assert all(not w.nav.topLevelItem(i).isHidden() for i in range(w.nav.topLevelItemCount()))
    w.close()


def test_toolbox_uses_icon_tiles():
    _app()
    page = ToolboxPage()
    tiles = page.findChildren(ToolTile)
    assert len(tiles) >= 16
    assert all(t.cursor().shape() == Qt.PointingHandCursor for t in tiles)
    page.close()
