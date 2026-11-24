"""«soundcloud» module server: connects the user's OWN SoundCloud app (OAuth 2.1 code + PKCE) and uploads songs and album sets.
Standard library only (http.client + ssl). Nothing is uploaded unless the UI asks for it after the user confirms a preview.

Files (only in the local data folder, datos/modulos/soundcloud/; never in estado.json, never in the package):
  cuenta.json   {client_id, client_secret, access_token, refresh_token, expira, usuario:{username, permalink_url}}
                The secret and the tokens are never sent back to the UI (the secret is masked) and never printed.
  subidas.json  {"songs": {songId: {urn, url, titulo, archivo, t}}, "sets": {groupKey: {urn, url, titulo, pistas:[urn], t}}}
Every upload / update is also appended to datos/diario_movimientos.jsonl (op «soundcloud»; deshacer.py only replays op «move»).

Routes (/api/mod/soundcloud/…):
  GET  estado[?me=1]        connection state (masked secret, port, redirect URI); me=1 refreshes the account name from /me
  POST credenciales         {client_id, client_secret}  (empty secret = keep the saved one)
  POST borrar_credenciales  forget everything (disconnects first, best effort)
  POST conectar             → {url}: the SoundCloud authorize page (state + S256 code challenge; the verifier stays in memory)
  POST desconectar          POST /disconnect (best effort) and delete the tokens
  POST preparar             {items:[{id,p}], portada, key} → size/validity of each file + what was already uploaded
  POST subir                {id, p, titulo, sharing, …, portada} → {job}: streams a multipart upload from disk in a thread
  GET  progreso?job=…       {estado, enviados, total, resultado | error}
  POST actualizar           {id, urn, titulo, …}: PUT /tracks/{urn} (metadata only; audio cannot be replaced)
  POST crear_set            {key, titulo, urns:[…], …, actualizar?}: POST /playlists (or PUT), then GET it and fix the order
  GET  subidas              the upload record
  POST numeros              {items:[{id, urn}], si_no_hoy?} → {job}: GET /tracks/{urn} one by one (plays, likes, comments, reposts),
                            kept in numeros.json {songId: {urn, hist:[{f, plays, likes, comments, reposts}]}} (one row per day)
  GET  numeros              numeros.json
  POST claves               {pares:[[old, new]]}: an album folder moved (project published as an album): its set record follows
Public route (no access check; validated by its single-use `state`): GET /soundcloud/callback (OAuth redirect).

Tests: GESTOR_SOUNDCLOUD_AUTH and GESTOR_SOUNDCLOUD_API override https://secure.soundcloud.com and https://api.soundcloud.com
(a local fake server). Without them the real URLs are used.
"""
import base64
import hashlib
import html
import http.client
import json
import mimetypes
import os
import re
import secrets
import shutil
import ssl
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

try:
    from modulos_core import idioma_de, traducir
except ImportError:  # pragma: no cover
    def idioma_de(h):
        return "es"

    def traducir(t, lang):
        return t

AUTH_REAL, API_REAL = "https://secure.soundcloud.com", "https://api.soundcloud.com"
AUTH = (os.environ.get("GESTOR_SOUNDCLOUD_AUTH") or AUTH_REAL).rstrip("/")
API = (os.environ.get("GESTOR_SOUNDCLOUD_API") or API_REAL).rstrip("/")
PRUEBA = AUTH != AUTH_REAL or API != API_REAL
PUERTO_OFICIAL = 8765
RUTA_CALLBACK = "/soundcloud/callback"
AUDIO = {".wav", ".wave", ".aif", ".aiff", ".flac", ".ogg", ".oga", ".mp2", ".mp3", ".aac", ".m4a", ".amr", ".wma"}
IMAGEN = {".jpg", ".jpeg", ".png", ".gif"}
MAX_AUDIO = 4 * 1024 ** 3
MAX_IMAGEN = 8 * 1024 ** 2
LICENCIAS = {"all-rights-reserved", "no-rights-reserved", "cc-by", "cc-by-nc", "cc-by-nd", "cc-by-sa", "cc-by-nc-nd", "cc-by-nc-sa"}

LOCK = threading.RLock()
PEND = {}   # OAuth state → {verifier, redirect, lang, t}
JOBS = {}   # upload job id → progress


def aviso(texto):
    """Marks a user-facing message (so extraer.py finds it for the translation dictionary)."""
    return texto


MSG = {
    "no_conectado": aviso("No estás conectado a SoundCloud. Conecta tu cuenta en la sección SoundCloud."),
    "sesion": aviso("SoundCloud no acepta la sesión. Vuelve a conectar tu cuenta."),
    "prohibido": aviso("SoundCloud no lo permite (403). Comprueba que tu cuenta tiene Artist Pro y que la app puede subir pistas."),
    "no_encontrado": aviso("SoundCloud no encuentra ese elemento (404): puede que se haya borrado."),
    "grande": aviso("El archivo es demasiado grande para SoundCloud (máximo 4 GB)."),
    "rechazado": aviso("SoundCloud ha rechazado los datos (422). Revisa el título, el archivo o los campos."),
    "limite": aviso("Demasiadas peticiones a SoundCloud (límite por minuto). Espera un poco y vuelve a intentarlo."),
    "servidor": aviso("SoundCloud tiene un problema ahora mismo. Inténtalo más tarde."),
    "otro": aviso("SoundCloud ha devuelto un error."),
    "red": aviso("No se pudo conectar con SoundCloud. Comprueba tu conexión a internet."),
    "credenciales": aviso("Faltan el Client ID o el Client Secret."),
    "token": aviso("SoundCloud no aceptó la autorización. Revisa el Client ID, el Client Secret y la Redirect URI, y vuelve a conectar."),
    "archivo": aviso("No encuentro el archivo de audio en la biblioteca."),
    "formato": aviso("SoundCloud no acepta este tipo de archivo de audio."),
    "portada": aviso("La portada no es JPG, PNG o GIF (o pasa de 8 MB): se sube sin carátula."),
    "titulo": aviso("Falta el título."),
    "pistas": aviso("No hay ninguna pista subida para crear el álbum."),
    "trabajo": aviso("No encuentro esa subida (¿se ha reiniciado el gestor?)."),
}
PAGINAS = {
    "ok": {"titulo": "Conectado a SoundCloud", "mensaje": "Ya puedes cerrar esta pestaña y volver al gestor."},
    "cancelado": {"titulo": "Conexión cancelada", "mensaje": "No se ha conectado nada. Puedes cerrar esta pestaña y volver a intentarlo desde el gestor."},
    "caducado": {"titulo": "Enlace no válido", "mensaje": "Este enlace de conexión no es válido o ha caducado. Vuelve a pulsar «Conectar» en el gestor."},
    "fallo": {"titulo": "No se pudo conectar", "mensaje": "SoundCloud no aceptó la autorización. Revisa el Client ID, el Client Secret y la Redirect URI, y vuelve a conectar."},
    "boton": {"label": "Cerrar esta pestaña"},
}


class ScError(Exception):
    def __init__(self, clave, status=0, detalle="", espera=0):
        super().__init__(clave)
        self.clave, self.status, self.detalle, self.espera = clave, status, detalle, espera


# ------------------------------------------------------------------------------------------------ files
def _leer(p, defecto):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def _escribir(p, d):
    p = Path(p)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _cuenta(ctx):
    return _leer(Path(ctx.datos) / "cuenta.json", {})


def _guardar_cuenta(ctx, cu):
    with LOCK:
        _escribir(Path(ctx.datos) / "cuenta.json", cu)


def _subidas(ctx):
    d = _leer(Path(ctx.datos) / "subidas.json", {})
    d.setdefault("songs", {})
    d.setdefault("sets", {})
    return d


def _anotar(ctx, tipo, clave, valor, accion, titulo):
    """Saves the result in subidas.json and appends it to the journal (datos/diario_movimientos.jsonl)."""
    with LOCK:
        d = _subidas(ctx)
        d[tipo][clave] = valor
        _escribir(Path(ctx.datos) / "subidas.json", d)
        jp = Path(ctx.datos).parent.parent / "diario_movimientos.jsonl"
        try:
            nid = sum(1 for _ in open(jp, encoding="utf-8")) + 1 if jp.exists() else 1
            with open(jp, "a", encoding="utf-8") as j:
                j.write(json.dumps({"id": nid, "t": time.strftime("%Y-%m-%d %H:%M:%S"), "op": "soundcloud", "accion": accion,
                                    "song": titulo, "ref": clave, "urn": valor.get("urn", ""), "url": valor.get("url", "")},
                                   ensure_ascii=False) + "\n")
        except OSError:
            pass


def _mascara(s):
    s = str(s or "")
    return "" if not s else "••••••••" + s[-4:] if len(s) > 8 else "••••"


def _limpiar(ctx, texto):
    """Removes any secret that an error body could echo back."""
    texto = str(texto or "")
    cu = _cuenta(ctx)
    for k in ("client_secret", "access_token", "refresh_token"):
        v = cu.get(k)
        if v and len(v) > 3:
            texto = texto.replace(v, "••••")
    return re.sub(r"(?i)((?:access|refresh)_token|client_secret|code_verifier)([\"'=:\s]+)[^\s\"'&,}]+", r"\1\2••••", texto)


# ------------------------------------------------------------------------------------------------ HTTP
def _http(metodo, url, cabeceras=None, cuerpo=None, partes=None, total=None, progreso=None, timeout=60):
    """One HTTP request. `partes` = list of bytes and Paths, streamed from disk (big audio files never go into memory)."""
    u = urlparse(url)
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(u.netloc, timeout=timeout, context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(u.netloc, timeout=timeout)
    try:
        conn.putrequest(metodo, (u.path or "/") + ("?" + u.query if u.query else ""), skip_accept_encoding=True)
        for k, v in (cabeceras or {}).items():
            conn.putheader(k, v)
        if partes is not None:
            conn.putheader("Content-Length", str(total))
        elif cuerpo is not None:
            conn.putheader("Content-Length", str(len(cuerpo)))
        conn.endheaders()
        try:
            if partes is not None:
                enviados = 0
                for p in partes:
                    if isinstance(p, (bytes, bytearray)):
                        conn.send(p)
                        enviados += len(p)
                    else:
                        with open(p, "rb") as f:
                            while True:
                                trozo = f.read(1 << 20)
                                if not trozo:
                                    break
                                conn.send(trozo)
                                enviados += len(trozo)
                                if progreso:
                                    progreso(enviados)
                if progreso:
                    progreso(enviados)
            elif cuerpo is not None:
                conn.send(cuerpo)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the server answered before the end of the body (e.g. 401/413): read that answer
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


def _detalle(b):
    """Short form of an API error body."""
    t = b.decode("utf-8", "replace") if isinstance(b, (bytes, bytearray)) else str(b or "")
    try:
        j = json.loads(t)
        partes = []
        if isinstance(j, dict):
            for e in j.get("errors") or []:
                partes.append(str(e.get("error_message") or e.get("message") or e) if isinstance(e, dict) else str(e))
            for k in ("error_description", "message", "error"):
                if j.get(k) and isinstance(j[k], str):
                    partes.append(j[k])
        t = " · ".join(dict.fromkeys(partes)) or t
    except ValueError:
        t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:200]


def _clave(st):
    return {401: "sesion", 403: "prohibido", 404: "no_encontrado", 413: "grande", 422: "rechazado", 429: "limite"}.get(
        st, "servidor" if st >= 500 else "otro")


def _espera(h):
    try:
        return max(0, int(float(h.get("retry-after") or 0)))
    except ValueError:
        return 0


def _post_token(datos):
    try:
        st, _, b = _http("POST", AUTH + "/oauth/token", {"Accept": "application/json; charset=utf-8",
                                                       "Content-Type": "application/x-www-form-urlencoded"},
                         cuerpo=urlencode(datos).encode("utf-8"), timeout=30)
    except (OSError, http.client.HTTPException) as ex:
        raise ScError("red", 0, type(ex).__name__)
    try:
        j = json.loads(b.decode("utf-8")) if b.strip() else {}
    except ValueError:
        j = {}
    return st, j, b


def _guardar_tokens(ctx, cu, j):
    cu["access_token"] = j["access_token"]
    if j.get("refresh_token"):
        cu["refresh_token"] = j["refresh_token"]   # single use: always keep the newest one
    cu["expira"] = time.time() + int(j.get("expires_in") or 3600)
    cu["scope"] = j.get("scope", "")
    _guardar_cuenta(ctx, cu)
    return cu


def _refrescar(ctx, viejo):
    """Exchanges the refresh token (single use) for new tokens. Serialized: another thread may have done it already."""
    with LOCK:
        cu = _cuenta(ctx)
        if cu.get("access_token") and cu.get("access_token") != viejo and cu.get("expira", 0) > time.time() + 60:
            return cu
        if not cu.get("refresh_token") or not cu.get("client_id"):
            raise ScError("sesion", 401)
        st, j, b = _post_token({"grant_type": "refresh_token", "client_id": cu["client_id"],
                                "client_secret": cu.get("client_secret", ""), "refresh_token": cu["refresh_token"]})
        if st == 200 and j.get("access_token"):
            return _guardar_tokens(ctx, cu, j)
        if st in (400, 401, 403):  # the refresh token is no longer valid: the user has to connect again
            for k in ("access_token", "refresh_token", "expira"):
                cu.pop(k, None)
            _guardar_cuenta(ctx, cu)
            raise ScError("sesion", st, _limpiar(ctx, _detalle(b)))
        raise ScError(_clave(st), st, _limpiar(ctx, _detalle(b)))


def _api(ctx, metodo, ruta, js=None, partes=None, total=None, tipo=None, progreso=None, timeout=60, _r401=True, _r429=True):
    cu = _cuenta(ctx)
    if not cu.get("access_token") and not cu.get("refresh_token"):
        raise ScError("no_conectado")
    if not cu.get("access_token") or cu.get("expira", 0) < time.time() + (600 if partes is not None else 120):
        cu = _refrescar(ctx, cu.get("access_token"))
    cab = {"Authorization": "OAuth " + cu["access_token"], "Accept": "application/json; charset=utf-8"}
    cuerpo = None
    if js is not None:
        cab["Content-Type"] = "application/json; charset=utf-8"
        cuerpo = json.dumps(js, ensure_ascii=False).encode("utf-8")
    elif partes is not None:
        cab["Content-Type"] = tipo
    try:
        st, h, b = _http(metodo, API + ruta, cab, cuerpo=cuerpo, partes=partes, total=total, progreso=progreso, timeout=timeout)
    except (OSError, http.client.HTTPException) as ex:
        raise ScError("red", 0, type(ex).__name__)
    if st == 401 and _r401:
        _refrescar(ctx, cu["access_token"])
        return _api(ctx, metodo, ruta, js, partes, total, tipo, progreso, timeout, False, _r429)
    if st == 429 and _r429 and partes is None and _espera(h) <= 30:   # small requests wait once; uploads report it
        time.sleep(_espera(h) or 5)
        return _api(ctx, metodo, ruta, js, partes, total, tipo, progreso, timeout, _r401, False)
    if st >= 400:
        raise ScError(_clave(st), st, _limpiar(ctx, _detalle(b)), _espera(h))
    try:
        return json.loads(b.decode("utf-8")) if b.strip() else {}
    except ValueError:
        return {}


def _multipart(campos, archivos):
    """campos = [(name, text)], archivos = [(name, Path, filename)] → (parts, total length, content type)."""
    lim = "----GestorSC" + secrets.token_hex(12)
    partes, total = [], 0
    for k, v in campos:
        b = (f'--{lim}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n').encode("utf-8") + str(v).encode("utf-8") + b"\r\n"
        partes.append(b)
        total += len(b)
    for k, p, nombre in archivos:
        nombre = re.sub(r'[^A-Za-z0-9._ -]', "_", nombre) or "archivo"
        ct = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        cab = (f'--{lim}\r\nContent-Disposition: form-data; name="{k}"; filename="{nombre}"\r\nContent-Type: {ct}\r\n\r\n').encode("utf-8")
        partes += [cab, Path(p), b"\r\n"]
        total += len(cab) + Path(p).stat().st_size + 2
    fin = f"--{lim}--\r\n".encode("utf-8")
    partes.append(fin)
    return partes, total + len(fin), "multipart/form-data; boundary=" + lim


# ------------------------------------------------------------------------------------------------ helpers
def _lang(req):
    return idioma_de(req.h)


def _error(req, ex, lang=None):
    lang = lang or _lang(req)
    if isinstance(ex, ScError):
        return req.send({"ok": False, "codigo": ex.clave, "error": traducir(MSG.get(ex.clave, MSG["otro"]), lang),
                         "detalle": ex.detalle, "http": ex.status, "espera": ex.espera})
    raise ex


def _fallo_dict(ex, lang):
    return {"codigo": ex.clave, "error": traducir(MSG.get(ex.clave, MSG["otro"]), lang), "detalle": ex.detalle, "http": ex.status, "espera": ex.espera}


def _puerto(req):
    try:
        return int(req.h.server.server_address[1])
    except Exception:  # noqa: BLE001
        return PUERTO_OFICIAL


def _redirect(puerto):
    return f"http://127.0.0.1:{puerto}{RUTA_CALLBACK}"


def _ruta(ctx, rel, tipos, maximo):
    """A file of the library (relative path), validated: inside the library, an allowed type and size. → (Path, size) or ScError."""
    rel = str(rel or "").replace("\\", "/").strip("/")
    if not rel:
        raise ScError("archivo")
    raiz = Path(ctx.root).resolve()
    p = (raiz / rel).resolve()
    try:
        p.relative_to(raiz)
    except ValueError:
        raise ScError("archivo")
    if not p.is_file():
        raise ScError("archivo")
    if p.suffix.lower() not in tipos:
        raise ScError("formato" if tipos is AUDIO else "portada")
    n = p.stat().st_size
    if n > maximo or n == 0:
        raise ScError("grande" if tipos is AUDIO else "portada")
    return p, n


LADO_PORTADA = 3500


def _portada(ctx, rel):
    """The cover for SoundCloud: the file itself when it is JPG/PNG/GIF, at most 8 MB and at most 3500 px; otherwise a lighter
    JPEG copy (largest side 3500 px, quality lowered until it is under 8 MB) made with Pillow. The original is never touched."""
    p, n = _ruta_img(ctx, rel)
    try:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
            if n <= MAX_IMAGEN and max(w, h) <= LADO_PORTADA:
                return p, n
            import hashlib
            st = p.stat()
            clave = hashlib.md5(f"{p}|{st.st_size}|{st.st_mtime_ns}|{LADO_PORTADA}".encode("utf-8", "ignore")).hexdigest()[:16]
            d = Path(tempfile.gettempdir()) / "gm_sc_portadas"
            d.mkdir(exist_ok=True)
            dst = d / (clave + ".jpg")
            if not dst.exists() or dst.stat().st_size > MAX_IMAGEN:
                im.load()
                x = im.convert("RGB")
                x.thumbnail((LADO_PORTADA, LADO_PORTADA))
                for q in (92, 85, 78, 70, 60):
                    x.save(dst, "JPEG", quality=q, optimize=True)
                    if dst.stat().st_size <= MAX_IMAGEN:
                        break
        if dst.stat().st_size > MAX_IMAGEN or dst.stat().st_size == 0:
            raise ScError("portada")
        return dst, dst.stat().st_size
    except ScError:
        raise
    except Exception:
        if n <= MAX_IMAGEN:
            return p, n        # no Pillow / unreadable by Pillow: the original if SoundCloud accepts its size
        raise ScError("portada")


def _ruta_img(ctx, rel):
    """The library image (any size) → (Path, size); ScError if it is outside the library or not JPG/PNG/GIF."""
    rel = str(rel or "").replace("\\", "/").strip("/")
    raiz = Path(ctx.root).resolve()
    p = (raiz / rel).resolve() if rel else None
    if p is None or not p.is_file():
        raise ScError("archivo")
    try:
        p.relative_to(raiz)
    except ValueError:
        raise ScError("archivo")
    if p.suffix.lower() not in IMAGEN or p.stat().st_size == 0:
        raise ScError("portada")
    return p, p.stat().st_size


def _tag_list(tags, sep):
    out = []
    for t in tags or []:
        t = re.sub(r'["\s]+', " ", str(t)).strip()
        if t and t.lower() not in (x.lower().strip('"') for x in out):
            out.append(f'"{t}"' if (" " in t and sep == " ") else t)
    return sep.join(out[:30])


def _campos(d, prefijo, sep_tags):
    """Optional metadata shared by tracks and sets (only what has a value)."""
    out = []
    lic = d.get("license") if d.get("license") in LICENCIAS else "all-rights-reserved"
    sharing = "public" if d.get("sharing") == "public" else "private"
    out += [(f"{prefijo}[sharing]", sharing), (f"{prefijo}[license]", lic)]
    for k in ("description", "genre", "label_name", "release_date"):
        v = str(d.get(k) or "").strip()
        if k == "release_date" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            v = ""
        if v:
            out.append((f"{prefijo}[{k}]", v[:4000]))
    tl = _tag_list(d.get("tags"), sep_tags)
    if tl:
        out.append((f"{prefijo}[tag_list]", tl))
    return out


def _urn(j, tipo):
    return j.get("urn") or (f"soundcloud:{tipo}:{j['id']}" if j.get("id") is not None else "")


def _ruta_urn(tipo, urn):
    return f"/{tipo}/" + quote(str(urn), safe=":")


# ------------------------------------------------------------------------------------------------ routes: connection
def estado(req, ctx):
    cu = _cuenta(ctx)
    p = _puerto(req)
    conectado = bool(cu.get("access_token") or cu.get("refresh_token"))
    out = {"ok": True, "conectado": conectado, "client_id": cu.get("client_id", ""), "secreto": _mascara(cu.get("client_secret")),
           "tiene_secreto": bool(cu.get("client_secret")), "usuario": cu.get("usuario") or {}, "puerto": p,
           "puerto_ok": p == PUERTO_OFICIAL, "redirect_uri": _redirect(p), "redirect_oficial": _redirect(PUERTO_OFICIAL), "prueba": PRUEBA}
    if conectado and req.arg("me") == "1":
        try:
            me = _api(ctx, "GET", "/me", timeout=20)
            cu = _cuenta(ctx)
            cu["usuario"] = {"username": me.get("username", ""), "permalink_url": me.get("permalink_url", "")}
            _guardar_cuenta(ctx, cu)
            out["usuario"] = cu["usuario"]
            if me.get("upload_seconds_left") is not None:
                out["segundos_libres"] = me.get("upload_seconds_left")
        except ScError as ex:
            out["aviso"] = _fallo_dict(ex, _lang(req))
            out["conectado"] = bool(_cuenta(ctx).get("refresh_token") or _cuenta(ctx).get("access_token"))
    req.send(out)


def credenciales(req, ctx):
    d = req.json()
    cid, sec = str(d.get("client_id") or "").strip(), str(d.get("client_secret") or "").strip()
    cu = _cuenta(ctx)
    if not sec and cid == cu.get("client_id"):
        sec = cu.get("client_secret", "")
    if not cid or not sec:
        return _error(req, ScError("credenciales"))
    if cid != cu.get("client_id") or sec != cu.get("client_secret"):   # another app: the old tokens belong to the old one
        cu = {"client_id": cid, "client_secret": sec}
    _guardar_cuenta(ctx, cu)
    req.send({"ok": True, "client_id": cid, "secreto": _mascara(sec)})


def borrar_credenciales(req, ctx):
    _desconectar(ctx)
    try:
        (Path(ctx.datos) / "cuenta.json").unlink()
    except OSError:
        pass
    req.send({"ok": True})


def conectar(req, ctx):
    cu = _cuenta(ctx)
    if not cu.get("client_id") or not cu.get("client_secret"):
        return _error(req, ScError("credenciales"))
    verifier = secrets.token_urlsafe(64)[:96]
    reto = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    st = secrets.token_urlsafe(24)
    ahora = time.time()
    with LOCK:
        for k in [k for k, v in PEND.items() if ahora - v["t"] > 900]:
            PEND.pop(k, None)
        PEND[st] = {"verifier": verifier, "redirect": _redirect(_puerto(req)), "lang": _lang(req), "t": ahora, "client_id": cu["client_id"]}
    url = AUTH + "/authorize?" + urlencode({"client_id": cu["client_id"], "redirect_uri": _redirect(_puerto(req)), "response_type": "code",
                                           "code_challenge": reto, "code_challenge_method": "S256", "state": st})
    req.send({"ok": True, "url": url})


def _pagina(req, clave, lang, code=200):
    p = PAGINAS[clave]
    t = lambda s: html.escape(traducir(s, lang))  # noqa: E731
    ok = clave == "ok"
    b = f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t(p['titulo'])}</title><style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#111318;color:#eef;display:grid;place-items:center;min-height:100vh;margin:0}}
.c{{background:#1c1f27;border-radius:18px;padding:32px 36px;max-width:440px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.4)}}
.i{{font-size:44px}}h1{{font-size:22px;margin:10px 0}}p{{color:#aab;line-height:1.5}}button{{margin-top:12px;border:0;border-radius:999px;padding:10px 18px;font:inherit;background:#ff5500;color:#fff;cursor:pointer}}</style></head>
<body><div class="c"><div class="i">{'✅' if ok else '⚠️'}</div><h1>{t(p['titulo'])}</h1><p>{t(p['mensaje'])}</p>
<button onclick="window.close()">{t(PAGINAS['boton']['label'])}</button></div></body></html>""".encode("utf-8")
    req.h.send_response(code)
    req.h.send_header("Content-Type", "text/html; charset=utf-8")
    req.h.send_header("Content-Length", str(len(b)))
    req.h.send_header("Cache-Control", "no-store")
    req.h.send_header("Referrer-Policy", "no-referrer")
    req.h.end_headers()
    req.h.wfile.write(b)


def callback(req, ctx):
    """OAuth redirect: /soundcloud/callback?code=…&state=…  (public route: the single-use `state` is the check)."""
    st = req.arg("state")
    with LOCK:
        p = PEND.pop(st, None) if st else None
    if not p or time.time() - p["t"] > 900:
        return _pagina(req, "caducado", (p or {}).get("lang") or "es", 400)
    lang = p["lang"]
    if req.arg("error") or not req.arg("code"):
        return _pagina(req, "cancelado", lang)
    cu = _cuenta(ctx)
    if cu.get("client_id") != p["client_id"] or not cu.get("client_secret"):
        return _pagina(req, "fallo", lang, 400)
    try:
        code, j, _ = _post_token({"grant_type": "authorization_code", "client_id": cu["client_id"], "client_secret": cu["client_secret"],
                                  "redirect_uri": p["redirect"], "code_verifier": p["verifier"], "code": req.arg("code")})
    except ScError:
        return _pagina(req, "fallo", lang, 502)
    if code != 200 or not j.get("access_token"):
        cu["ultimo_error"] = "token"
        _guardar_cuenta(ctx, cu)
        return _pagina(req, "fallo", lang, 400)
    cu.pop("ultimo_error", None)
    cu = _guardar_tokens(ctx, cu, j)
    try:
        me = _api(ctx, "GET", "/me", timeout=20)
        cu = _cuenta(ctx)
        cu["usuario"] = {"username": me.get("username", ""), "permalink_url": me.get("permalink_url", "")}
        _guardar_cuenta(ctx, cu)
    except ScError:
        pass
    _pagina(req, "ok", lang)


def _desconectar(ctx):
    cu = _cuenta(ctx)
    if cu.get("access_token"):
        try:
            _http("POST", API + "/disconnect", {"Authorization": "OAuth " + cu["access_token"], "Accept": "application/json; charset=utf-8"},
                  cuerpo=b"", timeout=10)
        except (OSError, http.client.HTTPException):
            pass
    for k in ("access_token", "refresh_token", "expira", "scope", "usuario"):
        cu.pop(k, None)
    if cu:
        _guardar_cuenta(ctx, cu)


def desconectar(req, ctx):
    _desconectar(ctx)
    req.send({"ok": True})


# ------------------------------------------------------------------------------------------------ routes: upload
def preparar(req, ctx):
    d = req.json()
    lang = _lang(req)
    sub = _subidas(ctx)
    out = []
    for it in d.get("items") or []:
        r = {"id": it.get("id"), "p": it.get("p"), "subida": sub["songs"].get(str(it.get("id"))) or None}
        try:
            p, n = _ruta(ctx, it.get("p"), AUDIO, MAX_AUDIO)
            r.update(ok=True, bytes=n, nombre=p.name)
        except ScError as ex:
            r.update(ok=False, **_fallo_dict(ex, lang))
        out.append(r)
    portada = None
    if d.get("portada"):
        try:
            p, n = _portada(ctx, d["portada"])
            portada = {"ok": True, "bytes": n, "nombre": p.name}
        except ScError:
            portada = {"ok": False, "error": traducir(MSG["portada"], lang)}
    req.send({"ok": True, "items": out, "portada": portada, "set": sub["sets"].get(str(d.get("key") or "")) or None})


def _trabajo_subir(ctx, job, d, lang):
    J = JOBS[job]
    tmpd = None
    try:
        p, n = _ruta(ctx, d.get("p"), AUDIO, MAX_AUDIO)
        # what goes up is a CLEAN copy (no tags: title, comments, Suno data, cover…); the original stays as it is
        import limpiar_tags
        tmpd = tempfile.mkdtemp(prefix="gm_limpio_")
        try:
            limpio = limpiar_tags.limpiar_copia(p, Path(tmpd) / p.name, ctx.ffmpeg() if callable(getattr(ctx, "ffmpeg", None)) else None)
        except (ValueError, OSError):
            raise ScError("archivo")
        titulo = str(d.get("titulo") or "").strip()[:250]
        campos = [("track[title]", titulo)] + _campos(d, "track", " ")
        if str(d.get("isrc") or "").strip():
            campos.append(("track[isrc]", re.sub(r"[^A-Za-z0-9]", "", str(d["isrc"])).upper()[:12]))
        archivos = [("track[asset_data]", limpio, p.name)]
        img = None
        if d.get("portada"):
            try:
                img, _ = _portada(ctx, d["portada"])
            except ScError:
                J["sin_caratula"] = True
        intento_img = img is not None
        while True:
            partes, total, tipo = _multipart(campos, archivos + ([("track[artwork_data]", img, img.name)] if intento_img else []))
            J.update(total=total, enviados=0)
            try:
                j = _api(ctx, "POST", "/tracks", partes=partes, total=total, tipo=tipo,
                         progreso=lambda x: J.__setitem__("enviados", x), timeout=600)
                break
            except ScError as ex:
                if intento_img and ex.status in (400, 403, 413, 415, 422):   # artwork is PRO only: try again without it
                    intento_img = False
                    J["sin_caratula"] = True
                    continue
                raise
        urn = _urn(j, "tracks")
        val = {"urn": urn, "url": j.get("permalink_url", ""), "titulo": titulo, "archivo": p.name, "bytes": n,
               "sharing": j.get("sharing") or ("public" if d.get("sharing") == "public" else "private"), "t": time.strftime("%Y-%m-%d %H:%M")}
        _anotar(ctx, "songs", str(d.get("id")), val, "subir", titulo)
        J.update(estado="hecho", resultado=val, enviados=J.get("total", 0))
    except ScError as ex:
        J.update(estado="error", **_fallo_dict(ex, lang))
    except Exception as ex:  # noqa: BLE001
        J.update(estado="error", codigo="otro", error=traducir(MSG["otro"], lang), detalle=type(ex).__name__)
    finally:
        if tmpd:
            shutil.rmtree(tmpd, ignore_errors=True)


def subir(req, ctx):
    d = req.json()
    lang = _lang(req)
    if not str(d.get("titulo") or "").strip():
        return _error(req, ScError("titulo"))
    cu = _cuenta(ctx)
    if not cu.get("access_token") and not cu.get("refresh_token"):
        return _error(req, ScError("no_conectado"))
    try:
        _ruta(ctx, d.get("p"), AUDIO, MAX_AUDIO)
    except ScError as ex:
        return _error(req, ex)
    job = secrets.token_hex(8)
    with LOCK:
        for k in [k for k, v in JOBS.items() if time.time() - v["t"] > 6 * 3600]:
            JOBS.pop(k, None)
        JOBS[job] = {"estado": "subiendo", "enviados": 0, "total": 0, "t": time.time(), "id": d.get("id")}
    threading.Thread(target=_trabajo_subir, args=(ctx, job, d, lang), daemon=True).start()
    req.send({"ok": True, "job": job})


def progreso(req, ctx):
    J = JOBS.get(req.arg("job"))
    if not J:
        return _error(req, ScError("trabajo"))
    req.send({"ok": True, **{k: v for k, v in J.items() if k != "t"}})


def actualizar(req, ctx):
    """Updates the metadata of an already uploaded track (the audio cannot be replaced)."""
    d = req.json()
    urn = str(d.get("urn") or "")
    titulo = str(d.get("titulo") or "").strip()[:250]
    if not urn or not titulo:
        return _error(req, ScError("titulo"))
    t = {"title": titulo}
    for k, v in _campos(d, "x", " "):
        t[k[2:-1]] = v
    if str(d.get("isrc") or "").strip():
        t["isrc"] = re.sub(r"[^A-Za-z0-9]", "", str(d["isrc"])).upper()[:12]
    try:
        j = _api(ctx, "PUT", _ruta_urn("tracks", urn), js={"track": t})
    except ScError as ex:
        return _error(req, ex)
    prev = _subidas(ctx)["songs"].get(str(d.get("id"))) or {}
    val = {**prev, "urn": _urn(j, "tracks") or urn, "url": j.get("permalink_url") or prev.get("url", ""), "titulo": titulo,
           "sharing": j.get("sharing") or t["sharing"], "t": time.strftime("%Y-%m-%d %H:%M")}
    _anotar(ctx, "songs", str(d.get("id")), val, "actualizar", titulo)
    req.send({"ok": True, "resultado": val})


def _pistas_de(j):
    return [_urn(t, "tracks") for t in (j.get("tracks") or []) if isinstance(t, dict)]


def crear_set(req, ctx):
    d = req.json()
    lang = _lang(req)
    titulo = str(d.get("titulo") or "").strip()[:250]
    urns = [str(u) for u in d.get("urns") or [] if u]
    if not titulo:
        return _error(req, ScError("titulo"))
    if not urns:
        return _error(req, ScError("pistas"))
    set_type = "playlist" if d.get("set_type") == "playlist" else "album"
    campos = _campos(d, "playlist", ",")
    pl = {"title": titulo, "set_type": set_type, "tracks": [{"urn": u} for u in urns]}
    for k, v in campos:
        pl[k[9:-1]] = v
    sin_caratula = False
    try:
        if d.get("actualizar"):
            urn = str(d["actualizar"])
            j = _api(ctx, "PUT", _ruta_urn("playlists", urn), js={"playlist": pl})
            accion = "set_actualizar"
        else:
            img = None
            if d.get("portada"):
                try:
                    img, _ = _portada(ctx, d["portada"])
                except ScError:
                    sin_caratula = True
            j = None
            if img is not None:
                c = [("playlist[title]", titulo), ("playlist[set_type]", set_type)] + campos + [("playlist[tracks][][urn]", u) for u in urns]
                partes, total, tipo = _multipart(c, [("playlist[artwork_data]", img, img.name)])
                try:
                    j = _api(ctx, "POST", "/playlists", partes=partes, total=total, tipo=tipo, timeout=120)
                except ScError as ex:
                    if ex.status not in (400, 403, 413, 415, 422):
                        raise
                    sin_caratula = True   # artwork may need PRO: create it without
            if j is None:
                j = _api(ctx, "POST", "/playlists", js={"playlist": pl})
            urn = _urn(j, "playlists")
            accion = "set"
        # SoundCloud does not document that the order is kept: read it back and fix it if needed
        orden = "no_verificado"
        try:
            g = _api(ctx, "GET", _ruta_urn("playlists", urn) + "?show_tracks=true")
            if _pistas_de(g) == urns:
                orden = "ok"
            else:
                _api(ctx, "PUT", _ruta_urn("playlists", urn), js={"playlist": {"tracks": [{"urn": u} for u in urns]}})
                g = _api(ctx, "GET", _ruta_urn("playlists", urn) + "?show_tracks=true")
                orden = "corregido" if _pistas_de(g) == urns else "distinto"
            j = {**j, "permalink_url": g.get("permalink_url") or j.get("permalink_url")}
        except ScError:
            pass
    except ScError as ex:
        return _error(req, ex, lang)
    val = {"urn": urn, "url": j.get("permalink_url", ""), "titulo": titulo, "pistas": urns, "set_type": set_type,
           "sharing": pl.get("sharing", "private"), "t": time.strftime("%Y-%m-%d %H:%M")}
    _anotar(ctx, "sets", str(d.get("key") or urn), val, accion, titulo)
    req.send({"ok": True, "resultado": val, "orden": orden, "sin_caratula": sin_caratula})


def subidas(req, ctx):
    req.send({"ok": True, **_subidas(ctx)})


# ------------------------------------------------------------------------------------------------ routes: numbers (plays, likes…)
def _cifra(j, *claves):
    for k in claves:
        v = j.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return None


def _numeros_de(j):
    """Counters of a track as returned by GET /tracks/{urn}. SoundCloud's field names have changed over time: missing → left out."""
    out = {"plays": _cifra(j, "playback_count", "plays_count"), "likes": _cifra(j, "likes_count", "favoritings_count"),
           "comments": _cifra(j, "comment_count", "comments_count"), "reposts": _cifra(j, "reposts_count", "repost_count")}
    return {k: v for k, v in out.items() if v is not None}


def _guardar_numeros(ctx, sid, urn, fila):
    """numeros.json = {songId: {urn, hist:[{f, plays, likes, comments, reposts}]}}; at most one row per day per song."""
    with LOCK:
        p = Path(ctx.datos) / "numeros.json"
        d = _leer(p, {})
        x = d.setdefault(sid, {"urn": urn, "hist": []})
        x["urn"] = urn
        x["hist"] = [h for h in x.get("hist", []) if h.get("f") != fila["f"]] + [fila]
        x["hist"].sort(key=lambda h: h.get("f", ""))
        _escribir(p, d)


def _trabajo_numeros(ctx, job, items, lang):
    J = JOBS[job]
    for it in items:
        sid, urn = str(it["id"]), str(it["urn"])
        for intento in range(2):
            try:
                j = _api(ctx, "GET", _ruta_urn("tracks", urn), timeout=30, _r429=False)
                fila = {"f": time.strftime("%Y-%m-%d"), **_numeros_de(j)}
                _guardar_numeros(ctx, sid, urn, fila)
                J["resultados"][sid] = {"urn": urn, **fila}
                break
            except ScError as ex:
                if ex.status == 429 and intento == 0 and (ex.espera or 0) <= 60:   # respect Retry-After once, then stop
                    J["esperando"] = ex.espera or 5
                    time.sleep(ex.espera or 5)
                    J.pop("esperando", None)
                    continue
                if ex.status == 429 or ex.clave in ("no_conectado", "sesion", "red"):
                    J.update(estado="error", **_fallo_dict(ex, lang))
                    return
                J["errores"].append({"id": sid, **_fallo_dict(ex, lang)})
                break
        J["hechos"] += 1
    J["estado"] = "hecho"


def numeros(req, ctx):
    """POST {items:[{id, urn}], si_no_hoy?} → {job} (GET progreso?job=…): reads the counters of each track, one after another.
    si_no_hoy: skip the songs already read today (used when a song page opens)."""
    d = req.json()
    lang = _lang(req)
    cu = _cuenta(ctx)
    if not cu.get("access_token") and not cu.get("refresh_token"):
        return _error(req, ScError("no_conectado"))
    hoy = time.strftime("%Y-%m-%d")
    hechos = _leer(Path(ctx.datos) / "numeros.json", {})
    items, vistos = [], set()
    for it in d.get("items") or []:
        sid, urn = str(it.get("id") or ""), str(it.get("urn") or "")
        if not sid or not urn.startswith("soundcloud:tracks:") or sid in vistos:
            continue
        vistos.add(sid)
        if d.get("si_no_hoy") and any(h.get("f") == hoy for h in (hechos.get(sid) or {}).get("hist", [])):
            continue
        items.append({"id": sid, "urn": urn})
    if not items:
        return req.send({"ok": True, "nada": True})
    job = secrets.token_hex(8)
    with LOCK:
        JOBS[job] = {"estado": "leyendo", "hechos": 0, "total": len(items), "resultados": {}, "errores": [], "t": time.time()}
    threading.Thread(target=_trabajo_numeros, args=(ctx, job, items, lang), daemon=True).start()
    req.send({"ok": True, "job": job})


def isrcs(req, ctx):
    """GET: reads (read-only) the ISRC that SoundCloud holds for each track uploaded from here → {isrcs:{songId:{isrc, titulo, fuente}}}.
    Changes nothing, neither on SoundCloud nor here: assigning them is up to the user."""
    out, errores = {}, []
    for sid, s in list(_subidas(ctx)["songs"].items()):
        urn = str(s.get("urn") or "")
        if not urn.startswith("soundcloud:tracks:"):
            continue
        try:
            j = _api(ctx, "GET", _ruta_urn("tracks", urn))
        except ScError as ex:
            errores.append({"id": sid, "error": str(ex)})
            continue
        pm = j.get("publisher_metadata") if isinstance(j.get("publisher_metadata"), dict) else {}
        for fuente, v in (("isrc", j.get("isrc")), ("publisher_metadata.isrc", pm.get("isrc"))):
            if str(v or "").strip():
                out[sid] = {"isrc": re.sub(r"[^A-Za-z0-9]", "", str(v)).upper(), "titulo": s.get("titulo", ""), "fuente": fuente}
                break
        else:
            out[sid] = {"isrc": "", "titulo": s.get("titulo", ""), "fuente": "", "claves": sorted(j.keys())[:60]}
    req.send({"ok": True, "isrcs": out, "errores": errores})


def catalogo(req, ctx):
    """GET: reads (read-only) EVERY track of the connected account, with the ISRC SoundCloud holds → {pistas:[{urn,titulo,isrc,url,sharing}]}."""
    pistas, ruta, n = [], "/me/tracks?limit=200&linked_partitioning=true", 0
    try:
        while ruta and n < 20:
            j = _api(ctx, "GET", ruta)
            n += 1
            lista = j.get("collection") if isinstance(j, dict) else j
            for t in lista or []:
                if not isinstance(t, dict):
                    continue
                pm = t.get("publisher_metadata") if isinstance(t.get("publisher_metadata"), dict) else {}
                isrc = re.sub(r"[^A-Za-z0-9]", "", str(t.get("isrc") or pm.get("isrc") or "")).upper()
                pistas.append({"urn": _urn(t, "tracks"), "titulo": t.get("title", ""), "isrc": isrc,
                               "url": t.get("permalink_url", ""), "sharing": t.get("sharing", ""),
                               "reproducciones": t.get("playback_count"), "likes": t.get("favoritings_count"), "comentarios": t.get("comment_count"),
                               "reposts": t.get("reposts_count"), "duracion": t.get("duration"), "genero": t.get("genre"), "etiquetas": t.get("tag_list"),
                               "fecha": t.get("created_at"), "licencia": t.get("license"), "lanzamiento": t.get("release_date") or t.get("release")})
            nxt = j.get("next_href") if isinstance(j, dict) else None
            ruta = nxt[len(API):] if nxt and nxt.startswith(API) else None
    except ScError as ex:
        return _error(req, ex)
    req.send({"ok": True, "pistas": pistas})


def disponible(req, ctx):
    """POST {isrcs:[…]} → {res:{isrc:{ok, titulo, artista, url}}}. Asks Deezer's public catalogue (no account, no keys) whether each ISRC is
    on sale there. Only the ISRCs leave this computer (they are public catalogue identifiers). Read-only."""
    d = req.json()
    isrcs = [re.sub(r"[^A-Za-z0-9]", "", str(i)).upper() for i in (d.get("isrcs") or [])][:40]
    res = {}
    for i in isrcs:
        if len(i) != 12 or i in res:
            continue
        try:
            c = http.client.HTTPSConnection("api.deezer.com", timeout=12, context=ssl.create_default_context())
            c.request("GET", "/track/isrc:" + i, headers={"Accept": "application/json", "User-Agent": "MusicManager"})
            r = c.getresponse()
            j = json.loads(r.read().decode("utf-8") or "{}")
            c.close()
        except (OSError, http.client.HTTPException, ValueError):
            res[i] = {"ok": None, "error": "red"}
            continue
        if isinstance(j, dict) and j.get("id") and not j.get("error"):
            res[i] = {"ok": True, "titulo": j.get("title", ""), "artista": (j.get("artist") or {}).get("name", ""), "url": j.get("link", ""), "segundos": j.get("duration")}
        else:
            res[i] = {"ok": None if (j.get("error") or {}).get("code") == 4 else False}   # 4 = quota: we do not know
        time.sleep(0.15)
    req.send({"ok": True, "res": res})


def numeros_guardados(req, ctx):
    req.send({"ok": True, "numeros": _leer(Path(ctx.datos) / "numeros.json", {})})


def claves(req, ctx):
    """POST {pares:[[old, new]…]}: album folders that moved (a project published as an album) keep their uploaded set."""
    d = req.json()
    with LOCK:
        s = _subidas(ctx)
        cambio = False
        for par in d.get("pares") or []:
            if isinstance(par, list) and len(par) == 2 and str(par[0]) in s["sets"] and str(par[1]) not in s["sets"]:
                s["sets"][str(par[1])] = s["sets"].pop(str(par[0]))
                cambio = True
        if cambio:
            _escribir(Path(ctx.datos) / "subidas.json", s)
    req.send({"ok": True})


ROUTES = {
    "GET estado": estado,
    "POST credenciales": credenciales,
    "POST borrar_credenciales": borrar_credenciales,
    "POST conectar": conectar,
    "POST desconectar": desconectar,
    "POST preparar": preparar,
    "POST subir": subir,
    "GET progreso": progreso,
    "POST actualizar": actualizar,
    "POST crear_set": crear_set,
    "GET subidas": subidas,
    "POST numeros": numeros,
    "GET numeros": numeros_guardados,
    "GET isrcs": isrcs,
    "GET catalogo": catalogo,
    "POST disponible": disponible,
    "POST claves": claves,
}
PUBLIC_ROUTES = {"GET callback": callback}
