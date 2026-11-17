"""Look of the editor: palette, stylesheet and hand-drawn icons.

Nothing here depends on the platform: the style is Qt's own Fusion, colours
come from one table and icons are painted with QPainter, so the window looks
the same on Windows and Linux and needs no system icon theme.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap)
from PySide6.QtWidgets import QProxyStyle, QStyle

CANVAS = "#111216"        # around the game screen
SCREEN = "#1b1d25"        # the game screen mock
WINDOW = "#16171c"
SURFACE = "#1c1e25"       # side panels, bars
RAISED = "#262933"        # buttons, cards
INPUT = "#121318"
HOVER = "#30343f"
PRESSED = "#3a3f4c"
BORDER = "#31343f"
BORDER_STRONG = "#4a4f5f"
TEXT = "#e5e7ee"
MUTED = "#8f95a6"
DISABLED = "#5b6070"
ACCENT = "#e3b45a"        # the warm gold of the game's own UI
ACCENT_HOVER = "#efc573"
ACCENT_TEXT = "#1b1405"
ACCENT_DIM = "#3d3521"
OK = "#62c58c"
WARN = "#f0a04b"
DANGER = "#e8666c"

STYLE = f"""
QMainWindow, QDialog {{ background: {WINDOW}; }}
QToolTip {{ background: #0c0d10; color: {TEXT}; border: 1px solid {BORDER_STRONG};
           padding: 5px 8px; }}

QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; padding: 3px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 5px; }}
QMenuBar::item:selected, QMenuBar::item:pressed {{ background: {HOVER}; }}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; padding: 5px; }}
QMenu::item {{ padding: 6px 26px 6px 30px; border-radius: 5px; }}
QMenu::item:selected {{ background: {PRESSED}; }}
QMenu::item:disabled {{ color: {DISABLED}; }}
QMenu::separator {{ height: 1px; background: {BORDER_STRONG}; margin: 5px 8px; }}
QMenu::icon {{ left: 8px; }}
QMenu::indicator {{ left: 8px; width: 14px; height: 14px; }}

QToolBar {{ background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER};
           padding: 6px 8px; spacing: 2px; }}
QToolBar::separator {{ width: 1px; background: {BORDER}; margin: 5px 7px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
              padding: 5px; }}
QToolButton:hover {{ background: {HOVER}; }}
QToolButton:pressed {{ background: {PRESSED}; }}
QToolButton:checked {{ background: {ACCENT_DIM}; border-color: #6b5a2c; }}
QToolButton:disabled {{ color: {DISABLED}; }}
QToolButton#primary {{ background: {ACCENT}; color: {ACCENT_TEXT}; font-weight: bold;
                      padding: 6px 26px 6px 12px; }}
QToolButton#primary:hover, QToolButton#primary:pressed {{ background: {ACCENT_HOVER}; }}
QToolButton#primary:disabled {{ background: {RAISED}; color: {MUTED};
                               border-color: {BORDER}; }}
QToolButton#primary::menu-indicator {{ subcontrol-position: right center; right: 9px; }}
QToolButton#flat {{ padding: 3px; }}

QPushButton {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
              padding: 6px 14px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled {{ color: {DISABLED}; border-color: {BORDER}; }}
QPushButton:default {{ background: {ACCENT}; color: {ACCENT_TEXT}; border-color: {ACCENT};
                      font-weight: bold; }}
QPushButton:default:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#small {{ padding: 3px 10px; }}

QLineEdit {{ background: {INPUT}; border: 1px solid {BORDER}; border-radius: 6px;
            padding: 5px 8px; selection-background-color: {ACCENT};
            selection-color: {ACCENT_TEXT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QListWidget {{ background: transparent; border: none; outline: 0; }}
QListWidget#panels::item {{ padding: 4px 4px; border-radius: 5px; }}
QListWidget#panels::item:hover {{ background: {RAISED}; }}
QListWidget#panels::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}
QListWidget#cards {{ background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: #3b404e; border-radius: 3px; }}
QScrollBar::handle:hover {{ background: #50566a; }}
QScrollBar::handle:vertical {{ min-height: 30px; margin: 2px; }}
QScrollBar::handle:horizontal {{ min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: {WINDOW}; }}
QGraphicsView {{ border: none; background: {CANVAS}; }}

#sidebar {{ background: {SURFACE}; }}
#docbar {{ background: {WINDOW}; border-bottom: 1px solid {BORDER}; }}
#card {{ background: {RAISED}; border-radius: 8px; }}
QLabel#muted, QLabel#section {{ color: {MUTED}; }}
QLabel#warn {{ color: {WARN}; }}
QLabel#key {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 4px;
             padding: 2px 7px; }}
"""


def palette():
    pal = QPalette()
    roles = {
        QPalette.Window: SURFACE, QPalette.WindowText: TEXT, QPalette.Base: INPUT,
        QPalette.AlternateBase: SURFACE, QPalette.Text: TEXT, QPalette.Button: RAISED,
        QPalette.ButtonText: TEXT, QPalette.BrightText: "#ffffff",
        QPalette.Highlight: ACCENT, QPalette.HighlightedText: ACCENT_TEXT,
        QPalette.ToolTipBase: "#0c0d10", QPalette.ToolTipText: TEXT,
        QPalette.PlaceholderText: DISABLED, QPalette.Link: ACCENT,
        QPalette.Light: "#3a3e4b", QPalette.Midlight: "#30333e", QPalette.Mid: "#22242c",
        QPalette.Dark: "#0e0f12", QPalette.Shadow: "#000000",
    }
    for role, colour in roles.items():
        pal.setColor(role, QColor(colour))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(DISABLED))
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor(PRESSED))
    return pal


class Style(QProxyStyle):
    """Fusion with check boxes that stay readable on the dark surfaces."""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element not in (QStyle.PE_IndicatorCheckBox,
                           QStyle.PE_IndicatorItemViewItemCheck):
            super().drawPrimitive(element, option, painter, widget)
            return
        side = min(option.rect.width(), option.rect.height(), 16)
        box = QRectF(option.rect.center().x() - side / 2 + 1,
                     option.rect.center().y() - side / 2 + 1, side - 1, side - 1)
        enabled = bool(option.state & QStyle.State_Enabled)
        marked = bool(option.state & (QStyle.State_On | QStyle.State_NoChange))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if marked:
            fill = QColor(ACCENT if enabled else PRESSED)
            painter.setPen(QPen(fill, 1))
        else:
            fill = QColor(INPUT)
            hover = enabled and option.state & QStyle.State_MouseOver
            painter.setPen(QPen(QColor(MUTED if hover else
                                       BORDER_STRONG if enabled else BORDER), 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 3.5, 3.5)
        if marked:
            painter.setPen(QPen(QColor(ACCENT_TEXT if enabled else MUTED), 1.8,
                                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x, y, u = box.left(), box.top(), box.width() / 10
            if option.state & QStyle.State_On:
                path = QPainterPath(QPointF(x + 2.4 * u, y + 5.2 * u))
                path.lineTo(x + 4.3 * u, y + 7.2 * u)
                path.lineTo(x + 7.7 * u, y + 3 * u)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
            else:                       # partially checked
                painter.drawLine(QPointF(x + 2.8 * u, y + 5 * u), QPointF(x + 7.2 * u, y + 5 * u))
        painter.restore()


def apply(app):
    """Give the whole application the dark look."""
    style = Style("Fusion")
    style.setParent(app)              # keep the Python object alive with the app
    app.setStyle(style)
    app.setPalette(palette())
    app.setStyleSheet(STYLE)


# ---------------------------------------------------------------- icons
#
# Every icon is drawn on a 20x20 grid with a round 1.6 pen. `p` is a painter
# whose pen and brush are already set: the pen strokes, the brush is a soft
# fill of the same colour for solid parts.

def _poly(p, *points, closed=False):
    path = QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(*pt)
    if closed:
        path.closeSubpath()
    p.drawPath(path)


def _line(p, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _solid(p, x, y, w, h):
    p.drawRoundedRect(QRectF(x, y, w, h), 1, 1)


def _hollow(p):
    p.setBrush(Qt.NoBrush)


def _save(p):
    _hollow(p)
    _poly(p, (3.5, 3.5), (13.5, 3.5), (16.5, 6.5), (16.5, 16.5), (3.5, 16.5), closed=True)
    _poly(p, (6.5, 3.5), (6.5, 7.5), (12, 7.5), (12, 3.5))
    _poly(p, (6.5, 16.5), (6.5, 11.5), (13.5, 11.5), (13.5, 16.5))


def _undo(p):
    _hollow(p)
    _poly(p, (7.5, 4.5), (4, 8), (7.5, 11.5))
    path = QPainterPath(QPointF(4, 8))
    path.lineTo(11.5, 8)
    path.arcTo(QRectF(7, 8, 9, 8), 90, -180)
    path.lineTo(8, 16)
    p.drawPath(path)


def _redo(p):
    p.translate(20, 0)
    p.scale(-1, 1)
    _undo(p)


def _align_left(p):
    _line(p, 3.5, 3, 3.5, 17)
    _solid(p, 6.5, 5, 10, 4)
    _solid(p, 6.5, 11, 6, 4)


def _align_right(p):
    p.translate(20, 0)
    p.scale(-1, 1)
    _align_left(p)


def _align_top(p):
    _line(p, 3, 3.5, 17, 3.5)
    _solid(p, 5, 6.5, 4, 10)
    _solid(p, 11, 6.5, 4, 6)


def _align_bottom(p):
    p.translate(0, 20)
    p.scale(1, -1)
    _align_top(p)


def _pack_row(p):
    _solid(p, 2.5, 6, 15, 8)
    _line(p, 7.5, 6, 7.5, 14)
    _line(p, 12.5, 6, 12.5, 14)


def _pack_col(p):
    _solid(p, 6, 2.5, 8, 15)
    _line(p, 6, 7.5, 14, 7.5)
    _line(p, 6, 12.5, 14, 12.5)


def _eye(p):
    _hollow(p)
    path = QPainterPath(QPointF(2.5, 10))
    path.quadTo(10, 1.5, 17.5, 10)
    path.quadTo(10, 18.5, 2.5, 10)
    p.drawPath(path)
    p.drawEllipse(QPointF(10, 10), 2.3, 2.3)


def _eye_off(p):
    _eye(p)
    _line(p, 4, 16.5, 16, 3.5)


def _ghost(p):
    # A dashed panel outline: "panels hidden in game".
    _hollow(p)
    pen = QPen(p.pen())
    pen.setDashPattern([1.6, 1.9])
    p.setPen(pen)
    p.drawRoundedRect(QRectF(3.5, 5, 13, 10), 1.5, 1.5)


def _magnet(p):
    _hollow(p)
    pen = QPen(p.pen())
    pen.setWidthF(3.4)
    pen.setCapStyle(Qt.FlatCap)
    p.setPen(pen)
    path = QPainterPath(QPointF(5.5, 7.6))
    path.lineTo(5.5, 11)
    path.arcTo(QRectF(5.5, 6.5, 9, 9), 180, 180)
    path.lineTo(14.5, 7.6)
    p.drawPath(path)
    _line(p, 5.5, 3.2, 5.5, 5.8)
    _line(p, 14.5, 3.2, 14.5, 5.8)


def _image(p):
    _hollow(p)
    p.drawRoundedRect(QRectF(3, 4, 14, 12), 1.5, 1.5)
    _poly(p, (3.5, 14), (7.5, 9.5), (10.5, 12.5), (12.5, 10.5), (16.5, 14))
    p.drawEllipse(QPointF(13, 7.5), 1, 1)


def _skill(p):
    _hollow(p)
    p.drawRoundedRect(QRectF(3.5, 3.5, 13, 13), 2, 2)
    p.setBrush(QBrush(p.pen().color()))
    pen = QPen(p.pen())
    pen.setWidthF(0.8)
    p.setPen(pen)
    _poly(p, (11.2, 5.5), (7, 10.8), (9.6, 10.8), (8.6, 14.5), (13, 9.2), (10.4, 9.2),
          closed=True)


def _lens(p):
    _hollow(p)
    p.drawEllipse(QPointF(9, 9), 5.2, 5.2)
    _line(p, 13, 13, 16.8, 16.8)


def _zoom_in(p):
    _lens(p)
    _line(p, 6.8, 9, 11.2, 9)
    _line(p, 9, 6.8, 9, 11.2)


def _zoom_out(p):
    _lens(p)
    _line(p, 6.8, 9, 11.2, 9)


def _fit(p):
    _hollow(p)
    _poly(p, (3.5, 7.5), (3.5, 3.5), (7.5, 3.5))
    _poly(p, (12.5, 3.5), (16.5, 3.5), (16.5, 7.5))
    _poly(p, (16.5, 12.5), (16.5, 16.5), (12.5, 16.5))
    _poly(p, (7.5, 16.5), (3.5, 16.5), (3.5, 12.5))


def _trash(p):
    _hollow(p)
    _line(p, 3.5, 6, 16.5, 6)
    _poly(p, (7.5, 6), (7.5, 3.5), (12.5, 3.5), (12.5, 6))
    _poly(p, (5, 6), (6, 16.5), (14, 16.5), (15, 6))
    _line(p, 8.5, 9, 8.5, 13.5)
    _line(p, 11.5, 9, 11.5, 13.5)


def _pencil(p):
    _hollow(p)
    _poly(p, (4, 16), (4.8, 12.4), (13.2, 4), (16, 6.8), (7.6, 15.2), closed=True)
    _line(p, 11.2, 6, 14, 8.8)


def _copy(p):
    _hollow(p)
    p.drawRoundedRect(QRectF(7, 7, 9.5, 9.5), 1.5, 1.5)
    _poly(p, (4.5, 13), (3.5, 13), (3.5, 3.5), (13, 3.5), (13, 4.5))


def _user(p):
    _hollow(p)
    p.drawEllipse(QPointF(10, 7), 3.2, 3.2)
    path = QPainterPath(QPointF(4, 17))
    path.arcTo(QRectF(4, 11.5, 12, 11), 180, -180)
    p.drawPath(path)


def _monitor(p):
    _hollow(p)
    p.drawRoundedRect(QRectF(3, 4, 14, 9.5), 1.5, 1.5)
    _line(p, 10, 13.5, 10, 16.5)
    _line(p, 6.5, 16.5, 13.5, 16.5)


def _folder(p):
    _hollow(p)
    _poly(p, (3, 5), (8, 5), (10, 7.5), (17, 7.5), (17, 15.5), (3, 15.5), closed=True)


def _download(p):
    _hollow(p)
    _line(p, 10, 3.5, 10, 12.5)
    _poly(p, (6.5, 9), (10, 12.5), (13.5, 9))
    _line(p, 4, 16.5, 16, 16.5)


def _write(p):
    # An arrow going into a slot.
    _hollow(p)
    _poly(p, (11.5, 3.5), (16.5, 3.5), (16.5, 16.5), (11.5, 16.5))
    _line(p, 3, 10, 12, 10)
    _poly(p, (8.8, 6.6), (12.2, 10), (8.8, 13.4))


def _lock(p):
    _solid(p, 5, 9, 10, 7.5)
    _hollow(p)
    path = QPainterPath(QPointF(7, 9))
    path.lineTo(7, 7)
    path.arcTo(QRectF(7, 4, 6, 6), 180, -180)
    path.lineTo(13, 9)
    p.drawPath(path)


def _revert(p):
    _hollow(p)
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 12, 12), 150)
    path.arcTo(QRectF(4, 4, 12, 12), 150, -300)
    p.drawPath(path)
    _poly(p, (2.5, 4.5), (4.6, 7.4), (8, 6.3))


def _keyboard(p):
    _hollow(p)
    p.drawRoundedRect(QRectF(2.5, 5, 15, 10), 1.5, 1.5)
    for x in (5.5, 8.5, 11.5, 14.5):
        p.drawPoint(QPointF(x, 8.5))
    _line(p, 6.5, 12, 13.5, 12)


_ICONS = {
    "save": _save, "undo": _undo, "redo": _redo, "align_left": _align_left,
    "align_right": _align_right, "align_top": _align_top, "align_bottom": _align_bottom,
    "pack_row": _pack_row, "pack_col": _pack_col, "eye": _eye, "eye_off": _eye_off,
    "ghost": _ghost, "magnet": _magnet, "image": _image, "skill": _skill,
    "search": _lens, "zoom_in": _zoom_in, "zoom_out": _zoom_out, "fit": _fit,
    "trash": _trash, "pencil": _pencil, "copy": _copy, "user": _user,
    "monitor": _monitor, "folder": _folder, "download": _download, "write": _write,
    "lock": _lock, "revert": _revert, "keyboard": _keyboard,
}
_cache = {}


def pixmap(name, colour=TEXT, size=20, scale=2):
    """One icon as a pixmap of `size` logical pixels."""
    pix = QPixmap(size * scale, size * scale)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size * scale / 20, size * scale / 20)
    stroke = QColor(colour)
    fill = QColor(stroke)
    fill.setAlpha(70)
    p.setPen(QPen(stroke, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(fill))
    _ICONS[name](p)
    p.end()
    pix.setDevicePixelRatio(scale)
    return pix


def icon(name, colour=TEXT, on=ACCENT, disabled=DISABLED):
    """A QIcon with normal, disabled and checked states."""
    key = (name, colour, on, disabled)
    if key not in _cache:
        ic = QIcon()
        for scale in (1, 2, 3):
            ic.addPixmap(pixmap(name, colour, scale=scale), QIcon.Normal, QIcon.Off)
            ic.addPixmap(pixmap(name, on, scale=scale), QIcon.Normal, QIcon.On)
            ic.addPixmap(pixmap(name, disabled, scale=scale), QIcon.Disabled, QIcon.Off)
            ic.addPixmap(pixmap(name, disabled, scale=scale), QIcon.Disabled, QIcon.On)
        _cache[key] = ic
    return _cache[key]
