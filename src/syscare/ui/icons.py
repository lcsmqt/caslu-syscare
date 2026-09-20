"""Vector UI icons drawn with QPainter — no image assets or extra deps."""
from __future__ import annotations

from math import cos, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

# Default stroke matches the theme accent (scope-cyan).
DEFAULT = "#3DB8C5"


def _pen(color: str, width: float = 1.7) -> QPen:
    p = QPen(QColor(color))
    p.setWidthF(width)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def _r(size: float, m: float = 0.18) -> QRectF:
    return QRectF(size * m, size * m, size * (1 - 2 * m), size * (1 - 2 * m))


def _stroke(p: QPainter, color: str, w: float = 1.7):
    p.setPen(_pen(color, w))
    p.setBrush(Qt.NoBrush)


def _fill(p: QPainter, color: str):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))


def _app(p, s, c):
    r = _r(s, 0.12)
    _stroke(p, c, 1.6)
    p.drawRoundedRect(r, s * 0.16, s * 0.16)
    y = s * 0.52
    pts = [QPointF(s * 0.28, y), QPointF(s * 0.38, y), QPointF(s * 0.46, s * 0.32),
           QPointF(s * 0.56, s * 0.68), QPointF(s * 0.64, y), QPointF(s * 0.74, y)]
    path = QPainterPath(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.drawPath(path)


def _dashboard(p, s, c):
    _stroke(p, c)
    g, gap = s * 0.28, s * 0.08
    x0, y0 = s * 0.2, s * 0.2
    p.drawRoundedRect(QRectF(x0, y0, g, g), 2, 2)
    p.drawRoundedRect(QRectF(x0 + g + gap, y0, g, g), 2, 2)
    p.drawRoundedRect(QRectF(x0, y0 + g + gap, g, g), 2, 2)
    p.drawRoundedRect(QRectF(x0 + g + gap, y0 + g + gap, g, g), 2, 2)


def _pulse(p, s, c):
    _stroke(p, c, 1.8)
    y = s * 0.5
    pts = [QPointF(s * 0.14, y), QPointF(s * 0.30, y), QPointF(s * 0.40, s * 0.22),
           QPointF(s * 0.52, s * 0.78), QPointF(s * 0.62, y), QPointF(s * 0.86, y)]
    path = QPainterPath(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.drawPath(path)


def _cpu(p, s, c):
    r = _r(s, 0.28)
    _stroke(p, c)
    p.drawRoundedRect(r, 2.5, 2.5)
    inner = r.adjusted(s * 0.08, s * 0.08, -s * 0.08, -s * 0.08)
    p.drawRect(inner)
    m = s * 0.08
    for t in (0.38, 0.5, 0.62):
        p.drawLine(QPointF(s * t, r.top() - m), QPointF(s * t, r.top()))
        p.drawLine(QPointF(s * t, r.bottom()), QPointF(s * t, r.bottom() + m))
        p.drawLine(QPointF(r.left() - m, s * t), QPointF(r.left(), s * t))
        p.drawLine(QPointF(r.right(), s * t), QPointF(r.right() + m, s * t))


def _disk(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(_r(s, 0.22), s * 0.12, s * 0.12)
    p.drawEllipse(QRectF(s * 0.42, s * 0.40, s * 0.16, s * 0.16))
    p.drawLine(QPointF(s * 0.32, s * 0.70), QPointF(s * 0.68, s * 0.70))


def _battery(p, s, c):
    _stroke(p, c)
    body = QRectF(s * 0.18, s * 0.32, s * 0.56, s * 0.36)
    p.drawRoundedRect(body, 3, 3)
    p.drawRoundedRect(QRectF(body.right(), s * 0.42, s * 0.08, s * 0.16), 1.5, 1.5)
    _fill(p, c)
    p.drawRoundedRect(QRectF(s * 0.24, s * 0.38, s * 0.28, s * 0.24), 1.5, 1.5)


def _gauge(p, s, c):
    _stroke(p, c, 1.8)
    r = QRectF(s * 0.18, s * 0.22, s * 0.64, s * 0.64)
    p.drawArc(r, 30 * 16, 120 * 16)
    p.drawLine(QPointF(s * 0.5, s * 0.58), QPointF(s * 0.70, s * 0.34))
    p.drawEllipse(QRectF(s * 0.45, s * 0.53, s * 0.10, s * 0.10))


def _warning(p, s, c):
    _stroke(p, c, 1.8)
    path = QPainterPath()
    path.moveTo(s * 0.50, s * 0.16)
    path.lineTo(s * 0.86, s * 0.82)
    path.lineTo(s * 0.14, s * 0.82)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.50, s * 0.38), QPointF(s * 0.50, s * 0.58))
    p.drawPoint(QPointF(s * 0.50, s * 0.70))


def _update(p, s, c):
    _stroke(p, c, 1.8)
    p.drawArc(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 40 * 16, 240 * 16)
    p.drawLine(QPointF(s * 0.72, s * 0.22), QPointF(s * 0.72, s * 0.40))
    p.drawLine(QPointF(s * 0.72, s * 0.22), QPointF(s * 0.54, s * 0.28))


def _wrench(p, s, c):
    _stroke(p, c, 1.9)
    path = QPainterPath()
    path.moveTo(s * 0.28, s * 0.28)
    path.quadTo(s * 0.18, s * 0.18, s * 0.32, s * 0.18)
    path.quadTo(s * 0.42, s * 0.22, s * 0.40, s * 0.34)
    path.lineTo(s * 0.78, s * 0.72)
    path.quadTo(s * 0.86, s * 0.80, s * 0.74, s * 0.82)
    path.lineTo(s * 0.36, s * 0.44)
    p.drawPath(path)
    p.drawEllipse(QRectF(s * 0.22, s * 0.22, s * 0.16, s * 0.16))


def _gear(p, s, c):
    _stroke(p, c)
    p.drawEllipse(QRectF(s * 0.32, s * 0.32, s * 0.36, s * 0.36))
    p.drawEllipse(QRectF(s * 0.42, s * 0.42, s * 0.16, s * 0.16))
    for deg in range(0, 360, 45):
        a = radians(deg)
        p.drawLine(QPointF(s * 0.5 + cos(a) * s * 0.22, s * 0.5 + sin(a) * s * 0.22),
                   QPointF(s * 0.5 + cos(a) * s * 0.34, s * 0.5 + sin(a) * s * 0.34))


def _usb(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(QRectF(s * 0.38, s * 0.14, s * 0.24, s * 0.22), 2, 2)
    p.drawRoundedRect(QRectF(s * 0.30, s * 0.34, s * 0.40, s * 0.52), 4, 4)
    p.drawLine(QPointF(s * 0.42, s * 0.48), QPointF(s * 0.42, s * 0.66))
    p.drawLine(QPointF(s * 0.58, s * 0.48), QPointF(s * 0.58, s * 0.66))


def _box(p, s, c):
    _stroke(p, c)
    p.drawRect(QRectF(s * 0.22, s * 0.38, s * 0.56, s * 0.44))
    path = QPainterPath()
    path.moveTo(s * 0.22, s * 0.38)
    path.lineTo(s * 0.50, s * 0.18)
    path.lineTo(s * 0.78, s * 0.38)
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.50, s * 0.82))


def _document(p, s, c):
    _stroke(p, c)
    path = QPainterPath()
    path.moveTo(s * 0.32, s * 0.16)
    path.lineTo(s * 0.58, s * 0.16)
    path.lineTo(s * 0.74, s * 0.32)
    path.lineTo(s * 0.74, s * 0.84)
    path.lineTo(s * 0.32, s * 0.84)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.58, s * 0.16), QPointF(s * 0.58, s * 0.32))
    p.drawLine(QPointF(s * 0.58, s * 0.32), QPointF(s * 0.74, s * 0.32))
    p.drawLine(QPointF(s * 0.40, s * 0.50), QPointF(s * 0.66, s * 0.50))
    p.drawLine(QPointF(s * 0.40, s * 0.62), QPointF(s * 0.66, s * 0.62))
    p.drawLine(QPointF(s * 0.40, s * 0.74), QPointF(s * 0.58, s * 0.74))


def _shield(p, s, c):
    _stroke(p, c, 1.8)
    path = QPainterPath()
    path.moveTo(s * 0.50, s * 0.14)
    path.lineTo(s * 0.80, s * 0.28)
    path.lineTo(s * 0.80, s * 0.52)
    path.quadTo(s * 0.80, s * 0.78, s * 0.50, s * 0.88)
    path.quadTo(s * 0.20, s * 0.78, s * 0.20, s * 0.52)
    path.lineTo(s * 0.20, s * 0.28)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.38, s * 0.52), QPointF(s * 0.48, s * 0.62))
    p.drawLine(QPointF(s * 0.48, s * 0.62), QPointF(s * 0.66, s * 0.42))


def _activity(p, s, c):
    _stroke(p, c, 1.8)
    p.drawRoundedRect(_r(s, 0.16), 4, 4)
    y = s * 0.58
    pts = [QPointF(s * 0.26, y), QPointF(s * 0.36, y), QPointF(s * 0.44, s * 0.36),
           QPointF(s * 0.54, s * 0.70), QPointF(s * 0.62, y), QPointF(s * 0.74, y)]
    path = QPainterPath(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.drawPath(path)


def _power(p, s, c):
    _stroke(p, c, 1.9)
    p.drawArc(QRectF(s * 0.22, s * 0.24, s * 0.56, s * 0.56), 55 * 16, 250 * 16)
    p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.50, s * 0.48))


def _broom(p, s, c):
    _stroke(p, c, 1.8)
    p.drawLine(QPointF(s * 0.32, s * 0.78), QPointF(s * 0.70, s * 0.22))
    p.drawLine(QPointF(s * 0.22, s * 0.62), QPointF(s * 0.46, s * 0.86))
    p.drawLine(QPointF(s * 0.22, s * 0.62), QPointF(s * 0.30, s * 0.78))
    p.drawLine(QPointF(s * 0.46, s * 0.86), QPointF(s * 0.32, s * 0.78))


def _wifi(p, s, c):
    _stroke(p, c, 1.8)
    p.drawArc(QRectF(s * 0.18, s * 0.28, s * 0.64, s * 0.64), 40 * 16, 100 * 16)
    p.drawArc(QRectF(s * 0.30, s * 0.40, s * 0.40, s * 0.40), 40 * 16, 100 * 16)
    p.drawEllipse(QRectF(s * 0.46, s * 0.68, s * 0.08, s * 0.08))


def _clipboard(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(QRectF(s * 0.26, s * 0.22, s * 0.48, s * 0.64), 3, 3)
    p.drawRoundedRect(QRectF(s * 0.36, s * 0.14, s * 0.28, s * 0.14), 2, 2)
    p.drawLine(QPointF(s * 0.36, s * 0.48), QPointF(s * 0.64, s * 0.48))
    p.drawLine(QPointF(s * 0.36, s * 0.60), QPointF(s * 0.64, s * 0.60))


def _compare(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(QRectF(s * 0.16, s * 0.22, s * 0.30, s * 0.56), 3, 3)
    p.drawRoundedRect(QRectF(s * 0.54, s * 0.22, s * 0.30, s * 0.56), 3, 3)
    p.drawLine(QPointF(s * 0.50, s * 0.30), QPointF(s * 0.50, s * 0.70))


def _clock(p, s, c):
    _stroke(p, c, 1.8)
    p.drawEllipse(_r(s, 0.16))
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.50, s * 0.32))
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.66, s * 0.58))


def _lock(p, s, c):
    _stroke(p, c, 1.8)
    p.drawRoundedRect(QRectF(s * 0.28, s * 0.46, s * 0.44, s * 0.36), 4, 4)
    p.drawArc(QRectF(s * 0.34, s * 0.22, s * 0.32, s * 0.32), 0, 180 * 16)
    p.drawLine(QPointF(s * 0.34, s * 0.38), QPointF(s * 0.34, s * 0.46))
    p.drawLine(QPointF(s * 0.66, s * 0.38), QPointF(s * 0.66, s * 0.46))


def _toolbox(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(QRectF(s * 0.16, s * 0.40, s * 0.68, s * 0.42), 4, 4)
    path = QPainterPath()
    path.moveTo(s * 0.34, s * 0.40)
    path.lineTo(s * 0.34, s * 0.28)
    path.lineTo(s * 0.66, s * 0.28)
    path.lineTo(s * 0.66, s * 0.40)
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.16, s * 0.56), QPointF(s * 0.84, s * 0.56))


def _folder(p, s, c):
    _stroke(p, c)
    path = QPainterPath()
    path.moveTo(s * 0.18, s * 0.34)
    path.lineTo(s * 0.18, s * 0.78)
    path.lineTo(s * 0.82, s * 0.78)
    path.lineTo(s * 0.82, s * 0.40)
    path.lineTo(s * 0.48, s * 0.40)
    path.lineTo(s * 0.40, s * 0.28)
    path.lineTo(s * 0.18, s * 0.28)
    path.closeSubpath()
    p.drawPath(path)


def _refresh(p, s, c):
    _update(p, s, c)


def _scan(p, s, c):
    _stroke(p, c, 1.8)
    p.drawEllipse(QRectF(s * 0.20, s * 0.18, s * 0.48, s * 0.48))
    p.drawLine(QPointF(s * 0.58, s * 0.60), QPointF(s * 0.78, s * 0.82))


def _stop(p, s, c):
    _stroke(p, c, 1.8)
    p.drawEllipse(_r(s, 0.16))
    p.drawLine(QPointF(s * 0.34, s * 0.34), QPointF(s * 0.66, s * 0.66))
    p.drawLine(QPointF(s * 0.66, s * 0.34), QPointF(s * 0.34, s * 0.66))


def _terminal(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(_r(s, 0.16), 4, 4)
    p.drawLine(QPointF(s * 0.30, s * 0.40), QPointF(s * 0.42, s * 0.50))
    p.drawLine(QPointF(s * 0.42, s * 0.50), QPointF(s * 0.30, s * 0.60))
    p.drawLine(QPointF(s * 0.48, s * 0.62), QPointF(s * 0.68, s * 0.62))


def _sliders(p, s, c):
    _stroke(p, c, 1.8)
    for x, y in ((0.32, 0.42), (0.50, 0.62), (0.68, 0.34)):
        p.drawLine(QPointF(s * x, s * 0.20), QPointF(s * x, s * 0.80))
        p.drawEllipse(QRectF(s * x - s * 0.06, s * y - s * 0.06, s * 0.12, s * 0.12))


def _info(p, s, c):
    _stroke(p, c, 1.8)
    p.drawEllipse(_r(s, 0.16))
    p.drawLine(QPointF(s * 0.50, s * 0.46), QPointF(s * 0.50, s * 0.70))
    p.drawPoint(QPointF(s * 0.50, s * 0.36))


def _key(p, s, c):
    _stroke(p, c, 1.8)
    p.drawEllipse(QRectF(s * 0.18, s * 0.30, s * 0.32, s * 0.32))
    p.drawLine(QPointF(s * 0.48, s * 0.46), QPointF(s * 0.84, s * 0.46))
    p.drawLine(QPointF(s * 0.72, s * 0.46), QPointF(s * 0.72, s * 0.60))
    p.drawLine(QPointF(s * 0.82, s * 0.46), QPointF(s * 0.82, s * 0.56))


def _list(p, s, c):
    _stroke(p, c, 1.8)
    for y in (0.30, 0.50, 0.70):
        p.drawEllipse(QRectF(s * 0.20, s * y - s * 0.04, s * 0.08, s * 0.08))
        p.drawLine(QPointF(s * 0.36, s * y), QPointF(s * 0.80, s * y))


def _monitor(p, s, c):
    _stroke(p, c)
    p.drawRoundedRect(QRectF(s * 0.16, s * 0.20, s * 0.68, s * 0.48), 3, 3)
    p.drawLine(QPointF(s * 0.50, s * 0.68), QPointF(s * 0.50, s * 0.78))
    p.drawLine(QPointF(s * 0.34, s * 0.80), QPointF(s * 0.66, s * 0.80))


def _network(p, s, c):
    _stroke(p, c, 1.7)
    p.drawEllipse(QRectF(s * 0.22, s * 0.18, s * 0.56, s * 0.64))
    p.drawEllipse(QRectF(s * 0.38, s * 0.18, s * 0.24, s * 0.64))
    p.drawLine(QPointF(s * 0.22, s * 0.50), QPointF(s * 0.78, s * 0.50))


def _export(p, s, c):
    _stroke(p, c, 1.8)
    p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.50, s * 0.58))
    p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.38, s * 0.32))
    p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.62, s * 0.32))
    path = QPainterPath()
    path.moveTo(s * 0.24, s * 0.50)
    path.lineTo(s * 0.24, s * 0.82)
    path.lineTo(s * 0.76, s * 0.82)
    path.lineTo(s * 0.76, s * 0.50)
    p.drawPath(path)


def _undo(p, s, c):
    _stroke(p, c, 1.8)
    p.drawArc(QRectF(s * 0.22, s * 0.26, s * 0.56, s * 0.52), 40 * 16, 250 * 16)
    p.drawLine(QPointF(s * 0.28, s * 0.22), QPointF(s * 0.28, s * 0.40))
    p.drawLine(QPointF(s * 0.28, s * 0.22), QPointF(s * 0.44, s * 0.28))


def _search(p, s, c):
    _scan(p, s, c)


def _dot(p, s, c):
    _stroke(p, c)
    p.drawEllipse(QRectF(s * 0.38, s * 0.38, s * 0.24, s * 0.24))


def _check(p, s, c):
    _stroke(p, c, 2.0)
    path = QPainterPath()
    path.moveTo(s * 0.22, s * 0.52)
    path.lineTo(s * 0.42, s * 0.72)
    path.lineTo(s * 0.80, s * 0.30)
    p.drawPath(path)


def _play(p, s, c):
    _stroke(p, c, 1.8)
    path = QPainterPath()
    path.moveTo(s * 0.34, s * 0.22)
    path.lineTo(s * 0.78, s * 0.50)
    path.lineTo(s * 0.34, s * 0.78)
    path.closeSubpath()
    p.drawPath(path)


def _health(p, s, c):
    _pulse(p, s, c)


_DRAW = {
    "app": _app, "dashboard": _dashboard, "pulse": _pulse, "health": _health,
    "cpu": _cpu, "disk": _disk, "battery": _battery, "gauge": _gauge,
    "warning": _warning, "update": _update, "wrench": _wrench, "gear": _gear,
    "usb": _usb, "box": _box, "document": _document, "shield": _shield,
    "activity": _activity, "power": _power, "broom": _broom, "wifi": _wifi,
    "clipboard": _clipboard, "compare": _compare, "clock": _clock, "lock": _lock,
    "toolbox": _toolbox, "folder": _folder, "refresh": _refresh, "scan": _scan,
    "stop": _stop, "terminal": _terminal, "sliders": _sliders, "info": _info,
    "key": _key, "list": _list, "monitor": _monitor, "network": _network,
    "export": _export, "undo": _undo, "search": _search, "dot": _dot,
    "check": _check, "play": _play,
}

NAMES = tuple(_DRAW)


def pixmap(name: str, size: int = 20, color: str = DEFAULT) -> QPixmap:
    dpr = 2
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(dpr, dpr)
    _DRAW.get(name, _dot)(p, float(size), color)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int = 20, color: str = DEFAULT, selected: str = "#062026") -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, color), QIcon.Normal, QIcon.Off)
    ic.addPixmap(pixmap(name, size, selected), QIcon.Selected)
    ic.addPixmap(pixmap(name, size, color), QIcon.Active)
    return ic


def window_icon() -> QIcon:
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64):
        ic.addPixmap(pixmap("app", sz, DEFAULT))
    return ic
