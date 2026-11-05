"""Servidor del módulo «masterizado»: solo sirve para GUARDAR los másters en la biblioteca.
Todo el procesado de audio se hace en el navegador; aquí únicamente se escribe el WAV ya terminado.

Rutas:
  POST guardar_master?id=<idCancion>&nombre=<archivo.wav>   cuerpo = el WAV en bruto
       → lo guarda en  <carpeta de la canción>/master/  sin sobrescribir nunca (si existe añade « (2)», « (3)»…)
  POST guardar_master?mix=<idMixtape>&id=<idItem>&nombre=…  → igual, pero en MIXTAPES/_masters/<idMixtape>/ (los mixtapes nunca escriben en master/ de las canciones)
  GET  masters?mix=<idMixtape>                               → lo que ya hay en esa carpeta
  GET  masters?ids=<id1>,<id2>…                              → qué archivos hay ya en la carpeta master/ de cada canción
"""
import os
import re
from pathlib import Path

LIMITE = 4 * 1024 * 1024 * 1024 - 1024  # un WAV no pasa de 4 GB


def _carpeta_cancion(ctx, sid):
    """Carpeta de la canción, validada: tiene que existir y quedar DENTRO de la biblioteca."""
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
    m = (base / "master").resolve()  # si «master» fuese un enlace hacia fuera, tampoco vale
    try:
        m.relative_to(Path(ctx.root).resolve())
    except ValueError:
        return None
    return m


def _carpeta_mix(ctx, mid):
    """MIXTAPES/_masters/<id del mixtape>/ dentro de la biblioteca. Nunca las carpetas master/ de las canciones."""
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
        while final.exists():  # NUNCA se sobrescribe nada
            k += 1
            final = m / f"{stem} ({k}).wav"
        os.rename(tmp, final)  # (en Windows falla si existe; en el resto, la comprobación de arriba basta)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    rel = final.relative_to(Path(ctx.root).resolve()).as_posix()
    req.send({"ok": True, "nombre": final.name, "ruta": rel, "bytes": n, "renombrado": final.name != nombre})


def masters(req, ctx):
    """Lista lo que ya hay en master/ (para avisar antes de guardar)."""
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
