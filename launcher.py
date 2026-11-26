#!/usr/bin/env python3
"""
Launcher of the Christmas tree. Uses only the standard library, so it runs on a fresh Python.

1. Online: checks GitHub for a newer version and updates the app files (settings stay).
2. Prepares its own Python environment (.venv) and installs missing libraries.
3. Starts the tree without a console window; a running tree is replaced.
4. Adds a launcher icon, so later starts need no terminal: Linux - app menu entry and (once) a
   desktop icon; Windows - (once) shortcuts on the desktop and in the Start menu.

  start.bat / start.sh               update, install, start
  start.bat --stop / start.sh stop   close the running tree
  --no-update                        skip the update check
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

__author__ = "Andrii Havrysh"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = "andriydeveloper/tree"
BRANCH = "main"
COMMIT_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"   # always fresh
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/VERSION"   # cached up to 5 minutes
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
KEEP = {"settings.json", "tree.log", ".venv", ".git", ".launcher.lock"}   # an update never replaces these
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


def fetch(url, timeout=6):
    request = urllib.request.Request(url, headers={"User-Agent": "christmas-tree-launcher"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def latest():
    """
    Version and archive of the newest commit. The commit comes from the GitHub API, so a fresh push
    is seen at once (raw files are cached for minutes); files of a fixed commit never change.
    """
    try:
        sha = json.loads(fetch(COMMIT_URL))["sha"]
        version = fetch(f"https://raw.githubusercontent.com/{REPO}/{sha}/VERSION").decode().strip()
        return version, f"https://github.com/{REPO}/archive/{sha}.zip"
    except Exception:                                         # API limit (60 an hour) etc.: the cached way
        return fetch(VERSION_URL).decode().strip(), ZIP_URL


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
        remote, zip_url = latest()
    except Exception as e:                                    # offline, GitHub down, no VERSION yet
        log(f"update check skipped ({e.__class__.__name__})")
        return False
    if version_tuple(remote) <= version_tuple(local):
        log(f"version {local} is up to date")
        return False

    log(f"updating {local} -> {remote}")
    try:
        with urllib.request.urlopen(zip_url, timeout=60) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        names = archive.namelist()
        if any(n.startswith("/") or ".." in n.split("/") for n in names):
            raise ValueError("unsafe path in the archive")
        root = names[0].split("/")[0]
        with tempfile.TemporaryDirectory() as tmp:
            for info in archive.infolist():
                path = archive.extract(info, tmp)
                mode = (info.external_attr >> 16) & 0o777    # zipfile drops modes: start.sh must stay executable
                if mode and not info.is_dir():
                    os.chmod(path, mode)
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


def notify(message):
    """Desktop notification, for starts without a terminal (Linux; Windows shows the console)."""
    if not WINDOWS and shutil.which("notify-send"):
        subprocess.call(["notify-send", "-i", os.path.join(APP_DIR, "icon.svg"), "Christmas tree", message],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def desktop_entry_text():
    def quoted(path):                                         # Exec quoting of the desktop entry spec
        return '"' + "".join("\\" + c if c in '"`$\\' else c for c in path) + '"'
    return ("[Desktop Entry]\nType=Application\nName=Christmas tree\n"
            "Comment=Animated Christmas tree in the screen corner\n"
            f"Exec={quoted(sys.executable)} {quoted(os.path.join(APP_DIR, 'launcher.py'))}\n"
            f"Icon={os.path.join(APP_DIR, 'icon.svg')}\n"
            "Terminal=false\nCategories=Utility;\nStartupNotify=false\n")


def write_if_changed(path, text, mode=0o644):
    try:
        with open(path) as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)
    return True


def linux_icons():
    text = desktop_entry_text()
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    if write_if_changed(os.path.join(data, "applications", "christmas-tree.desktop"), text):
        log("added to the app menu: Christmas tree")             # the path follows the folder if it moves
    marker = os.path.join(VENV, ".desktop-icon")
    if os.path.exists(marker):                                # once only: a removed icon stays removed
        return
    try:
        desktop = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True).stdout.strip()
    except OSError:
        desktop = ""
    desktop = desktop or os.path.expanduser("~/Desktop")
    if os.path.isdir(desktop):
        icon = os.path.join(desktop, "christmas-tree.desktop")
        write_if_changed(icon, text, 0o755)
        if shutil.which("gio"):                               # GNOME desktop: allow launching
            subprocess.call(["gio", "set", icon, "metadata::trusted", "true"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"desktop icon: {icon}")
    open(marker, "w").close()


def windows_icons():
    marker = os.path.join(VENV, ".desktop-icon")
    if os.path.exists(marker):                                # once only: a removed shortcut stays removed
        return
    q = lambda path: path.replace("'", "''")                  # PowerShell single quotes
    bat, ico = os.path.join(APP_DIR, "start.bat"), os.path.join(APP_DIR, "icon.ico")
    script = "".join(
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('{place}')"
        f"+'\\Christmas tree.lnk');$s.TargetPath='{q(bat)}';$s.WorkingDirectory='{q(APP_DIR)}';"
        f"$s.IconLocation='{q(ico)}';$s.WindowStyle=7;$s.Save();"
        for place in ("Desktop", "Programs"))
    code = subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    if code == 0:
        log("shortcuts added: desktop and Start menu")
        open(marker, "w").close()


def add_icons():
    try:
        windows_icons() if WINDOWS else linux_icons()
    except Exception as e:                                    # icons are a convenience, never block the start
        log(f"no launcher icon ({e.__class__.__name__}: {e})")


def system_library():
    """
    Qt 6.5+ on X11 needs the system library libxcb-cursor0, missing on a fresh Ubuntu and not
    installable with pip. With apt and pkexec the user is asked for the password in a dialog.
    """
    if WINDOWS or sys.platform == "darwin" or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return True
    import ctypes.util
    if ctypes.util.find_library("xcb-cursor"):
        return True
    log("the system library libxcb-cursor0 is missing (Qt needs it)")
    if shutil.which("pkexec") and shutil.which("apt-get") and os.environ.get("DISPLAY"):
        notify("One system library is missing (libxcb-cursor0). Enter your password to install it.")
        subprocess.call(["pkexec", "apt-get", "install", "-y", "libxcb-cursor0"])
        if ctypes.util.find_library("xcb-cursor"):
            log("libxcb-cursor0 installed")
            return True
    message = ("Missing system library. Install it and start again: sudo apt install libxcb-cursor0 "
               "(Fedora: sudo dnf install xcb-util-cursor, Arch: sudo pacman -S xcb-util-cursor)")
    log(message)
    notify(message)
    return False


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
    notify("First start: installing libraries, this takes a few minutes. The tree appears by itself.")
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
    process = subprocess.Popen([python, os.path.join(APP_DIR, "tree.py"), *args], **options)
    try:                                                      # a start that fails at once is reported
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        return True
    if process.returncode == 0:
        return True
    log_file.close()
    with open(os.path.join(APP_DIR, "tree.log")) as f:
        lines = [line.strip() for line in f if line.strip()]
    reason = lines[-1] if lines else f"exit code {process.returncode}"
    log(f"the tree could not start: {reason}")
    notify(f"The tree could not start: {reason[:200]}. Details: {os.path.join(APP_DIR, 'tree.log')}")
    return False


def lock():
    """Only one launcher at a time; a lock older than 20 minutes is left over from a crash."""
    path = os.path.join(APP_DIR, ".launcher.lock")
    for _ in range(2):
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) < 20 * 60:
                    return None
                os.remove(path)
            except OSError:
                return None
    return None


def main():
    path = lock()
    if path is None:
        log("already starting, please wait")
        notify("Already starting, please wait.")
        return 0
    try:
        return run()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def run():
    args = [a for a in sys.argv[1:] if a not in ("--no-update", "stop", "--stop")]
    stop = "--stop" in sys.argv or "stop" in sys.argv
    if sys.version_info < MIN_PYTHON:
        log(f"Python {'.'.join(map(str, MIN_PYTHON))} or newer is needed, this is {sys.version.split()[0]}")
        return 1
    if not stop and "--no-update" not in sys.argv and update():
        # the launcher itself may be new: run the updated one (it takes the lock itself)
        os.remove(os.path.join(APP_DIR, ".launcher.lock"))
        return subprocess.call([sys.executable, os.path.abspath(__file__), *sys.argv[1:], "--no-update"])
    python = environment()
    if python is None:
        return 1
    if stop:
        return subprocess.call([python, os.path.join(APP_DIR, "tree.py"), "--stop"])
    if not system_library():
        return 1
    started = start(python, args)
    add_icons()
    if not started:
        return 1
    log("started")
    return 0


if __name__ == "__main__":
    sys.exit(main())
