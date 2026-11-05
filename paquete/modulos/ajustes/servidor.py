"""Ajustes del gestor: carpeta de la biblioteca, nombre y titular, y carpetas extra donde buscar plugins VST3.
Las preferencias que comparten varios módulos se guardan con ctx.guardar_ajustes (datos/ajustes.json)."""
import os
import string
import sys
from pathlib import Path


def vst_defecto():
    h = Path.home()
    if sys.platform.startswith("win"):
        return [r"C:\Program Files\Common Files\VST3", str(h / "AppData" / "Local" / "Programs" / "Common" / "VST3")]
    if sys.platform == "darwin":
        return ["/Library/Audio/Plug-Ins/VST3", str(h / "Library" / "Audio" / "Plug-Ins" / "VST3"), "/Library/Audio/Plug-Ins/Components"]
    return [str(h / ".vst3"), "/usr/lib/vst3", "/usr/local/lib/vst3"]


def estado(req, ctx):
    cfg = dict(ctx.cfg or {})
    aj = ctx.ajustes()
    extra = aj.get("vst_carpetas", [])
    req.send({"ok": True, "biblioteca": str(ctx.root), "editable": hasattr(ctx, "cambiar_biblioteca"),
              "artista": aj.get("artista") or cfg.get("artista", ""), "titular": aj.get("titular") or cfg.get("titular", ""),
              "vst_defecto": [{"p": p, "existe": os.path.isdir(p)} for p in vst_defecto()],
              "vst_extra": [{"p": p, "existe": os.path.isdir(p)} for p in extra],
              "datos": str(ctx.datos.parent.parent), "sistema": sys.platform})


def guardar(req, ctx):
    d = req.json()
    nombre = {"artista": str(d.get("artista", "")).strip(), "titular": str(d.get("titular", "")).strip()}
    if hasattr(ctx, "guardar_cfg"):
        ctx.guardar_cfg(nombre)
    ctx.guardar_ajustes(nombre)
    if isinstance(d.get("vst_carpetas"), list):
        ctx.guardar_ajustes({"vst_carpetas": [str(x) for x in d["vst_carpetas"] if str(x).strip()]})
    req.send({"ok": True})


def biblioteca(req, ctx):
    if not hasattr(ctx, "cambiar_biblioteca"):
        return req.send({"ok": False, "error": "En esta instalación la carpeta de la música es fija."}, 400)
    try:
        ruta = ctx.cambiar_biblioteca(req.json().get("ruta", ""))
    except ValueError as ex:
        return req.send({"ok": False, "error": str(ex)}, 400)
    req.send({"ok": True, "ruta": ruta})


def carpetas(req, ctx):
    """Explorador de carpetas: solo lista nombres de subcarpetas (no lee contenido)."""
    ruta = req.arg("ruta")
    if not ruta:
        if os.name == "nt":
            unidades = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            return req.send({"ok": True, "ruta": "", "padre": None, "carpetas": [{"n": u, "p": u} for u in unidades]})
        ruta = str(Path.home())
    p = Path(ruta).expanduser()
    try:
        p = p.resolve()
        subs = sorted((x for x in p.iterdir() if x.is_dir() and not x.name.startswith(".")), key=lambda x: x.name.lower())
    except OSError as ex:
        return req.send({"ok": False, "error": f"No puedo abrir esa carpeta ({ex.__class__.__name__})."}, 400)
    padre = str(p.parent) if p.parent != p else ("" if os.name == "nt" else None)
    req.send({"ok": True, "ruta": str(p), "padre": padre, "carpetas": [{"n": x.name, "p": str(x)} for x in subs[:600]]})


ROUTES = {"GET estado": estado, "POST guardar": guardar, "POST biblioteca": biblioteca, "GET carpetas": carpetas}
