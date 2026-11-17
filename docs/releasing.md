# Releasing bdo-ui

For the maintainer.

Copies in the wild look at the `VERSION` file on the `main` branch, so a
pushed version bump is offered to everyone at once.

1. Raise the number in `VERSION`, commit, push to `main`.
2. `python3 tools/build_windows.py` builds
   `dist/bdo-ui-<version>-windows-x64.zip` from the committed state, on any
   system. Python and Qt versions and their hashes are pinned at the top of
   the script.
3. `gh release create v<version> dist/bdo-ui-<version>-windows-x64.zip --target main`

The self-update replaces the program files only. A change of the bundled
Python or Qt reaches Windows users through a new package.
