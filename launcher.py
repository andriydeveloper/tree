#!/usr/bin/env python3
"""
Launcher of the Christmas tree. Uses only the standard library, so it runs on a fresh Python.

1. Online: checks GitHub for a newer version and updates the app files (settings stay).
2. Prepares its own Python environment (.venv) and installs missing libraries.
3. Starts the tree without a console window; a running tree is replaced.

  start.bat / start.sh               update, install, start
  start.bat --stop / start.sh stop   close the running tree
  --no-update                        skip the update check
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

__author__ = "Andrii Havrysh"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = "andriydeveloper/tree"
BRANCH = "main"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/VERSION"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
KEEP = {"settings.json", "tree.log", ".venv", ".git"}       # an update never replaces these
VENV = os.path.join(APP_DIR, ".venv")
WINDOWS = os.name == "nt"
MIN_PYTHON = (3, 9)
# module to import -> package that provides it (keep in sync with requirements.txt)
REQUIREMENTS = [("cairo", "pycairo>=1.20"),
                ("PySide6.QtWidgets, PySide6.QtSvg, PySide6.QtNetwork", "PySide6-Essentials>=6.5")]


def log(message):
    print(f"[tree] {message}", flush=True)


def version_tuple(text):
    return tuple(int(p) if p.isdigit() else 0 for p in text.strip().split("."))


def local_version():
    try:
        with open(os.path.join(APP_DIR, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "0"


def update():
    """True when files were replaced by a newer version from GitHub."""
    if os.path.isdir(os.path.join(APP_DIR, ".git")):         # a git checkout is updated by git
        if shutil.which("git"):
            result = subprocess.run(["git", "-C", APP_DIR, "pull", "--ff-only", "--quiet"],
                                    capture_output=True, text=True, timeout=60)
            log("git pull: " + ("done" if result.returncode == 0 else "skipped, " + result.stderr.strip()[-200:]))
        return False
    local = local_version()
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=4) as response:
            remote = response.read().decode().strip()
    except Exception as e:                                    # offline, GitHub down, no VERSION yet
        log(f"update check skipped ({e.__class__.__name__})")
        return False
    if version_tuple(remote) <= version_tuple(local):
        log(f"version {local} is up to date")
        return False

    log(f"updating {local} -> {remote}")
    try:
        with urllib.request.urlopen(ZIP_URL, timeout=60) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        names = archive.namelist()
        if any(n.startswith("/") or ".." in n.split("/") for n in names):
            raise ValueError("unsafe path in the archive")
        root = names[0].split("/")[0]
        with tempfile.TemporaryDirectory() as tmp:
            archive.extractall(tmp)
            source = os.path.join(tmp, root)
            for name in os.listdir(source):
                if name in KEEP:
                    continue
                src, dst = os.path.join(source, name), os.path.join(APP_DIR, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
    except Exception as e:
        log(f"update failed, the current version stays: {e}")
        return False
    log(f"updated to {remote}")
    return True


def venv_python(windowed=False):
    if WINDOWS:
        return os.path.join(VENV, "Scripts", "pythonw.exe" if windowed else "python.exe")
    return os.path.join(VENV, "bin", "python")


def missing(python):
    """Packages whose modules cannot be imported (an already present system pycairo counts)."""
    return [package for module, package in REQUIREMENTS
            if subprocess.call([python, "-c", f"import {module}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0]


def works(python):
    return not missing(python)


def has_pip(python):
    return subprocess.call([python, "-m", "pip", "--version"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def install_pip(python):
    """Some Linux systems create a venv without pip (no python3-venv package): bring pip in, no sudo."""
    log("installing pip into .venv")
    try:
        with urllib.request.urlopen("https://bootstrap.pypa.io/get-pip.py", timeout=60) as response:
            script = response.read()
    except Exception as e:
        log(f"could not download pip ({e.__class__.__name__})")
        return False
    with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=False) as f:
        f.write(script)
    try:
        return subprocess.call([python, f.name, "--quiet", "--disable-pip-version-check"]) == 0
    finally:
        os.unlink(f.name)


def share_system_packages():
    """A venv created after a failed first try may not see system packages (e.g. the system pycairo)."""
    config = os.path.join(VENV, "pyvenv.cfg")
    try:
        with open(config) as f:
            text = f.read()
        if "include-system-site-packages = false" in text:
            with open(config, "w") as f:
                f.write(text.replace("include-system-site-packages = false", "include-system-site-packages = true"))
    except OSError:
        pass


def environment():
    """Python that has all libraries, installing them into .venv when needed. None on failure."""
    python = venv_python()
    if not os.path.exists(python):
        log("creating the Python environment (.venv)")
        # system packages stay visible: on Linux the system pycairo is used, nothing to compile
        base = [sys.executable, "-m", "venv", "--system-site-packages"]
        if subprocess.call(base + [VENV], stderr=subprocess.DEVNULL) != 0:
            shutil.rmtree(VENV, ignore_errors=True)
            if subprocess.call(base + ["--without-pip", VENV]) != 0:
                if works(sys.executable):                     # no venv at all, but the system has everything
                    return sys.executable
                log("could not create .venv; on Debian/Ubuntu: sudo apt install python3-venv")
                return None
    share_system_packages()
    if works(python):
        return python
    if not has_pip(python) and not install_pip(python):
        return None
    packages = missing(python)
    log(f"installing {', '.join(packages)}, the first start takes a few minutes...")
    code = subprocess.call([python, "-m", "pip", "install", "--disable-pip-version-check", *packages])
    if code != 0 or not works(python):
        log("could not install the libraries. Check the internet connection and start again.")
        if not WINDOWS:
            log("if pycairo fails to build: sudo apt install python3-cairo (or libcairo2-dev pkg-config)")
        return None
    return python


def start(python, args):
    if WINDOWS:
        windowed = venv_python(windowed=True)
        python = windowed if python == venv_python() and os.path.exists(windowed) else python
    log_file = open(os.path.join(APP_DIR, "tree.log"), "w")
    options = {"cwd": APP_DIR, "stdout": log_file, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if WINDOWS:
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
    else:
        options["start_new_session"] = True
    subprocess.Popen([python, os.path.join(APP_DIR, "tree.py"), *args], **options)


def main():
    args = [a for a in sys.argv[1:] if a not in ("--no-update", "stop", "--stop")]
    stop = "--stop" in sys.argv or "stop" in sys.argv
    if sys.version_info < MIN_PYTHON:
        log(f"Python {'.'.join(map(str, MIN_PYTHON))} or newer is needed, this is {sys.version.split()[0]}")
        return 1
    if not stop and "--no-update" not in sys.argv and update():
        # the launcher itself may be new: run the updated one
        return subprocess.call([sys.executable, os.path.abspath(__file__), *sys.argv[1:], "--no-update"])
    python = environment()
    if python is None:
        return 1
    if stop:
        return subprocess.call([python, os.path.join(APP_DIR, "tree.py"), "--stop"])
    start(python, args)
    log("started")
    return 0


if __name__ == "__main__":
    sys.exit(main())
