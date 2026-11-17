"""Paths and configuration shared by the manager and its scripts (Windows, Mac and Linux)."""
import json
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))    # True inside the executable (PyInstaller)
if FROZEN:
    RES = Path(sys._MEIPASS)                    # bundled code, static files and modules (read-only)
    CODE = RES / "gestor"
    APP = Path(sys.executable).resolve().parent  # folder of the executable: config.json and datos/ live here
    if sys.platform == "darwin" and APP.name == "MacOS" and APP.parent.name == "Contents":
        APP = APP.parent.parent.parent          # inside GestorMusica.app: use the folder that contains the .app
    if not os.access(APP, os.W_OK):             # e.g. installed in /Applications or on a read-only disk
        APP = Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/share") / "GestorMusica"
        APP.mkdir(parents=True, exist_ok=True)
else:
    CODE = Path(__file__).resolve().parent      # .../GestorMusica/gestor
    APP = CODE.parent                           # .../GestorMusica
    RES = APP
LOCAL = APP / "datos"                           # per-computer files: generated data, thumbnails, access token
DATOS = LOCAL                                  # shared files (stars, notes, journal…): moved into the library folder by usar_biblioteca()
CONFIG = APP / "config.json"
RESERVED = {"stems", "versiones", "master", "sesiones", "otros", "docs", "midi", "arte", "video"}
AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".aif", ".aiff"}
DEFAULTS = {"biblioteca": "", "artista": "", "titular": "", "puerto": 8765}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def root():
    """Music library folder (the one chosen the first time)."""
    b = load_config().get("biblioteca") or os.environ.get("GESTOR_BIBLIOTECA", "")
    return Path(b).expanduser().resolve() if b else None


def lp(p):
    """Long path on Windows (more than 260 characters); does nothing on Mac and Linux."""
    p = os.path.abspath(str(p))
    return "\\\\?\\" + p if os.name == "nt" and not p.startswith("\\\\?\\") else p


def posix(p):
    return str(p).replace("\\", "/")


def layout_dirs(r):
    for d in ("unreleased", "prereleased", "published/Singles", "published/Álbumes", "ARTE"):
        (r / d).mkdir(parents=True, exist_ok=True)


SHARED_FILES = ("estado.json", "medios_estado.json", "decisiones.csv", "diario_movimientos.jsonl", "ids.json")


def usar_biblioteca():
    """Your own data (stars, notes, rights, journal…) lives INSIDE the music folder (<library>/_GestorMusica/datos), so
    every computer that opens the same Dropbox folder sees the same things; only the path of the library is per computer.
    Generated data and thumbnails stay local. Data already next to the program is copied there the first time."""
    global DATOS
    r = root()
    LOCAL.mkdir(parents=True, exist_ok=True)
    if not r or not r.is_dir():
        DATOS = LOCAL
        return DATOS
    d = r / "_GestorMusica" / "datos"
    try:
        d.mkdir(parents=True, exist_ok=True)
        import shutil
        for n in SHARED_FILES:
            if not (d / n).exists() and (LOCAL / n).exists():
                shutil.copy2(LOCAL / n, d / n)
        if not (d / "modulos").exists() and (LOCAL / "modulos").is_dir():
            shutil.copytree(LOCAL / "modulos", d / "modulos")
        DATOS = d
    except OSError:
        DATOS = LOCAL
    return DATOS


usar_biblioteca()
