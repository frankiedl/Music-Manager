"""«huella» module server: checks whether a master already sounds like something known, using AudD audio recognition
(https://audd.io) with the user's OWN API token. Standard library only (http.client + ssl). Nothing leaves the computer
unless the user confirms in the UI; and not the whole song when it is long: only one clip of one minute from the middle of the song (mono, low bitrate) cut
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
  GET  dossier?id=…    the full verification package (ZIP: report, fragments, raw AudD responses, SHA-256 manifest, how-to)
  POST registro        {id, autor, plataforma, ref, fecha}: the authorship registration the person declares (not verified)
  GET  informe?id=…&lang=es|en    a printable report (HTML) of the last check of a song: file name, SHA-256, date, clips, result. It is NOT an
                       authorship certificate: it only documents what AudD answered for that exact file on that day.
Tests: GESTOR_HUELLA_API=http://127.0.0.1:PORT points to a local fake server instead of https://api.audd.io.
"""
import base64
import hashlib
import html
import http.client
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
import zipfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

API_REAL = "https://api.audd.io"
API = (os.environ.get("GESTOR_HUELLA_API") or API_REAL).rstrip("/")
AUDIO = {".wav", ".wave", ".aif", ".aiff", ".flac", ".ogg", ".oga", ".mp3", ".aac", ".m4a", ".wma"}
VERSION = "huella 1.4"
SEG = 60                 # seconds per clip
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
    """ONE clip of SEG seconds from the middle of the song (the whole song when it is about a minute or less) → [(segundo, Path)]."""
    dur = _duracion(ff, p)
    if dur <= SEG + 3:
        puntos = [0]
    else:
        puntos = [(dur - SEG) / 2]
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
    return j, txt


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _utc(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _ffver(ff):
    try:
        r = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout or "").splitlines()[0][:120]
    except Exception:  # noqa: BLE001
        return ""


def _seguro(t):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(t))


def _trabajo(ctx, job, token, items):
    J = JOBS[job]
    ff = _ffmpeg(ctx)
    ver = _ffver(ff) if ff else ""
    res = _resultados(ctx)
    for it in items:
        sid = str(it["id"])
        p = it["p"]
        st = p.stat()
        sello = time.strftime("%Y%m%d-%H%M%S")
        ed = Path(ctx.datos) / "evidencias" / _seguro(sid) / sello
        r = {"t": time.strftime("%Y-%m-%d %H:%M"), "t_utc": _utc(), "modulo": VERSION, "titulo": it.get("titulo") or p.stem, "archivo": p.name,
             "bytes": st.st_size, "modificado_utc": _utc(st.st_mtime), "sha256": _sha256(p), "duracion": round(_duracion(ff, p), 1) if ff else 0,
             "ffmpeg": ver, "api": API, "clips": 0, "seg_s": SEG, "segundos": [], "fragmentos": [], "coincidencias": [], "evidencia": sello}
        try:
            with tempfile.TemporaryDirectory(prefix="gm_huella_") as tmp:
                if ff:
                    clips = _cortes(ff, p, tmp)
                elif st.st_size <= MAX_DIRECTO:
                    clips = [(0, p)]
                else:
                    raise HError("Hace falta ffmpeg para cortar fragmentos de un archivo grande.")
                ed.mkdir(parents=True, exist_ok=True)
                vistos = {}
                for n, (seg, f) in enumerate(clips, 1):
                    hora = _utc()
                    j, raw = _enviar(token, f)
                    dst = ed / f"fragmento_{n}_s{seg}{f.suffix}"
                    shutil.copyfile(f, dst)
                    (ed / f"respuesta_{n}.json").write_text(raw, encoding="utf-8")
                    r["clips"] += 1
                    r["segundos"].append(seg)
                    m = j.get("result")
                    hay = isinstance(m, dict) and bool(m.get("title") or m.get("artist"))
                    r["fragmentos"].append({"n": n, "segundo": seg, "archivo": dst.name, "bytes": dst.stat().st_size, "sha256": _sha256(dst),
                                            "hora_utc": hora, "respuesta": f"respuesta_{n}.json", "estado": j.get("status"), "coincide": hay})
                    if hay:
                        k = (str(m.get("artist", "")).lower(), str(m.get("title", "")).lower())
                        e = vistos.setdefault(k, {"artista": m.get("artist", ""), "titulo": m.get("title", ""), "album": m.get("album", ""),
                                                  "sello": m.get("label", ""), "fecha": m.get("release_date", ""), "link": m.get("song_link", ""), "tc": m.get("timecode", ""), "en": []})
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
            items.append({"id": x.get("id"), "p": _ruta(ctx, x.get("p")), "titulo": str(x.get("titulo") or "")[:200]})
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


def _registros(ctx):
    try:
        return json.loads((Path(ctx.datos) / "registros.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def registro(req, ctx):
    d = req.json() or {}
    sid = str(d.get("id") or "")
    if not sid:
        return req.send({"ok": False, "error": "Falta la canción."})
    reg = _registros(ctx)
    reg[sid] = {k: str(d.get(k) or "").strip()[:600] for k in ("autor", "plataforma", "ref", "fecha", "letra_original", "musica_herr", "ia_max", "suno_ref", "suno_plan", "aportacion")}
    (Path(ctx.datos) / "registros.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    req.send({"ok": True})


CAMPOS_DECL = ("autor", "plataforma", "letra_original", "musica_herr", "ia_max", "suno_plan", "aportacion")


def _defecto(ctx):
    """The person's standing declaration, applied to every song that has no value of its own (kept only in the local data folder)."""
    try:
        return json.loads((Path(ctx.datos) / "defecto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def defecto(req, ctx):
    d = req.json() or {}
    (Path(ctx.datos) / "defecto.json").write_text(json.dumps({k: str(d.get(k) or "").strip()[:600] for k in CAMPOS_DECL}, ensure_ascii=False), encoding="utf-8")
    req.send({"ok": True})


def registros(req, ctx):
    req.send({"ok": True, "registros": _registros(ctx), "defecto": _defecto(ctx)})


def _logos(ctx):
    """AudD's logos, only if the person put them in datos/modulos/huella/logos/ (they are not part of the package)."""
    out = ""
    for n, h in (("audd.png", 30), ("audd-icono.png", 36)):
        try:
            b = (Path(ctx.datos) / "logos" / n).read_bytes()
        except OSError:
            continue
        if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) < 300000:
            out += '<img src="data:image/png;base64,%s" alt="AudD" style="height:%dpx">' % (base64.b64encode(b).decode(), h)
    return out


CSS_INFORME = 'body{font:14px/1.55 system-ui,sans-serif;max-width:820px;margin:36px auto;padding:0 20px;color:#111}h1{font-size:22px;margin:6px 0 4px}h2{font-size:16px;margin:26px 0 6px;border-bottom:1px solid #ccc;padding-bottom:3px}\ntable{border-collapse:collapse;width:100%;margin:8px 0}td,th{border-bottom:1px solid #e2e2e2;padding:6px;vertical-align:top;text-align:left;font-size:13px}td:first-child{color:#444;width:34%}\ncode,pre{font-size:12px;word-break:break-all;white-space:pre-wrap}.aviso{background:#f4f4f6;border-radius:8px;padding:12px 14px;font-size:13px}.logos{display:flex;gap:14px;align-items:center}.firma{display:grid;grid-template-columns:1fr 1fr;gap:26px 30px;margin-top:34px}.firma div{border-top:1px solid #111;padding-top:4px;font-size:12px;color:#333}.pie{font-size:11px;color:#555;margin-top:22px}@media print{body{margin:0}}'


def _html(ctx, sid, r, lang="es"):
    en = lang == "en"

    def T(es, ing):
        return ing if en else es
    e = html.escape
    g = {**_defecto(ctx), **{k: v for k, v in _registros(ctx).get(sid, {}).items() if v}}
    titulo = r.get("titulo", "")
    obra = ("“%s”" if en else "«%s»") % e(titulo)
    autor = e(g.get("autor") or T("[nombre del autor/a]", "[author's name]"))
    frases = []
    if g.get("letra_original") == "si":
        frases.append(T("Las letras de %s son textos originales de mi autoría.", "The lyrics of %s are original texts written by me.") % obra)
    elif g.get("letra_original") == "no":
        frases.append(T("Las letras de %s no son textos originales de mi autoría.", "The lyrics of %s are not original texts written by me.") % obra)
    if g.get("musica_herr"):
        frases.append(T("La música de %s consiste en arreglos realizados con %s.", "The music of %s consists of arrangements made with %s.") % (obra, e(g["musica_herr"])))
    ia = re.sub(r"[^0-9.,]", "", str(g.get("ia_max") or ""))
    if ia:
        frases.append(T("%s no ha sido generada al 100%% por inteligencia artificial: la proporción de IA en esta obra no supera el %s%%.",
                        "%s has not been 100%% generated by artificial intelligence: the share of AI in this work does not exceed %s%%.") % (obra, e(ia)))
    extra = ""
    for k, es, ing in (("suno_ref", "Creación en SUNO (enlace o ID)", "Creation in SUNO (link or ID)"), ("suno_plan", "Plan de SUNO al crearla", "SUNO plan when it was created"),
                       ("aportacion", "Aportación del autor/a", "Author's own contribution")):
        if g.get(k):
            extra += "<tr><td>%s</td><td>%s</td></tr>" % (T(es, ing), e(g[k]))
    reg = ""
    if g.get("ref"):
        reg = "<tr><td>%s</td><td>%s · %s%s</td></tr>" % (T("Registro de autoría aportado", "Authorship registration provided"), e(g.get("plataforma", "")), T("referencia: ", "reference: ") + e(g["ref"]),
                                                          ((" · " + T("fecha del registro: ", "registration date: ") + e(g["fecha"])) if g.get("fecha") else ""))
    if r.get("error"):
        res = "<p><b>%s</b> %s</p>" % (T("La comprobación no se completó:", "The check did not complete:"), e(r["error"]))
    elif not r["coincidencias"]:
        res = "<p><b>%s</b> (%s).</p>" % (T("AudD no reconoció coincidencias en los fragmentos enviados", "AudD found no matches in the clips sent"), r["clips"])
    else:
        res = "<p><b>%s</b></p><ul>%s</ul>" % (T("AudD reconoció coincidencias:", "AudD reported matches:"), "".join(
            "<li>%s, %s%s%s %s (%s %s%s)</li>" % (e(c["artista"]), e(c["titulo"]), (" · " + T("álbum «", "album “") + e(c["album"]) + T("»", "”")) if c.get("album") else "",
                                                  (" · " + e(c["fecha"])) if c.get("fecha") else "", e(c.get("link", "")), T("en el segundo", "at second"),
                                                  ", ".join(str(x) for x in c["en"]), (T(", que suena como el minuto ", ", sounding like minute ") + e(c["tc"]) + T(" de la otra obra", " of the other work")) if c.get("tc") else "")
            for c in r["coincidencias"]))
    filas = "".join("<tr><td>%s</td><td>s %s</td><td><code>%s</code></td><td>%s…</td><td>%s</td><td>%s</td></tr>" % (
        f["n"], f["segundo"], e(f["archivo"]), f["sha256"][:16], e(f["hora_utc"]), T("coincidencia", "match") if f["coincide"] else T("sin coincidencia", "no match")) for f in r.get("fragmentos", []))
    api = r.get("api") or API_REAL
    rec = r["fragmentos"][0]["archivo"] if r.get("fragmentos") else "clip_1.mp3"
    seg0 = r["fragmentos"][0]["segundo"] if r.get("fragmentos") else 0
    segl = r.get("seg_s", 12)
    hoy = time.strftime("%Y-%m-%d")
    logos = _logos(ctx)
    h = ['<!doctype html><html lang="%s"><meta charset="utf-8"><title>%s</title><style>%s</style>' % (lang, T("Expediente de verificación de huella de audio", "Audio fingerprint verification dossier"), CSS_INFORME)]
    h.append('<div class="logos">%s</div><h1>%s</h1>' % (logos, T("Expediente de verificación de huella de audio", "Audio fingerprint verification dossier")))
    h.append("<p>%s</p>" % T("Generado por el módulo «Huella» (%s) con el servicio de reconocimiento de audio AudD. El expediente completo (ZIP) incluye los fragmentos enviados, las respuestas originales del servicio y un manifiesto con sus huellas SHA-256.",
                              "Generated by the “Huella” module (%s) using the AudD audio recognition service. The full dossier (ZIP) includes the clips sent, the service's original responses and a manifest with their SHA-256 hashes.") % e(r.get("modulo", VERSION)))
    h.append("<h2>1. %s</h2>" % T("Declaración de autoría y firma de responsabilidad del autor", "Declaration of authorship and author's signed statement of responsibility"))
    h.append("<p>%s</p>" % (T("Yo, <b>%s</b>, como autor/a de la obra %s, declaro bajo mi responsabilidad que:", "I, <b>%s</b>, as the author of the work %s, declare under my own responsibility that:") % (autor, obra)))
    h.append("<ul>%s</ul>" % "".join("<li>%s</li>" % x for x in frases) if frases else "<p><i>%s</i></p>" % T("No se ha indicado ninguna declaración sobre letras, música o uso de IA.", "No statement about lyrics, music or use of AI has been entered."))
    if extra or reg:
        h.append("<table>%s%s</table>" % (extra, reg))
    h.append("<p>%s</p>" % T("Esto es una declaración de autoría, hecha y firmada bajo la responsabilidad del autor/a. Este documento no la verifica: es la propia persona autora quien responde de ella.",
                              "This is a declaration of authorship, made and signed under the author's own responsibility. This document does not verify it: the author alone answers for it."))
    h.append('<div class="firma"><div>%s: %s</div><div>%s: %s</div><div>%s</div><div>%s</div></div>' % (
        T("Firma", "Signature"), "&nbsp;", T("Nombre", "Name"), autor, T("Lugar", "Place"), T("Fecha de la firma (documento generado el %s)", "Date signed (document generated on %s)") % hoy))
    h.append("<h2>2. %s</h2>" % T("Archivo comprobado", "Audio file checked"))
    h.append("<table><tr><td>%s</td><td>%s</td></tr><tr><td>%s</td><td>%s</td></tr><tr><td>%s</td><td>%s s</td></tr><tr><td>%s</td><td>%s (UTC)</td></tr><tr><td>%s</td><td><code>%s</code></td></tr></table>" % (
        T("Obra", "Work"), e(titulo), T("Nombre del archivo y tamaño", "File name and size"), "%s, %s bytes" % (e(r["archivo"]), r.get("bytes", "")), T("Duración", "Duration"), r.get("duracion", ""),
        T("Última modificación del archivo", "File last modified"), e(r.get("modificado_utc", "")), T("Huella SHA-256 del archivo", "SHA-256 hash of the file"), r["sha256"]))
    h.append("<h2>3. %s</h2><ol>" % T("Procedimiento", "Procedure"))
    h.append("<li>%s</li>" % T("Se calcula la huella SHA-256 del archivo completo (arriba).", "The SHA-256 hash of the whole file is computed (above)."))
    h.append("<li>%s</li>" % (T("Con ffmpeg (%s) se corta(n) %s fragmento(s) de %s segundos del propio archivo, en mono, 22 050 Hz, MP3 a 64 kbps, de la parte central de la canción. Orden: <code>ffmpeg -y -ss SEGUNDO -t %s -i ARCHIVO -vn -ac 1 -ar 22050 -b:a 64k FRAGMENTO.mp3</code>",
                                "With ffmpeg (%s), %s clip(s) of %s seconds are cut from the file itself, mono, 22,050 Hz, MP3 at 64 kbps, from the middle of the song. Command: <code>ffmpeg -y -ss SECOND -t %s -i FILE -vn -ac 1 -ar 22050 -b:a 64k CLIP.mp3</code>")
                                % (e(r.get("ffmpeg") or T("ffmpeg no disponible", "ffmpeg not available")), r.get("clips", 0), segl, segl)))
    h.append("<li>%s</li>" % T("Cada fragmento se envía por POST (multipart) a <code>%s</code> con la cuenta del propio autor. No se envía el archivo original completo: solo un fragmento de la parte central de la canción (en una canción de un minuto o menos, casi entera).",
                                "Each clip is sent by POST (multipart) to <code>%s</code> using the author's own account. The complete original file is not sent: only a clip from the middle of the song (almost the whole song if it is one minute or shorter).") % e(api))
    h.append("<li>%s</li></ol>" % T("Se guarda tal cual la respuesta JSON de AudD de cada fragmento y la hora UTC del envío.", "AudD's JSON response for each clip is kept unchanged, with the UTC time it was sent."))
    h.append("<table><tr><td>%s</td><td>%s UTC (%s)</td></tr></table>" % (T("Fecha y hora de la comprobación", "Date and time of the check"), e(r.get("t_utc", "")), e(r["t"]) + T(" hora local del equipo", " local computer time")))
    h.append("<h2>4. %s</h2><table><tr><th>#</th><th>%s</th><th>%s</th><th>SHA-256</th><th>%s</th><th>%s</th></tr>%s</table>%s" % (
        T("Resultado por fragmento", "Result per clip"), T("Segundo", "Second"), T("Archivo", "File"), T("Hora UTC", "UTC time"), T("Resultado", "Result"), filas, res))
    h.append("<h2>5. %s</h2><ol>" % T("Cómo comprobar que es cierto (para una plataforma o un tercero)", "How to verify it (for a platform or a third party)"))
    h.append("<li>%s</li>" % T("<b>Identidad del archivo.</b> Pide el archivo original y calcula su huella: Windows <code>Get-FileHash -Algorithm SHA256 \"ARCHIVO\"</code>; Mac y Linux <code>shasum -a 256 ARCHIVO</code>. Debe ser igual a la de la sección 2.",
                                "<b>File identity.</b> Ask for the original file and compute its hash: Windows <code>Get-FileHash -Algorithm SHA256 \"FILE\"</code>; Mac and Linux <code>shasum -a 256 FILE</code>. It must equal the one in section 2."))
    h.append("<li>%s</li>" % (T("<b>Fragmentos.</b> Genera tus propios fragmentos con la orden de la sección 3 (por ejemplo <code>-ss %s</code>). Pueden no ser idénticos byte a byte a los del expediente si usas otra versión de ffmpeg, pero suenan igual.",
                                "<b>Clips.</b> Cut your own clips with the command in section 3 (for example <code>-ss %s</code>). They may not be byte-identical to the dossier's if you use another ffmpeg version, but they sound the same.") % seg0))
    h.append("<li>%s</li>" % (T("<b>Respuesta del servicio.</b> Con tu propia cuenta de AudD envía los fragmentos del expediente (o los tuyos): <code>curl https://api.audd.io/ -F api_token=TU_TOKEN -F file=@%s</code> y compara con las respuestas guardadas.",
                                "<b>Service response.</b> With your own AudD account, send the dossier's clips (or your own): <code>curl https://api.audd.io/ -F api_token=YOUR_TOKEN -F file=@%s</code> and compare with the saved responses.") % e(rec)))
    h.append("<li>%s</li>" % T("<b>Integridad del expediente.</b> Calcula el SHA-256 de cada archivo del ZIP y compáralo con <code>manifest.json</code>. Si alguna huella no coincide, el archivo fue modificado después de generarse.",
                                "<b>Dossier integrity.</b> Compute the SHA-256 of each file in the ZIP and compare it with <code>manifest.json</code>. If any hash differs, the file was modified after it was generated."))
    h.append("<li>%s</li></ol>" % T("<b>Declaraciones y fecha de autoría.</b> Verifica el registro en la plataforma indicada en la sección 1 con la referencia aportada, y pide a la persona autora su material de creación (proyecto de SUNO, versiones, borradores de la letra) para respaldar lo declarado.",
                                     "<b>Declarations and authorship date.</b> Check the registration on the platform named in section 1 using the reference provided, and ask the author for the creation material (SUNO project, versions, lyric drafts) that supports what is declared."))
    h.append('<h2>6. %s</h2><div class="aviso">%s</div>' % (T("Límites y aviso", "Limits and notice"), T(
        "Este documento <b>no es un certificado de autoría</b> ni acredita derechos. Lo ha generado el propio ordenador de la persona autora: AudD no firma sus respuestas, y la hora es la del reloj del equipo. Su valor depende de que un tercero pueda repetir las comprobaciones de la sección 5. «Sin coincidencias» solo indica que el catálogo de AudD no detectó nada parecido, no que nadie más tenga una obra igual. La huella de audio tampoco determina si una pista se creó con IA: las declaraciones sobre letras, arreglos con SUNO y uso de IA son de la persona autora y se firman bajo su responsabilidad.",
        "This document is <b>not an authorship certificate</b> and does not prove rights. It was generated by the author's own computer: AudD does not sign its responses, and the time is the computer's clock. Its value depends on a third party being able to repeat the checks in section 5. “No matches” only means AudD's catalogue did not detect anything similar, not that nobody else has an identical work. An audio fingerprint cannot tell whether a track was created with AI either: the statements about lyrics, SUNO arrangements and use of AI are the author's and are signed under the author's responsibility.")))
    h.append('<p class="pie">%s</p></html>' % T("AudD y su logotipo son marcas de sus propietarios y se muestran solo para identificar el servicio consultado. AudD no ha emitido ni avala este documento.",
                                                  "AudD and its logo are trademarks of their owners and are shown only to identify the service consulted. AudD has not issued or endorsed this document."))
    return "".join(h)


def _con_sha(ctx, sid):
    r = _resultados(ctx).get(str(sid))
    if not r or not r.get("sha256"):
        return None
    return r


def _lang(req):
    return "en" if str(req.arg("lang") or "").lower().startswith("en") else "es"


def informe(req, ctx):
    sid = str(req.arg("id"))
    r = _con_sha(ctx, sid)
    if not r:
        return req.send({"ok": False, "error": "Esta canción no tiene una comprobación con informe. Vuelve a comprobarla."})
    lang = _lang(req)
    d = Path(ctx.datos) / "informes"
    d.mkdir(parents=True, exist_ok=True)
    f = d / (_seguro(sid) + "_" + lang + ".html")
    f.write_text(_html(ctx, sid, r, lang), encoding="utf-8")
    req.file(f, "text/html; charset=utf-8")


def dossier(req, ctx):
    """ZIP: INFORME_es.html + REPORT_en.html, evidencia.json, manifest.json (SHA-256 of every file), COMO_VERIFICAR.txt, fragmentos/, respuestas/."""
    sid = str(req.arg("id"))
    r = _con_sha(ctx, sid)
    if not r:
        return req.send({"ok": False, "error": "Esta canción no tiene una comprobación con informe. Vuelve a comprobarla."})
    ed = Path(ctx.datos) / "evidencias" / _seguro(sid) / r.get("evidencia", "")
    d = Path(ctx.datos) / "informes"
    d.mkdir(parents=True, exist_ok=True)
    z = d / (_seguro(sid) + "_expediente.zip")
    contenido = {"INFORME_es.html": _html(ctx, sid, r, "es").encode("utf-8"), "REPORT_en.html": _html(ctx, sid, r, "en").encode("utf-8"),
                 "evidencia.json": json.dumps({"comprobacion": r, "registro_declarado": {**_defecto(ctx), **_registros(ctx).get(sid, {})}}, ensure_ascii=False, indent=1).encode("utf-8"),
                 "COMO_VERIFICAR.txt": ("CÓMO VERIFICAR / HOW TO VERIFY\n\n1. Calcula el SHA-256 del archivo original y compáralo con INFORME_es.html (sección 2).\n"
                                        "   Windows: Get-FileHash -Algorithm SHA256 ARCHIVO    Mac/Linux: shasum -a 256 ARCHIVO\n"
                                        "2. Envía fragmentos/* a AudD con tu cuenta: curl https://api.audd.io/ -F api_token=TU_TOKEN -F file=@fragmentos/ARCHIVO.mp3\n"
                                        "   y compara con respuestas/respuesta_N.json.\n"
                                        "3. Comprueba que cada archivo del ZIP coincide con manifest.json (SHA-256).\n"
                                        "4. Verifica el registro de autoría con la plataforma y la referencia indicadas.\n"
                                        "5. Las declaraciones sobre letras, arreglos y uso de IA las firma la persona autora: pide su material de creación.\n\n"
                                        "1. Compute the SHA-256 of the original audio file and compare it with REPORT_en.html (section 2).\n"
                                        "2. Send fragmentos/* to AudD with your own token and compare with respuestas/*.json.\n"
                                        "3. Check every file against manifest.json (SHA-256). 4. Verify the authorship registration with the named platform.\n"
                                        "5. The statements about lyrics, arrangements and use of AI are signed by the author: ask for the creation material.\n\n"
                                        "Este paquete no es un certificado de autoría. / This package is not an authorship certificate.\n").encode("utf-8")}
    if ed.is_dir():
        for f in sorted(ed.iterdir()):
            if f.is_file():
                contenido[("fragmentos/" if f.name.startswith("fragmento") else "respuestas/") + f.name] = f.read_bytes()
    manifest = {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for n, b in contenido.items()}
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, b in contenido.items():
            zf.writestr(n, b)
        zf.writestr("manifest.json", json.dumps({"generado_utc": _utc(), "modulo": VERSION, "archivos": manifest}, indent=1))
    req.file(z, "application/zip", descarga="expediente_huella_" + _seguro(r.get("titulo", sid)) + ".zip")


def resultados(req, ctx):
    req.send({"ok": True, "resultados": _resultados(ctx)})


ROUTES = {
    "GET estado": estado,
    "POST token": token,
    "POST borrar_token": borrar_token,
    "POST comprobar": comprobar,
    "GET progreso": progreso,
    "GET resultados": resultados,
    "GET informe": informe,
    "GET dossier": dossier,
    "POST registro": registro,
    "POST defecto": defecto,
    "GET registros": registros,
}
