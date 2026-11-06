"""Server of the "masterizado" module: it only SAVES the masters into the library.
All audio processing happens in the browser; here the finished WAV is just written.

Routes:
  POST guardar_master?id=<songId>&nombre=<file.wav>   body = the raw WAV
       → saved in  <song folder>/master/  never overwriting (if it exists " (2)", " (3)"… is appended)
  POST guardar_master?mix=<mixtapeId>&id=<itemId>&nombre=…  → same, but in MIXTAPES/_masters/<mixtapeId>/ (mixtapes never write into the songs' master/)
  GET  masters?mix=<mixtapeId>                               → what is already in that folder
  GET  masters?ids=<id1>,<id2>…                              → which files are already in each song's master/ folder
"""
import os
import re
from pathlib import Path

LIMITE = 4 * 1024 * 1024 * 1024 - 1024  # a WAV cannot exceed 4 GB


def _carpeta_cancion(ctx, sid):
    """Song folder, validated: it must exist and be INSIDE the library."""
    s = ctx.song(sid) if sid else None
    if not s or not s.get("dir"):
        return None
    rel = str(s["dir"]).replace("\n", " ").replace("\\", "/").strip("/")
    raiz = Path(ctx.root).resolve()
    base = (raiz / rel).resolve()
    try:
        base.relative_to(raiz)
    except ValueError:
        return None
    return base if base.is_dir() else None


def _carpeta_master(ctx, sid):
    base = _carpeta_cancion(ctx, sid)
    if not base:
        return None
    m = (base / "master").resolve()  # if «master» were a link pointing outside, it is not valid either
    try:
        m.relative_to(Path(ctx.root).resolve())
    except ValueError:
        return None
    return m


def _carpeta_mix(ctx, mid):
    """MIXTAPES/_masters/<mixtape id>/ inside the library. Never the songs' master/ folders."""
    mid = re.sub(r"[^A-Za-z0-9_-]", "_", str(mid or ""))
    if not mid:
        return None
    raiz = Path(ctx.root).resolve()
    m = (raiz / "MIXTAPES" / "_masters" / mid).resolve()
    try:
        m.relative_to(raiz)
    except ValueError:
        return None
    return m


def _nombre_wav(ctx, nombre):
    n = ctx.safe_name(nombre or "", "master")
    n = re.sub(r"\.wav$", "", n, flags=re.I).strip(" .") or "master"
    return n[:150] + ".wav"


def guardar_master(req, ctx):
    sid = req.arg("id")
    mix = req.arg("mix")
    m = _carpeta_mix(ctx, mix) if mix else _carpeta_master(ctx, sid)
    if not m:
        return req.send({"ok": False, "error": "No encuentro la carpeta de destino en la biblioteca."}, 400)
    n = req.tam()
    if n < 44 or n > LIMITE:
        return req.send({"ok": False, "error": "El archivo recibido no es un WAV válido (tamaño)."}, 400)
    m.mkdir(parents=True, exist_ok=True)
    nombre = _nombre_wav(ctx, req.arg("nombre"))
    tmp = m / (".parte-" + os.urandom(4).hex() + ".tmp")
    try:
        req.guardar_en(tmp)
        with open(tmp, "rb") as f:
            cab = f.read(12)
        if cab[:4] != b"RIFF" or cab[8:12] != b"WAVE":
            raise ValueError("el archivo recibido no es un WAV")
        stem, final, k = nombre[:-4], m / nombre, 1
        while final.exists():  # NOTHING is ever overwritten
            k += 1
            final = m / f"{stem} ({k}).wav"
        os.rename(tmp, final)  # (on Windows it fails if it exists; elsewhere the check above is enough)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    rel = final.relative_to(Path(ctx.root).resolve()).as_posix()
    req.send({"ok": True, "nombre": final.name, "ruta": rel, "bytes": n, "renombrado": final.name != nombre})


def masters(req, ctx):
    """Lists what is already in master/ (to warn before saving)."""
    out = {}
    if req.arg("mix"):
        m = _carpeta_mix(ctx, req.arg("mix"))
        return req.send({"ok": True, "masters": {"mix": sorted(p.name for p in m.iterdir() if p.is_file() and not p.name.startswith(".")) if m and m.is_dir() else []}})
    for sid in [x for x in req.arg("ids").split(",") if x]:
        m = _carpeta_master(ctx, sid)
        out[sid] = sorted(p.name for p in m.iterdir() if p.is_file() and not p.name.startswith(".")) if m and m.is_dir() else []
    req.send({"ok": True, "masters": out})


ROUTES = {
    "POST guardar_master": guardar_master,
    "GET masters": masters,
}
