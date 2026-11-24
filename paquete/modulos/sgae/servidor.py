"""«sgae» module server (PERSONAL: modulo.json says "distribuir": false, so it is never in the public package).

What it does: opens a separate Chrome/Edge window (its own profile, OUTSIDE any synced folder) at the SGAE electronic office. The person logs
in there themself: SGAE e-mails a one-time code and the person types it; this module never sees the password or the code and never reads the mailbox.
Through the browser's debugging port (Chrome DevTools Protocol, spoken here with a tiny standard-library WebSocket client) the module can RECORD the
network requests that the SGAE web makes (to learn how its forms talk to the server). Nothing is sent anywhere else.

Recording rules: only requests to the SGAE hosts; analytics are ignored; the bodies of login/authentication requests are never stored;
values of keys that look like secrets (password, token, code…) are replaced; Authorization/Cookie header VALUES are never stored (only their names).
The log lives in %LOCALAPPDATA%/MusicManager/sgae/ (not in the Dropbox library).

Routes (/api/mod/sgae/…):
  GET  estado        {ok, chrome, abierto, conectado, url, grabando, n}
  POST abrir         opens the SGAE window (or reuses it)
  POST grabar        {on: bool, limpiar?: bool}
  GET  captura       the recorded requests (bodies shortened)
  POST guardar       writes the recording to a JSON file and returns its path
  POST cerrar        closes the window
Tests: GESTOR_SGAE_HOSTS (default «sgae.es»), GESTOR_SGAE_URL, GESTOR_SGAE_CDP (port), GESTOR_SGAE_HEADLESS=1.
"""
import base64
import http.client
import json
import os
import re
import shutil
import socket
import ssl
import unicodedata
from datetime import datetime, timezone
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

PORT = int(os.environ.get("GESTOR_SGAE_CDP") or 9223)
HOSTS = [h.strip() for h in (os.environ.get("GESTOR_SGAE_HOSTS") or "sgae.es").split(",") if h.strip()]
START_URL = os.environ.get("GESTOR_SGAE_URL") or "https://sede.sgae.es/auth/login"
HEADLESS = bool(os.environ.get("GESTOR_SGAE_HEADLESS"))
IGNORAR = ("google-analytics", "googletagmanager", "doubleclick", "gstatic.com", "fonts.g", "facebook", "hotjar", "clarity.ms")
API_OBRAS = (os.environ.get("GESTOR_SGAE_API_OBRAS") or "https://sedeelect-proxy-sede.sgae.es").rstrip("/")
API_REGISTRO = (os.environ.get("GESTOR_SGAE_API_REGISTRO") or "https://registroobras-proxy-sede.sgae.es").rstrip("/")
AUTH_URL = re.compile(r"login|auth|token|otp|verif|codigo|code|password|clave|sso|oauth", re.I)
SECRETO = re.compile(r'("(?:[^"]*(?:pass|contras|secret|token|code|codigo|otp|clave|pin|phone|telef|mail|dni|nif|ident)[^"]*)"\s*:\s*)("(?:[^"\\]|\\.)*"|[^,}\]\s]+)', re.I)
MAX_CAP = 600
LOCK = threading.RLock()


def _base():
    b = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    p = Path(b) / "MusicManager" / "sgae"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _chrome():
    c = [os.environ.get("GESTOR_SGAE_CHROME") or ""]
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        b = os.environ.get(var)
        if b:
            c += [f"{b}/Google/Chrome/Application/chrome.exe", f"{b}/Microsoft/Edge/Application/msedge.exe"]
    c += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        w = shutil.which(n)
        if w:
            c.append(w)
    return next((x for x in c if x and Path(x).exists()), None)


# ---------- minimal WebSocket client (RFC 6455, text frames) ----------
class WS:
    def __init__(self, url):
        u = urlparse(url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            ch = self.s.recv(4096)
            if not ch:
                raise OSError("sin respuesta del navegador")
            buf += ch
        head, _, rest = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise OSError("el navegador no aceptó la conexión de depuración")
        self.buf = rest
        self.s.settimeout(None)
        self.lock = threading.Lock()

    def send(self, text):
        data = text.encode("utf-8")
        n = len(data)
        mask = os.urandom(4)
        h = bytearray([0x81])
        if n < 126:
            h.append(0x80 | n)
        elif n < 65536:
            h += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            h += bytes([0x80 | 127]) + struct.pack(">Q", n)
        h += mask
        with self.lock:
            self.s.sendall(bytes(h) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            ch = self.s.recv(65536)
            if not ch:
                raise EOFError
            self.buf += ch
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n)
            if op == 8:
                return None
            if op in (0, 1, 2):
                msg += data
                if b1 & 0x80:
                    return msg.decode("utf-8", "replace")

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Estado:
    proc = None
    ws = None
    hilo = None
    grabando = False
    cap = []
    pend = {}
    nid = 0
    esperas = {}
    objetivo = None
    plantilla = None   # the person's own last registration (without title/files), learned from the SGAE web; kept in memory and in the local data folder
    sesion = None      # {auth, email}: kept ONLY in memory, never written to disk, never sent back to the UI
    miembro = None


E = Estado()


def _http(path, metodo="GET"):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
    try:
        c.request(metodo, path)
        r = c.getresponse()
        return json.loads(r.read().decode("utf-8") or "null")
    finally:
        c.close()


def _paginas():
    try:
        return [t for t in (_http("/json") or []) if t.get("type") == "page"]
    except (OSError, ValueError, http.client.HTTPException):
        return []


def _host_ok(url):
    h = (urlparse(url).hostname or "")
    return any(h == x or h.endswith("." + x) for x in HOSTS) and not any(i in url for i in IGNORAR)


def _limpiar(texto):
    return SECRETO.sub(lambda m: m.group(1) + '"<omitido>"', texto or "")


QUERY_SECRETA = re.compile(r"((?:^|[?&])[^=&]*(?:pin|code|codigo|token|pass|mail|email|otp|clave)[^=&]*=)[^&#]*", re.I)


def _url_limpia(url):
    """Query values that are codes or e-mail addresses (e.g. ?PIN=…, ?usermail=…) are never kept."""
    return QUERY_SECRETA.sub(lambda m: m.group(1) + "<omitido>", url or "")


def _cmd(metodo, params=None, espera=5):
    with LOCK:
        E.nid += 1
        i = E.nid
        ev = threading.Event()
        E.esperas[i] = [ev, None]
    E.ws.send(json.dumps({"id": i, "method": metodo, "params": params or {}}))
    ev.wait(espera)
    return (E.esperas.pop(i, [None, None])[1]) or {}


CRLF = chr(13) + chr(10)


def _corta(o):
    """JSON with every long string (e.g. a file encoded in base64) replaced by its first characters and its length."""
    if isinstance(o, str):
        return f"{o[:14]}…<{len(o)} caracteres>" if len(o) > 150 else o
    if isinstance(o, list):
        return [_corta(x) for x in o]
    if isinstance(o, dict):
        return {k: _corta(v) for k, v in o.items()}
    return o


def _estructura(txt):
    """Shape of a request body: JSON/text as it is (secrets replaced); multipart → the headers of each part, the files only as «N bytes»."""
    if "Content-Disposition" not in txt:
        try:
            return _limpiar(json.dumps(_corta(json.loads(txt)), ensure_ascii=False))[:8000]
        except ValueError:
            return _limpiar(txt)[:4000]
    b = txt.split(CRLF, 1)[0]
    out = []
    for parte in txt.split(b)[1:]:
        if parte.startswith("--"):
            break
        cab, _, cuerpo = parte.partition(CRLF + CRLF)
        cab = cab.replace(CRLF, " | ").strip(" |")
        out.append(f"{cab} | ({len(cuerpo)} bytes)" if "filename=" in cab else f"{cab} => {_limpiar(cuerpo.strip())[:3000]}")
    return CRLF.join(out)


def _post(rid, ent):
    r = _cmd("Network.getRequestPostData", {"requestId": rid}, 10).get("result", {})
    if r.get("postData") is not None:
        ent["cuerpo"] = _estructura(r["postData"])


def _ruta_plantilla():
    return _base() / "plantilla_alta.json"


def _aprender(rid, texto=None):
    """Keeps the person's data from a registration they just made (genre, author sheet, contact…); the file contents and the title are NOT kept."""
    try:
        if not texto:
            texto = _cmd("Network.getRequestPostData", {"requestId": rid}, 12).get("result", {}).get("postData")
        o = json.loads(texto or "")
    except (ValueError, TypeError):
        return
    if not isinstance(o, dict) or "creator" not in o:
        return
    tipos = {}
    for f in o.get("caseFiles") or []:
        ext = str(f.get("name", "")).rsplit(".", 1)[-1].lower()
        tipos["letra" if ext == "txt" else "audio"] = f.get("fileTypeId")
    for k in ("title", "dFechaAlta", "declarationDate", "workDuration", "caseFiles"):
        o.pop(k, None)
    E.plantilla = {"cuerpo": o, "tipos": tipos}
    _ruta_plantilla().write_text(json.dumps(E.plantilla, ensure_ascii=False, indent=1), encoding="utf-8")


def _plantilla():
    if not E.plantilla:
        try:
            E.plantilla = json.loads(_ruta_plantilla().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return E.plantilla


def _evento(m):
    p = m.get("params", {})
    met = m.get("method")
    if met == "Network.requestWillBeSent":
        r0 = p.get("request", {})
        u0 = r0.get("url", "")
        if _host_ok(u0):
            h0 = {k.lower(): v for k, v in (r0.get("headers") or {}).items()}
            if h0.get("enlinea-auth"):
                E.sesion = {"auth": h0["enlinea-auth"], "email": h0.get("enlinea-auth-email", ""), "t": time.time()}
            mm = re.search(r"[?&]memberCode=(\d+)", u0)
            if mm:
                E.miembro = mm.group(1)
    if met == "Network.requestWillBeSent":
        r1 = p.get("request", {})
        if r1.get("method") == "POST" and (urlparse(r1.get("url", "")).path or "").endswith("/user/cases/rgo") and _host_ok(r1.get("url", "")):
            threading.Thread(target=_aprender, args=(p.get("requestId"), r1.get("postData")), daemon=True).start()
    if not E.grabando:
        return
    if met == "Runtime.consoleAPICalled":
        a = ((p.get("args") or [{}])[0]).get("value")
        if isinstance(a, str) and a.startswith("__sgae__"):
            try:
                d = json.loads(a[8:])
            except ValueError:
                return
            for x in d.get("d") or []:
                if "valor" in x:
                    x["valor"] = _limpiar(x["valor"])[:3000]
            with LOCK:
                E.cap.append({"t": time.strftime("%H:%M:%S"), "metodo": d.get("m"), "url": _url_limpia(d.get("u")), "tipo": "formdata", "cabeceras": [],
                              "cuerpo": None, "formdata": d.get("d"), "estado": None, "auth": False})
        return
    if met == "Network.requestWillBeSent":
        r = p.get("request", {})
        url = r.get("url", "")
        externo = False
        if url.startswith(("data:", "blob:", "chrome")):
            return
        if not _host_ok(url):
            if r.get("method") == "GET" or any(i in url for i in IGNORAR):
                return
            externo = True        # e.g. a file-storage service the SGAE web uploads to: keep host and path, never the signed query
            url = url.split("?")[0] + "?<omitido>" if "?" in url else url
        auth = AUTH_URL.search(urlparse(url).path or "") is not None
        h = r.get("headers", {})
        body = r.get("postData")
        if body is None and r.get("postDataEntries"):
            try:
                raw = base64.b64decode(r["postDataEntries"][0].get("bytes") or "")
                ctl = chr(13) + chr(10) + chr(9)
                body = "".join(ch if (ch.isprintable() or ch in ctl) else "·" for ch in raw[:3000].decode("utf-8", "replace"))
            except (ValueError, KeyError, TypeError):
                body = None
        e = {"t": time.strftime("%H:%M:%S"), "metodo": r.get("method"), "url": _url_limpia(url), "externo": externo, "tipo": p.get("type"),
             "cabeceras": sorted(h.keys()), "aut": (h.get("Authorization") or h.get("authorization") or "").split(" ")[0] or None,
             "cuerpo": "<omitido: autenticación>" if (auth and body) else (_limpiar(body)[:4000] if body else None),
             "tiene_cuerpo": bool(r.get("hasPostData") or body), "estado": None, "auth": auth}
        with LOCK:
            E.pend[p.get("requestId")] = e
            E.cap.append(e)
            del E.cap[:-2000]
        if e["tiene_cuerpo"] and not e["cuerpo"] and not auth:
            threading.Thread(target=_post, args=(p.get("requestId"), e), daemon=True).start()
    elif met == "Network.responseReceived":
        e = E.pend.get(p.get("requestId"))
        if e:
            rs = p.get("response", {})
            e["estado"] = rs.get("status")
            e["mime"] = rs.get("mimeType")
    elif met == "Network.loadingFinished":
        e = E.pend.get(p.get("requestId"))
        if e and not e["auth"] and "json" in (e.get("mime") or "") and (p.get("encodedDataLength") or 0) < 200000:
            def _cuerpo(rid=p.get("requestId"), ent=e):
                r = _cmd("Network.getResponseBody", {"requestId": rid}, 4).get("result", {})
                if r.get("body") and not r.get("base64Encoded"):
                    ent["respuesta"] = _limpiar(r["body"])[:3000]
            threading.Thread(target=_cuerpo, daemon=True).start()


def _leer():
    ws = E.ws
    while True:
        try:
            t = ws.recv()
        except (OSError, EOFError, ValueError):
            break
        if t is None:
            break
        try:
            m = json.loads(t)
        except ValueError:
            continue
        if "id" in m:
            w = E.esperas.get(m["id"])
            if w:
                w[1] = m
                w[0].set()
        else:
            try:
                _evento(m)
            except Exception:
                pass
    E.ws = None


JS_HOOK = r"""(()=>{if(window.__sg)return;window.__sg=1;
const out=(m,u,b)=>{try{let d=null;
 if(b instanceof FormData){d=[...b.entries()].map(([k,v])=>v instanceof Blob?{campo:k,archivo:v.name||'',tipo:v.type,bytes:v.size}:{campo:k,valor:String(v).slice(0,1500)})}
 else if(b instanceof Blob){d=[{campo:'(blob)',tipo:b.type,bytes:b.size}]}
 else if(b instanceof ArrayBuffer||ArrayBuffer.isView(b)){d=[{campo:'(binario)',bytes:b.byteLength}]}
 else if(typeof b==='string'){let v=b;try{const cut=o=>typeof o==='string'?(o.length>200?'<'+o.length+' caracteres>':o):Array.isArray(o)?o.map(cut):(o&&typeof o==='object')?Object.fromEntries(Object.entries(o).map(([k,x])=>[k,cut(x)])):o;v=JSON.stringify(cut(JSON.parse(b)))}catch(e){v=b.slice(0,1500)}d=[{campo:'(texto)',bytes:b.length,valor:v}]}
 if(d)console.debug('__sgae__'+JSON.stringify({m:m,u:String(u).split('?')[0],d:d}))}catch(e){}};
const f=window.fetch;window.fetch=function(i,o){try{out((o&&o.method)||'GET',(i&&i.url)||i,o&&o.body)}catch(e){}return f.apply(this,arguments)};
const xo=XMLHttpRequest.prototype.open,xs=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;return xo.apply(this,arguments)};
XMLHttpRequest.prototype.send=function(b){out(this.__m,this.__u,b);return xs.apply(this,arguments)}})()"""


def _conectar():
    if E.ws and E.hilo and E.hilo.is_alive():
        return True
    pags = _paginas()
    if not pags:
        return False
    t = next((p for p in pags if _host_ok(p.get("url", ""))), pags[0])
    E.ws = WS(t["webSocketDebuggerUrl"])
    E.objetivo = t.get("id")
    E.hilo = threading.Thread(target=_leer, daemon=True)
    E.hilo.start()
    _cmd("Network.enable", {"maxPostDataSize": 65536})
    _cmd("Runtime.enable")
    _cmd("Page.enable")
    _cmd("Page.addScriptToEvaluateOnNewDocument", {"source": JS_HOOK})
    _cmd("Runtime.evaluate", {"expression": JS_HOOK})
    return True


def estado(req, ctx):
    pags = _paginas()
    url = next((p.get("url") for p in pags if _host_ok(p.get("url", ""))), (pags[0].get("url") if pags else ""))
    req.send({"ok": True, "chrome": bool(_chrome()), "abierto": bool(pags), "conectado": bool(E.ws and E.hilo and E.hilo.is_alive()),
              "sesion": bool(E.sesion and E.miembro), "plantilla": bool(_plantilla()),
              "url": url, "grabando": E.grabando, "n": len(E.cap), "hosts": HOSTS})


def _get(base, path):
    """READ-ONLY request to an SGAE service using the session of the window the person logged in to."""
    u = urlparse(base)
    if u.scheme == "https":
        c = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=25, context=ssl.create_default_context())
    else:
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=25)
    try:
        c.request("GET", path, headers={"Accept": "application/json", "enlinea-auth": E.sesion["auth"], "enlinea-auth-email": E.sesion["email"],
                                        "Origin": "https://sede.sgae.es", "Referer": "https://sede.sgae.es/", "User-Agent": "Mozilla/5.0"})
        r = c.getresponse()
        b = r.read()
        if r.status in (401, 403):
            raise PermissionError
        if r.status >= 400:
            raise OSError(f"SGAE respondió {r.status}")
        return json.loads(b.decode("utf-8") or "null")
    finally:
        c.close()


def comprobar(req, ctx):
    """GET (read only): the person's validated works, the ones waiting for validation and the rejected ones, from SGAE."""
    if not (E.sesion and E.miembro):
        return req.send({"ok": False, "error": "sin_sesion"})
    m = E.miembro
    try:
        w = _get(API_OBRAS, f"/v2/repertoire-performance/my-repertoire/works?workType=musical&memberCode={m}&subsidiaries=true&incompleteRecords=false&numElements=500")
        pe = _get(API_REGISTRO, f"/user/cases/rgo?memberCode={m}&type=musical-work&status=RUNNING")
        re_ = _get(API_REGISTRO, f"/user/cases/rgo?memberCode={m}&type=musical-work&status=CANCELED")
    except PermissionError:
        return req.send({"ok": False, "error": "sesion_caducada"})
    except (OSError, ValueError, http.client.HTTPException) as ex:
        return req.send({"ok": False, "error": "red", "detalle": str(ex)[:120]})
    res = {"ok": True,
           "validadas": [{"codigo": str(x.get("code")), "titulo": x.get("desc"), "iswc": x.get("iswc"), "fecha": x.get("registerDate"), "genero": x.get("genreDescription")} for x in ((w or {}).get("works") or [])],
           "pendientes": [{"rgo": x.get("number"), "titulo": x.get("summary"), "estado": x.get("status"), "fecha": x.get("startDate"), "uuid": x.get("uuid")} for x in (pe or [])],
           "rechazadas": [{"rgo": x.get("number"), "titulo": x.get("summary"), "motivo": x.get("commentReject")} for x in (re_ or [])]}
    res["cambios"] = _recordar(ctx, res)
    res["ultima"] = _memoria(ctx).get("ultima")
    req.send(res)


# MEMORY: what SGAE showed the last time it was read, kept in the local data folder, so the screen is useful without a session and a refresh can say what changed.
def _ruta_mem(ctx):
    return Path(ctx.datos) / "memoria.json"


def _memoria(ctx):
    try:
        return json.loads(_ruta_mem(ctx).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _recordar(ctx, res):
    """Saves the snapshot and returns what changed since the previous one (new validated works, new pending ones, newly rejected ones)."""
    ant = _memoria(ctx)
    cambios = {}
    if ant.get("ultima"):
        v0 = {x["codigo"] for x in ant.get("validadas", [])}
        p0 = {x["rgo"] for x in ant.get("pendientes", [])}
        r0 = {x["rgo"] for x in ant.get("rechazadas", [])}
        cambios = {"validadas": [x["titulo"] for x in res["validadas"] if x["codigo"] not in v0],
                   "pendientes": [x["titulo"] for x in res["pendientes"] if x["rgo"] not in p0],
                   "rechazadas": [x["titulo"] for x in res["rechazadas"] if x["rgo"] not in r0]}
    snap = {k: res[k] for k in ("validadas", "pendientes", "rechazadas")}
    snap["ultima"] = datetime.now().isoformat(timespec="seconds")
    snap["enviadas"] = ant.get("enviadas", [])
    try:
        _ruta_mem(ctx).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return cambios


def memoria(req, ctx):
    """GET: the last snapshot read from SGAE (works validated, in process, rejected, and the ones this manager sent), with the date it was read."""
    m = _memoria(ctx)
    req.send({"ok": bool(m.get("ultima")), **m} if m else {"ok": False})


JS_FORM = r"""(()=>{const root=document.querySelector('main')||document.body;
const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
const lab=e=>{let t='';if(e.id){try{const l=document.querySelector('label[for="'+CSS.escape(e.id)+'"]');if(l)t=l.innerText}catch(x){}}
 if(!t&&e.closest('label'))t=e.closest('label').innerText;if(!t&&e.getAttribute('aria-label'))t=e.getAttribute('aria-label');
 if(!t){let p=e.parentElement;for(let i=0;i<4&&p&&!t;i++,p=p.parentElement){const l=p.querySelector('label,legend,h3,h4');if(l&&l!==e)t=l.innerText}}
 return t.replace(/\s+/g,' ').trim().slice(0,90)};
const out=[...root.querySelectorAll('input,select,textarea,button,[role=radio],[role=combobox],[role=option],[role=tab]')].map((e,i)=>{const r=e.getBoundingClientRect();
 return {i,tag:e.tagName.toLowerCase(),type:e.type||null,id:e.id||null,name:e.getAttribute('name'),role:e.getAttribute('role'),aria:e.getAttribute('aria-label'),ph:e.getAttribute('placeholder'),
 label:lab(e),texto:e.tagName==='BUTTON'?e.innerText.replace(/\s+/g,' ').trim().slice(0,40):null,checked:('checked' in e)?e.checked:null,visible:vis(e),x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),cls:(e.className&&e.className.toString().slice(0,70))||null}});
return JSON.stringify({url:location.href.split('?')[0],titulo:document.title,campos:out})})()"""


def inspeccionar(req, ctx):
    """Describes the controls of the page currently shown in the window (labels, types, positions; NEVER the values typed in)."""
    if not E.ws:
        return req.send({"ok": False, "error": "no_abierto"})
    r = _cmd("Runtime.evaluate", {"expression": JS_FORM, "returnByValue": True}, 8).get("result", {}).get("result", {})
    try:
        d = json.loads(r.get("value") or "")
    except ValueError:
        return req.send({"ok": False, "error": "sin_datos"})
    ruta = _base() / "formulario.json"
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    req.send({"ok": True, "ruta": str(ruta), "n": len(d.get("campos", [])), "url": d.get("url")})


def titulo_sgae(texto):
    """SGAE title as agreed: UPPERCASE, no accents, keeping the Ñ."""
    s = (texto or "").upper().replace("Ñ", "\x00")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.replace("\x00", "Ñ").strip()


def _nombre_fichero(n):
    s = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9._-]", "", s.replace(" ", "_"))


def _carpeta(ctx):
    return (Path(ctx.root) / "SGAE-REGISTRO MUSICAL").resolve()


def _duracion(ctx, f):
    ff = ctx.ffmpeg()
    if not ff:
        return None
    r = subprocess.run([ff, "-i", str(f)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
    return int(round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 2)) if m else None


def _art(ctx):
    return str((getattr(ctx, "cfg", None) or {}).get("artista") or "").strip()


def _titulo_de(a, ctx):
    """Title from «<Title> audio <Artist>.mp3» (the artist comes from the configuration)."""
    art = _art(ctx)
    suf = f" audio {art}.mp3" if art else ""
    return a.name[: -len(suf)] if suf and a.name.endswith(suf) else a.name.rsplit(" audio ", 1)[0]


def _letra_de(a, titulo, ctx):
    art = _art(ctx)
    if art:
        return a.with_name(f"{titulo} letra {art}.txt")
    return next(iter(sorted(a.parent.glob(f"{titulo} letra *.txt"))), a.with_name(f"{titulo} letra.txt"))


def preparadas(req, ctx):
    """GET: the registrations ready in «SGAE-REGISTRO MUSICAL/…/SGAE enviado»: audio + lyrics pairs named «<Title> audio|letra <Artist>»."""
    base = _carpeta(ctx)
    out = []
    art = _art(ctx)
    for a in sorted(base.rglob(f"* audio {art}.mp3" if art else "* audio *.mp3")):
        titulo = _titulo_de(a, ctx)
        l = _letra_de(a, titulo, ctx)
        out.append({"titulo": titulo, "sgae": titulo_sgae(titulo), "mp3": str(a), "letra": str(l) if l.exists() else None,
                    "segundos": _duracion(ctx, a), "album": a.parent.parent.name})
    req.send({"ok": True, "items": out, "plantilla": bool(_plantilla())})


def _post_json(base, path, obj):
    u = urlparse(base)
    c = (http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=180, context=ssl.create_default_context()) if u.scheme == "https"
         else http.client.HTTPConnection(u.hostname, u.port or 80, timeout=180))
    try:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        c.request("POST", path, body=data, headers={"Accept": "application/json", "Content-Type": "application/json", "enlinea-auth": E.sesion["auth"],
                                                    "enlinea-auth-email": E.sesion["email"], "Origin": "https://sede.sgae.es", "Referer": "https://sede.sgae.es/",
                                                    "User-Agent": "Mozilla/5.0"})
        r = c.getresponse()
        b = r.read()
        if r.status in (401, 403):
            raise PermissionError
        return r.status, json.loads(b.decode("utf-8") or "null")
    finally:
        c.close()


def _existentes():
    m = E.miembro
    w = _get(API_OBRAS, f"/v2/repertoire-performance/my-repertoire/works?workType=musical&memberCode={m}&subsidiaries=true&incompleteRecords=false&numElements=500")
    p = _get(API_REGISTRO, f"/user/cases/rgo?memberCode={m}&type=musical-work&status=RUNNING")
    return {titulo_sgae(x.get("desc")) for x in ((w or {}).get("works") or [])} | {titulo_sgae(x.get("summary")) for x in (p or [])}


def enviar(req, ctx):
    """POST {mp3, letra, titulo?, segundos?, simular?, confirmado?}: registers ONE work, sending to SGAE what its web form sends (the person's own
    template + title, duration, dates and the two files). Without «confirmado» nothing is sent; «simular» only returns what would be sent."""
    d = req.json()
    pl = _plantilla()
    if not (E.sesion and E.miembro):
        return req.send({"ok": False, "error": "sin_sesion"})
    if not pl:
        return req.send({"ok": False, "error": "sin_plantilla"})
    base = _carpeta(ctx)
    try:
        a, l = Path(d.get("mp3") or "").resolve(), Path(d.get("letra") or "").resolve()
        for f in (a, l):
            f.relative_to(base)
            if not f.is_file():
                raise ValueError
    except (ValueError, OSError):
        return req.send({"ok": False, "error": "ficheros"})
    titulo = (d.get("titulo") or "").strip() or titulo_sgae(_titulo_de(a, ctx))
    seg = int(d.get("segundos") or _duracion(ctx, a) or 0)
    if not titulo or seg < 10:
        return req.send({"ok": False, "error": "datos"})
    if a.stat().st_size > 40_000_000 or l.stat().st_size > 2_000_000:
        return req.send({"ok": False, "error": "tamano"})
    cuerpo = json.loads(json.dumps(pl["cuerpo"]))
    ahora = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    cuerpo.update({"title": titulo, "dFechaAlta": ahora, "declarationDate": ahora, "workDuration": seg})
    tipos = pl.get("tipos") or {}
    cuerpo["caseFiles"] = [{"fileTypeId": tipos.get("audio", 1), "name": _nombre_fichero(a.name), "url": base64.b64encode(a.read_bytes()).decode()},
                           {"fileTypeId": tipos.get("letra", 4), "name": _nombre_fichero(l.name), "url": base64.b64encode(l.read_bytes()).decode()}]
    resumen = {"titulo": titulo, "segundos": seg, "audio": cuerpo["caseFiles"][0]["name"], "letra": cuerpo["caseFiles"][1]["name"],
               "autor": ((cuerpo.get("creator") or [{}])[0]).get("name"), "reparto": ((cuerpo.get("creator") or [{}])[0]).get("shares"),
               "interprete": [x.get("playerName") for x in cuerpo.get("players") or []]}
    try:
        if titulo_sgae(titulo) in _existentes():
            return req.send({"ok": False, "error": "duplicada", "resumen": resumen})
    except PermissionError:
        return req.send({"ok": False, "error": "sesion_caducada"})
    except (OSError, ValueError, http.client.HTTPException) as ex:
        return req.send({"ok": False, "error": "red", "detalle": str(ex)[:120]})
    if d.get("simular") or not d.get("confirmado"):
        return req.send({"ok": True, "simulado": True, "resumen": resumen})
    try:
        st, r = _post_json(API_REGISTRO, "/user/cases/rgo", cuerpo)
    except PermissionError:
        return req.send({"ok": False, "error": "sesion_caducada"})
    except (OSError, ValueError, http.client.HTTPException) as ex:
        return req.send({"ok": False, "error": "red", "detalle": str(ex)[:120]})
    if st == 200 and isinstance(r, dict) and r.get("status") == "ok":
        m = _memoria(ctx)
        m.setdefault("enviadas", []).append({"titulo": titulo, "caso": r.get("caseNumber"), "fecha": datetime.now().isoformat(timespec="seconds")})
        try:
            _ruta_mem(ctx).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        return req.send({"ok": True, "caso": r.get("caseNumber"), "resumen": resumen})
    req.send({"ok": False, "error": "rechazada", "estado": st, "respuesta": str(r)[:300], "resumen": resumen})


PROHIBIDOS = re.compile(r"enviar|registrar|guardar|elimin|borrar|aceptar|confirmar|firmar|cerrar sesi|salir|pagar|descargar|subir", re.I)
JS_PULSAR = """(texto=>{const root=document.querySelector('main')||document.body;
const c=[...root.querySelectorAll('a,button,td,span,div,li,tr,[role=tab],[role=button]')].filter(e=>e.children.length<=3&&(e.innerText||'').replace(/\\s+/g,' ').trim()===texto);
if(!c.length)return 'no encontrado';c.sort((a,b)=>a.innerText.length-b.innerText.length);const e=c[0];e.scrollIntoView({block:'center'});e.click();return 'ok'})"""


def pulsar(req, ctx):
    """POST {texto}: clicks (by its visible text) a navigation element of the SGAE window. Refuses anything that looks like sending, saving or deleting."""
    d = req.json()
    texto = " ".join(str(d.get("texto") or "").split())
    if not E.ws:
        return req.send({"ok": False, "error": "no_abierto"})
    if not texto or PROHIBIDOS.search(texto):
        return req.send({"ok": False, "error": "no_permitido"})
    r = _cmd("Runtime.evaluate", {"expression": JS_PULSAR + "(" + json.dumps(texto) + ")", "returnByValue": True}, 8).get("result", {}).get("result", {})
    req.send({"ok": r.get("value") == "ok", "resultado": r.get("value")})


def refrescar(req, ctx):
    """Reloads the page of the window: the SGAE web then repeats its requests and the module picks up the session."""
    try:
        _conectar()  # the window may be open from before (manager restarted): attach to it first
    except OSError:
        pass
    if not E.ws:
        return req.send({"ok": False, "error": "no_abierto"})
    _cmd("Page.reload", {}, 8)
    req.send({"ok": True})


def _claves(o, prof=0):
    if isinstance(o, dict):
        return {k: _claves(v, prof + 1) for k, v in o.items()} if prof < 3 else "{…}"
    if isinstance(o, list):
        return [_claves(o[0], prof + 1)] if o else []
    return type(o).__name__


def sondear(req, ctx):
    """POST {uuid, numero}: READ-ONLY. Which SGAE address returns the full detail of an existing registration? Returns status and key names only."""
    d = req.json()
    if not (E.sesion and E.miembro):
        return req.send({"ok": False, "error": "sin_sesion"})
    m = E.miembro
    u, n = str(d.get("uuid") or ""), str(d.get("numero") or "")
    cand = [f"/user/cases/rgo/{u}?memberCode={m}", f"/user/cases/{u}?memberCode={m}", f"/user/cases/rgo/{n}?memberCode={m}", f"/user/cases/rgo/{u}",
            f"/user/cases/case/{u}?memberCode={m}", f"/front/cases/{u}?memberCode={m}", f"/user/cases/detail/{u}?memberCode={m}", f"/user/cases/rgo/{u}/detail?memberCode={m}"]
    out = []
    for c in cand:
        try:
            r = _get(API_REGISTRO, c)
            out.append({"ruta": c.replace(m, "<m>"), "ok": True, "claves": _claves(r)})
        except PermissionError:
            return req.send({"ok": False, "error": "sesion_caducada"})
        except (OSError, ValueError, http.client.HTTPException) as ex:
            out.append({"ruta": c.replace(m, "<m>"), "ok": False, "error": str(ex)[:60]})
    req.send({"ok": True, "pruebas": out})


def abrir(req, ctx):
    if not _paginas():
        exe = _chrome()
        if not exe:
            return req.send({"ok": False, "error": "no_chrome"})
        args = [exe, f"--remote-debugging-port={PORT}", f"--user-data-dir={_base() / 'perfil'}", "--no-first-run", "--no-default-browser-check"]
        if HEADLESS:
            args.append("--headless=new")
        E.proc = subprocess.Popen(args + [START_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if _paginas():
                break
            time.sleep(0.25)
    try:
        ok = _conectar()
    except OSError as ex:
        return req.send({"ok": False, "error": str(ex)})
    req.send({"ok": bool(ok)})


def grabar(req, ctx):
    d = req.json()
    if not E.ws:
        try:
            if not _conectar():
                return req.send({"ok": False, "error": "no_abierto"})
        except OSError as ex:
            return req.send({"ok": False, "error": str(ex)})
    if d.get("limpiar"):
        with LOCK:
            E.cap.clear()
            E.pend.clear()
    E.grabando = bool(d.get("on"))
    req.send({"ok": True, "grabando": E.grabando, "n": len(E.cap)})


def captura(req, ctx):
    with LOCK:
        L = [dict(x, cuerpo=(x["cuerpo"][:MAX_CAP] if x.get("cuerpo") else None), respuesta=(x.get("respuesta") or "")[:MAX_CAP] or None) for x in E.cap[-400:]]
    req.send({"ok": True, "n": len(E.cap), "peticiones": L})


def guardar(req, ctx):
    p = _base() / f"captura_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with LOCK:
        p.write_text(json.dumps(E.cap, ensure_ascii=False, indent=1), encoding="utf-8")
    req.send({"ok": True, "ruta": str(p), "n": len(E.cap)})


def cerrar(req, ctx):
    try:
        if E.ws:
            _cmd("Browser.close", {}, 2)
    except Exception:
        pass
    if E.ws:
        E.ws.close()
    E.ws = None
    E.grabando = False
    if E.proc and E.proc.poll() is None:
        E.proc.terminate()
    req.send({"ok": True})


ROUTES = {
    "GET estado": estado,
    "POST abrir": abrir,
    "POST refrescar": refrescar,
    "POST pulsar": pulsar,
    "POST sondear": sondear,
    "POST grabar": grabar,
    "GET comprobar": comprobar,
    "GET memoria": memoria,
    "GET preparadas": preparadas,
    "POST enviar": enviar,
    "POST inspeccionar": inspeccionar,
    "GET captura": captura,
    "POST guardar": guardar,
    "POST cerrar": cerrar,
}
