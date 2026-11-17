# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""The main window of the editor."""

import sys
import time

from PySide6.QtCore import QByteArray, QPointF, QProcess, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QKeySequence, QPixmap,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QGraphicsPixmapItem, QGraphicsScene, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QPushButton, QSizePolicy, QSpinBox, QSplitter, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)

from .. import core, i18n, updater
from ..i18n import tr, trn
from . import theme
from .canvas import PanelItem, SCENE_MARGIN, SNAP_DIST, View
from .delegates import CardDelegate, PanelDelegate, ROLE_CARD, ROLE_EL, ROLE_KIND
from .dialogs import AboutDialog, CharacterDialog, ScreenDialog, ShortcutsDialog, pick_game_folder
from .language import LANG_AUTO, apply_language, configured_language, system_language
from .watch import GameWatch, UpdateWatch
from .widgets import (ElidedLabel, Pill, TipStrip, ask, ask_text, fmt_screen, letter_pixmap,
                      muted_label, notify, portrait_pixmap, profile_parts, profile_summary,
                      section_label, warn)


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
        self.new_version = None     # a newer version found on GitHub
        self.restart_on_close = False
        self.live_texts = []        # callables that put the translated texts in place
        self.toolbar_width = 0      # what the toolbar needs with every label shown

        fams = core.families()
        if not fams:
            raise core.BdoUiError(tr("err.no_families", path=core.config.BDO_DIR))
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

        self.update_watch = UpdateWatch(self)
        self.update_watch.checked.connect(self.update_checked)
        self.update_watch.failed.connect(self.update_check_failed)
        self.update_watch.installed.connect(self.update_installed)
        self.update_watch.install_failed.connect(self.update_install_failed)
        # Looked at when the timer fires, so switching it off right away works too.
        QTimer.singleShot(2000, lambda: self.act_update_auto.isChecked()
                          and self.isVisible() and self.check_updates(False))
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

    def live(self, fn):
        """Run `fn` now and again on every language switch; it sets translated texts."""
        self.live_texts.append(fn)
        fn()

    def t(self, setter, key):
        """Keep a text of the window (label, title, tooltip...) in the current language."""
        self.live(lambda: setter(tr(key)))

    def follow_tip(self, widget, action):
        """Give a widget the tooltip of an action, in whatever language that is."""
        self.live(lambda: widget.setToolTip(action.toolTip()))

    def build_actions(self):
        def mk(key, slot, keys=(), icon=None, checkable=False, checked=False):
            # `key` is the text; the tooltip is `key`.tip, or the text when there is none.
            a = QAction(self)
            if icon:
                a.setIcon(theme.icon(icon))
            keys = [QKeySequence(k) for k in ((keys,) if isinstance(keys, str) else keys)]
            if keys:
                a.setShortcuts(keys)

            def label():
                a.setText(tr(key))
                tip = tr(key + ".tip") if i18n.has(key + ".tip") else tr(key).rstrip("…")
                if keys:
                    tip += f"  ({keys[0].toString(QKeySequence.NativeText)})"
                a.setToolTip(tip)

            self.live(label)
            if checkable:
                a.setCheckable(True)
                a.setChecked(checked)
                a.toggled.connect(slot)
            else:
                a.triggered.connect(lambda _=False: slot())
            self.addAction(a)
            return a

        self.act_save = mk("act.save", self.save, "Ctrl+S", "save")
        self.act_save_as = mk("act.save_as", self.save_as, "Ctrl+Shift+S")
        self.act_revert = mk("act.revert", self.revert, (), "revert")
        self.act_rename = mk("act.rename", self.rename_preset, "F2", "pencil")
        self.act_duplicate = mk("act.duplicate", self.duplicate_preset, "Ctrl+D", "copy")
        self.act_delete = mk("act.delete", self.delete_preset, (), "trash")
        self.act_lib_folder = mk("act.lib_folder", self.open_lib_folder, (), "folder")
        self.act_game_folder = mk("act.game_folder", self.change_game_folder)
        self.act_quit = mk("act.quit", self.close, "Ctrl+Q")

        self.act_undo = mk("act.undo", self.undo, "Ctrl+Z", "undo")
        self.act_redo = mk("act.redo", self.redo, ("Ctrl+Shift+Z", "Ctrl+Y"), "redo")
        self.act_select_all = mk("act.select_all", self.select_all, "Ctrl+A")
        self.act_deselect = mk("act.deselect", self.scene.clearSelection, "Esc")
        self.act_toggle = mk("act.toggle", self.toggle_shown, "H", "eye")
        self.align_acts = [
            mk(key, lambda *_, mode=mode: self.align(mode), (), icon)
            for key, mode, icon in (
                ("act.align.left", "left", "align_left"),
                ("act.align.right", "right", "align_right"),
                ("act.align.top", "top", "align_top"),
                ("act.align.bottom", "bottom", "align_bottom"),
                ("act.align.row", "row", "pack_row"),
                ("act.align.col", "col", "pack_col"))]
        self.act_snap = mk("act.snap", lambda _: None, (), "magnet",
                           checkable=True, checked=True)

        self.act_char = mk("act.char", self.choose_character, (), "user")
        self.act_screen = mk("act.screen", self.change_screen, (), "monitor")
        self.act_get_icons = mk("act.get_icons", self.fetch_icons, (), "download")

        self.act_zoom_in = mk("act.zoom_in", lambda: self.view.zoom_by(1.25, False),
                              ("Ctrl+=", "Ctrl++"), "zoom_in")
        self.act_zoom_out = mk("act.zoom_out", lambda: self.view.zoom_by(1 / 1.25, False),
                               "Ctrl+-", "zoom_out")
        self.act_fit = mk("act.fit", self.view.fit, ("F", "Ctrl+0"), "fit")
        self.act_actual = mk("act.actual", self.zoom_actual, "Ctrl+1")
        self.act_hidden = mk("act.hidden", lambda _: self.apply_hidden_filter(), (),
                             "ghost", checkable=True, checked=True)
        self.act_icons = mk("act.icons", lambda _: self.scene.update(), (),
                            "skill", checkable=True, checked=True)
        self.act_bg_pick = mk("act.bg_pick", self.pick_background)
        self.act_bg = mk("act.bg", self.toggle_background, (), "image", checkable=True)
        self.act_tips = mk("act.tips", self.toggle_tips, checkable=True, checked=True)
        self.act_keys = mk("act.keys", self.show_shortcuts, "F1", "keyboard")
        self.act_update = mk("act.update", lambda: self.check_updates(True))
        self.act_about = mk("act.about", self.show_about)
        self.act_update_auto = mk("act.update_auto", lambda _: None,
                                  checkable=True, checked=True)

    def build_menus(self):
        def menu(parent, key):
            m = parent.addMenu("")
            self.t(m.setTitle, key)
            return m

        self.slot_menu = QMenu(self)
        self.t(self.slot_menu.setTitle, "menu.write")
        self.slot_menu.setIcon(theme.icon("write"))
        self.slot_menu.aboutToShow.connect(lambda: self.fill_slot_menu(self.slot_menu))

        bar = self.menuBar()
        m = menu(bar, "menu.file")
        m.addActions([self.act_save, self.act_save_as, self.act_revert])
        m.addSeparator()
        m.addActions([self.act_rename, self.act_duplicate, self.act_delete])
        m.addSeparator()
        m.addMenu(self.slot_menu)
        m.addSeparator()
        m.addActions([self.act_lib_folder, self.act_game_folder])
        m.addSeparator()
        m.addAction(self.act_quit)

        m = menu(bar, "menu.edit")
        m.addActions([self.act_undo, self.act_redo])
        m.addSeparator()
        m.addActions([self.act_select_all, self.act_deselect])
        m.addSeparator()
        m.addAction(self.act_toggle)
        self.align_menu = menu(m, "menu.align")
        self.align_menu.addActions(self.align_acts[:4])
        self.align_menu.addSeparator()
        self.align_menu.addActions(self.align_acts[4:])
        m.addSeparator()
        m.addAction(self.act_snap)

        m = menu(bar, "menu.layout")
        m.addActions([self.act_char, self.act_screen, self.act_get_icons])

        m = menu(bar, "menu.view")
        m.addActions([self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual])
        m.addSeparator()
        m.addActions([self.act_hidden, self.act_icons])
        m.addSeparator()
        m.addActions([self.act_bg_pick, self.act_bg])
        m.addSeparator()
        m.addAction(self.act_tips)
        m.addMenu(self.build_language_menu())

        m = menu(bar, "menu.help")
        m.addAction(self.act_keys)
        m.addSeparator()
        m.addActions([self.act_update, self.act_update_auto])
        m.addSeparator()
        m.addAction(self.act_about)

    def build_language_menu(self):
        """One entry per catalog found in lang/, plus "as the system"."""
        self.lang_menu = QMenu(self)
        self.lang_menu.setIcon(theme.icon("globe"))

        def title():
            # Findable in a language one cannot read.
            text = tr("menu.language")
            self.lang_menu.setTitle(text if text == "Language" else f"{text} (Language)")

        self.live(title)
        group = QActionGroup(self)
        names = i18n.names()
        self.lang_acts = {}
        for code in (LANG_AUTO, *names):
            a = QAction(names.get(code, ""), self)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, code=code: self.set_language(code))
            group.addAction(a)
            self.lang_menu.addAction(a)
            self.lang_acts[code] = a
            if code == LANG_AUTO:
                self.lang_menu.addSeparator()
        self.live(lambda: self.lang_acts[LANG_AUTO].setText(
            tr("lang.auto", name=names.get(system_language(), system_language()))))
        self.lang_acts[configured_language()].setChecked(True)
        return self.lang_menu

    def build_toolbar(self):
        tb = self.toolbar = QToolBar()
        self.addToolBar(tb)
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

        def grid_texts():
            prefix, off = tr("grid.prefix") + " ", tr("grid.off")
            self.grid_box.setPrefix(prefix)
            self.grid_box.setSpecialValueText(off)
            self.grid_box.setToolTip(tr("grid.tip"))
            fm = self.grid_box.fontMetrics()
            self.grid_box.setFixedWidth(max(104, 38 + max(
                fm.horizontalAdvance(off), fm.horizontalAdvance(prefix + "100"))))

        self.live(grid_texts)
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

        def section(key):
            label = section_label()
            self.t(label.setText, key)
            return label

        def search_box(placeholder, slot):
            box = QLineEdit()
            self.t(box.setPlaceholderText, placeholder)
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
        row.addWidget(section("side.library"))
        row.addStretch(1)
        for a in (self.act_duplicate, self.act_rename, self.act_delete):
            row.addWidget(flat(a))
        lay.addLayout(row)
        self.lib_search = search_box("side.search", self.filter_library)
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
        self.lib_empty = muted_label(wrap=True)
        self.t(self.lib_empty.setText, "side.empty")
        lay.addWidget(self.lib_empty)

        row = QHBoxLayout()
        row.addWidget(section("side.slots"))
        row.addStretch(1)
        self.lock_icon = QLabel()
        self.lock_icon.setPixmap(theme.pixmap("lock", theme.WARN, 16))
        self.lock_text = ElidedLabel()
        self.t(self.lock_text.setText, "side.readonly")
        self.lock_text.setObjectName("warn")
        row.addWidget(self.lock_icon)
        row.addWidget(self.lock_text)
        lay.addSpacing(6)
        lay.addLayout(row)
        row = QHBoxLayout()
        family_label = muted_label()
        self.t(family_label.setText, "side.family")
        row.addWidget(family_label)
        self.family_box = QComboBox()
        self.family_box.addItems(fams)
        self.t(self.family_box.setToolTip, "side.family.tip")
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
        self.doc_title = ElidedLabel()
        font = self.doc_title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        self.doc_title.setFont(font)
        row.addWidget(self.doc_title)
        self.doc_badge = Pill(dot=False)
        self.live(lambda: self.doc_badge.set(tr("doc.unsaved"), theme.ACCENT))
        row.addWidget(self.doc_badge)
        # The note takes whatever room is left and is the first thing to be cut.
        self.doc_source = ElidedLabel()
        self.doc_source.setObjectName("muted")
        self.doc_source.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.doc_source, 1)
        row.addWidget(flat(self.act_zoom_out))
        self.zoom_btn = QToolButton()
        self.zoom_btn.setObjectName("flat")
        self.t(self.zoom_btn.setToolTip, "zoom.tip")
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

        lay.addWidget(section("side.layout"))
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
        self.char_name = ElidedLabel()
        self.char_sub = ElidedLabel()
        self.char_sub.setObjectName("muted")
        col.addWidget(self.char_name)
        col.addWidget(self.char_sub)
        grid.addLayout(col, 0, 1)
        self.char_btn = QPushButton()          # labelled by update_title()
        self.char_btn.setObjectName("small")
        self.follow_tip(self.char_btn, self.act_char)
        self.char_btn.clicked.connect(self.choose_character)
        grid.addWidget(self.char_btn, 0, 2)
        screen_icon = QLabel()
        screen_icon.setPixmap(theme.pixmap("monitor", theme.MUTED, 20))
        screen_icon.setAlignment(Qt.AlignCenter)
        grid.addWidget(screen_icon, 1, 0)
        self.screen_label = QLabel()
        grid.addWidget(self.screen_label, 1, 1)
        self.screen_btn = QPushButton()
        self.t(self.screen_btn.setText, "insp.resize")
        self.screen_btn.setObjectName("small")
        self.follow_tip(self.screen_btn, self.act_screen)
        self.screen_btn.clicked.connect(self.change_screen)
        grid.addWidget(self.screen_btn, 1, 2)
        self.icons_label = QLabel()
        self.icons_label.setObjectName("warn")
        self.icons_label.setWordWrap(True)
        grid.addWidget(self.icons_label, 2, 0, 1, 2)
        self.icons_btn = QPushButton()
        self.t(self.icons_btn.setText, "insp.download")
        self.icons_btn.setObjectName("small")
        self.follow_tip(self.icons_btn, self.act_get_icons)
        self.icons_btn.clicked.connect(self.fetch_icons)
        grid.addWidget(self.icons_btn, 2, 2)
        grid.setColumnStretch(1, 1)
        lay.addWidget(card)

        lay.addSpacing(6)
        lay.addWidget(section("side.selection"))
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
            self.t(box.setToolTip, "insp.pos.tip")
            box.valueChanged.connect(self.spin_changed)
            row.addWidget(box, 1)
        col.addLayout(row)
        row = QHBoxLayout()
        self.vis_box = QCheckBox()
        self.t(self.vis_box.setText, "insp.visible")
        self.follow_tip(self.vis_box, self.act_toggle)
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
        row.addWidget(section("side.panels"))
        row.addStretch(1)
        self.panel_count = muted_label()
        row.addWidget(self.panel_count)
        lay.addLayout(row)
        self.panel_search = search_box("side.filter", self.filter_panels)
        lay.addWidget(self.panel_search)
        self.panel_list = QListWidget()
        self.panel_list.setObjectName("panels")
        self.panel_list.setItemDelegate(PanelDelegate(self))
        self.panel_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.panel_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.t(self.panel_list.setToolTip, "side.check.tip")
        self.panel_list.itemSelectionChanged.connect(self.list_selection_changed)
        self.panel_list.itemChanged.connect(self.list_item_changed)
        lay.addWidget(self.panel_list, 1)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setChildrenCollapsible(False)
        for i, (widget, minimum) in enumerate(((left, 250), (centre, 360), (right, 280))):
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
        self.update_btn = QPushButton()
        self.update_btn.setObjectName("update")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setStyleSheet(
            f"QPushButton#update {{ background: {theme.ACCENT}; color: {theme.ACCENT_TEXT};"
            f" border: none; border-radius: 9px; padding: 2px 12px; font-weight: bold; }}"
            f"QPushButton#update:hover {{ background: {theme.ACCENT_HOVER}; }}")
        self.update_btn.clicked.connect(self.install_update)
        self.update_btn.hide()
        self.live(self.label_update_btn)
        bar.addPermanentWidget(self.update_btn)
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
            self.act_update_auto.setChecked(bool(state.get("updates", True)))
        except (AttributeError, TypeError, ValueError):
            pass                      # a damaged config only loses the window layout

    def save_ui_state(self):
        try:
            core.save_config(gui={
                "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
                "splitter": self.splitter.sizes(),
                "snap": self.act_snap.isChecked(), "hidden": self.act_hidden.isChecked(),
                "icons": self.act_icons.isChecked(), "grid": self.grid,
                "tips": self.act_tips.isChecked(),
                "updates": self.act_update_auto.isChecked()})
        except OSError:
            pass

    # ------------------------------------------------------------ updates

    def label_update_btn(self):
        self.update_btn.setText(tr("update.button", version=self.new_version or ""))
        self.update_btn.setToolTip(tr("update.button.tip"))

    def check_updates(self, manual):
        if not self.update_watch.check(manual) and manual:
            self.statusBar().showMessage(tr("update.busy"), 4000)
        elif manual:
            self.statusBar().showMessage(tr("update.checking"))

    def update_checked(self, version, manual):
        self.new_version = version
        self.label_update_btn()
        self.update_btn.setVisible(bool(version))
        if not manual:
            return
        self.statusBar().clearMessage()
        if version:
            self.install_update()
        else:
            notify(self, tr("update.latest", version=updater.local_version()))

    def update_check_failed(self, problem, manual):
        if manual:                  # a silent check at start stays silent
            self.statusBar().clearMessage()
            warn(self, problem)

    def install_update(self):
        if not self.new_version:
            return
        if ask(self, tr("update.ask", new=self.new_version,
                        old=updater.local_version())) != "yes":
            return
        if self.update_watch.install():
            self.update_btn.setEnabled(False)
            self.statusBar().showMessage(tr("update.installing", version=self.new_version))
        else:
            self.statusBar().showMessage(tr("update.busy"), 4000)

    def update_installed(self, version):
        self.statusBar().clearMessage()
        self.new_version = None
        self.update_btn.setEnabled(True)
        self.update_btn.hide()
        if ask(self, tr("update.done", version=version)) == "yes":
            self.restart_on_close = True
            if not self.close():        # unsaved changes kept the window open
                self.restart_on_close = False

    def update_install_failed(self, problem):
        self.statusBar().clearMessage()
        self.update_btn.setEnabled(True)
        warn(self, tr("update.failed", problem=problem, url=updater.PAGE_URL))

    def restart(self):
        """Start the program again, on the entry that is open now."""
        args = [sys.argv[0]] if sys.argv and sys.argv[0] else []
        if args and self.preset and self.preset.name:
            args += ["edit", self.preset.name]
        QProcess.startDetached(sys.executable, args)

    # ------------------------------------------------------------ language

    def set_language(self, choice):
        """Switch the interface language now and remember the choice."""
        apply_language(choice)
        try:
            core.save_config(language=choice)
        except OSError:
            pass
        self.retranslate()

    def retranslate(self):
        """Put the current language on everything that is already on screen."""
        for fn in self.live_texts:
            fn()
        self.panel_list.blockSignals(True)
        for r in range(self.panel_list.count()):
            row = self.panel_list.item(r)
            el = row.data(ROLE_EL)
            row.setText(el.label())
            if not el.positioned:
                row.setToolTip(tr("panel.nopos.tip"))
        self.panel_list.blockSignals(False)
        self.filter_panels()
        self.statusBar().clearMessage()
        self.tips.show_tip()
        self.refresh_sources()
        self.set_game_running(self.game_is_running)
        if self.preset:
            self.load_icons()           # panel tooltips
        self.update_inspector()
        self.update_title()
        self.view.viewport().update()

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
            sub = text or tr("card.nochar")
            it = QListWidgetItem()
            it.setData(ROLE_KIND, ("lib", name))
            it.setData(ROLE_CARD, {
                "kind": ("lib", name), "title": name, "sub": sub, "note": note,
                "thumb": thumb or letter_pixmap(name[:1].upper(), 38, 38, 7)})
            it.setToolTip(f"{name}\n{sub}"
                          + ("\n" + tr("card.screen.tip", size=note) if note else ""))
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
        entries = [(tr("slot.n", n=i + 1), str(i + 1), t)
                   for i, t in enumerate(core.SLOT_TAGS)]
        entries.append((tr("slot.default"), tr("slot.default.letter"), core.REVERT_TAG))
        for text, letter, tag in entries:
            els = slots.get(tag, [])
            it = QListWidgetItem()
            if core.slot_is_empty(els):
                sub = tr("slot.empty")
                it.setFlags(Qt.NoItemFlags)
            else:
                count = sum(1 for e in els if e.index is not None)
                sub = (f"{fmt_screen(core.estimate_screen(els))}  ·  "
                       f"{trn('count.panels', count)}")
                it.setData(ROLE_KIND, ("slot", tag))
                it.setToolTip(tr("slot.open.tip"))
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
            warn(self, str(e))
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
        if self.dirty and ask(self, tr("msg.revert")) != "yes":
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
        menu.addAction(tr("ctx.open"), lambda *_: self.request_open(("lib", name)))
        menu.addSeparator()
        menu.addActions([self.act_rename, self.act_duplicate])
        write = menu.addMenu(tr("menu.write"))
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
        menu.addAction(tr("ctx.open"), lambda *_: self.request_open(kind))
        save = menu.addAction(tr("ctx.save_lib"),
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
        name, ok = ask_text(self, title, label, text)
        name = name.strip()
        if not ok or not name:
            return None
        try:
            return core.check_name(name)
        except core.BdoUiError as e:
            warn(self, str(e))
            return None

    def rename_preset(self):
        old = self.current_lib_name()
        if not old:
            return
        new = self.ask_name(tr("dlg.rename.title"), tr("dlg.rename.label"), old)
        if not new or new == old:
            return
        try:
            core.lib_rename(old, new)
        except (core.BdoUiError, OSError) as e:
            warn(self, str(e))
            return
        if self.preset and self.preset.name == old:
            self.preset.name = new
        self.after_library_change(tr("status.renamed", old=old, new=new), select=new)

    def duplicate_preset(self):
        old = self.current_lib_name()
        if not old:
            return
        new = self.ask_name(tr("dlg.duplicate.title"), tr("dlg.duplicate.label", name=old),
                            tr("dlg.duplicate.default", name=old))
        if not new:
            return
        try:
            if core.lib_path(new).exists():
                raise core.BdoUiError(tr("err.exists", name=new))
            core.lib_save(core.lib_load(old), new)
            profile = core.profile_for_preset(old)
            if profile:
                core.save_profile(new, profile)
        except (core.BdoUiError, OSError, ValueError) as e:
            warn(self, str(e))
            return
        self.after_library_change(tr("status.copied", old=old, new=new), select=new)

    def delete_preset(self):
        name = self.current_lib_name()
        if not name:
            return
        if ask(self, tr("msg.delete", name=name)) != "yes":
            return
        try:
            core.lib_delete(name)
        except (core.BdoUiError, OSError) as e:
            warn(self, str(e))
            return
        if self.preset and self.preset.name == name:
            self.preset.name = None
            self.dirty = True
        self.after_library_change(tr("status.deleted", name=name))

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
        core.config.LIB_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(core.config.LIB_DIR)))

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
                row.setToolTip(tr("panel.nopos.tip"))
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
            notify(self, tr("msg.save_first"))
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
            warn(self, str(e))
            return
        _, missing = self.load_icons()
        self.refresh_sources()
        self.update_title()
        who = {"name": self.preset.name, "char": core.char_title(family, char)}
        self.statusBar().showMessage(
            trn("status.bound.missing", missing, **who) if missing
            else tr("status.bound", **who), 10000)

    def fetch_icons(self):
        profile, missing = self.load_icons() if self.preset else (None, 0)
        if not profile:
            notify(self, tr("msg.no_char"))
            return
        if not missing:
            self.statusBar().showMessage(tr("status.icons_all"), 5000)
            return
        done = [0]

        def progress(_):
            done[0] += 1
            self.statusBar().showMessage(tr("status.downloading", n=done[0]))
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            fetched, failed = core.fetch_profile_icons(profile, progress=progress)
        finally:
            QApplication.restoreOverrideCursor()
        self.load_icons()
        self.update_title()
        self.statusBar().showMessage(
            trn("status.icons_done", fetched)
            + (tr("status.icons_failed", n=len(failed)) if failed else ""), 8000)

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
        r = ask(self, tr("msg.unsaved"), "save", "discard", "cancel")
        if r == "save":
            return self.save()
        return r == "discard"

    def save(self):
        if not self.preset:
            return False
        if not self.preset.name:
            return self.save_as()
        return self.do_save(self.preset.name)

    def save_as(self):
        if not self.preset:
            return False
        name = self.ask_name(tr("dlg.save.title"), tr("dlg.save.label"),
                             self.preset.name or "")
        if not name:
            return False
        if core.lib_path(name).exists() and name != self.preset.name and ask(
                self, tr("msg.overwrite", name=name)) != "yes":
            return False
        return self.do_save(name)

    def do_save(self, name):
        self.sync_model()
        old_name = self.preset.name
        try:
            core.lib_save(self.preset, name)
            self.store_slot_contents(old_name, name)
        except (core.BdoUiError, OSError) as e:
            warn(self, str(e))
            return False
        self.load_icons()
        self.dirty = False
        self.history = [self.snapshot()]
        self.hist_pos = 0
        self.known_lib = core.lib_list()
        self.refresh_sources()
        self.update_title()
        self.statusBar().showMessage(tr("status.saved", name=name), 4000)
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
        if ask(self, tr("msg.store_skills", name=name, when=when,
                        char=core.char_title(self.family, chars[0][1]))) == "yes":
            core.save_profile(name, core.capture_profile(self.family, chars[0][1]))

    def restore_slot_contents(self, name):
        """After writing a layout, offer to put the stored slot contents back.

        Returns how many slots were restored.
        """
        profile = core.profile_for_preset(name)
        if not profile:
            return 0
        try:
            _, _, _, changes = core.plan_skills(profile)
            if not changes:
                return 0
            shown = "\n".join("  " + c for c in changes[:12])
            if len(changes) > 12:
                shown += "\n  " + tr("msg.restore.more", n=len(changes) - 12)
            if ask(self, tr("msg.restore", char=profile["char"], name=name,
                            changes=shown)) != "yes":
                return 0
            core.apply_skills(profile)
            return len(changes)
        except (core.BdoUiError, OSError) as e:
            warn(self, str(e))
            return 0

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
                now = tr("slot.empty")
            else:
                count = sum(1 for e in els if e.index is not None)
                now = f"{fmt_screen(core.estimate_screen(els))}, {trn('count.panels', count)}"
            menu.addAction(tr("slot.now", n=i + 1, now=now),
                           lambda *_, i=i: self.write_slot(i, lib_name))

    def write_slot(self, slot, lib_name=None):
        """Write the open layout (or library entry `lib_name`) into a game slot."""
        preset = self.preset
        if lib_name and not (preset and preset.name == lib_name):
            try:
                preset = core.lib_load(lib_name)
            except (core.BdoUiError, OSError, ValueError) as e:
                warn(self, str(e))
                return
        if not preset:
            return
        if core.game_running():
            self.set_game_running(True)
            warn(self, tr("msg.running"))
            return
        question = [tr("msg.write", slot=slot + 1, family=self.family,
                       name=preset.name or tr("doc.unsaved_name"))]
        if preset is self.preset and self.dirty:
            question.append(tr("msg.write.dirty"))
        question.append(tr("msg.write.backup", path=core.config.BACKUP_DIR))
        if ask(self, "\n\n".join(question)) != "yes":
            return
        if preset is self.preset:
            self.sync_model()
        try:
            backup = core.write_slot(self.family, slot, [e.copy() for e in preset.els])
        except (core.BdoUiError, OSError) as e:
            warn(self, str(e))
            return
        restored = self.restore_slot_contents(preset.name) if preset.name else 0
        self.refresh_sources()
        report = [tr("status.written", slot=slot + 1)]
        if restored:
            report.append(trn("status.restored", restored))
        report += [tr("status.backup", path=backup), tr("status.ingame", slot=slot + 1)]
        self.statusBar().showMessage(" ".join(report), 15000)

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
            self.statusBar().showMessage(tr("status.align_need"), 4000)
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
            title = tr("insp.none")
            sub = tr("insp.none.hint") if self.preset else tr("insp.nolayout")
        elif len(rows) == 1:
            el = rows[0].data(ROLE_EL)
            title = el.label()
            if items:
                sub = tr("insp.size", index=el.index, w=items[0].size[0], h=items[0].size[1])
                if items[0].skill:
                    sub += f"\n{items[0].skill}"
            else:
                sub = tr("insp.nopos", index=el.index)
        else:
            title = trn("insp.multi", len(rows))
            sub = tr("insp.multi.hint")
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
            self.panel_count.setText(
                trn("insp.visible_count", sum(e.shown for e in els), total=len(els)))
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
        sub = menu.addMenu(tr("menu.align"))
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
        start = str(core.config.BDO_DIR / "ScreenShot")
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.bg.title"), start,
            f"{tr('dlg.bg.filter')} (*.jpg *.jpeg *.png *.bmp)")
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

    def show_about(self):
        AboutDialog(self).exec()

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
        self.statusBar().showMessage(tr("status.game_folder", path=core.config.BDO_DIR), 8000)

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
            self.game_pill.set(tr("game.running"), theme.WARN)
            self.write_btn.setText(tr("write.running"))
            self.write_btn.setIcon(theme.icon("lock", theme.MUTED, disabled=theme.MUTED))
            self.write_btn.setToolTip(tr("write.running.tip"))
        else:
            self.game_pill.set(tr("game.closed"), theme.OK)
            self.write_btn.setText(tr("menu.write"))
            self.write_btn.setIcon(theme.icon("write", theme.ACCENT_TEXT, disabled=theme.MUTED))
            self.write_btn.setToolTip(tr("write.tip"))
        self.lock_icon.setVisible(self.game_is_running)
        self.lock_text.setVisible(self.game_is_running)
        self.update_actions()
        self.fit_toolbar(measure=True)

    def fit_toolbar(self, measure=False):
        """Drop the text of the Save button when the toolbar would not fit the window."""
        button = self.toolbar.widgetForAction(self.act_save)
        if measure:
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.toolbar_width = self.toolbar.sizeHint().width()
        style = (Qt.ToolButtonIconOnly if self.toolbar_width > self.width()
                 else Qt.ToolButtonTextBesideIcon)
        if button.toolButtonStyle() != style:
            button.setToolButtonStyle(style)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_toolbar()

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
        name = (preset.name or tr("doc.untitled")) if preset else tr("doc.none")
        self.setWindowTitle(f"{name}[*] — bdo-ui")
        self.setWindowModified(bool(preset and self.dirty))
        self.doc_title.setText(name)
        self.doc_badge.setVisible(bool(preset and self.dirty))
        source = ""
        if preset and not preset.name:
            tag = preset.meta.get("from")
            if tag in core.SLOT_TAGS:
                source = tr("doc.from_slot", n=core.SLOT_TAGS.index(tag) + 1)
            elif tag == core.REVERT_TAG:
                source = tr("doc.from_default")
            else:
                source = tr("doc.not_saved")
        self.doc_source.setText(source)

        parts, portrait = profile_parts(self.profile) if preset else ([], None)
        thumb = portrait_pixmap(portrait, 40, 40, 7, 0.28) if portrait else None
        self.char_thumb.setPixmap(thumb or theme.pixmap("user", theme.MUTED, 40))
        if not preset:
            head, sub = tr("doc.none"), ""
        elif self.profile:
            head = parts[0]
            sub = " · ".join(parts[1:]) or tr(
                "insp.char_id", id=str(self.profile.get("char", ""))[-8:])
        else:
            head, sub = tr("insp.nochar"), tr("insp.noskills")
        self.char_name.setText(head)
        self.char_sub.setText(sub)
        self.char_thumb.setToolTip(
            tr("char.id", id=self.profile.get("char", "")) if preset and self.profile else "")
        self.char_btn.setText(tr("insp.change") if self.profile else tr("insp.choose"))
        self.char_btn.setEnabled(preset is not None)
        self.screen_label.setText(
            f"{preset.screen[0]} × {preset.screen[1]}" if preset else "")
        self.screen_label.setToolTip(tr("insp.screen.tip"))
        self.screen_btn.setEnabled(preset is not None)
        missing = self.missing_icons if preset else 0
        self.icons_label.setVisible(missing > 0)
        self.icons_btn.setVisible(missing > 0)
        self.icons_label.setText(trn("insp.icons_missing", missing))
        self.zoom_changed()
        self.sources.viewport().update()
        self.slots.viewport().update()
        self.update_actions()

    def closeEvent(self, event):
        if self.confirm_discard():
            self.timer.stop()
            self.save_ui_state()
            event.accept()
            if self.restart_on_close:
                self.restart()
        else:
            event.ignore()
