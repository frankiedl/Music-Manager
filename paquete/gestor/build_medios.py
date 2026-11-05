#!/usr/bin/env python3
"""Inventario de arte y vídeo -> datos/medios.json (solo lee tu música).

Recorre published/ prereleased/ unreleased/ (carpetas «arte» y «video» dentro de cada canción) y la carpeta ARTE/,
y agrupa por «dueño» (carpeta de canción o de álbum). Las miniaturas necesitan Pillow (pip install pillow);
sin Pillow se usan las imágenes pequeñas tal cual.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arte_map as am  # noqa: E402
import common as C  # noqa: E402

try:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
except ImportError:  # el gestor funciona igual, solo que las portadas grandes no tendrán miniatura
    Image = None

THUMBS = C.DATOS / "thumbs"
OUT = C.DATOS / "medios.json"
IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}
SRC_ART = {".psd", ".ai"}
VID = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
PROJ = {".aep", ".drp", ".prproj"}
KINDS = {"arte": "arte", "_arte-album": "arte", "video": "video", "_video-album": "video"}
WEB_IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def classify(ext):
    if ext in IMG:
        return "imagen"
    if ext in SRC_ART:
        return "fuente-arte"
    if ext in VID:
        return "video"
    if ext in PROJ:
        return "proyecto"
    return None


def thumb(rel, full):
    """Miniatura JPEG de 520 px en datos/thumbs (caché por ruta+tamaño+fecha). Devuelve el nombre o ''."""
    lp = C.lp(full)
    st = os.stat(lp)
    name = hashlib.md5(f"{rel}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest() + ".jpg"
    out = THUMBS / name
    if out.exists():
        return name
    if Image is None:
        if os.path.splitext(full)[1].lower() in WEB_IMG and st.st_size <= 4_000_000:
            shutil.copyfile(lp, out)
            return name
        return ""
    try:
        with Image.open(lp) as im:
            im.draft("RGB", (1040, 1040))
            im = im.convert("RGB")
            im.thumbnail((520, 520))
            im.save(out, "JPEG", quality=82)
        return name
    except Exception as e:  # noqa: BLE001
        print("  sin miniatura:", rel, e)
        return ""


def main():
    R = C.root()
    if not R or not R.is_dir():
        return 1
    THUMBS.mkdir(parents=True, exist_ok=True)
    owners = {}

    def add(owner, full, ambito):
        f = os.path.basename(full)
        k = classify(os.path.splitext(f)[1].lower())
        if not k:
            return
        try:
            mb = round(os.path.getsize(C.lp(full)) / 1e6, 1)
        except OSError:
            return
        rel = os.path.relpath(full, R)
        t = thumb(rel, full) if k == "imagen" else ""
        owners.setdefault(owner, []).append({"t": t, "p": C.posix(rel), "n": f, "k": k, "ambito": ambito, "mb": mb})

    for top in ("published", "prereleased", "unreleased"):
        base = R / top
        if not base.is_dir():
            continue
        for dp, _dns, fns in os.walk(C.lp(base)):
            dp = dp.replace("\\\\?\\", "")
            rel = os.path.relpath(dp, R).replace("\\", "/").split("/")
            hit = next((i for i, c in enumerate(rel) if c in KINDS), None)
            if hit is None:
                continue
            owner = "/".join(rel[:hit])
            for f in fns:
                if not f.startswith("."):
                    add(owner, os.path.join(dp, f), "album" if rel[hit].endswith("-album") else "cancion")
    art = R / "ARTE"
    if art.is_dir():
        for dp, _dns, fns in os.walk(C.lp(art)):
            dp = dp.replace("\\\\?\\", "")
            parts = os.path.relpath(dp, art).replace("\\", "/").split("/")
            res = am.owner_of(parts) if parts != ["."] else None
            if not res:
                continue
            owner_parts, ambito, _ = res
            for f in fns:
                if not f.startswith("."):
                    add("/".join(owner_parts), os.path.join(dp, f), ambito)
    lst = [{"owner": o, "items": sorted(it, key=lambda x: (x["k"], x["n"].lower()))} for o, it in sorted(owners.items())]
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"owners": lst}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"datos/medios.json: {len(lst)} carpetas con medios, {sum(len(o['items']) for o in lst)} archivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
