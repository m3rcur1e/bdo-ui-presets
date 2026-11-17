# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Small building blocks of the editor: message boxes, labels, portraits, the tips strip."""

import html
import time

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QInputDialog, QLabel, QMessageBox,
                               QPushButton, QSizePolicy, QWidget)

from .. import core, i18n
from ..i18n import tr
from . import theme


def notify(parent, text, icon=QMessageBox.Information):
    box = QMessageBox(icon, "bdo-ui", text, QMessageBox.NoButton, parent)
    box.addButton(tr("btn.ok"), QMessageBox.AcceptRole)
    box.exec()


def warn(parent, text):
    notify(parent, text, QMessageBox.Warning)


_ROLES = {"yes": QMessageBox.YesRole, "no": QMessageBox.NoRole,
          "save": QMessageBox.AcceptRole, "discard": QMessageBox.DestructiveRole,
          "cancel": QMessageBox.RejectRole}


def ask(parent, text, *buttons):
    """A question; returns the name of the chosen button ("yes" / "no" by default).

    The first button is the default one, the last one is what Esc picks.
    """
    buttons = buttons or ("yes", "no")
    box = QMessageBox(QMessageBox.Question, "bdo-ui", text, QMessageBox.NoButton, parent)
    made = {name: box.addButton(tr("btn." + name), _ROLES[name]) for name in buttons}
    box.setDefaultButton(made[buttons[0]])
    box.setEscapeButton(made[buttons[-1]])
    box.exec()
    clicked = box.clickedButton()
    return next((name for name, b in made.items() if b is clicked), buttons[-1])


def ask_text(parent, title, label, text=""):
    """One line of text; returns (text, accepted)."""
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setTextValue(text)
    dlg.setOkButtonText(tr("btn.ok"))
    dlg.setCancelButtonText(tr("btn.cancel"))
    for button in dlg.findChildren(QPushButton):
        button.setIcon(QIcon())
    accepted = dlg.exec() == QDialog.Accepted
    return dlg.textValue(), accepted


def plain_buttons(box, **texts):
    """Label the standard buttons of a button box from the catalog, without icons."""
    for name, button in (("ok", QDialogButtonBox.Ok), ("cancel", QDialogButtonBox.Cancel),
                         ("close", QDialogButtonBox.Close)):
        b = box.button(button)
        if b:
            b.setText(texts.get(name) or tr("btn." + name))
            b.setIcon(QIcon())


def fmt_screen(screen):
    return f"{screen[0]}×{screen[1]}"


def section_label(text=""):
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


class ElidedLabel(QLabel):
    """A one-line label that cuts its text with "…" instead of demanding room for it.

    Translated texts differ a lot in length; the full text goes to the tooltip
    whenever it is cut.
    """

    def __init__(self, text=""):
        super().__init__()
        self.full = ""
        self.setText(text)

    def setText(self, text):
        self.full = text
        self.updateGeometry()
        self.fit()

    def text(self):
        return self.full

    def fit(self):
        cut = self.fontMetrics().elidedText(self.full, Qt.ElideRight, self.width())
        if QLabel.text(self) != cut:
            super().setText(cut)
        self.setToolTip(self.full if cut != self.full else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.full) + 2,
                     super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance("…") + 2,
                     super().minimumSizeHint().height())


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
    return parts or [tr("char.anon", id=char[-8:])], core.portrait_path(char)


TIP_INTERVAL = 15000        # ms between tips


class TipStrip(QLabel):
    """One-line rotating hint in the status bar; a click shows the next one.

    The hints are the catalog keys "tip.1", "tip.2", ...
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index = int(time.time())
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
        tips = [k for k in i18n.keys("tip.") if k[4:].isdigit()]
        if not tips:
            self.setText("")
            return
        tip = tr(tips[self.index % len(tips)])
        self.setText(f'<span style="color:{theme.ACCENT}; font-weight:bold">'
                     f'{html.escape(tr("tip.label"))}</span>'
                     f'&nbsp;&nbsp;<span style="color:{theme.MUTED}">'
                     f'{html.escape(tip, quote=False)}</span>')
        # The strip is clipped in a narrow window; the tooltip has the full text.
        self.setToolTip(f"{tip}\n\n{tr('tip.next')}")

    def next_tip(self):
        self.index += 1
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
