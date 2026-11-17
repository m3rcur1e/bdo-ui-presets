# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Dialogs of the editor: character, screen size, shortcuts, about, game folder."""

import html
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
                               QVBoxLayout)

from .. import core, updater
from ..i18n import tr, trn
from . import theme
from .delegates import CharDelegate, ROLE_CARD, ROLE_EL
from .widgets import (ask_text, letter_pixmap, muted_label, notify, plain_buttons, portrait_pixmap,
                      section_label, warn)

# (section, ((input, what it does), ...)) as catalog keys. An input that does not
# start with "keys." is a plain key name and is shown as it is in every language.
SHORTCUTS = (
    ("keys.canvas", (
        ("keys.k.drag", "keys.drag"),
        ("keys.k.nudge", "keys.nudge"),
        ("keys.k.multi", "keys.multi"),
        ("keys.k.wheel", "keys.wheel"),
        ("keys.k.pan", "keys.pan"),
        ("F", "keys.fit"),
        ("Ctrl+1", "keys.actual"),
        ("H", "keys.toggle"),
        ("Ctrl+A / Esc", "keys.select"),
    )),
    ("keys.layout", (
        ("Ctrl+S / Ctrl+Shift+S", "keys.save"),
        ("Ctrl+Z / Ctrl+Shift+Z", "keys.undo"),
        ("Ctrl+F", "keys.search"),
        ("F2 / Ctrl+D / Delete", "keys.entry"),
    )),
)


class CharacterDialog(QDialog):
    """Pick the character a library entry belongs to, as a wall of portrait cards."""

    def __init__(self, parent, family, current):
        super().__init__(parent)
        self.family, self.current = family, current
        self.cards = []
        self.setWindowTitle(tr("char.title"))
        self.resize(1040, 790)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        text = QVBoxLayout()
        title = QLabel(tr("char.heading"))
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        title.setFont(font)
        text.addWidget(title)
        text.addWidget(muted_label(tr("char.intro", family=family), wrap=True))
        top.addLayout(text, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("char.search"))
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
        self.name_btn = QPushButton(tr("char.name_btn"))
        self.name_btn.setIcon(theme.icon("pencil"))
        self.name_btn.setToolTip(tr("char.name_btn.tip"))
        self.name_btn.setAutoDefault(False)
        self.name_btn.clicked.connect(self.rename)
        QShortcut(QKeySequence(Qt.Key_F2), self).activated.connect(self.rename)
        row.addWidget(self.name_btn)
        self.all_box = QCheckBox(tr("char.show_gone"))
        self.all_box.toggled.connect(self.populate)
        row.addWidget(self.all_box)
        row.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_btn = box.button(QDialogButtonBox.Ok)
        plain_buttons(box, ok=tr("char.use"))
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
                or tr("char.noclass")
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
            item.setToolTip(f"{tr('char.id', id=card['char'])}\n"
                            f"{trn('count.cooldown', card['cooldown'])}, "
                            f"{trn('count.quick', card['quick'])}")
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
        name, ok = ask_text(self, tr("char.name.title"), tr("char.name.label"), old)
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
        self.setWindowTitle(tr("screen.title"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)
        lay.addWidget(muted_label(tr("screen.intro"), wrap=True))
        form = QFormLayout()
        self.w, self.h = QSpinBox(), QSpinBox()
        for box, val in ((self.w, screen[0]), (self.h, screen[1])):
            box.setRange(640, 8000)
            box.setValue(val)
            box.setSuffix(" " + tr("screen.units"))
        form.addRow(tr("screen.width"), self.w)
        form.addRow(tr("screen.height"), self.h)
        self.scale = core.ui_scale()
        self.px = QComboBox()
        self.px.addItem(tr("screen.pick", scale=f"{self.scale:g}"))
        for w, h in self.WINDOWS:
            self.px.addItem(tr("screen.px", w=w, h=h), (w, h))
        self.px.setToolTip(tr("screen.pick.tip"))
        self.px.activated.connect(self.from_pixels)
        form.addRow(tr("screen.from_window"), self.px)
        btn = QPushButton(tr("screen.from_game"))
        btn.setAutoDefault(False)
        btn.clicked.connect(self.from_game)
        form.addRow("", btn)
        lay.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        plain_buttons(box, ok=tr("screen.resize"))
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
            notify(self, tr("screen.not_found"))
            return
        self.w.setValue(scr[0])
        self.h.setValue(scr[1])


class ShortcutsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("act.keys"))
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
            grid.addWidget(section_label(tr(title)), row, 0, 1, 2)
            row += 1
            for keys, what in rows:
                key = QLabel(tr(keys) if keys.startswith("keys.") else keys)
                key.setObjectName("key")
                grid.addWidget(key, row, 0, Qt.AlignLeft)
                grid.addWidget(QLabel(tr(what)), row, 1)
                row += 1
        lay.addLayout(grid)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        plain_buttons(box)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


class AboutDialog(QDialog):
    """Who wrote the program, its licence and where the original lives."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("act.about"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)
        name = QLabel(f"bdo-ui {html.escape(updater.local_version())}")
        font = name.font()
        font.setPointSizeF(font.pointSizeF() * 1.5)
        font.setBold(True)
        name.setFont(font)
        lay.addWidget(name)
        link = (f'<a href="{updater.PAGE_URL}" style="color: {theme.ACCENT}">'
                f'{html.escape(updater.PAGE_URL.split("//", 1)[1])}</a>')
        texts = [(tr("about.what"), False),
                 (html.escape(updater.COPYRIGHT), False),
                 (html.escape(tr("about.license")), False),
                 (tr("about.source", link=link), False),
                 (html.escape(tr("about.disclaimer")), True)]
        for text, muted in texts:
            label = QLabel(text)
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            if muted:
                label.setObjectName("muted")
            lay.addWidget(label)
        self.setMinimumWidth(440)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        plain_buttons(box)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


def pick_game_folder(parent=None):
    """Ask for the game's documents folder until a valid one is chosen."""
    start = str(core.config.BDO_DIR if core.config.BDO_DIR.is_dir() else Path.home())
    while True:
        path = QFileDialog.getExistingDirectory(
            parent, tr("dlg.folder.title"), start)
        if not path:
            return False
        try:
            core.set_docs(path)
            if core.families():
                return True
            problem = tr("msg.no_families")
        except core.BdoUiError as e:
            problem = str(e)
        warn(parent, problem)
        start = path
