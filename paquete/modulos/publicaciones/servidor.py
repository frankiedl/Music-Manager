"""«publicaciones» module server: makes a CLEAN copy of a song's audio (no tags at all) to hand to a distributor.
The original file is never touched; the copy goes to <library>/_para_subir/ (not scanned as part of the catalog).
Standard library only."""
import re
import sys
from pathlib import Path

AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".aif", ".aiff"}


def limpio(req, ctx):
    import limpiar_tags
    d = req.json()
    raiz = Path(ctx.root).resolve()
    rel = str(d.get("p") or "").replace("\\", "/").strip("/")
    p = (raiz / rel).resolve()
    try:
        p.relative_to(raiz)
    except ValueError:
        return req.send({"ok": False, "error": "Archivo no válido"})
    if not rel or not p.is_file() or p.suffix.lower() not in AUDIO:
        return req.send({"ok": False, "error": "Archivo no válido"})
    nombre = re.sub(r'[<>:"/\|?*\x00-\x1f]', "_", str(d.get("nombre") or p.stem)).strip(" .") or p.stem
    out = raiz / "_para_subir" / (nombre + p.suffix.lower())
    n = 2
    while out.exists():
        out = raiz / "_para_subir" / f"{nombre} ({n}){p.suffix.lower()}"
        n += 1
    try:
        limpiar_tags.limpiar_copia(p, out, ctx.ffmpeg() if callable(getattr(ctx, "ffmpeg", None)) else None)
    except (ValueError, OSError) as e:
        return req.send({"ok": False, "error": "No se pudo limpiar el archivo: " + str(e)[:160]})
    req.send({"ok": True, "p": out.relative_to(raiz).as_posix(), "nombre": out.name})


ROUTES = {"POST limpio": limpio}
