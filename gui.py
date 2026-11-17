"""PySide6 editor for BDO UI presets: drag panels on a canvas, keep a library."""

import sys
import threading
import time

from PySide6.QtCore import (QByteArray, QObject, QPointF, QRectF, QSize, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QIcon,
                           QImage, QKeySequence, QPainter, QPainterPath, QPen,
                           QPixmap, QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
                               QGraphicsItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QSpinBox, QSplitter, QStyle,
                               QStyledItemDelegate, QToolButton, QVBoxLayout,
                               QWidget)

import core
import panels
import theme

COLORS = {
    "quick": QColor(90, 170, 255),
    "cooldown": QColor(255, 170, 70),
    "chat": QColor(120, 210, 140),
    "other": QColor(190, 150, 240),
}
SNAP_DIST = 6
SCENE_MARGIN = 200          # room around the screen for panels that stick out
ROLE_EL = Qt.UserRole
ROLE_KIND = Qt.UserRole + 1
ROLE_CARD = Qt.UserRole + 2

SHORTCUTS = (
    ("Canvas", (
        ("Drag", "Move a panel; edges snap to other panels and the screen border"),
        ("Arrows / Shift+Arrows", "Nudge the selection by 1 / 10 units"),
        ("Ctrl+click, drag on empty space", "Select several panels"),
        ("Mouse wheel", "Zoom at the cursor"),
        ("Middle button drag, Space+drag", "Pan"),
        ("F", "Fit the whole screen"),
        ("Ctrl+1", "Zoom to 100%"),
        ("H", "Show / hide the selected panels in game"),
        ("Ctrl+A / Esc", "Select all / nothing"),
    )),
    ("Layout", (
        ("Ctrl+S / Ctrl+Shift+S", "Save / save under another name"),
        ("Ctrl+Z / Ctrl+Shift+Z", "Undo / redo"),
        ("Ctrl+F", "Search the library"),
        ("F2 / Ctrl+D / Delete", "Rename / duplicate / delete the library entry"),
    )),
)


def fmt_screen(screen):
    return f"{screen[0]}×{screen[1]}"


def section_label(text):
    """Small caps heading of a sidebar block."""
    label = QLabel(text)
    label.setObjectName("section")
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 0.85)
    font.setBold(True)
    font.setCapitalization(QFont.AllUppercase)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    label.setFont(font)
    return label


def muted_label(text="", wrap=False):
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(wrap)
    return label


_portraits = {}


def portrait_pixmap(path, w, h, radius=6, focus=0.5):
    """A saved character portrait cropped to w x h with rounded corners, or None.

    `focus` is where the crop sits vertically: 0 keeps the top, 1 the bottom.
    """
    try:
        key = (str(path), path.stat().st_mtime_ns, w, h, radius, focus)
    except (OSError, AttributeError):
        return None
    if key not in _portraits:
        pix = None
        image = QImage(str(path))
        if not image.isNull():
            # Saved portraits carry an empty alpha channel; drop it.
            image = image.convertToFormat(QImage.Format_RGB32).scaled(
                w * 2, h * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pix = QPixmap(w * 2, h * 2)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, w * 2, h * 2), radius * 2, radius * 2)
            painter.setClipPath(clip)
            painter.drawImage(0, 0, image, (image.width() - w * 2) // 2,
                              int((image.height() - h * 2) * focus))
            painter.end()
            pix.setDevicePixelRatio(2)
        _portraits[key] = pix
    return _portraits[key]


def letter_pixmap(text, w, h, radius=6):
    """Placeholder tile with a letter, for entries that have no portrait."""
    pix = QPixmap(w * 2, h * 2)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor(theme.BORDER_STRONG), 2))
    painter.setBrush(QColor(theme.RAISED))
    painter.drawRoundedRect(QRectF(1, 1, w * 2 - 2, h * 2 - 2), radius * 2, radius * 2)
    font = painter.font()
    font.setPixelSize(int(min(w, h) * 0.9))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(theme.MUTED))
    painter.drawText(pix.rect(), Qt.AlignCenter, text)
    painter.end()
    pix.setDevicePixelRatio(2)
    return pix


def profile_summary(profile):
    """(text, portrait path) describing the character a skill profile belongs to."""
    parts, portrait = profile_parts(profile)
    return " · ".join(parts), portrait


def profile_parts(profile):
    """([name, class, spec] as far as known, portrait path) of a skill profile."""
    if not profile:
        return [], None
    char = str(profile.get("char", ""))
    skills = [s for s in list(profile.get("cooldown", {}).values())
              + list(profile.get("quick", {}).values()) if s]
    cls, spec = core.char_class(skills)
    name = core.char_registry().get(char, {}).get("name", "")
    parts = [p for p in (name, cls, spec) if p]
    return parts or [f"char …{char[-8:]}"], core.portrait_path(char)


TIPS = (
    "Drag a panel to move it; arrow keys nudge it by 1 unit, Shift+arrows by 10.",
    "Layouts only reach the game through a slot: press “Write to game slot”, then "
    "in game open Edit UI and load that preset.",
    "Slots can be written only while Black Desert is closed — the running game "
    "rewrites its settings file on exit.",
    "Every write to a game slot keeps a copy of the game's file in the library's "
    ".backups folder.",
    "Press H to show or hide the selected panels in game; hidden ones stay on the "
    "canvas as faint outlines.",
    "Hold Space and drag, or drag with the middle button, to pan. The wheel zooms "
    "at the cursor, F fits the whole screen.",
    "View → Background screenshot… puts a game screenshot under the layout, so "
    "panels can be placed around your character.",
    "Select several panels with Ctrl+click or by dragging on empty space, then "
    "align them from the inspector or the Edit menu.",
    "Type exact X / Y values in the inspector on the right; with several panels "
    "selected they move as a group.",
    "Right-click a game slot to copy what is in it now into the library.",
    "Bind a character (Layout → Character…) and the entry also stores the skills "
    "in its quick and cooldown slots.",
    "Q1–Q20 are quick slots numbered as in game, C0–C19 are cooldown slots.",
    "Cooldown captions are drawn under the icon: leave a gap between rows of "
    "cooldown slots or the text overlaps.",
    "The game does not store character names on disk — give them once with "
    "“Name…” in the character picker.",
    "Turn on the grid in the toolbar to snap panels to a fixed step; the magnet "
    "toggles snapping to other panels.",
    "Ctrl+D duplicates the library entry — handy for trying a variant without "
    "losing the original.",
    "F1 lists all keyboard and mouse shortcuts.",
)
TIP_INTERVAL = 15000        # ms between tips


class TipStrip(QLabel):
    """One-line rotating hint in the status bar; a click shows the next one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index = int(time.time()) % len(TIPS)
        self.setTextFormat(Qt.RichText)
        self.setCursor(Qt.PointingHandCursor)
        # Let the status bar shrink the strip instead of widening the window.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_tip)
        self.timer.start(TIP_INTERVAL)
        self.show_tip()

    def show_tip(self):
        self.setText(f'<span style="color:{theme.ACCENT}; font-weight:bold">TIP</span>'
                     f'&nbsp;&nbsp;<span style="color:{theme.MUTED}">'
                     f'{TIPS[self.index]}</span>')
        # The strip is clipped in a narrow window; the tooltip has the full text.
        self.setToolTip(f"{TIPS[self.index]}\n\nClick for the next tip")

    def next_tip(self):
        self.index = (self.index + 1) % len(TIPS)
        self.show_tip()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.next_tip()
            self.timer.start(TIP_INTERVAL)      # restart the countdown
        else:
            super().mousePressEvent(event)


class Pill(QWidget):
    """A rounded status label, optionally with a coloured dot."""

    def __init__(self, dot=True):
        super().__init__()
        self.dot, self.text, self.colour = dot, "", QColor(theme.MUTED)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set(self, text, colour):
        self.text, self.colour = text, QColor(colour)
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text) + (36 if self.dot else 22),
                     fm.height() + 8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill, edge = QColor(self.colour), QColor(self.colour)
        fill.setAlpha(34)
        edge.setAlpha(110)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        left = 11
        if self.dot:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.colour)
            painter.drawEllipse(QPointF(14, r.center().y()), 4, 4)
            left = 25
        painter.setPen(self.colour)
        painter.drawText(self.rect().adjusted(left, 0, -8, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text)


class GameWatch(QObject):
    """Checks for the game process off the GUI thread (on Windows it runs tasklist)."""

    result = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False

    def poll(self):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            running = bool(core.game_running())
        except Exception:
            running = False
        self.busy = False
        try:
            self.result.emit(running)
        except RuntimeError:
            pass                      # the window is already gone


# ---------------------------------------------------------------- canvas

class PanelItem(QGraphicsRectItem):
    def __init__(self, el, size, win):
        super().__init__(0, 0, size[0], size[1])
        self.el, self.size, self.win = el, size, win
        self.setPos(int(el.get("PosX")), int(el.get("PosY")))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.icon = None       # QPixmap of the skill sitting in this slot, if known
        self.skill = None      # name of that skill
        self.setToolTip(f"{el.label()}  (#{el.index})  {size[0]}x{size[1]}")
        self.color = COLORS[panels.group(el.index)]
        self.setZValue(1 if min(size) < 120 else 0)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not self.win.loading:
            return self.win.adjust_position(self, value)
        if change == QGraphicsItem.ItemPositionHasChanged and not self.win.loading:
            self.win.item_moved(self)
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        shown = self.el.shown
        selected = self.isSelected()
        hover = bool(option.state & QStyle.State_MouseOver)
        if not shown:
            # Panels hidden in game stay on the canvas as faint ghosts.
            painter.setOpacity(0.65 if selected or hover else 0.3)
        fill = QColor(self.color)
        fill.setAlpha((95 if hover else 70) if shown else 18)
        edge = QColor(self.color if shown else QColor(130, 130, 130))
        pen = QPen(edge.lighter(130) if hover else edge, 0,
                   Qt.SolidLine if shown else Qt.DashLine)
        if selected:
            pen = QPen(QColor(255, 255, 255), 2)
            pen.setCosmetic(True)
            fill.setAlpha(140 if shown else 50)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRect(self.rect())

        w, h = self.size
        small = min(w, h) < 70
        text = self.el.short_label() if small else self.el.label()
        if self.icon is not None and self.win.act_icons.isChecked():
            # Skill icon as the game draws it (about 35 of the slot's 50 units),
            # at the bottom of taller quick-slot panels; slot name in the corner.
            side = 36
            target = QRectF((w - side) / 2, h - 50 + (50 - side) / 2, side, side)
            painter.drawPixmap(target, self.icon, QRectF(self.icon.rect()))
            font = QFont(painter.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            tag = QRectF(0, 0, 6 + 7 * len(text), 13)
            painter.fillRect(tag, QColor(0, 0, 0, 170))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(tag, Qt.AlignCenter, text)
            return
        font = QFont(painter.font())
        font.setPixelSize(max(9, min(64, int(min(h * 0.45, w / max(3, len(text)) * 1.6)))))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255) if shown else QColor(150, 150, 150))
        painter.drawText(self.rect().adjusted(2, 1, -2, -1),
                         Qt.AlignCenter | Qt.TextWordWrap, text)


class View(QGraphicsView):
    ZOOM_MIN, ZOOM_MAX = 0.05, 8.0

    def __init__(self, scene, win):
        super().__init__(scene)
        self.win = win
        self.auto_fit = True       # keep the whole screen in view while resizing
        self.guides = []           # [("v" | "h", coordinate)] snap lines being shown
        self.pan_from = None
        self.space = False
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setFrameShape(QFrame.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    # ---- zoom

    def zoom(self):
        return self.transform().m11()

    def zoom_by(self, factor, at_cursor=True):
        if not self.win.preset:
            return
        old = self.zoom()
        new = max(self.ZOOM_MIN, min(self.ZOOM_MAX, old * factor))
        if abs(new - old) < 1e-6:
            return
        if not at_cursor:
            self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.scale(new / old, new / old)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.auto_fit = False
        self.win.zoom_changed()

    def fit(self):
        if not self.win.preset:
            return
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self.auto_fit = True
        self.win.zoom_changed()

    def set_guides(self, guides):
        if guides != self.guides:
            self.guides = guides
            self.viewport().update()

    # ---- events

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if dy:
            self.zoom_by(1.15 ** (dy / 120))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or (
                self.space and event.button() == Qt.LeftButton):
            self.pan_from = event.position().toPoint()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pan_from is not None:
            now = event.position().toPoint()
            delta = now - self.pan_from
            self.pan_from = now
            for bar, d in ((self.horizontalScrollBar(), delta.x()),
                           (self.verticalScrollBar(), delta.y())):
                bar.setValue(bar.value() - d)
            self.auto_fit = False
            return
        super().mouseMoveEvent(event)
        self.win.show_cursor(self.mapToScene(event.position().toPoint()))

    def mouseReleaseEvent(self, event):
        if self.pan_from is not None:
            self.pan_from = None
            self.viewport().setCursor(Qt.OpenHandCursor if self.space else Qt.ArrowCursor)
            return
        super().mouseReleaseEvent(event)
        self.set_guides([])
        self.win.commit()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.win.show_cursor(None)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            if not event.isAutoRepeat():
                self.space = True
                self.viewport().setCursor(Qt.OpenHandCursor)
            return
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        delta = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0),
                 Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}.get(event.key())
        if delta and self.scene().selectedItems():
            self.win.nudge(*delta)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.space = False
            if self.pan_from is None:
                self.viewport().setCursor(Qt.ArrowCursor)
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.space = False
        if self.pan_from is None:
            self.viewport().setCursor(Qt.ArrowCursor)

    def contextMenuEvent(self, event):
        if not self.win.preset:
            return
        item = self.itemAt(event.pos())
        if isinstance(item, PanelItem) and not item.isSelected():
            self.scene().clearSelection()
            item.setSelected(True)
        self.win.canvas_menu().exec(event.globalPos())

    # ---- painting

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(theme.CANVAS))
        preset = self.win.preset
        if not preset:
            return
        w, h = preset.screen
        frame = QRectF(0, 0, w, h)
        painter.fillRect(frame, QColor(theme.SCREEN))
        step = self.win.grid
        if step and step * self.zoom() >= 6:
            painter.setPen(QPen(QColor(255, 255, 255, 16), 0))
            area = rect.intersected(frame)
            x = int(area.left() // step) * step
            while x <= area.right():
                if x >= area.left():
                    painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
                x += step
            y = int(area.top() // step) * step
            while y <= area.bottom():
                if y >= area.top():
                    painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
                y += step
        painter.setPen(QPen(QColor(theme.BORDER_STRONG), 0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(frame)

    def drawForeground(self, painter, rect):
        preset = self.win.preset
        if preset and self.guides:
            pen = QPen(QColor(theme.ACCENT), 0, Qt.DashLine)
            painter.setPen(pen)
            w, h = preset.screen
            for axis, value in self.guides:
                if axis == "v":
                    painter.drawLine(QPointF(value, -SCENE_MARGIN),
                                     QPointF(value, h + SCENE_MARGIN))
                else:
                    painter.drawLine(QPointF(-SCENE_MARGIN, value),
                                     QPointF(w + SCENE_MARGIN, value))
        # The rest is drawn in viewport pixels, whatever the zoom.
        painter.save()
        painter.setWorldMatrixEnabled(False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        if preset:
            corner = self.mapFromScene(QPointF(0, 0))
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(corner.x(), corner.y() - 7,
                             f"Game screen  {preset.screen[0]} × {preset.screen[1]} UI units")
        else:
            font = painter.font()
            font.setPointSizeF(font.pointSizeF() * 1.35)
            painter.setFont(font)
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter,
                             "Pick a layout in the library on the left,\n"
                             "or open one of the game's three preset slots.")
        painter.restore()


# ---------------------------------------------------------------- list delegates

class CardDelegate(QStyledItemDelegate):
    """Row of the library / game-slot lists: thumbnail, title and a muted second line."""

    def __init__(self, win, row=54, thumb=38):
        super().__init__(win)
        self.win, self.row, self.thumb = win, row, thumb

    def sizeHint(self, option, index):
        return QSize(120, self.row)

    def paint(self, painter, option, index):
        card = index.data(ROLE_CARD)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(option.rect).adjusted(1, 2, -1, -2)
        enabled = bool(index.flags() & Qt.ItemIsEnabled)
        is_open = self.win.is_open(card["kind"])
        if is_open:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.ACCENT_DIM))
            painter.drawRoundedRect(r, 7, 7)
            painter.setBrush(QColor(theme.ACCENT))
            painter.drawRoundedRect(QRectF(r.left(), r.top() + 9, 3, r.height() - 18), 1.5, 1.5)
        elif enabled and option.state & (QStyle.State_Selected | QStyle.State_MouseOver):
            painter.setPen(QPen(QColor(theme.BORDER_STRONG), 1)
                           if option.state & QStyle.State_Selected else Qt.NoPen)
            painter.setBrush(QColor(theme.RAISED))
            painter.drawRoundedRect(r, 7, 7)

        side = self.thumb
        x, y = r.left() + 10, r.top() + (r.height() - side) / 2
        if not enabled:
            painter.setOpacity(0.45)
        painter.drawPixmap(QPointF(x, y), card["thumb"])
        painter.setOpacity(1.0)

        tx = x + side + 10
        right = r.right() - 10
        if is_open and self.win.dirty:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.ACCENT))
            painter.drawEllipse(QPointF(right - 4, r.center().y()), 4, 4)
            right -= 16
        title_font = QFont(option.font)
        title_font.setBold(is_open)
        sub_font = QFont(option.font)
        sub_font.setPointSizeF(sub_font.pointSizeF() * 0.88)
        mid = r.center().y()
        title_right = right
        if card.get("note"):
            painter.setFont(sub_font)
            fm = painter.fontMetrics()
            width = fm.horizontalAdvance(card["note"])
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(QRectF(right - width, mid - fm.height() - 1, width, fm.height()),
                             Qt.AlignRight | Qt.AlignVCenter, card["note"])
            title_right = right - width - 8
        painter.setFont(title_font)
        fm = painter.fontMetrics()
        painter.setPen(QColor(theme.TEXT if enabled else theme.DISABLED))
        painter.drawText(QRectF(tx, mid - fm.height(), title_right - tx, fm.height()),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         fm.elidedText(card["title"], Qt.ElideRight, int(title_right - tx)))
        painter.setFont(sub_font)
        fm = painter.fontMetrics()
        painter.setPen(QColor(theme.MUTED if enabled else theme.DISABLED))
        painter.drawText(QRectF(tx, mid + 1, right - tx, fm.height()),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         fm.elidedText(card["sub"], Qt.ElideRight, int(right - tx)))
        painter.restore()


class PanelDelegate(QStyledItemDelegate):
    """Panel list row: the default checkbox + name, with the panel index at the right."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        el = index.data(ROLE_EL)
        if el is None:
            return
        painter.save()
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(option.rect.adjusted(0, 0, -8, 0),
                         Qt.AlignRight | Qt.AlignVCenter, f"#{el.index}")
        painter.restore()


class CharDelegate(QStyledItemDelegate):
    """Character card of the picker: portrait, name, class, last login, bound layouts."""

    PORTRAIT = QSize(150, 193)      # same 624x804 proportions the game saves
    CELL = QSize(194, 322)

    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog

    def sizeHint(self, option, index):
        return self.CELL

    def paint(self, painter, option, index):
        card = index.data(ROLE_CARD)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(option.rect).adjusted(5, 5, -5, -5)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        painter.setPen(QPen(QColor(theme.ACCENT), 2) if selected else
                       QPen(QColor(theme.BORDER_STRONG if hover else theme.BORDER), 1))
        painter.setBrush(QColor(theme.ACCENT_DIM if selected else
                                theme.HOVER if hover else theme.RAISED))
        painter.drawRoundedRect(r, 9, 9)

        pw, ph = self.PORTRAIT.width(), self.PORTRAIT.height()
        px, py = r.left() + (r.width() - pw) / 2, r.top() + 11
        gone = card["order"] is None
        if gone:
            painter.setOpacity(0.45)
        painter.drawPixmap(QPointF(px, py), card["pixmap"])
        painter.setOpacity(1.0)

        small = QFont(option.font)
        small.setPointSizeF(small.pointSizeF() * 0.85)
        if card["char"] == self.dialog.current:
            self.chip(painter, small, QPointF(px + 7, py + 7), "Current",
                      QColor(theme.ACCENT), QColor(theme.ACCENT_TEXT))
        elif gone:
            self.chip(painter, small, QPointF(px + 7, py + 7), "Not in game",
                      QColor(0, 0, 0, 190), QColor(theme.TEXT))

        y = py + ph + 8
        width = r.width() - 16
        font = QFont(option.font)
        font.setBold(bool(card["name"]))
        font.setItalic(not card["name"])
        painter.setFont(font)
        fm = painter.fontMetrics()
        painter.setPen(QColor(theme.TEXT if card["name"] else theme.DISABLED))
        painter.drawText(QRectF(r.left() + 8, y, width, fm.height()), Qt.AlignCenter,
                         fm.elidedText(card["name"] or "no name yet", Qt.ElideRight, int(width)))
        y += fm.height() + 1
        painter.setFont(option.font)
        fm = painter.fontMetrics()
        painter.setPen(QColor(theme.TEXT if card["class"] else theme.MUTED))
        painter.drawText(QRectF(r.left() + 8, y, width, fm.height()), Qt.AlignCenter,
                         fm.elidedText(card["kind"], Qt.ElideRight, int(width)))
        y += fm.height() + 1
        painter.setFont(small)
        fm = painter.fontMetrics()
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(QRectF(r.left() + 8, y, width, fm.height()), Qt.AlignCenter,
                         "played " + card["when"])
        if card["entries"]:
            y += fm.height() + 5
            text = fm.elidedText(", ".join(card["entries"]), Qt.ElideRight, int(width) - 18)
            w = fm.horizontalAdvance(text) + 16
            self.chip(painter, small, QPointF(r.center().x() - w / 2, y), text,
                      QColor(theme.CANVAS), QColor(theme.ACCENT), QColor(theme.ACCENT_DIM))
        painter.restore()

    @staticmethod
    def chip(painter, font, pos, text, fill, colour, edge=None):
        painter.setFont(font)
        fm = painter.fontMetrics()
        rect = QRectF(pos.x(), pos.y(), fm.horizontalAdvance(text) + 16, fm.height() + 4)
        painter.setPen(QPen(edge, 1) if edge else Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(colour)
        painter.drawText(rect, Qt.AlignCenter, text)


# ---------------------------------------------------------------- dialogs

class CharacterDialog(QDialog):
    """Pick the character a library entry belongs to, as a wall of portrait cards."""

    def __init__(self, parent, family, current):
        super().__init__(parent)
        self.family, self.current = family, current
        self.cards = []
        self.setWindowTitle("Character of this layout")
        self.resize(1040, 790)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        text = QVBoxLayout()
        title = QLabel("Which character is this layout for?")
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        title.setFont(font)
        text.addWidget(title)
        text.addWidget(muted_label(
            f"Family {family}. The skills in the chosen character's quick and cooldown "
            "slots are stored with the layout."))
        top.addLayout(text, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, class or layout")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(theme.icon("search", theme.MUTED), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(290)
        self.search.textChanged.connect(self.populate)
        top.addWidget(self.search, 0, Qt.AlignBottom)
        lay.addLayout(top)

        self.list = QListWidget()
        self.list.setObjectName("cards")
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setItemDelegate(CharDelegate(self))
        self.list.setGridSize(CharDelegate.CELL)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.verticalScrollBar().setSingleStep(30)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.list.itemSelectionChanged.connect(self.selection_changed)
        lay.addWidget(self.list)

        row = QHBoxLayout()
        self.name_btn = QPushButton("Name…")
        self.name_btn.setIcon(theme.icon("pencil"))
        self.name_btn.setToolTip("The game keeps character names on its servers, "
                                 "so type it once here  (F2)")
        self.name_btn.setAutoDefault(False)
        self.name_btn.clicked.connect(self.rename)
        QShortcut(QKeySequence(Qt.Key_F2), self).activated.connect(self.rename)
        row.addWidget(self.name_btn)
        self.all_box = QCheckBox("Show characters that are no longer in the game")
        self.all_box.toggled.connect(self.populate)
        row.addWidget(self.all_box)
        row.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_btn = box.button(QDialogButtonBox.Ok)
        self.ok_btn.setText("Use this character")
        self.ok_btn.setIcon(QIcon())
        box.button(QDialogButtonBox.Cancel).setIcon(QIcon())
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        row.addWidget(box)
        lay.addLayout(row)

        if not core.skill_db():       # one request: names and classes of all skills
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                core.fetch_skill_db()
            except Exception:
                pass                  # offline: cards simply show no class
            finally:
                QApplication.restoreOverrideCursor()
        self.fill()
        self.list.setFocus()

    def fill(self):
        """Read the characters from the game files, then show them."""
        size = CharDelegate.PORTRAIT
        self.cards = core.char_cards(self.family)
        for card in self.cards:
            card["kind"] = " · ".join(p for p in (card["class"], card["spec"]) if p) \
                or "class unknown"
            card["when"] = time.strftime("%d.%m.%Y %H:%M", time.localtime(card["mtime"]))
            card["pixmap"] = (
                portrait_pixmap(card["portrait"], size.width(), size.height(), 7)
                if card["portrait"] else None) or letter_pixmap(
                    (card["class"] or "?")[0], size.width(), size.height(), 7)
        self.populate()

    def populate(self, *_):
        keep = self.chosen() or self.current
        needle = self.search.text().strip().lower()
        self.list.clear()
        for card in self.cards:
            if card["order"] is None and not self.all_box.isChecked():
                continue
            hay = " ".join([card["name"], card["kind"], *card["entries"]]).lower()
            if needle and needle not in hay:
                continue
            item = QListWidgetItem()
            item.setData(ROLE_EL, card["char"])
            item.setData(ROLE_CARD, card)
            item.setToolTip(f"Character {card['char']}\n{card['cooldown']} cooldown slots, "
                            f"{card['quick']} quick-slot skills")
            self.list.addItem(item)
            if card["char"] == keep:
                self.list.setCurrentItem(item)
        self.selection_changed()

    def selection_changed(self):
        self.ok_btn.setEnabled(self.chosen() is not None)
        self.name_btn.setEnabled(self.chosen() is not None)

    def rename(self):
        char = self.chosen()
        if not char:
            return
        old = core.char_registry().get(char, {}).get("name", "")
        name, ok = QInputDialog.getText(self, "Character name", "Name:", text=old)
        if ok:
            core.set_char_name(char, name)
            self.fill()

    def chosen(self):
        row = self.list.currentItem()
        return row.data(ROLE_EL) if row else None


class ScreenDialog(QDialog):
    WINDOWS = ((1920, 1080), (2560, 1080), (2560, 1440), (3440, 1440), (3840, 2160))

    def __init__(self, parent, screen):
        super().__init__(parent)
        self.setWindowTitle("Screen size")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)
        lay.addWidget(muted_label(
            "The size of the game window in UI units (pixels divided by the UI scale "
            "from the game options). Panels keep their relative position — centre / "
            "screen — like the game does.", wrap=True))
        form = QFormLayout()
        self.w, self.h = QSpinBox(), QSpinBox()
        for box, val in ((self.w, screen[0]), (self.h, screen[1])):
            box.setRange(640, 8000)
            box.setValue(val)
            box.setSuffix(" units")
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        self.scale = core.ui_scale()
        self.px = QComboBox()
        self.px.addItem(f"pick pixels, UI scale {self.scale:g}…")
        for w, h in self.WINDOWS:
            self.px.addItem(f"{w} × {h} px", (w, h))
        self.px.setToolTip("Fill in the size for a game window of that many pixels, "
                           "using the UI scale from the game options")
        self.px.activated.connect(self.from_pixels)
        form.addRow("From window", self.px)
        btn = QPushButton("Take from the running game window")
        btn.setAutoDefault(False)
        btn.clicked.connect(self.from_game)
        form.addRow("", btn)
        lay.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Resize")
        for b in box.buttons():
            b.setIcon(QIcon())
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.setMinimumWidth(440)

    def from_pixels(self, row):
        size = self.px.itemData(row)
        if size:
            self.w.setValue(round(size[0] / self.scale))
            self.h.setValue(round(size[1] / self.scale))
        self.px.setCurrentIndex(0)

    def from_game(self):
        scr = core.game_window_screen()
        if not scr:
            QMessageBox.information(self, "bdo-ui", "Game window not found.")
            return
        self.w.setValue(scr[0])
        self.h.setValue(scr[1])


class ShortcutsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Keyboard and mouse")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        row = 0
        for title, rows in SHORTCUTS:
            if row:
                grid.setRowMinimumHeight(row, 10)
                row += 1
            grid.addWidget(section_label(title), row, 0, 1, 2)
            row += 1
            for keys, what in rows:
                key = QLabel(keys)
                key.setObjectName("key")
                grid.addWidget(key, row, 0, Qt.AlignLeft)
                grid.addWidget(QLabel(what), row, 1)
                row += 1
        lay.addLayout(grid)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.button(QDialogButtonBox.Close).setIcon(QIcon())
        box.rejected.connect(self.reject)
        lay.addWidget(box)


# ---------------------------------------------------------------- main window

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.loading = False
        self.preset = None
        self.profile = None         # skill profile of the open library entry
        self.missing_icons = 0
        self.items = []
        self.dirty = False
        self.history, self.hist_pos = [], -1
        self.bg_item = None
        self.bg_path = None
        self.grid = 0
        self.syncing_selection = False
        self.game_is_running = False

        fams = core.families()
        if not fams:
            raise core.BdoUiError(f"no families found under {core.BDO_DIR}")
        self.family = fams[0]

        self.scene = QGraphicsScene(self)
        self.view = View(self.scene, self)
        self.scene.selectionChanged.connect(self.selection_changed)

        self.build_actions()
        self.build_menus()
        self.build_toolbar()
        self.build_body(fams)
        self.build_statusbar()
        self.setMinimumSize(1040, 640)
        self.resize(1500, 950)
        self.restore_ui_state()

        self.watch = GameWatch(self)
        self.watch.result.connect(self.set_game_running)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(3000)
        self.known_lib = core.lib_list()
        self.refresh_sources()
        self.set_game_running(core.game_running())
        self.update_inspector()
        self.update_title()
        self.view.setFocus()

    # ------------------------------------------------------------ UI build

    def build_actions(self):
        def mk(text, slot, keys=(), tip=None, icon=None, checkable=False, checked=False):
            a = QAction(text, self)
            if icon:
                a.setIcon(theme.icon(icon))
            keys = [QKeySequence(k) for k in ((keys,) if isinstance(keys, str) else keys)]
            if keys:
                a.setShortcuts(keys)
            tip = tip or text.rstrip("…")
            if keys:
                tip += f"  ({keys[0].toString(QKeySequence.NativeText)})"
            a.setToolTip(tip)
            if checkable:
                a.setCheckable(True)
                a.setChecked(checked)
                a.toggled.connect(slot)
            else:
                a.triggered.connect(lambda _=False: slot())
            self.addAction(a)
            return a

        self.act_save = mk("Save", self.save, "Ctrl+S", "Save to the library", "save")
        self.act_save_as = mk("Save as…", self.save_as, "Ctrl+Shift+S",
                              "Save to the library under another name")
        self.act_revert = mk("Revert to saved", self.revert, (),
                             "Drop the changes and reload the layout", "revert")
        self.act_rename = mk("Rename…", self.rename_preset, "F2",
                             "Rename the library entry", "pencil")
        self.act_duplicate = mk("Duplicate…", self.duplicate_preset, "Ctrl+D",
                                "Copy the library entry under a new name", "copy")
        self.act_delete = mk("Delete…", self.delete_preset, (),
                             "Delete the library entry  (Del)", "trash")
        self.act_lib_folder = mk("Open library folder", self.open_lib_folder, (),
                                 "Show the library files in the file manager", "folder")
        self.act_game_folder = mk("Game folder…", self.change_game_folder, (),
                                  "Choose the game's 'Black Desert' documents folder")
        self.act_quit = mk("Quit", self.close, "Ctrl+Q")

        self.act_undo = mk("Undo", self.undo, "Ctrl+Z", icon="undo")
        self.act_redo = mk("Redo", self.redo, ("Ctrl+Shift+Z", "Ctrl+Y"), icon="redo")
        self.act_select_all = mk("Select all", self.select_all, "Ctrl+A")
        self.act_deselect = mk("Select nothing", self.scene.clearSelection, "Esc")
        self.act_toggle = mk("Show / hide in game", self.toggle_shown, "H",
                             "Show or hide the selected panels in game", "eye")
        self.align_acts = [
            mk(text, lambda *_, mode=mode: self.align(mode), (), tip, "align_" + mode
               if mode in ("left", "right", "top", "bottom") else "pack_" + mode)
            for text, mode, tip in (
                ("Align left edges", "left", None), ("Align right edges", "right", None),
                ("Align top edges", "top", None), ("Align bottom edges", "bottom", None),
                ("Pack into a row", "row", "Put the selected panels side by side, left to right"),
                ("Pack into a column", "col", "Stack the selected panels, top to bottom"))]
        self.act_snap = mk("Snap to panels", lambda _: None, (),
                           "Snap edges to nearby panels and the screen border while dragging",
                           "magnet", checkable=True, checked=True)

        self.act_char = mk("Character…", self.choose_character, (),
                           "Bind this library entry to a character: its quick-slot and "
                           "cooldown-slot skills are stored with the layout", "user")
        self.act_screen = mk("Screen size…", self.change_screen, (),
                             "Screen size the layout is made for", "monitor")
        self.act_get_icons = mk("Download skill icons", self.fetch_icons, (),
                                "Download missing skill icons of the bound character "
                                "from bdocodex.com", "download")

        self.act_zoom_in = mk("Zoom in", lambda: self.view.zoom_by(1.25, False),
                              ("Ctrl+=", "Ctrl++"), icon="zoom_in")
        self.act_zoom_out = mk("Zoom out", lambda: self.view.zoom_by(1 / 1.25, False),
                               "Ctrl+-", icon="zoom_out")
        self.act_fit = mk("Fit screen", self.view.fit, ("F", "Ctrl+0"),
                          "Fit the whole game screen into the window", "fit")
        self.act_actual = mk("Zoom to 100%", self.zoom_actual, "Ctrl+1")
        self.act_hidden = mk("Panels hidden in game", lambda _: self.apply_hidden_filter(), (),
                             "Draw the panels that are hidden in game as faint outlines",
                             "ghost", checkable=True, checked=True)
        self.act_icons = mk("Skill icons", lambda _: self.scene.update(), (),
                            "Draw skill icons in the slots (needs a bound character)",
                            "skill", checkable=True, checked=True)
        self.act_bg_pick = mk("Background screenshot…", self.pick_background, (),
                              "Show a game screenshot under the layout")
        self.act_bg = mk("Show background", self.toggle_background, (),
                         "Show a game screenshot under the layout",
                         "image", checkable=True)
        self.act_tips = mk("Tips", self.toggle_tips, (),
                           "Show a line of hints at the bottom of the window",
                           checkable=True, checked=True)
        self.act_keys = mk("Keyboard and mouse", self.show_shortcuts, "F1", icon="keyboard")

    def build_menus(self):
        self.slot_menu = QMenu("Write to game slot", self)
        self.slot_menu.setIcon(theme.icon("write"))
        self.slot_menu.aboutToShow.connect(lambda: self.fill_slot_menu(self.slot_menu))

        bar = self.menuBar()
        m = bar.addMenu("&File")
        m.addActions([self.act_save, self.act_save_as, self.act_revert])
        m.addSeparator()
        m.addActions([self.act_rename, self.act_duplicate, self.act_delete])
        m.addSeparator()
        m.addMenu(self.slot_menu)
        m.addSeparator()
        m.addActions([self.act_lib_folder, self.act_game_folder])
        m.addSeparator()
        m.addAction(self.act_quit)

        m = bar.addMenu("&Edit")
        m.addActions([self.act_undo, self.act_redo])
        m.addSeparator()
        m.addActions([self.act_select_all, self.act_deselect])
        m.addSeparator()
        m.addAction(self.act_toggle)
        self.align_menu = m.addMenu("Align")
        self.align_menu.addActions(self.align_acts[:4])
        self.align_menu.addSeparator()
        self.align_menu.addActions(self.align_acts[4:])
        m.addSeparator()
        m.addAction(self.act_snap)

        m = bar.addMenu("&Layout")
        m.addActions([self.act_char, self.act_screen, self.act_get_icons])

        m = bar.addMenu("&View")
        m.addActions([self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual])
        m.addSeparator()
        m.addActions([self.act_hidden, self.act_icons])
        m.addSeparator()
        m.addActions([self.act_bg_pick, self.act_bg])
        m.addSeparator()
        m.addAction(self.act_tips)

        m = bar.addMenu("&Help")
        m.addAction(self.act_keys)

    def build_toolbar(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setContextMenuPolicy(Qt.PreventContextMenu)

        tb.addAction(self.act_save)
        tb.widgetForAction(self.act_save).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addSeparator()
        tb.addActions([self.act_undo, self.act_redo])
        tb.addSeparator()
        tb.addActions(self.align_acts)
        tb.addSeparator()
        tb.addAction(self.act_toggle)
        tb.addSeparator()
        tb.addAction(self.act_snap)
        self.grid_box = QSpinBox()
        self.grid_box.setRange(0, 100)
        self.grid_box.setPrefix("Grid ")
        self.grid_box.setSpecialValueText("Grid off")
        self.grid_box.setToolTip("Snap dragged panels to a grid of this many UI units "
                                 "(replaces snapping to panels)")
        self.grid_box.setFixedWidth(104)
        self.grid_box.valueChanged.connect(self.grid_changed)
        tb.addWidget(self.grid_box)
        tb.addSeparator()
        tb.addActions([self.act_hidden, self.act_icons, self.act_bg])

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.write_btn = QToolButton()
        self.write_btn.setObjectName("primary")
        self.write_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.write_btn.setPopupMode(QToolButton.InstantPopup)
        self.write_btn.setMenu(self.slot_menu)
        tb.addWidget(self.write_btn)

    def build_body(self, fams):
        def flat(action):
            b = QToolButton()
            b.setObjectName("flat")
            b.setDefaultAction(action)
            b.setIconSize(QSize(18, 18))
            return b

        def search_box(placeholder, slot):
            box = QLineEdit()
            box.setPlaceholderText(placeholder)
            box.setClearButtonEnabled(True)
            box.addAction(theme.icon("search", theme.MUTED), QLineEdit.LeadingPosition)
            box.textChanged.connect(slot)
            return box

        # ---- left: library and game slots
        left = QWidget()
        left.setObjectName("sidebar")
        lay = QVBoxLayout(left)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(section_label("Library"))
        row.addStretch(1)
        for a in (self.act_duplicate, self.act_rename, self.act_delete):
            row.addWidget(flat(a))
        lay.addLayout(row)
        self.lib_search = search_box("Search layouts", self.filter_library)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        lay.addWidget(self.lib_search)

        self.sources = QListWidget()
        self.sources.setItemDelegate(CardDelegate(self))
        self.sources.setMouseTracking(True)
        self.sources.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.sources.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sources.customContextMenuRequested.connect(self.library_menu)
        self.sources.itemActivated.connect(self.source_activated)
        self.sources.itemClicked.connect(self.source_activated)
        self.sources.currentItemChanged.connect(lambda *_: self.update_actions())
        delete = QShortcut(QKeySequence(Qt.Key_Delete), self.sources)
        delete.setContext(Qt.WidgetShortcut)
        delete.activated.connect(self.delete_preset)
        lay.addWidget(self.sources, 1)
        self.lib_empty = muted_label(
            "The library is empty.\nOpen a game slot below and save it "
            "to keep that layout here.", wrap=True)
        lay.addWidget(self.lib_empty)

        row = QHBoxLayout()
        row.addWidget(section_label("Game slots"))
        row.addStretch(1)
        self.lock_icon = QLabel()
        self.lock_icon.setPixmap(theme.pixmap("lock", theme.WARN, 16))
        self.lock_text = QLabel("read-only")
        self.lock_text.setObjectName("warn")
        row.addWidget(self.lock_icon)
        row.addWidget(self.lock_text)
        lay.addSpacing(6)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(muted_label("Family"))
        self.family_box = QComboBox()
        self.family_box.addItems(fams)
        self.family_box.setToolTip("Game account (family) whose three preset slots are "
                                   "shown and written; the one played last comes first")
        self.family_box.currentTextChanged.connect(self.family_changed)
        row.addWidget(self.family_box, 1)
        lay.addLayout(row)
        self.slots = QListWidget()
        self.slots.setItemDelegate(CardDelegate(self, row=46, thumb=30))
        self.slots.setMouseTracking(True)
        self.slots.setFixedHeight(4 * 46 + 4)
        self.slots.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.slots.setContextMenuPolicy(Qt.CustomContextMenu)
        self.slots.customContextMenuRequested.connect(self.slot_list_menu)
        self.slots.itemActivated.connect(self.source_activated)
        self.slots.itemClicked.connect(self.source_activated)
        lay.addWidget(self.slots)

        # ---- centre: document bar and canvas
        centre = QWidget()
        lay = QVBoxLayout(centre)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bar.setObjectName("docbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 7, 8, 7)
        row.setSpacing(10)
        self.doc_title = QLabel()
        font = self.doc_title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        self.doc_title.setFont(font)
        row.addWidget(self.doc_title)
        self.doc_badge = Pill(dot=False)
        self.doc_badge.set("Unsaved changes", theme.ACCENT)
        row.addWidget(self.doc_badge)
        self.doc_source = muted_label()
        row.addWidget(self.doc_source)
        row.addStretch(1)
        row.addWidget(flat(self.act_zoom_out))
        self.zoom_btn = QToolButton()
        self.zoom_btn.setObjectName("flat")
        self.zoom_btn.setToolTip("Zoom; click for 100%  (Ctrl+1)")
        self.zoom_btn.setMinimumWidth(54)
        self.zoom_btn.clicked.connect(self.zoom_actual)
        row.addWidget(self.zoom_btn)
        row.addWidget(flat(self.act_zoom_in))
        row.addWidget(flat(self.act_fit))
        lay.addWidget(bar)
        lay.addWidget(self.view, 1)

        # ---- right: layout, selection, panel list
        right = QWidget()
        right.setObjectName("sidebar")
        lay = QVBoxLayout(right)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(section_label("Layout"))
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.char_thumb = QLabel()
        self.char_thumb.setFixedSize(40, 40)
        grid.addWidget(self.char_thumb, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.char_name = QLabel()
        self.char_name.setMinimumWidth(40)
        self.char_sub = muted_label()
        col.addWidget(self.char_name)
        col.addWidget(self.char_sub)
        grid.addLayout(col, 0, 1)
        self.char_btn = QPushButton("Change…")
        self.char_btn.setObjectName("small")
        self.char_btn.setToolTip(self.act_char.toolTip())
        self.char_btn.clicked.connect(self.choose_character)
        grid.addWidget(self.char_btn, 0, 2)
        screen_icon = QLabel()
        screen_icon.setPixmap(theme.pixmap("monitor", theme.MUTED, 20))
        screen_icon.setAlignment(Qt.AlignCenter)
        grid.addWidget(screen_icon, 1, 0)
        self.screen_label = QLabel()
        grid.addWidget(self.screen_label, 1, 1)
        self.screen_btn = QPushButton("Resize…")
        self.screen_btn.setObjectName("small")
        self.screen_btn.setToolTip(self.act_screen.toolTip())
        self.screen_btn.clicked.connect(self.change_screen)
        grid.addWidget(self.screen_btn, 1, 2)
        self.icons_label = QLabel()
        self.icons_label.setObjectName("warn")
        self.icons_label.setWordWrap(True)
        grid.addWidget(self.icons_label, 2, 0, 1, 2)
        self.icons_btn = QPushButton("Download")
        self.icons_btn.setObjectName("small")
        self.icons_btn.setToolTip(self.act_get_icons.toolTip())
        self.icons_btn.clicked.connect(self.fetch_icons)
        grid.addWidget(self.icons_btn, 2, 2)
        grid.setColumnStretch(1, 1)
        lay.addWidget(card)

        lay.addSpacing(6)
        lay.addWidget(section_label("Selection"))
        card = QFrame()
        card.setObjectName("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(7)
        self.sel_title = QLabel()
        font = self.sel_title.font()
        font.setBold(True)
        self.sel_title.setFont(font)
        self.sel_sub = muted_label(wrap=True)
        self.sel_sub.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.sel_sub.setFixedHeight(self.sel_sub.fontMetrics().lineSpacing() * 2 + 2)
        col.addWidget(self.sel_title)
        col.addWidget(self.sel_sub)
        row = QHBoxLayout()
        self.x_box, self.y_box = QSpinBox(), QSpinBox()
        for box, name in ((self.x_box, "X "), (self.y_box, "Y ")):
            box.setRange(-4000, 12000)
            box.setPrefix(name)
            box.setKeyboardTracking(False)
            box.setToolTip("Position of the top-left corner in UI units")
            box.valueChanged.connect(self.spin_changed)
            row.addWidget(box, 1)
        col.addLayout(row)
        row = QHBoxLayout()
        self.vis_box = QCheckBox("Visible in game")
        self.vis_box.setToolTip(self.act_toggle.toolTip())
        self.vis_box.clicked.connect(lambda _: self.toggle_shown())
        row.addWidget(self.vis_box)
        row.addStretch(1)
        col.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(0)
        for a in self.align_acts:
            row.addWidget(flat(a))
        row.addStretch(1)
        col.addLayout(row)
        lay.addWidget(card)

        lay.addSpacing(6)
        row = QHBoxLayout()
        row.addWidget(section_label("Panels"))
        row.addStretch(1)
        self.panel_count = muted_label()
        row.addWidget(self.panel_count)
        lay.addLayout(row)
        self.panel_search = search_box("Filter panels", self.filter_panels)
        lay.addWidget(self.panel_search)
        self.panel_list = QListWidget()
        self.panel_list.setObjectName("panels")
        self.panel_list.setItemDelegate(PanelDelegate(self))
        self.panel_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.panel_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.panel_list.setToolTip("Checkbox = visible in game")
        self.panel_list.itemSelectionChanged.connect(self.list_selection_changed)
        self.panel_list.itemChanged.connect(self.list_item_changed)
        lay.addWidget(self.panel_list, 1)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setChildrenCollapsible(False)
        for i, (widget, minimum) in enumerate(((left, 230), (centre, 360), (right, 280))):
            widget.setMinimumWidth(minimum)
            self.splitter.addWidget(widget)
            self.splitter.setStretchFactor(i, 1 if widget is centre else 0)
        self.splitter.setSizes([280, 910, 310])
        self.setCentralWidget(self.splitter)

    def build_statusbar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setContentsMargins(6, 2, 8, 3)
        # Temporary status messages cover the strip and it comes back after them.
        self.tips = TipStrip()
        bar.addWidget(self.tips, 1)
        self.tips.setVisible(self.act_tips.isChecked())
        self.cursor_label = QLabel()
        self.cursor_label.setMinimumWidth(110)
        bar.addPermanentWidget(self.cursor_label)
        self.game_pill = Pill()
        bar.addPermanentWidget(self.game_pill)

    def restore_ui_state(self):
        state = core.load_config().get("gui")
        if not isinstance(state, dict):
            return
        try:
            if state.get("geometry"):
                self.restoreGeometry(QByteArray.fromBase64(state["geometry"].encode("ascii")))
            sizes = [int(v) for v in state.get("splitter", [])]
            if len(sizes) == 3 and all(v > 0 for v in sizes):
                self.splitter.setSizes(sizes)
            self.act_snap.setChecked(bool(state.get("snap", True)))
            self.act_hidden.setChecked(bool(state.get("hidden", True)))
            self.act_icons.setChecked(bool(state.get("icons", True)))
            self.grid_box.setValue(int(state.get("grid", 0)))
            self.act_tips.setChecked(bool(state.get("tips", True)))
            self.tips.setVisible(self.act_tips.isChecked())
        except (AttributeError, TypeError, ValueError):
            pass                      # a damaged config only loses the window layout

    def save_ui_state(self):
        try:
            core.save_config(gui={
                "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
                "splitter": self.splitter.sizes(),
                "snap": self.act_snap.isChecked(), "hidden": self.act_hidden.isChecked(),
                "icons": self.act_icons.isChecked(), "grid": self.grid,
                "tips": self.act_tips.isChecked()})
        except OSError:
            pass

    # ------------------------------------------------------------ sources

    def is_open(self, kind):
        """True if the list entry `kind` is the layout on the canvas."""
        if not self.preset:
            return False
        if kind[0] == "lib":
            return self.preset.name == kind[1]
        return (not self.preset.name and self.preset.meta.get("from") == kind[1]
                and self.preset.meta.get("family") == self.family)

    def refresh_sources(self):
        keep = self.current_lib_name()
        self.sources.clear()
        names = core.lib_list()
        for name in names:
            text, portrait = profile_summary(core.profile_for_preset(name))
            thumb = portrait_pixmap(portrait, 38, 38, 7, 0.28) if portrait else None
            screen = core.lib_meta(name).get("screen") or ()
            note = fmt_screen(screen) if len(screen) == 2 else ""
            sub = text or "No character"
            it = QListWidgetItem()
            it.setData(ROLE_KIND, ("lib", name))
            it.setData(ROLE_CARD, {
                "kind": ("lib", name), "title": name, "sub": sub, "note": note,
                "thumb": thumb or letter_pixmap(name[:1].upper(), 38, 38, 7)})
            it.setToolTip(f"{name}\n{sub}" + (f"\nScreen {note} UI units" if note else ""))
            self.sources.addItem(it)
            if name == (self.preset.name if self.preset and self.preset.name else keep):
                self.sources.setCurrentItem(it)
        self.lib_empty.setVisible(not names)
        self.filter_library()

        self.slots.clear()
        try:
            slots = core.read_slots(self.family)
        except (core.BdoUiError, OSError) as e:
            slots = {}
            self.statusBar().showMessage(str(e))
        entries = [(f"Slot {i + 1}", str(i + 1), t) for i, t in enumerate(core.SLOT_TAGS)]
        entries.append(("Game default", "D", core.REVERT_TAG))
        for text, letter, tag in entries:
            els = slots.get(tag, [])
            it = QListWidgetItem()
            if core.slot_is_empty(els):
                sub = "empty"
                it.setFlags(Qt.NoItemFlags)
            else:
                count = sum(1 for e in els if e.index is not None)
                sub = f"{fmt_screen(core.estimate_screen(els))}  ·  {count} panels"
                it.setData(ROLE_KIND, ("slot", tag))
                it.setToolTip("Open a copy of this game slot; it becomes a library "
                              "entry when saved")
            it.setData(ROLE_CARD, {"kind": ("slot", tag), "title": text, "sub": sub,
                                   "thumb": letter_pixmap(letter, 30, 30, 6)})
            self.slots.addItem(it)
        self.update_actions()

    def filter_library(self, *_):
        needle = self.lib_search.text().strip().lower()
        for i in range(self.sources.count()):
            it = self.sources.item(i)
            card = it.data(ROLE_CARD)
            it.setHidden(bool(needle) and needle not in
                         f"{card['title']} {card['sub']}".lower())

    def focus_search(self):
        self.lib_search.setFocus()
        self.lib_search.selectAll()

    def source_activated(self, item):
        kind = item.data(ROLE_KIND)
        if kind and not self.is_open(kind):
            # Opening rebuilds the lists, so let the click finish first.
            QTimer.singleShot(0, lambda: self.request_open(kind))

    def request_open(self, kind):
        if self.is_open(kind):          # a double click asks twice
            return
        if not self.confirm_discard():
            self.refresh_sources()      # put the highlight back on the open entry
            return
        self.open_source(kind)

    def open_source(self, kind):
        try:
            if kind[0] == "lib":
                preset = core.lib_load(kind[1])
            else:
                preset = core.preset_from_slot(self.family, kind[1])
        except (core.BdoUiError, OSError, ValueError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return False
        self.open_preset(preset)
        self.refresh_sources()
        return True

    def revert(self):
        if not self.preset:
            return
        if self.preset.name:
            kind = ("lib", self.preset.name)
        elif self.preset.meta.get("from"):
            kind = ("slot", self.preset.meta["from"])
        else:
            return
        if self.dirty and QMessageBox.question(
                self, "bdo-ui", "Drop all unsaved changes of this layout?") != QMessageBox.Yes:
            return
        self.open_source(kind)

    def family_changed(self, fam):
        self.family = fam
        self.refresh_sources()

    def library_menu(self, pos):
        item = self.sources.itemAt(pos)
        if not item:
            return
        self.sources.setCurrentItem(item)
        name = item.data(ROLE_KIND)[1]
        menu = QMenu(self)
        menu.addAction("Open", lambda *_: self.request_open(("lib", name)))
        menu.addSeparator()
        menu.addActions([self.act_rename, self.act_duplicate])
        write = menu.addMenu("Write to game slot")
        write.setIcon(theme.icon("write"))
        self.fill_slot_menu(write, name)
        write.setEnabled(not self.game_is_running)
        menu.addSeparator()
        menu.addAction(self.act_delete)
        menu.exec(self.sources.viewport().mapToGlobal(pos))

    def slot_list_menu(self, pos):
        item = self.slots.itemAt(pos)
        kind = item.data(ROLE_KIND) if item else None
        if not kind:
            return
        menu = QMenu(self)
        menu.addAction("Open", lambda *_: self.request_open(kind))
        save = menu.addAction("Save to the library…",
                              lambda *_: self.save_slot_to_library(kind))
        save.setIcon(theme.icon("save"))
        menu.exec(self.slots.viewport().mapToGlobal(pos))

    def save_slot_to_library(self, kind):
        if not self.is_open(kind):
            if not self.confirm_discard() or not self.open_source(kind):
                return
        self.save_as()

    def ask_name(self, title, label, text=""):
        """Ask for a library name; returns a valid name or None."""
        name, ok = QInputDialog.getText(self, title, label, text=text)
        name = name.strip()
        if not ok or not name:
            return None
        try:
            return core.check_name(name)
        except core.BdoUiError as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return None

    def rename_preset(self):
        old = self.current_lib_name()
        if not old:
            return
        new = self.ask_name("Rename layout", "New name:", old)
        if not new or new == old:
            return
        try:
            core.lib_rename(old, new)
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        if self.preset and self.preset.name == old:
            self.preset.name = new
        self.after_library_change(f"Renamed “{old}” to “{new}”", select=new)

    def duplicate_preset(self):
        old = self.current_lib_name()
        if not old:
            return
        new = self.ask_name("Duplicate layout", f"Name of the copy of “{old}”:", old + " copy")
        if not new:
            return
        try:
            if core.lib_path(new).exists():
                raise core.BdoUiError(f"preset {new!r} already exists")
            core.lib_save(core.lib_load(old), new)
            profile = core.profile_for_preset(old)
            if profile:
                core.save_profile(new, profile)
        except (core.BdoUiError, OSError, ValueError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        self.after_library_change(f"“{old}” copied to “{new}”", select=new)

    def delete_preset(self):
        name = self.current_lib_name()
        if not name:
            return
        if QMessageBox.question(self, "bdo-ui", f"Delete layout “{name}” from the library?") \
                != QMessageBox.Yes:
            return
        try:
            core.lib_delete(name)
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        if self.preset and self.preset.name == name:
            self.preset.name = None
            self.dirty = True
        self.after_library_change(f"Deleted “{name}”")

    def after_library_change(self, message, select=None):
        self.known_lib = core.lib_list()
        self.refresh_sources()
        if select:
            for i in range(self.sources.count()):
                if self.sources.item(i).data(ROLE_KIND)[1] == select:
                    self.sources.setCurrentItem(self.sources.item(i))
        if self.preset:
            self.load_icons()
        self.update_title()
        self.statusBar().showMessage(message, 5000)

    def current_lib_name(self):
        it = self.sources.currentItem()
        kind = it.data(ROLE_KIND) if it else None
        return kind[1] if kind and kind[0] == "lib" else None

    def open_lib_folder(self):
        core.LIB_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(core.LIB_DIR)))

    # ------------------------------------------------------------ document

    def set_scene_rect(self):
        w, h = self.preset.screen
        self.scene.setSceneRect(-SCENE_MARGIN, -SCENE_MARGIN,
                                w + 2 * SCENE_MARGIN, h + 2 * SCENE_MARGIN)

    def open_preset(self, preset):
        self.loading = True
        for item in self.items:
            self.scene.removeItem(item)
        self.items = []
        self.preset = preset
        self.set_scene_rect()

        self.panel_list.blockSignals(True)
        self.panel_list.clear()
        for el in preset.els:
            if el.index is None:
                continue
            row = QListWidgetItem(el.label())
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
            row.setCheckState(Qt.Checked if el.shown else Qt.Unchecked)
            row.setData(ROLE_EL, el)
            if not el.positioned:
                row.setForeground(QColor(theme.MUTED))
                row.setToolTip("No position stored: only visibility can be changed")
            self.panel_list.addItem(row)
            if el.positioned:
                item = PanelItem(el, core.panel_size(el, preset.screen), self)
                item.row = row
                row.setData(ROLE_KIND, item)
                self.scene.addItem(item)
                self.items.append(item)
        self.panel_list.blockSignals(False)
        self.loading = False

        self.dirty = False
        self.history = [self.snapshot()]
        self.hist_pos = 0
        self.apply_background()
        self.apply_hidden_filter()
        self.filter_panels()
        self.load_icons()
        self.update_inspector()
        self.update_title()
        self.view.fit()

    def load_icons(self):
        """Attach cached skill icons to the slots, using the profile named like the preset."""
        profile = core.profile_for_preset(self.preset.name) if self.preset else None
        skills = core.slot_skills(profile) if profile else {}
        missing = 0
        for item in self.items:
            skill = skills.get(item.el.index)
            path = core.icon_path(skill) if skill else None
            pix = QPixmap(str(path)) if path else None
            item.icon = pix if pix is not None and not pix.isNull() else None
            item.skill = core.skill_name(skill, profile) if skill else None
            tip = f"{item.el.label()}  (#{item.el.index})  {item.size[0]}x{item.size[1]}"
            if skill:
                tip += f"\n{item.skill}"
                missing += item.icon is None
            item.setToolTip(tip)
        self.profile, self.missing_icons = profile, missing
        self.scene.update()
        return profile, missing

    def choose_character(self):
        if not self.preset:
            return
        if not self.preset.name:
            QMessageBox.information(self, "bdo-ui",
                                    "Save the layout to the library first, then bind it.")
            return
        old = core.profile_for_preset(self.preset.name)
        family = (old or {}).get("family") or self.family
        dlg = CharacterDialog(self, family, (old or {}).get("char"))
        if dlg.exec() != QDialog.Accepted or not dlg.chosen():
            self.refresh_sources()      # a character may have been named meanwhile
            self.update_title()
            return
        char = dlg.chosen()
        try:
            core.save_profile(self.preset.name, core.capture_profile(family, char, keep=old))
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        _, missing = self.load_icons()
        self.refresh_sources()
        self.update_title()
        self.statusBar().showMessage(
            f"“{self.preset.name}” is bound to {core.char_title(family, char)}"
            + (f"; {missing} skill icons are not downloaded yet" if missing else ""), 10000)

    def fetch_icons(self):
        profile, missing = self.load_icons() if self.preset else (None, 0)
        if not profile:
            QMessageBox.information(
                self, "bdo-ui",
                "This layout has no character yet.\n\nSkill icons are drawn for the "
                "skills of the character bound to the layout (Layout → Character…).")
            return
        if not missing:
            self.statusBar().showMessage("All skill icons are already downloaded", 5000)
            return
        done = [0]

        def progress(_):
            done[0] += 1
            self.statusBar().showMessage(f"Downloading skill icons… {done[0]}")
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            fetched, failed = core.fetch_profile_icons(profile, progress=progress)
        finally:
            QApplication.restoreOverrideCursor()
        self.load_icons()
        self.update_title()
        self.statusBar().showMessage(
            f"{fetched} icons downloaded" + (f", {len(failed)} failed" if failed else ""), 8000)

    def snapshot(self):
        pos = tuple((int(i.pos().x()), int(i.pos().y())) for i in self.items)
        shown = tuple(el.get("IsShow") for el in self.preset.els)
        return (pos, shown, self.preset.screen)

    def restore(self, snap):
        pos, shown, screen = snap
        self.loading = True
        if screen != self.preset.screen:
            self.preset.screen = screen
            self.set_scene_rect()
            self.apply_background()
        for item, p in zip(self.items, pos):
            item.setPos(*p)
        for el, s in zip(self.preset.els, shown):
            if s is not None:
                el.set("IsShow", s)
        self.panel_list.blockSignals(True)
        for r in range(self.panel_list.count()):
            row = self.panel_list.item(r)
            row.setCheckState(Qt.Checked if row.data(ROLE_EL).shown else Qt.Unchecked)
        self.panel_list.blockSignals(False)
        self.loading = False
        self.apply_hidden_filter()
        self.scene.update()
        self.update_inspector()

    def commit(self):
        """Record an undo step if the layout changed since the last one."""
        if not self.preset:
            return
        snap = self.snapshot()
        if snap == self.history[self.hist_pos]:
            return
        del self.history[self.hist_pos + 1:]
        self.history.append(snap)
        self.hist_pos += 1
        self.dirty = True
        self.update_title()

    def undo(self):
        if self.preset and self.hist_pos > 0:
            self.hist_pos -= 1
            self.restore(self.history[self.hist_pos])
            self.dirty = True
            self.update_title()

    def redo(self):
        if self.preset and self.hist_pos < len(self.history) - 1:
            self.hist_pos += 1
            self.restore(self.history[self.hist_pos])
            self.dirty = True
            self.update_title()

    def sync_model(self):
        """Push canvas positions into the elements (only where they changed)."""
        base_screen = self.history[0][2]
        for item in self.items:
            x, y = int(item.pos().x()), int(item.pos().y())
            el = item.el
            if (x, y) != (int(el.get("PosX")), int(el.get("PosY"))) \
                    or self.preset.screen != base_screen:
                core.set_position(el, x, y, item.size, self.preset.screen)

    def confirm_discard(self):
        if not (self.preset and self.dirty):
            return True
        r = QMessageBox.question(
            self, "bdo-ui", "The current layout has unsaved changes. Save them?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def save(self):
        if not self.preset:
            return False
        if not self.preset.name:
            return self.save_as()
        return self.do_save(self.preset.name)

    def save_as(self):
        if not self.preset:
            return False
        name = self.ask_name("Save layout", "Name in the library:", self.preset.name or "")
        if not name:
            return False
        if core.lib_path(name).exists() and name != self.preset.name and QMessageBox.question(
                self, "bdo-ui", f"Overwrite existing layout “{name}”?") != QMessageBox.Yes:
            return False
        return self.do_save(name)

    def do_save(self, name):
        self.sync_model()
        old_name = self.preset.name
        try:
            core.lib_save(self.preset, name)
            self.store_slot_contents(old_name, name)
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return False
        self.load_icons()
        self.dirty = False
        self.history = [self.snapshot()]
        self.hist_pos = 0
        self.known_lib = core.lib_list()
        self.refresh_sources()
        self.update_title()
        self.statusBar().showMessage(f"Saved “{name}”", 4000)
        return True

    def store_slot_contents(self, old_name, name):
        """A library entry keeps the slot contents next to the layout."""
        if core.profile_for_preset(name):
            return
        old = core.profile_for_preset(old_name)
        if old:                         # "Save as": the copy keeps the same contents
            core.save_profile(name, old)
            return
        chars = core.characters(self.family)
        if not chars:
            return
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(chars[0][0]))
        if QMessageBox.question(
                self, "bdo-ui",
                f"Store the skills sitting in the quick and cooldown slots with “{name}”?\n\n"
                f"They are read from the character played last "
                f"({core.char_title(self.family, chars[0][1])}, {when}).\n"
                "Choose No if this layout belongs to another character; pick it "
                "later with Layout → Character…") == QMessageBox.Yes:
            core.save_profile(name, core.capture_profile(self.family, chars[0][1]))

    def restore_slot_contents(self, name):
        """After writing a layout, offer to put the stored slot contents back."""
        profile = core.profile_for_preset(name)
        if not profile:
            return ""
        try:
            _, _, _, changes = core.plan_skills(profile)
            if not changes:
                return ""
            shown = "\n".join("  " + c for c in changes[:12])
            more = f"\n  … and {len(changes) - 12} more" if len(changes) > 12 else ""
            if QMessageBox.question(
                    self, "bdo-ui",
                    f"Character {profile['char']} differs from the slot contents stored "
                    f"with “{name}”:\n\n{shown}{more}\n\nRestore them too?"
                    ) != QMessageBox.Yes:
                return ""
            core.apply_skills(profile)
            return f" {len(changes)} slot contents restored."
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return ""

    def fill_slot_menu(self, menu, lib_name=None):
        """Three "write here" entries that say what each game slot holds now."""
        menu.clear()
        try:
            slots = core.read_slots(self.family)
        except (core.BdoUiError, OSError):
            slots = {}
        for i, tag in enumerate(core.SLOT_TAGS):
            els = slots.get(tag, [])
            if core.slot_is_empty(els):
                now = "empty"
            else:
                count = sum(1 for e in els if e.index is not None)
                now = f"{fmt_screen(core.estimate_screen(els))}, {count} panels"
            menu.addAction(f"Slot {i + 1}   —   now {now}",
                           lambda *_, i=i: self.write_slot(i, lib_name))

    def write_slot(self, slot, lib_name=None):
        """Write the open layout (or library entry `lib_name`) into a game slot."""
        preset = self.preset
        if lib_name and not (preset and preset.name == lib_name):
            try:
                preset = core.lib_load(lib_name)
            except (core.BdoUiError, OSError, ValueError) as e:
                QMessageBox.warning(self, "bdo-ui", str(e))
                return
        if not preset:
            return
        if core.game_running():
            self.set_game_running(True)
            QMessageBox.warning(
                self, "bdo-ui",
                "Black Desert is running.\n\nThe game rewrites its settings file while "
                "it runs, so the change would be lost. Close the game and try again.")
            return
        name = preset.name or "unsaved layout"
        note = ("\n\nIt has unsaved changes; the slot gets the layout as it is on "
                "the canvas now." if preset is self.preset and self.dirty else "")
        if QMessageBox.question(
                self, "bdo-ui",
                f"Replace game slot {slot + 1} of family {self.family} with “{name}”?{note}\n\n"
                "The current file is committed to the settings repo and copied to "
                f"{core.BACKUP_DIR} first.") != QMessageBox.Yes:
            return
        if preset is self.preset:
            self.sync_model()
        try:
            backup = core.write_slot(self.family, slot, [e.copy() for e in preset.els])
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        extra = self.restore_slot_contents(preset.name) if preset.name else ""
        self.refresh_sources()
        self.statusBar().showMessage(
            f"Slot {slot + 1} written.{extra} Backup: {backup}. "
            f"In game: Edit UI → load preset {slot + 1}.", 15000)

    # ------------------------------------------------------------ editing

    def adjust_position(self, item, value):
        x, y = round(value.x()), round(value.y())
        single = len(self.scene.selectedItems()) <= 1
        guides = []
        if self.grid and single:
            x, y = round(x / self.grid) * self.grid, round(y / self.grid) * self.grid
        elif self.act_snap.isChecked() and single:
            x, y, guides = self.snap(item, x, y)
        self.view.set_guides(guides)
        w, h = self.preset.screen
        x = max(-item.size[0] + 10, min(w - 10, x))
        y = max(-item.size[1] + 10, min(h - 10, y))
        return QPointF(x, y)

    def snap(self, item, x, y):
        """Snap edges to the screen border and to nearby visible panels.

        Returns the new position and the guide lines of the edges it stuck to.
        """
        iw, ih = item.size
        best_x, best_y = (SNAP_DIST + 1, x, None), (SNAP_DIST + 1, y, None)
        xs, ys = [0, self.preset.screen[0]], [0, self.preset.screen[1]]
        for other in self.items:
            if other is item or not other.isVisible():
                continue
            ox, oy = other.pos().x(), other.pos().y()
            ow, oh = other.size
            # Only panels that are close on the other axis act as magnets.
            if oy - ih - 40 < y < oy + oh + 40:
                xs += [ox, ox + ow]
            if ox - iw - 40 < x < ox + ow + 40:
                ys += [oy, oy + oh]
        for edge in xs:
            for cand in (edge, edge - iw):
                if abs(cand - x) < best_x[0]:
                    best_x = (abs(cand - x), cand, edge)
        for edge in ys:
            for cand in (edge, edge - ih):
                if abs(cand - y) < best_y[0]:
                    best_y = (abs(cand - y), cand, edge)
        guides = [(axis, best[2]) for axis, best in (("v", best_x), ("h", best_y))
                  if best[2] is not None]
        return round(best_x[1]), round(best_y[1]), guides

    def item_moved(self, item):
        if item.isSelected():
            self.show_coords()

    def nudge(self, dx, dy):
        self.loading = True
        for item in self.selected_items():
            item.setPos(item.pos().x() + dx, item.pos().y() + dy)
        self.loading = False
        self.show_coords()
        self.commit()

    def align(self, mode):
        sel = self.selected_items()
        if len(sel) < 2:
            self.statusBar().showMessage("Select two or more panels to align", 4000)
            return
        self.loading = True
        if mode == "left":
            v = min(i.pos().x() for i in sel)
            for i in sel:
                i.setX(v)
        elif mode == "right":
            v = max(i.pos().x() + i.size[0] for i in sel)
            for i in sel:
                i.setX(v - i.size[0])
        elif mode == "top":
            v = min(i.pos().y() for i in sel)
            for i in sel:
                i.setY(v)
        elif mode == "bottom":
            v = max(i.pos().y() + i.size[1] for i in sel)
            for i in sel:
                i.setY(v - i.size[1])
        elif mode == "row":
            sel.sort(key=lambda i: i.pos().x())
            x, y = sel[0].pos().x(), sel[0].pos().y()
            for i in sel:
                i.setPos(x, y)
                x += i.size[0]
        elif mode == "col":
            sel.sort(key=lambda i: i.pos().y())
            x, y = sel[0].pos().x(), sel[0].pos().y()
            for i in sel:
                i.setPos(x, y)
                y += i.size[1]
        self.loading = False
        self.show_coords()
        self.commit()

    def toggle_shown(self):
        """Show the selected panels in game, or hide them if all are shown already."""
        rows = self.panel_list.selectedItems()
        if not rows:
            return
        turn_on = not all(r.data(ROLE_EL).shown for r in rows)
        self.panel_list.blockSignals(True)
        for r in rows:
            r.data(ROLE_EL).set("IsShow", "true" if turn_on else "false")
            r.setCheckState(Qt.Checked if turn_on else Qt.Unchecked)
        self.panel_list.blockSignals(False)
        self.visibility_changed()

    def list_item_changed(self, row):
        el = row.data(ROLE_EL)
        el.set("IsShow", "true" if row.checkState() == Qt.Checked else "false")
        self.visibility_changed()

    def visibility_changed(self):
        self.apply_hidden_filter()
        self.scene.update()
        self.commit()
        self.update_inspector()

    def apply_hidden_filter(self):
        show_hidden = self.act_hidden.isChecked()
        for item in self.items:
            item.setVisible(show_hidden or item.el.shown)

    def grid_changed(self, value):
        self.grid = value
        self.view.viewport().update()

    def change_screen(self):
        if not self.preset:
            return
        dlg = ScreenDialog(self, self.preset.screen)
        if dlg.exec() != QDialog.Accepted:
            return
        new = (dlg.w.value(), dlg.h.value())
        old = self.preset.screen
        if new == old:
            return
        self.loading = True
        for item in self.items:
            cx = (item.pos().x() + item.size[0] / 2) / old[0]
            cy = (item.pos().y() + item.size[1] / 2) / old[1]
            item.setPos(round(cx * new[0] - item.size[0] / 2),
                        round(cy * new[1] - item.size[1] / 2))
        self.loading = False
        self.preset.screen = new
        self.set_scene_rect()
        self.apply_background()
        self.commit()
        self.update_inspector()
        self.view.fit()

    # ------------------------------------------------------------ selection

    def selected_items(self):
        return [i for i in self.scene.selectedItems() if isinstance(i, PanelItem)]

    def select_all(self):
        self.syncing_selection = True
        for item in self.items:
            item.setSelected(item.isVisible())
        self.syncing_selection = False
        self.selection_changed()

    def selection_changed(self):
        if self.syncing_selection:
            return
        sel = self.selected_items()
        self.syncing_selection = True
        self.panel_list.clearSelection()
        for item in sel:
            item.row.setSelected(True)
        if sel:
            self.panel_list.scrollToItem(sel[0].row)
        self.syncing_selection = False
        self.update_inspector()

    def list_selection_changed(self):
        if self.syncing_selection:
            return
        self.syncing_selection = True
        self.scene.clearSelection()
        for row in self.panel_list.selectedItems():
            item = row.data(ROLE_KIND)
            if isinstance(item, PanelItem):
                item.setSelected(True)
        self.syncing_selection = False
        self.update_inspector()

    def update_inspector(self):
        rows = self.panel_list.selectedItems() if self.preset else []
        items = self.selected_items()
        if not rows:
            title = "Nothing selected"
            sub = ("Click a panel on the canvas or in the list below."
                   if self.preset else "No layout is open.")
        elif len(rows) == 1:
            el = rows[0].data(ROLE_EL)
            title = el.label()
            if items:
                sub = f"#{el.index}  ·  {items[0].size[0]} × {items[0].size[1]} units"
                if items[0].skill:
                    sub += f"\n{items[0].skill}"
            else:
                sub = f"#{el.index}  ·  no position stored, only visibility can be changed"
        else:
            title = f"{len(rows)} panels selected"
            sub = "X and Y move the whole group."
        self.sel_title.setText(title)
        self.sel_sub.setText(sub)
        for box in (self.x_box, self.y_box):
            box.setEnabled(bool(items))
        self.show_coords()
        shown = [r.data(ROLE_EL).shown for r in rows]
        self.vis_box.setEnabled(bool(rows))
        self.vis_box.setTristate(bool(shown) and any(shown) and not all(shown))
        self.vis_box.setCheckState(Qt.Unchecked if not any(shown) else
                                   Qt.Checked if all(shown) else Qt.PartiallyChecked)
        if self.preset:
            els = [e for e in self.preset.els if e.index is not None]
            self.panel_count.setText(f"{sum(e.shown for e in els)} of {len(els)} visible in game")
        else:
            self.panel_count.setText("")
        self.update_actions()

    def show_coords(self):
        items = self.selected_items()
        if not items:
            return
        origin = (min(i.pos().x() for i in items), min(i.pos().y() for i in items))
        for box, v in zip((self.x_box, self.y_box), origin):
            box.blockSignals(True)
            box.setValue(int(v))
            box.blockSignals(False)

    def spin_changed(self):
        items = self.selected_items()
        if not items:
            return
        dx = self.x_box.value() - min(i.pos().x() for i in items)
        dy = self.y_box.value() - min(i.pos().y() for i in items)
        if not (dx or dy):
            return
        self.loading = True
        for item in items:
            item.setPos(item.pos().x() + dx, item.pos().y() + dy)
        self.loading = False
        self.commit()

    def filter_panels(self, *_):
        needle = self.panel_search.text().strip().lower()
        for r in range(self.panel_list.count()):
            row = self.panel_list.item(r)
            el = row.data(ROLE_EL)
            row.setHidden(bool(needle) and needle not in f"{el.label()} #{el.index}".lower())

    def canvas_menu(self):
        menu = QMenu(self)
        menu.addAction(self.act_toggle)
        sub = menu.addMenu("Align")
        sub.addActions(self.align_acts[:4])
        sub.addSeparator()
        sub.addActions(self.align_acts[4:])
        sub.setEnabled(len(self.selected_items()) >= 2)
        menu.addSeparator()
        menu.addActions([self.act_select_all, self.act_fit])
        return menu

    # ------------------------------------------------------------ view

    def zoom_actual(self):
        self.view.zoom_by(1 / self.view.zoom(), False)

    def zoom_changed(self):
        self.zoom_btn.setText(f"{round(self.view.zoom() * 100)}%" if self.preset else "")

    def show_cursor(self, pos):
        text = ""
        if pos is not None and self.preset:
            w, h = self.preset.screen
            if 0 <= pos.x() <= w and 0 <= pos.y() <= h:
                text = f"x {int(pos.x())}   y {int(pos.y())}"
        self.cursor_label.setText(text)

    def pick_background(self):
        start = str(core.BDO_DIR / "ScreenShot")
        path, _ = QFileDialog.getOpenFileName(
            self, "Game screenshot", start, "Images (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return False
        self.bg_path = path
        self.act_bg.setChecked(True)
        self.apply_background()
        return True

    def toggle_background(self, on):
        if on and not self.bg_path:     # nothing to show yet: ask for a screenshot
            if not self.pick_background():
                self.act_bg.setChecked(False)
        elif self.bg_item:
            self.bg_item.setVisible(on)

    def apply_background(self):
        if self.bg_item:
            self.scene.removeItem(self.bg_item)
            self.bg_item = None
        if not (self.bg_path and self.preset):
            return
        pix = QPixmap(self.bg_path)
        if pix.isNull():
            return
        self.bg_item = QGraphicsPixmapItem(pix)
        w, h = self.preset.screen
        self.bg_item.setTransform(
            self.bg_item.transform().scale(w / pix.width(), h / pix.height()))
        self.bg_item.setOpacity(0.55)
        self.bg_item.setZValue(-5)
        self.bg_item.setVisible(self.act_bg.isChecked())
        self.scene.addItem(self.bg_item)

    def toggle_tips(self, on):
        self.tips.setVisible(on)

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    # ------------------------------------------------------------ misc

    def change_game_folder(self):
        if not pick_game_folder(self):
            return
        fams = core.families()
        self.family_box.blockSignals(True)
        self.family_box.clear()
        self.family_box.addItems(fams)
        self.family_box.blockSignals(False)
        self.family = fams[0]
        self.refresh_sources()
        self.statusBar().showMessage(f"Game folder: {core.BDO_DIR}", 8000)

    def refresh_status(self):
        # Pick up presets added or removed outside this window (CLI, another run).
        names = core.lib_list()
        if names != self.known_lib:
            self.known_lib = names
            self.refresh_sources()
        self.watch.poll()

    def set_game_running(self, running):
        self.game_is_running = bool(running)
        if running:
            self.game_pill.set("Game is running — slots are read-only", theme.WARN)
            self.write_btn.setText("Game is running")
            self.write_btn.setIcon(theme.icon("lock", theme.MUTED, disabled=theme.MUTED))
            self.write_btn.setToolTip(
                "Close Black Desert to write a slot: the game rewrites its settings "
                "file while it runs, so the change would be lost")
        else:
            self.game_pill.set("Game is closed — slots can be written", theme.OK)
            self.write_btn.setText("Write to game slot")
            self.write_btn.setIcon(theme.icon("write", theme.ACCENT_TEXT, disabled=theme.MUTED))
            self.write_btn.setToolTip(
                "Put this layout into one of the three in-game preset slots")
        self.lock_icon.setVisible(self.game_is_running)
        self.lock_text.setVisible(self.game_is_running)
        self.update_actions()

    def update_actions(self):
        has = self.preset is not None
        selected = len(self.selected_items()) if has else 0
        self.act_save.setEnabled(has and (self.dirty or not self.preset.name))
        self.act_save_as.setEnabled(has)
        self.act_revert.setEnabled(has and self.dirty and bool(
            self.preset.name or self.preset.meta.get("from")))
        for a in (self.act_rename, self.act_duplicate, self.act_delete):
            a.setEnabled(self.current_lib_name() is not None)
        self.act_undo.setEnabled(has and self.hist_pos > 0)
        self.act_redo.setEnabled(has and self.hist_pos < len(self.history) - 1)
        self.act_toggle.setEnabled(has and bool(self.panel_list.selectedItems()))
        for a in self.align_acts:
            a.setEnabled(selected >= 2)
        self.align_menu.setEnabled(selected >= 2)
        for a in (self.act_select_all, self.act_char, self.act_screen, self.act_zoom_in,
                  self.act_zoom_out, self.act_fit, self.act_actual, self.act_bg_pick,
                  self.act_bg):
            a.setEnabled(has)
        self.act_get_icons.setEnabled(has and self.missing_icons > 0)
        can_write = has and not self.game_is_running
        self.write_btn.setEnabled(can_write)
        self.slot_menu.setEnabled(can_write)

    def update_title(self):
        """Refresh everything that describes the open layout as a whole."""
        preset = self.preset
        name = (preset.name or "Untitled layout") if preset else "No layout open"
        self.setWindowTitle(f"{name}[*] — bdo-ui")
        self.setWindowModified(bool(preset and self.dirty))
        self.doc_title.setText(name)
        self.doc_badge.setVisible(bool(preset and self.dirty))
        source = ""
        if preset and not preset.name:
            tag = preset.meta.get("from")
            if tag in core.SLOT_TAGS:
                source = f"copy of game slot {core.SLOT_TAGS.index(tag) + 1}, "
            elif tag == core.REVERT_TAG:
                source = "copy of the game default, "
            source += "not in the library yet"
        self.doc_source.setText(source)

        parts, portrait = profile_parts(self.profile) if preset else ([], None)
        thumb = portrait_pixmap(portrait, 40, 40, 7, 0.28) if portrait else None
        self.char_thumb.setPixmap(thumb or theme.pixmap("user", theme.MUTED, 40))
        if not preset:
            head, sub = "No layout open", ""
        elif self.profile:
            head = parts[0]
            sub = " · ".join(parts[1:]) or f"id …{str(self.profile.get('char', ''))[-8:]}"
        else:
            head, sub = "No character", "no skills stored"
        self.char_name.setText(head)
        self.char_sub.setText(sub)
        self.char_thumb.setToolTip(
            f"Character {self.profile.get('char', '')}" if preset and self.profile else "")
        self.char_btn.setText("Change…" if self.profile else "Choose…")
        self.char_btn.setEnabled(preset is not None)
        self.screen_label.setText(
            f"{preset.screen[0]} × {preset.screen[1]}" if preset else "")
        self.screen_label.setToolTip("Size of the game screen in UI units")
        self.screen_btn.setEnabled(preset is not None)
        missing = self.missing_icons if preset else 0
        self.icons_label.setVisible(missing > 0)
        self.icons_btn.setVisible(missing > 0)
        self.icons_label.setText(f"{missing} skill icons are not downloaded")
        self.zoom_changed()
        self.sources.viewport().update()
        self.slots.viewport().update()
        self.update_actions()

    def closeEvent(self, event):
        if self.confirm_discard():
            self.timer.stop()
            self.save_ui_state()
            event.accept()
        else:
            event.ignore()


def pick_game_folder(parent=None):
    """Ask for the game's documents folder until a valid one is chosen."""
    start = str(core.BDO_DIR if core.BDO_DIR.is_dir() else core.Path.home())
    while True:
        path = QFileDialog.getExistingDirectory(
            parent, "Choose the 'Black Desert' folder (the one with UserCache inside)", start)
        if not path:
            return False
        try:
            core.set_docs(path)
            if core.families():
                return True
            problem = "No family folders with saved settings in there yet."
        except core.BdoUiError as e:
            problem = str(e)
        QMessageBox.warning(parent, "bdo-ui", problem)
        start = path


def run(open_name=None):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("bdo-ui")
    app.setDesktopFileName("bdo-ui")
    theme.apply(app)
    if not core.docs_valid():
        QMessageBox.information(
            None, "bdo-ui",
            "Black Desert settings were not found automatically.\n\n"
            f"Looked in: {core.BDO_DIR}\n\n"
            "Choose the game's 'Black Desert' documents folder — the one that "
            "contains GameOption.txt and UserCache. It will be remembered.")
        if not pick_game_folder():
            return 1
    win = Main()
    if open_name:
        win.open_preset(core.lib_load(open_name))
        win.refresh_sources()
    win.show()
    QTimer.singleShot(0, win.view.fit)
    return app.exec()
