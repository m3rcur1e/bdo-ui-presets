# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Start of the editor: the application object, language, the first window."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .. import core
from ..i18n import tr
from . import theme
from .dialogs import pick_game_folder
from .language import apply_language, configured_language
from .widgets import notify
from .window import Main


def run(open_name=None):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("bdo-ui")
    app.setDesktopFileName("bdo-ui")
    theme.apply(app)
    apply_language(configured_language())
    if not core.docs_valid():
        notify(None, tr("msg.not_found", path=core.config.BDO_DIR))
        if not pick_game_folder():
            return 1
    win = Main()
    if open_name:
        win.open_preset(core.lib_load(open_name))
        win.refresh_sources()
    win.show()
    QTimer.singleShot(0, win.view.fit)
    return app.exec()
