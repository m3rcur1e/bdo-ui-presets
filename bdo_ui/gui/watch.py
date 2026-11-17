# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Background checks that must not block the window: is the game running, is there an update."""

import threading

from PySide6.QtCore import QObject, Signal

from .. import core, updater


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


class UpdateWatch(QObject):
    """Looks for a newer version, and installs it, off the GUI thread."""

    checked = Signal(object, bool)      # newer version or None, asked by the user
    failed = Signal(str, bool)          # problem, asked by the user
    installed = Signal(str)             # version the program folder is at now
    install_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False

    def start(self, work, *args):
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=work, args=args, daemon=True).start()
        return True

    def emit(self, signal, *values):
        self.busy = False
        try:
            signal.emit(*values)
        except RuntimeError:
            pass                      # the window is already gone

    def check(self, manual):
        return self.start(self.do_check, manual)

    def do_check(self, manual):
        try:
            self.emit(self.checked, updater.check(), manual)
        except Exception as e:        # no network must never break the editor
            self.emit(self.failed, str(e), manual)

    def install(self):
        return self.start(self.do_install)

    def do_install(self):
        try:
            self.emit(self.installed, updater.install())
        except Exception as e:
            self.emit(self.install_failed, str(e))
