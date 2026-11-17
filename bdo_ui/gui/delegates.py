# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""How the rows of the lists are drawn: library cards, panels, characters."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..i18n import tr
from . import theme

ROLE_EL = Qt.UserRole
ROLE_KIND = Qt.UserRole + 1
ROLE_CARD = Qt.UserRole + 2


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

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        el = index.data(ROLE_EL)
        if el is not None:      # keep a long name off the index
            fm = option.fontMetrics
            room = option.rect.width() - fm.horizontalAdvance(f"#{el.index}") - 48
            option.text = fm.elidedText(option.text, Qt.ElideRight, max(room, 20))

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
            self.chip(painter, small, QPointF(px + 7, py + 7), tr("char.current"),
                      QColor(theme.ACCENT), QColor(theme.ACCENT_TEXT))
        elif gone:
            self.chip(painter, small, QPointF(px + 7, py + 7), tr("char.gone"),
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
                         fm.elidedText(card["name"] or tr("char.noname"), Qt.ElideRight,
                                       int(width)))
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
                         fm.elidedText(tr("char.played", when=card["when"]), Qt.ElideRight,
                                       int(width)))
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
