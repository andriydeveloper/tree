# Christmas tree

A small animated Christmas tree that sits in the corner of the screen, always on top, with a
transparent background. Every start grows a different spruce.

- Procedural spruce: trunk with scaly bark, roots and bends; branches in whorls, twigs and needles
  with their own density; cones, snow on branches; a random topper.
- Random gifts under the tree, partly hidden by the lower branches.
- Wind gusts from the left or right, sometimes slanting down. The tree bends, every branch swings on
  its own (mass, sail, strength), branches shelter each other, ornaments and garlands move with
  their branches.
- Garlands hang on branches and sag between them, with several light programs.
- Falling snow, a semi-transparent WiMo logo flying over the whole scene.
- The previous fixed cartoon tree is still there: Settings > General > Tree style = classic.
- Topper, snow, gifts, needles, garlands and ornaments can be switched off in Settings > General; the tree stays the same.
- A new tree is grown in the background: the old one keeps moving and a loader shows the progress in percent.

## Start

**Windows:** double click `start.bat`.
**Linux:** run `./start.sh` (or double click it in a file manager that runs scripts).

The first start takes a few minutes. The launcher:

1. checks this repository for a newer version and updates the app (only when online);
2. creates its own Python environment in `.venv` and installs the missing libraries
   (`pycairo`, `PySide6-Essentials`);
3. starts the tree without a console window. A tree that is already running is replaced;
4. adds a launcher, so the next starts need no terminal:
   - Linux: "Christmas tree" in the app menu (can be pinned to the dock) and, once, a desktop icon;
   - Windows: once, shortcuts on the desktop and in the Start menu.

   An icon you delete is not created again. When the folder moves, the menu entry follows it.

Python 3.9 or newer is needed. On Windows `start.bat` tries to install it with `winget` when it is
missing; otherwise get it from https://www.python.org/downloads/.

To close the tree: right click > Close, or `start.bat --stop` / `./start.sh stop`.

## Controls

| Action | Result |
| --- | --- |
| Left click | next garland program |
| Left button + move | move the tree |
| Middle click | new random tree |
| Right click | menu: new random tree, show logo, settings, close |

## Settings

Right click > Settings. All values are applied at once and saved to `settings.json` next to the
app (only the values that differ from the defaults). An update never touches this file.
`Tree seed` keeps a tree you like: the seed of the current tree is written to `tree.log`.

## Updates

The launcher compares the local `VERSION` with `VERSION` on the `main` branch of
https://github.com/andriydeveloper/tree. To publish a new version, raise the number in `VERSION`
and push to `main`. A git clone is updated with `git pull --ff-only` instead.

## Files

| File | Purpose |
| --- | --- |
| `start.bat`, `start.sh` | start by double click / from the terminal |
| `launcher.py` | update, environment, libraries, start (standard library only) |
| `tree.py` | the tree itself |
| `requirements.txt` | libraries the tree needs |
| `VERSION` | version used by the update check |
| `wimo-logo-blau.svg` | the logo shape |
| `icon.svg`, `icon.ico` | launcher icon (Linux, Windows) |

## Author

Andrii Havrysh
