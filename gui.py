"""PySide6 editor for BDO UI presets: drag panels on a canvas, keep a library."""

import sys

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QImage,
                           QKeySequence, QPainter, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDockWidget, QFileDialog,
                               QFormLayout, QGraphicsItem,
                               QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout,
                               QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

import core
import panels

COLORS = {
    "quick": QColor(90, 170, 255),
    "cooldown": QColor(255, 170, 70),
    "chat": QColor(120, 210, 140),
    "other": QColor(190, 150, 240),
}
SNAP_DIST = 6
ROLE_EL = Qt.UserRole
ROLE_KIND = Qt.UserRole + 1


class PanelItem(QGraphicsRectItem):
    def __init__(self, el, size, win):
        super().__init__(0, 0, size[0], size[1])
        self.el, self.size, self.win = el, size, win
        self.setPos(int(el.get("PosX")), int(el.get("PosY")))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.icon = None       # QPixmap of the skill sitting in this slot, if known
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
        if not shown:
            # Panels hidden in game stay on the canvas as faint ghosts.
            painter.setOpacity(0.6 if self.isSelected() else 0.28)
        fill = QColor(self.color)
        fill.setAlpha(70 if shown else 18)
        edge = QColor(self.color if shown else QColor(130, 130, 130))
        pen = QPen(edge, 0, Qt.SolidLine if shown else Qt.DashLine)
        if self.isSelected():
            pen = QPen(QColor(255, 255, 255), 0)
            fill.setAlpha(130 if shown else 50)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRect(self.rect())

        w, h = self.size
        small = min(w, h) < 70
        text = self.el.short_label() if small else self.el.label()
        if self.icon is not None and self.win.icons_box.isChecked():
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
    def __init__(self, scene, win):
        super().__init__(scene)
        self.win = win
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QColor(24, 24, 28))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.win.commit()

    def keyPressEvent(self, event):
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        delta = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0),
                 Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}.get(event.key())
        if delta and self.scene().selectedItems():
            self.win.nudge(*delta)
            return
        super().keyPressEvent(event)

    def fit(self):
        self.fitInView(self.sceneRect().adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio)


class CharacterDialog(QDialog):
    """Pick the character a library entry belongs to, as a wall of portrait cards."""

    CARD = QSize(156, 201)      # portrait, same 624x804 proportions the game saves

    def __init__(self, parent, family, current):
        super().__init__(parent)
        self.family, self.current = family, current
        self.setWindowTitle("Character of this layout")
        self.resize(1010, 760)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            f"Family {family}. The skills in the chosen character's quick and cooldown "
            "slots are stored with the layout."))
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(self.CARD)
        self.list.setGridSize(QSize(self.CARD.width() + 34, self.CARD.height() + 92))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.setSpacing(6)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        lay.addWidget(self.list)

        row = QHBoxLayout()
        rename = QPushButton("Name…")
        rename.setToolTip("The game keeps character names on its servers, so type it once here")
        rename.clicked.connect(self.rename)
        row.addWidget(rename)
        self.all_box = QCheckBox("Show characters that are no longer in the game")
        self.all_box.toggled.connect(self.fill)
        row.addWidget(self.all_box)
        row.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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

    def portrait(self, card):
        w, h = self.CARD.width(), self.CARD.height()
        pix = QPixmap(w, h)
        pix.fill(QColor(44, 44, 54))
        painter = QPainter(pix)
        image = QImage(str(card["portrait"])) if card["portrait"] else QImage()
        if not image.isNull():
            # Saved portraits carry an empty alpha channel; drop it.
            image = image.convertToFormat(QImage.Format_RGB32).scaled(
                w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawImage(0, 0, image, (image.width() - w) // 2, (image.height() - h) // 2)
        else:
            font = painter.font()
            font.setPixelSize(64)
            painter.setFont(font)
            painter.setPen(QColor(120, 120, 135))
            painter.drawText(pix.rect(), Qt.AlignCenter, (card["class"] or "?")[0])
        if card["char"] == self.current:
            painter.setPen(QPen(QColor(255, 200, 80), 6))
            painter.drawRect(3, 3, w - 6, h - 6)
        painter.end()
        return pix

    def fill(self):
        import time
        keep = self.chosen() or self.current
        self.list.clear()
        for card in core.char_cards(self.family):
            if card["order"] is None and not self.all_box.isChecked():
                continue
            kind = " · ".join(p for p in (card["class"], card["spec"]) if p) or "class unknown"
            lines = [card["name"] or "(no name)", kind,
                     time.strftime("%d.%m.%Y %H:%M", time.localtime(card["mtime"]))]
            if card["entries"]:
                lines.append("▣ " + ", ".join(card["entries"]))
            item = QListWidgetItem(QIcon(self.portrait(card)), "\n".join(lines))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            item.setData(ROLE_EL, card["char"])
            item.setToolTip(f"{card['char']}\n{card['cooldown']} cooldown slots, "
                            f"{card['quick']} quick-slot skills")
            self.list.addItem(item)
            if card["char"] == keep:
                self.list.setCurrentItem(item)

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
    def __init__(self, parent, screen):
        super().__init__(parent)
        self.setWindowTitle("Screen size (UI units)")
        form = QFormLayout(self)
        self.w, self.h = QSpinBox(), QSpinBox()
        for box, val in ((self.w, screen[0]), (self.h, screen[1])):
            box.setRange(640, 8000)
            box.setValue(val)
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        btn = QPushButton("Take from running game window")
        btn.clicked.connect(self.from_game)
        form.addRow(btn)
        form.addRow(QLabel("Panels keep their relative position\n"
                           "(centre / screen), like the game does."))
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)

    def from_game(self):
        scr = core.game_window_screen()
        if not scr:
            QMessageBox.information(self, "bdo-ui", "Game window not found.")
            return
        self.w.setValue(scr[0])
        self.h.setValue(scr[1])


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.loading = False
        self.preset = None
        self.items = []
        self.dirty = False
        self.history, self.hist_pos = [], -1
        self.bg_item = None
        self.bg_path = None
        self.grid = 0
        self.syncing_selection = False

        fams = core.families()
        if not fams:
            raise core.BdoUiError(f"no families found under {core.BDO_DIR}")
        self.family = fams[0]

        self.scene = QGraphicsScene(self)
        self.frame = self.scene.addRect(QRectF(), QPen(QColor(110, 110, 120), 0),
                                        QBrush(QColor(38, 38, 46)))
        self.frame.setZValue(-10)
        self.view = View(self.scene, self)
        self.setCentralWidget(self.view)
        self.scene.selectionChanged.connect(self.selection_changed)

        self.build_toolbar(fams)
        self.build_docks()
        self.resize(1500, 950)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(3000)
        self.refresh_sources()
        self.refresh_status()
        self.update_title()

    # ------------------------------------------------------------ UI build

    def build_toolbar(self, fams):
        tb = self.addToolBar("main")
        tb.setMovable(False)

        tb.addWidget(QLabel(" Family "))
        self.family_box = QComboBox()
        self.family_box.addItems(fams)
        self.family_box.currentTextChanged.connect(self.family_changed)
        tb.addWidget(self.family_box)
        tb.addSeparator()

        def act(text, slot, shortcut=None, tip=None):
            a = QAction(text, self)
            a.triggered.connect(lambda _=False: slot())
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setToolTip(tip)
            tb.addAction(a)
            return a

        act("Save", self.save, "Ctrl+S", "Save to the library")
        act("Save as…", self.save_as, "Ctrl+Shift+S")

        self.write_btn = QToolButton()
        self.write_btn.setText("Write to game slot")
        self.write_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.write_btn)
        for i in range(3):
            menu.addAction(f"Slot {i + 1}", lambda i=i: self.write_slot(i))
        self.write_btn.setMenu(menu)
        tb.addWidget(self.write_btn)
        tb.addSeparator()

        self.undo_act = act("Undo", self.undo, "Ctrl+Z")
        self.redo_act = act("Redo", self.redo, "Ctrl+Shift+Z")
        tb.addSeparator()

        align = QToolButton()
        align.setText("Align")
        align.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(align)
        for text, mode in (("Left edges", "left"), ("Right edges", "right"),
                           ("Top edges", "top"), ("Bottom edges", "bottom"),
                           ("Pack into a row", "row"), ("Pack into a column", "col")):
            menu.addAction(text, lambda mode=mode: self.align(mode))
        align.setMenu(menu)
        tb.addWidget(align)

        act("Show/Hide", self.toggle_shown, "H", "Toggle IsShow of selected panels")
        tb.addSeparator()

        self.snap_box = QCheckBox("Snap to panels")
        self.snap_box.setChecked(True)
        tb.addWidget(self.snap_box)
        tb.addWidget(QLabel("  Grid "))
        self.grid_box = QSpinBox()
        self.grid_box.setRange(0, 100)
        self.grid_box.setSpecialValueText("off")
        self.grid_box.valueChanged.connect(lambda v: setattr(self, "grid", v))
        tb.addWidget(self.grid_box)
        self.hidden_box = QCheckBox("Hidden panels")
        self.hidden_box.setChecked(True)
        self.hidden_box.toggled.connect(self.apply_hidden_filter)
        tb.addWidget(self.hidden_box)
        self.icons_box = QCheckBox("Skill icons")
        self.icons_box.setChecked(True)
        self.icons_box.setToolTip("Draw skill icons in the slots (needs a skill "
                                  "profile named like the preset)")
        self.icons_box.toggled.connect(lambda _: self.scene.update())
        tb.addWidget(self.icons_box)
        act("Get icons", self.fetch_icons,
            tip="Download missing skill icons for this preset's profile from bdocodex.com")
        self.char_act = act("Character…", self.choose_character,
                            tip="Bind this library entry to a character: its quick-slot and "
                                "cooldown-slot skills are stored with the layout")
        tb.addSeparator()

        act("Screen…", self.change_screen, tip="Screen size the layout is made for")
        act("Background…", self.pick_background, tip="Show a game screenshot under the layout")
        self.bg_box = QCheckBox("show")
        self.bg_box.setChecked(True)
        self.bg_box.toggled.connect(lambda on: self.bg_item and self.bg_item.setVisible(on))
        tb.addWidget(self.bg_box)
        act("Fit", self.view.fit, "F")
        tb.addSeparator()
        act("Game folder…", self.change_game_folder,
            tip="Choose the game's 'Black Desert' documents folder")

    def build_docks(self):
        left = QWidget()
        lay = QVBoxLayout(left)
        self.sources = QListWidget()
        self.sources.itemActivated.connect(self.source_activated)
        self.sources.itemClicked.connect(self.source_activated)
        lay.addWidget(self.sources)
        row = QHBoxLayout()
        for text, slot in (("Rename", self.rename_preset), ("Delete", self.delete_preset)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        dock = QDockWidget("Presets", self)
        dock.setWidget(left)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        right = QWidget()
        lay = QVBoxLayout(right)
        self.panel_list = QListWidget()
        self.panel_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.panel_list.itemSelectionChanged.connect(self.list_selection_changed)
        self.panel_list.itemChanged.connect(self.list_item_changed)
        lay.addWidget(self.panel_list)
        form = QFormLayout()
        self.x_box, self.y_box = QSpinBox(), QSpinBox()
        for box in (self.x_box, self.y_box):
            box.setRange(-4000, 12000)
            box.setKeyboardTracking(False)
            box.valueChanged.connect(self.spin_changed)
        form.addRow("X", self.x_box)
        form.addRow("Y", self.y_box)
        lay.addLayout(form)
        dock = QDockWidget("Panels (checkbox = visible in game)", self)
        dock.setWidget(right)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    # ------------------------------------------------------------ sources

    def refresh_sources(self):
        self.sources.clear()

        def header(text):
            it = QListWidgetItem(text)
            it.setFlags(Qt.NoItemFlags)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            self.sources.addItem(it)

        header("Library")
        for name in core.lib_list():
            it = QListWidgetItem("  " + name)
            it.setData(ROLE_KIND, ("lib", name))
            self.sources.addItem(it)
            if self.preset and self.preset.name == name:
                self.sources.setCurrentItem(it)
        header(f"Game slots · family {self.family}")
        try:
            slots = core.read_slots(self.family)
        except (core.BdoUiError, OSError) as e:
            slots = {}
            self.statusBar().showMessage(str(e))
        entries = [(f"Slot {i + 1}", t) for i, t in enumerate(core.SLOT_TAGS)]
        entries.append(("Game default (revert)", core.REVERT_TAG))
        for text, tag in entries:
            els = slots.get(tag, [])
            if core.slot_is_empty(els):
                it = QListWidgetItem(f"  {text} — empty")
                it.setFlags(Qt.NoItemFlags)
            else:
                scr = core.estimate_screen(els)
                it = QListWidgetItem(f"  {text}  ({scr[0]}x{scr[1]})")
                it.setData(ROLE_KIND, ("slot", tag))
            self.sources.addItem(it)

    def source_activated(self, item):
        kind = item.data(ROLE_KIND)
        if not kind or not self.confirm_discard():
            return
        try:
            if kind[0] == "lib":
                preset = core.lib_load(kind[1])
            else:
                preset = core.preset_from_slot(self.family, kind[1])
        except (core.BdoUiError, OSError, ValueError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        self.open_preset(preset)

    def family_changed(self, fam):
        self.family = fam
        self.refresh_sources()

    def rename_preset(self):
        kind = self.current_lib_name()
        if not kind:
            return
        new, ok = QInputDialog.getText(self, "Rename preset", "New name:", text=kind)
        if not ok or new == kind:
            return
        try:
            core.lib_rename(kind, new.strip())
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        if self.preset and self.preset.name == kind:
            self.preset.name = new.strip()
        self.refresh_sources()
        self.update_title()

    def delete_preset(self):
        name = self.current_lib_name()
        if not name:
            return
        if QMessageBox.question(self, "bdo-ui", f"Delete preset “{name}” from the library?") \
                != QMessageBox.Yes:
            return
        core.lib_delete(name)
        if self.preset and self.preset.name == name:
            self.preset.name = None
            self.dirty = True
        self.refresh_sources()
        self.update_title()

    def current_lib_name(self):
        it = self.sources.currentItem()
        kind = it.data(ROLE_KIND) if it else None
        return kind[1] if kind and kind[0] == "lib" else None

    # ------------------------------------------------------------ document

    def open_preset(self, preset):
        self.loading = True
        for item in self.items:
            self.scene.removeItem(item)
        self.items = []
        self.preset = preset
        w, h = preset.screen
        self.frame.setRect(0, 0, w, h)
        self.scene.setSceneRect(-200, -200, w + 400, h + 400)

        self.panel_list.blockSignals(True)
        self.panel_list.clear()
        for el in preset.els:
            if el.index is None:
                continue
            row = QListWidgetItem(f"{el.label()}   #{el.index}")
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
            row.setCheckState(Qt.Checked if el.shown else Qt.Unchecked)
            row.setData(ROLE_EL, el)
            if not el.positioned:
                row.setForeground(QColor(150, 150, 150))
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
        self.load_icons()
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
            tip = f"{item.el.label()}  (#{item.el.index})  {item.size[0]}x{item.size[1]}"
            if skill:
                tip += f"\n{core.skill_name(skill, profile)}"
                missing += item.icon is None
            item.setToolTip(tip)
        self.scene.update()
        return profile, missing

    def choose_character(self):
        if not (self.preset and self.preset.name):
            QMessageBox.information(self, "bdo-ui",
                                    "Save the layout to the library first, then bind it.")
            return
        old = core.profile_for_preset(self.preset.name)
        family = (old or {}).get("family") or self.family
        dlg = CharacterDialog(self, family, (old or {}).get("char"))
        if dlg.exec() != QDialog.Accepted or not dlg.chosen():
            return
        char = dlg.chosen()
        try:
            core.save_profile(self.preset.name, core.capture_profile(family, char, keep=old))
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        _, missing = self.load_icons()
        self.update_title()
        self.statusBar().showMessage(
            f"“{self.preset.name}” is bound to {core.char_title(family, char)}"
            + (f"; {missing} icons missing — press “Get icons”" if missing else ""), 10000)

    def fetch_icons(self):
        profile, missing = self.load_icons() if self.preset else (None, 0)
        if not profile:
            QMessageBox.information(
                self, "bdo-ui",
                "This preset has no skill profile.\n\nIcons come from a profile with the "
                f"same name as the preset in\n{core.SKILLS_DIR}")
            return
        if not missing:
            self.statusBar().showMessage("All skill icons are already downloaded", 5000)
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            fetched, failed = core.fetch_profile_icons(
                profile, progress=lambda _: QApplication.processEvents())
        finally:
            QApplication.restoreOverrideCursor()
        self.load_icons()
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
            self.frame.setRect(0, 0, *screen)
            self.scene.setSceneRect(-200, -200, screen[0] + 400, screen[1] + 400)
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
        self.selection_changed()

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
        name, ok = QInputDialog.getText(self, "Save preset", "Name in the library:",
                                        text=self.preset.name or "")
        name = name.strip()
        if not ok or not name:
            return False
        try:
            exists = core.lib_path(name).exists()
        except core.BdoUiError as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return False
        if exists and name != self.preset.name and QMessageBox.question(
                self, "bdo-ui", f"Overwrite existing preset “{name}”?") != QMessageBox.Yes:
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
        import time
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(chars[0][0]))
        if QMessageBox.question(
                self, "bdo-ui",
                f"Store the skills sitting in the quick and cooldown slots with “{name}”?\n\n"
                f"They are read from the character played last ({chars[0][1]}, {when}).\n"
                "Choose No if this layout belongs to another character; it can be "
                "attached later with:  bdo-ui skills <name> --capture --char <id>"
                ) == QMessageBox.Yes:
            core.save_profile(name, core.capture_profile(self.family, chars[0][1]))

    def restore_slot_contents(self):
        """After writing a layout, offer to put the stored slot contents back."""
        profile = core.profile_for_preset(self.preset.name)
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
                    f"with “{self.preset.name}”:\n\n{shown}{more}\n\nRestore them too?"
                    ) != QMessageBox.Yes:
                return ""
            core.apply_skills(profile)
            return f" {len(changes)} slot contents restored."
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return ""

    def write_slot(self, slot):
        if not self.preset:
            return
        if core.game_running():
            QMessageBox.warning(
                self, "bdo-ui",
                "Black Desert is running.\n\nThe game rewrites its settings file while "
                "it runs, so the change would be lost. Close the game and try again.")
            return
        name = self.preset.name or "unsaved layout"
        if QMessageBox.question(
                self, "bdo-ui",
                f"Replace game slot {slot + 1} of family {self.family} with “{name}”?\n\n"
                "The current file is committed to the settings repo and copied to "
                f"{core.BACKUP_DIR} first.") != QMessageBox.Yes:
            return
        self.sync_model()
        try:
            backup = core.write_slot(self.family, slot, [e.copy() for e in self.preset.els])
        except (core.BdoUiError, OSError) as e:
            QMessageBox.warning(self, "bdo-ui", str(e))
            return
        extra = self.restore_slot_contents()
        self.refresh_sources()
        self.statusBar().showMessage(
            f"Slot {slot + 1} written.{extra} Backup: {backup}. "
            f"In game: Edit UI → load preset {slot + 1}.", 15000)

    # ------------------------------------------------------------ editing

    def adjust_position(self, item, value):
        x, y = round(value.x()), round(value.y())
        single = len(self.scene.selectedItems()) <= 1
        if self.grid and single:
            x, y = round(x / self.grid) * self.grid, round(y / self.grid) * self.grid
        elif self.snap_box.isChecked() and single:
            x, y = self.snap(item, x, y)
        w, h = self.preset.screen
        x = max(-item.size[0] + 10, min(w - 10, x))
        y = max(-item.size[1] + 10, min(h - 10, y))
        return QPointF(x, y)

    def snap(self, item, x, y):
        """Snap edges to the screen border and to nearby visible panels."""
        iw, ih = item.size
        best_x, best_y = (SNAP_DIST + 1, x), (SNAP_DIST + 1, y)
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
                    best_x = (abs(cand - x), cand)
        for edge in ys:
            for cand in (edge, edge - ih):
                if abs(cand - y) < best_y[0]:
                    best_y = (abs(cand - y), cand)
        return round(best_x[1]), round(best_y[1])

    def item_moved(self, item):
        if item.isSelected() and len(self.scene.selectedItems()) == 1:
            self.show_coords(item)

    def nudge(self, dx, dy):
        for item in self.scene.selectedItems():
            self.loading = True
            item.setPos(item.pos().x() + dx, item.pos().y() + dy)
            self.loading = False
        self.selection_changed()
        self.commit()

    def align(self, mode):
        sel = [i for i in self.scene.selectedItems() if isinstance(i, PanelItem)]
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
        self.commit()

    def toggle_shown(self):
        rows = self.panel_list.selectedItems()
        if not rows:
            return
        turn_on = not all(r.data(ROLE_EL).shown for r in rows)
        for r in rows:
            r.setCheckState(Qt.Checked if turn_on else Qt.Unchecked)

    def list_item_changed(self, row):
        el = row.data(ROLE_EL)
        el.set("IsShow", "true" if row.checkState() == Qt.Checked else "false")
        self.apply_hidden_filter()
        self.scene.update()
        self.commit()

    def apply_hidden_filter(self):
        show_hidden = self.hidden_box.isChecked()
        for item in self.items:
            item.setVisible(show_hidden or item.el.shown)

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
        self.frame.setRect(0, 0, *new)
        self.scene.setSceneRect(-200, -200, new[0] + 400, new[1] + 400)
        self.apply_background()
        self.commit()
        self.view.fit()

    # ------------------------------------------------------------ selection

    def selection_changed(self):
        if self.syncing_selection:
            return
        sel = [i for i in self.scene.selectedItems() if isinstance(i, PanelItem)]
        self.syncing_selection = True
        self.panel_list.clearSelection()
        for item in sel:
            item.row.setSelected(True)
        if sel:
            self.panel_list.scrollToItem(sel[0].row)
        self.syncing_selection = False
        if len(sel) == 1:
            self.show_coords(sel[0])
        for box in (self.x_box, self.y_box):
            box.setEnabled(len(sel) == 1)

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
        sel = self.scene.selectedItems()
        if len(sel) == 1:
            self.show_coords(sel[0])
        for box in (self.x_box, self.y_box):
            box.setEnabled(len(sel) == 1)

    def show_coords(self, item):
        for box, v in ((self.x_box, item.pos().x()), (self.y_box, item.pos().y())):
            box.blockSignals(True)
            box.setValue(int(v))
            box.blockSignals(False)

    def spin_changed(self):
        sel = self.scene.selectedItems()
        if len(sel) != 1:
            return
        self.loading = True
        sel[0].setPos(self.x_box.value(), self.y_box.value())
        self.loading = False
        self.commit()

    # ------------------------------------------------------------ misc

    def pick_background(self):
        start = str(core.BDO_DIR / "ScreenShot")
        path, _ = QFileDialog.getOpenFileName(
            self, "Game screenshot", start, "Images (*.jpg *.jpeg *.png *.bmp)")
        if path:
            self.bg_path = path
            self.bg_box.setChecked(True)
            self.apply_background()

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
        self.bg_item.setVisible(self.bg_box.isChecked())
        self.scene.addItem(self.bg_item)

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
        if names != getattr(self, "known_lib", None):
            if hasattr(self, "known_lib"):
                self.refresh_sources()
            self.known_lib = names
        running = core.game_running()
        self.write_btn.setEnabled(not running)
        self.write_btn.setToolTip(
            "Close Black Desert to write a slot" if running
            else "Put this layout into one of the three in-game preset slots")
        self.game_label_text = ("game is running — slots are read-only" if running
                                else "game is closed — slots can be written")
        self.update_title()

    def update_title(self):
        name = "no layout"
        if self.preset:
            name = self.preset.name or "unsaved layout"
            name += f"  [{self.preset.screen[0]}x{self.preset.screen[1]}]"
            profile = core.profile_for_preset(self.preset.name)
            name += (f"  ({core.char_title(profile['family'], profile['char'])})"
                     if profile else "  (no character)")
        mark = " *" if self.dirty else ""
        status = getattr(self, "game_label_text", "")
        self.setWindowTitle(f"bdo-ui — {name}{mark} — {status}")
        self.undo_act.setEnabled(self.hist_pos > 0)
        self.redo_act.setEnabled(self.hist_pos < len(self.history) - 1)

    def closeEvent(self, event):
        if self.confirm_discard():
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
