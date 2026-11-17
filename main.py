#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Start bdo-ui from the program folder: python3 main.py [command ...].

The program itself is the bdo_ui package next to this file.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from bdo_ui.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
