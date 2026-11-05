"""Rutas y configuración compartidas por el gestor y sus scripts (Windows, Mac y Linux)."""
import json
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))    # True dentro del ejecutable (PyInstaller)
if FROZEN:
    RES = Path(sys._MEIPASS)                    # código, estáticos y módulos empaquetados (solo lectura)
    CODE = RES / "gestor"
    APP = Path(sys.executable).resolve().parent  # carpeta del ejecutable: aquí viven config.json y datos/
    if sys.platform == "darwin" and APP.name == "MacOS" and APP.parent.name == "Contents":
        APP = APP.parent.parent.parent          # dentro de GestorMusica.app: se usa la carpeta que contiene la .app
    if not os.access(APP, os.W_OK):             # p. ej. instalado en /Applications o en un disco de solo lectura
        APP = Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/share") / "GestorMusica"
        APP.mkdir(parents=True, exist_ok=True)
else:
    CODE = Path(__file__).resolve().parent      # .../GestorMusica/gestor
    APP = CODE.parent                           # .../GestorMusica
    RES = APP
DATOS = APP / "datos"                           # tu estado, diario y datos generados (se crea solo)
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
    """Carpeta de la biblioteca de música (la que eliges la primera vez)."""
    b = load_config().get("biblioteca") or os.environ.get("GESTOR_BIBLIOTECA", "")
    return Path(b).expanduser().resolve() if b else None


def lp(p):
    """Ruta larga en Windows (más de 260 caracteres); en Mac y Linux no hace nada."""
    p = os.path.abspath(str(p))
    return "\\\\?\\" + p if os.name == "nt" and not p.startswith("\\\\?\\") else p


def posix(p):
    return str(p).replace("\\", "/")


def layout_dirs(r):
    for d in ("unreleased", "prereleased", "published/Singles", "published/Álbumes", "ARTE"):
        (r / d).mkdir(parents=True, exist_ok=True)
