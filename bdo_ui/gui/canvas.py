# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""The canvas: the game screen with the panels as draggable rectangles."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsView, QStyle

from .. import panels
from ..i18n import tr
from . import theme

COLORS = {
    "quick": QColor(90, 170, 255),
    "cooldown": QColor(255, 170, 70),
    "chat": QColor(120, 210, 140),
    "other": QColor(190, 150, 240),
}
SNAP_DIST = 6
SCENE_MARGIN = 200          # room around the screen for panels that stick out


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
                             tr("canvas.screen", w=preset.screen[0], h=preset.screen[1]))
        else:
            font = painter.font()
            font.setPointSizeF(font.pointSizeF() * 1.35)
            painter.setFont(font)
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, tr("canvas.empty"))
        painter.restore()
