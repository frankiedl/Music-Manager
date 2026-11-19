"""«huella» module server: checks whether a master already sounds like something known, using AudD audio recognition
(https://audd.io) with the user's OWN API token. Standard library only (http.client + ssl). Nothing leaves the computer
unless the user confirms in the UI; and never the whole song: only three short clips (12 s each, mono, low bitrate) cut
with ffmpeg from the master.

Files (only in the local data folder datos/modulos/huella/; never in estado.json, never in the package):
  cuenta.json      {token}                      the AudD token; never sent back to the UI and never printed
  resultados.json  {songId: {t, archivo, clips, coincidencias:[{artista, titulo, album, sello, fecha, link, en}], error?}}

Routes (/api/mod/huella/…):
  GET  estado          {ok, token: bool, ffmpeg: bool}
  POST token           {token}   save the token        POST borrar_token   forget it
  POST comprobar       {items:[{id, p}]}  → {job}: cuts 3 clips per song and asks AudD (a thread)
  GET  progreso?job=…  {estado, hechos, total, resultados}
  GET  resultados      the saved results
Tests: GESTOR_HUELLA_API=http://127.0.0.1:PORT points to a local fake server instead of https://api.audd.io.
"""
import http.client
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

API_REAL = "https://api.audd.io"
API = (os.environ.get("GESTOR_HUELLA_API") or API_REAL).rstrip("/")
AUDIO = {".wav", ".wave", ".aif", ".aiff", ".flac", ".ogg", ".oga", ".mp3", ".aac", ".m4a", ".wma"}
SEG = 12                 # seconds per clip
MAX_DIRECTO = 9 * 1024 * 1024   # AudD standard endpoint accepts up to 10 MB: without ffmpeg we only send files under this size
MAX_ITEMS = 40
LOCK = threading.RLock()
JOBS = {}


class HError(Exception):
    pass


def _cuenta(ctx):
    try:
        return json.loads((Path(ctx.datos) / "cuenta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(ctx, d):
    p = Path(ctx.datos) / "cuenta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


def _resultados(ctx):
    try:
        return json.loads((Path(ctx.datos) / "resultados.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ffmpeg(ctx):
    f = getattr(ctx, "ffmpeg", None)
    try:
        return f() if callable(f) else (shutil.which("ffmpeg") or None)
    except Exception:  # noqa: BLE001
        return None


def _ruta(ctx, rel):
    rel = str(rel or "").replace("\\", "/").strip("/")
    raiz = Path(ctx.root).resolve()
    p = (raiz / rel).resolve() if rel else None
    if p is None:
        raise HError("No encuentro el archivo.")
    try:
        p.relative_to(raiz)
    except ValueError:
        raise HError("El archivo está fuera de la biblioteca.")
    if not p.is_file() or p.suffix.lower() not in AUDIO:
        raise HError("No es un archivo de audio de la biblioteca.")
    return p


def _duracion(ff, p):
    """Seconds of an audio file (parsed from ffmpeg's banner) or 0 if unknown."""
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", str(p)], capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    except Exception:  # noqa: BLE001
        return 0


def _cortes(ff, p, tmp):
    """Up to three clips (at ~20 %, 50 % and 80 % of the song) → [(segundo, Path)]."""
    dur = _duracion(ff, p)
    if dur <= SEG + 3:
        puntos = [0]
    else:
        puntos = [max(0, min(dur - SEG - 1, dur * f)) for f in (0.2, 0.5, 0.8)]
    out = []
    for i, s in enumerate(puntos):
        dst = Path(tmp) / f"{i}.mp3"
        r = subprocess.run([ff, "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", str(SEG), "-i", str(p), "-vn", "-ac", "1", "-ar", "22050", "-b:a", "64k", str(dst)],
                           capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and dst.is_file() and dst.stat().st_size > 2000:
            out.append((int(s), dst))
    if not out:
        raise HError("No pude cortar fragmentos del audio.")
    return out


def _enviar(token, ruta):
    """POST one clip to AudD (multipart) → the parsed JSON. Raises HError with a plain message."""
    u = urlparse(API)
    limite = "----h" + secrets.token_hex(12)
    datos = ruta.read_bytes()
    cuerpo = b""
    for k, v in (("api_token", token), ("return", "")):
        if v:
            cuerpo += f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    cuerpo += (f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="clip{ruta.suffix}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + datos + f"\r\n--{limite}--\r\n".encode()
    try:
        if u.scheme == "https":
            c = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=60, context=ssl.create_default_context())
        else:
            c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=60)
        c.request("POST", (u.path or "/") + "", body=cuerpo, headers={"Content-Type": "multipart/form-data; boundary=" + limite, "Content-Length": str(len(cuerpo))})
        r = c.getresponse()
        txt = r.read().decode("utf-8", "replace")
        c.close()
        j = json.loads(txt)
    except (OSError, ValueError, http.client.HTTPException):
        raise HError("No pude hablar con AudD. Revisa la conexión.")
    if j.get("status") == "error":
        e = (j.get("error") or {})
        cod = e.get("error_code")
        if cod in (900, 901):
            raise HError("AudD no acepta ese token. Revísalo en dashboard.audd.io.")
        raise HError("AudD respondió con un error" + (f" (#{cod})" if cod else "") + ".")
    return j


def _trabajo(ctx, job, token, items):
    J = JOBS[job]
    ff = _ffmpeg(ctx)
    res = _resultados(ctx)
    for it in items:
        sid = str(it["id"])
        r = {"t": time.strftime("%Y-%m-%d %H:%M"), "archivo": it["p"].name, "clips": 0, "coincidencias": []}
        try:
            with tempfile.TemporaryDirectory(prefix="gm_huella_") as tmp:
                if ff:
                    clips = _cortes(ff, it["p"], tmp)
                elif it["p"].stat().st_size <= MAX_DIRECTO:
                    clips = [(0, it["p"])]
                else:
                    raise HError("Hace falta ffmpeg para cortar fragmentos de un archivo grande.")
                vistos = {}
                for seg, f in clips:
                    j = _enviar(token, f)
                    r["clips"] += 1
                    m = j.get("result")
                    if isinstance(m, dict) and (m.get("title") or m.get("artist")):
                        k = (str(m.get("artist", "")).lower(), str(m.get("title", "")).lower())
                        e = vistos.setdefault(k, {"artista": m.get("artist", ""), "titulo": m.get("title", ""), "album": m.get("album", ""),
                                                  "sello": m.get("label", ""), "fecha": m.get("release_date", ""), "link": m.get("song_link", ""), "en": []})
                        e["en"].append(seg)
                r["coincidencias"] = list(vistos.values())
        except HError as ex:
            r["error"] = str(ex)
        except Exception:  # noqa: BLE001
            r["error"] = "Algo falló al comprobar esta canción."
        res[sid] = r
        with LOCK:
            J["hechos"] += 1
            J["resultados"][sid] = r
        if r.get("error", "").startswith("AudD no acepta"):
            break
    try:
        (Path(ctx.datos) / "resultados.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    with LOCK:
        J["estado"] = "listo"


def estado(req, ctx):
    req.send({"ok": True, "token": bool(_cuenta(ctx).get("token")), "ffmpeg": bool(_ffmpeg(ctx)), "prueba": API != API_REAL})


def token(req, ctx):
    t = str((req.json() or {}).get("token") or "").strip()
    if not t or len(t) > 200 or re.search(r"\s", t):
        return req.send({"ok": False, "error": "El token no tiene buena pinta. Cópialo entero desde dashboard.audd.io."})
    _guardar(ctx, {"token": t})
    req.send({"ok": True})


def borrar_token(req, ctx):
    try:
        (Path(ctx.datos) / "cuenta.json").unlink()
    except OSError:
        pass
    req.send({"ok": True})


def comprobar(req, ctx):
    d = req.json() or {}
    t = _cuenta(ctx).get("token")
    if not t:
        return req.send({"ok": False, "error": "Primero guarda tu token de AudD."})
    items = []
    try:
        for x in (d.get("items") or [])[:MAX_ITEMS]:
            items.append({"id": x.get("id"), "p": _ruta(ctx, x.get("p"))})
    except HError as ex:
        return req.send({"ok": False, "error": str(ex)})
    if not items:
        return req.send({"ok": False, "error": "No hay canciones con audio para comprobar."})
    job = secrets.token_hex(8)
    with LOCK:
        for k in [k for k, v in JOBS.items() if time.time() - v["t"] > 6 * 3600]:
            JOBS.pop(k, None)
        JOBS[job] = {"estado": "leyendo", "hechos": 0, "total": len(items), "resultados": {}, "t": time.time()}
    threading.Thread(target=_trabajo, args=(ctx, job, t, items), daemon=True).start()
    req.send({"ok": True, "job": job})


def progreso(req, ctx):
    J = JOBS.get(req.arg("job"))
    if not J:
        return req.send({"ok": False, "error": "No encuentro esa comprobación."})
    with LOCK:
        req.send({"ok": True, **{k: v for k, v in J.items() if k != "t"}})


def resultados(req, ctx):
    req.send({"ok": True, "resultados": _resultados(ctx)})


ROUTES = {
    "GET estado": estado,
    "POST token": token,
    "POST borrar_token": borrar_token,
    "POST comprobar": comprobar,
    "GET progreso": progreso,
    "GET resultados": resultados,
}
