#!/usr/bin/env python3
r"""Builds the manager's executable with PyInstaller (folder mode) from the already generated generic package.

  python construir.py [--paquete PATH/GestorMusica] [--salida PATH] [--sin-manual]

Requires:  pip install pyinstaller pillow reportlab   (Python 3.11 or 3.12 recommended, see CONSTRUIR.md)
Result:    SALIDA/GestorMusica-<system>/  with  GestorMusica(.exe | .app), support folder (_internal) and the manuals (Manual_ESP.pdf, Manual_ENG.pdf, Manual_DEUT.pdf, Manual_PORT.pdf)
           SALIDA/GestorMusica-<system>.zip
"""
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE.parent
arg = lambda n, d: Path(sys.argv[sys.argv.index(n) + 1]).resolve() if n in sys.argv else d  # noqa: E731
PAQ = arg("--paquete", DIST / "salida" / "GestorMusica" if (DIST / "salida" / "GestorMusica").is_dir() else DIST / "paquete")
SAL = arg("--salida", DIST / "salida")
SIS = {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(platform.system(), platform.system().lower())
if SIS == "mac":
    SIS += "-" + ("apple-silicon" if platform.machine() == "arm64" else "intel")
NOMBRE = "GestorMusica"
# the stdlib used by gestor.py, the scripts and the modules' servidor.py (loaded by path, so PyInstaller does not see them)
HIDDEN = ["argparse", "concurrent.futures", "csv", "ctypes", "datetime", "difflib", "glob", "hashlib", "http.server", "importlib.util",
          "json", "math", "mimetypes", "platform", "re", "secrets", "shutil", "socket", "string", "subprocess", "threading", "traceback",
          "types", "unicodedata", "urllib.parse", "urllib.request", "urllib.error", "uuid", "webbrowser", "zipfile", "zlib",
          "tkinter", "tkinter.filedialog", "PIL.Image", "PIL.ImageOps"]


def main():
    if not (PAQ / "gestor" / "index.html").is_file():
        raise SystemExit(f"Cannot find the generic package in {PAQ}. Run empaquetar.py first")
    sep = os.pathsep
    trabajo = SAL / "_pyi"
    shutil.rmtree(trabajo, ignore_errors=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", NOMBRE, "--distpath", str(trabajo / "dist"),
           "--workpath", str(trabajo / "build"), "--specpath", str(trabajo),
           "--add-data", f"{PAQ / 'gestor'}{sep}gestor", "--add-data", f"{PAQ / 'modulos'}{sep}modulos",
           "--exclude-module", "numpy", "--exclude-module", "pedalboard"]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    cmd += ["--windowed"] if SIS.startswith("mac") else []   # Windows: keep the small text window ("close it to quit")
    if SIS.startswith("mac"):
        cmd += ["--target-architecture", "universal2"] if os.environ.get("GM_UNIVERSAL2") else []
        cmd += ["--osx-bundle-identifier", "app.gestormusica.local"]
    cmd.append(str(HERE / "app.py"))
    subprocess.run(cmd, check=True)
    out = SAL / f"{NOMBRE}-{SIS}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    src = trabajo / "dist"
    if SIS.startswith("mac"):
        shutil.copytree(src / f"{NOMBRE}.app", out / f"{NOMBRE}.app", symlinks=True)
    else:
        for it in (src / NOMBRE).iterdir():
            (shutil.copytree if it.is_dir() else shutil.copy2)(it, out / it.name)
    (out / "datos").mkdir()
    if "--sin-manual" not in sys.argv:
        subprocess.run([sys.executable, str(DIST / "manual" / "hacer_manual.py"), str(out)], check=True)  # Manual_ESP/ENG/DEUT/PORT.pdf
    shutil.rmtree(trabajo, ignore_errors=True)
    zp = SAL / f"{NOMBRE}-{SIS}.zip"
    zp.unlink(missing_ok=True)
    if SIS.startswith("mac"):  # ditto keeps symlinks and permissions inside the .app
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(out), str(zp)], check=True)
        print("Done:", out, "| Zip:", zp)
        return
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_dir() or f.is_symlink() and False:
                continue
            zi = zipfile.ZipInfo.from_file(f, f.relative_to(SAL).as_posix())
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if os.access(f, os.X_OK) and SIS != "windows" else 0o644) << 16
            z.writestr(zi, f.read_bytes())
    print(f"Done: {out}\nZip: {zp} ({round(zp.stat().st_size / 1048576, 1)} MB)")


if __name__ == "__main__":
    main()
