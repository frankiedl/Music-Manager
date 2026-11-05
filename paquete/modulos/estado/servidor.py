"""Módulo «estado» (servidor). Guarda en ctx.datos, en el equipo de la persona:
   informes/<id>.json   cada informe CSV importado (filas ya normalizadas)
   perfiles.json        perfiles de «qué columna es qué»
   alias.json           títulos/ISRC que la persona ha casado a mano con sus canciones
   spotify.json         claves propias de Spotify (solo si activa la conexión opcional)
   spotify_catalogo.json  datos públicos de catálogo traídos de Spotify
Nada de esto viaja al estado compartido (estado.json)."""
import base64
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

MAX_INFORME = 60 * 1024 * 1024
ID_OK = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


def _leer(p, defecto):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def _escribir(p, obj, privado=False):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    if privado:
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass


def _dir_inf(ctx):
    d = Path(ctx.datos) / "informes"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- informes
def datos(req, ctx):
    informes = []
    for f in sorted(_dir_inf(ctx).glob("*.json")):
        inf = _leer(f, None)
        if isinstance(inf, dict) and inf.get("id"):
            informes.append(inf)
    informes.sort(key=lambda x: x.get("importado", ""))
    req.send({"ok": True, "informes": informes,
              "perfiles": _leer(Path(ctx.datos) / "perfiles.json", []),
              "alias": _leer(Path(ctx.datos) / "alias.json", {"t": {}, "isrc": {}}),
              "spotify": _spotify_resumen(ctx)})


def informe_guardar(req, ctx):
    if req.tam() > MAX_INFORME:
        return req.send({"ok": False, "error": "El informe es demasiado grande."}, 413)
    inf = (req.json() or {}).get("informe")
    if not isinstance(inf, dict) or not isinstance(inf.get("filas"), list):
        return req.send({"ok": False, "error": "Informe no válido."}, 400)
    iid = inf.get("id") if ID_OK.match(str(inf.get("id", ""))) else uuid.uuid4().hex[:12]
    inf["id"] = iid
    inf.setdefault("importado", time.strftime("%Y-%m-%dT%H:%M:%S"))
    _escribir(_dir_inf(ctx) / f"{iid}.json", inf)
    req.send({"ok": True, "id": iid})


def informe_borrar(req, ctx):
    iid = str((req.json() or {}).get("id", ""))
    if not ID_OK.match(iid):
        return req.send({"ok": False, "error": "Identificador no válido."}, 400)
    p = _dir_inf(ctx) / f"{iid}.json"
    if p.is_file():
        p.unlink()  # dato propio del módulo (un informe importado), no música de la persona
    req.send({"ok": True})


def perfiles_guardar(req, ctx):
    pf = (req.json() or {}).get("perfiles")
    if not isinstance(pf, list):
        return req.send({"ok": False, "error": "Perfiles no válidos."}, 400)
    _escribir(Path(ctx.datos) / "perfiles.json", pf)
    req.send({"ok": True})


def alias_guardar(req, ctx):
    al = (req.json() or {}).get("alias")
    if not isinstance(al, dict):
        return req.send({"ok": False, "error": "Datos no válidos."}, 400)
    _escribir(Path(ctx.datos) / "alias.json", {"t": al.get("t", {}), "isrc": al.get("isrc", {})})
    req.send({"ok": True})


# ---------------------------------------------------------------- Spotify (opcional, opt-in)
# Solo datos PÚBLICOS de catálogo, con las claves propias de la persona (flujo «Client Credentials»:
# no entra en su cuenta ni lee datos privados). Lo único que sale del equipo hacia Spotify: las claves
# (para pedir un permiso temporal) y el texto de búsqueda (título de la canción y nombre del artista).
SP_TOKEN = "https://accounts.spotify.com/api/token"
SP_API = "https://api.spotify.com/v1"
_tok = {"v": None, "hasta": 0}


def _spotify_cfg(ctx):
    return _leer(Path(ctx.datos) / "spotify.json", {})


def _spotify_resumen(ctx):
    c = _spotify_cfg(ctx)
    cat = _leer(Path(ctx.datos) / "spotify_catalogo.json", {})
    return {"configurado": bool(c.get("id") and c.get("secreto")), "activo": bool(c.get("activo")),
            "artista": c.get("artista", ""), "mercado": c.get("mercado", ""),
            "id_visible": (c.get("id", "")[:4] + "…") if c.get("id") else "",
            "catalogo": cat, "actualizado": cat.get("_fecha", "")}


def spotify_guardar(req, ctx):
    b = req.json() or {}
    c = _spotify_cfg(ctx)
    for k in ("id", "secreto"):
        v = str(b.get(k, "")).strip()
        if v:
            c[k] = v
    c["artista"] = str(b.get("artista", c.get("artista", ""))).strip()
    c["mercado"] = str(b.get("mercado", c.get("mercado", ""))).strip().upper()[:2]
    c["activo"] = bool(b.get("activo"))
    _escribir(Path(ctx.datos) / "spotify.json", c, privado=True)
    _tok.update(v=None, hasta=0)
    req.send({"ok": True, "spotify": _spotify_resumen(ctx)})


def spotify_olvidar(req, ctx):
    for n in ("spotify.json", "spotify_catalogo.json"):
        p = Path(ctx.datos) / n
        if p.is_file():
            p.unlink()
    _tok.update(v=None, hasta=0)
    req.send({"ok": True, "spotify": _spotify_resumen(ctx)})


def _sp_pedir(url, datos=None, cab=None):
    rq = urllib.request.Request(url, data=datos, headers=cab or {})
    try:
        with urllib.request.urlopen(rq, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = ""
        try:
            cuerpo = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"Spotify respondió {e.code}. {cuerpo}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo contactar con Spotify ({e.reason}). ¿Hay conexión a Internet?") from None


def _sp_token(ctx):
    if _tok["v"] and time.time() < _tok["hasta"] - 30:
        return _tok["v"]
    c = _spotify_cfg(ctx)
    if not (c.get("id") and c.get("secreto")):
        raise RuntimeError("Faltan las claves de Spotify.")
    basic = base64.b64encode(f"{c['id']}:{c['secreto']}".encode()).decode()
    r = _sp_pedir(SP_TOKEN, urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
                  {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
    _tok.update(v=r["access_token"], hasta=time.time() + int(r.get("expires_in", 3600)))
    return _tok["v"]


def spotify_probar(req, ctx):
    try:
        _sp_token(ctx)
        req.send({"ok": True, "mensaje": "Las claves funcionan: Spotify ha dado permiso de lectura del catálogo público."})
    except Exception as e:  # noqa: BLE001
        req.send({"ok": False, "error": str(e)})


def _norm(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def spotify_consultar(req, ctx):
    """body: {canciones:[{id,titulo}]}  → busca cada título del artista y guarda lo público que encuentre."""
    c = _spotify_cfg(ctx)
    if not c.get("activo"):
        return req.send({"ok": False, "error": "La conexión con Spotify está desactivada."})
    if not c.get("artista"):
        return req.send({"ok": False, "error": "Indica el nombre de tu artista en Spotify."})
    lista = (req.json() or {}).get("canciones") or []
    cat = _leer(Path(ctx.datos) / "spotify_catalogo.json", {})
    hallados = faltan = 0
    try:
        tok = _sp_token(ctx)
        for it in lista[:120]:
            tit = str(it.get("titulo", "")).strip()
            if not tit:
                continue
            q = f'track:"{tit}" artist:"{c["artista"]}"'
            prm = {"q": q, "type": "track", "limit": 5}
            if c.get("mercado"):
                prm["market"] = c["mercado"]
            r = _sp_pedir(SP_API + "/search?" + urllib.parse.urlencode(prm), cab={"Authorization": "Bearer " + tok})
            mejor = None
            for t in (r.get("tracks") or {}).get("items") or []:
                if _norm(t.get("name", "")) == _norm(tit) and any(_norm(a.get("name", "")) == _norm(c["artista"]) for a in t.get("artists", [])):
                    mejor = t
                    break
            if mejor:
                hallados += 1
                cat[it["id"]] = {"nombre": mejor.get("name"), "url": (mejor.get("external_urls") or {}).get("spotify", ""),
                                 "isrc": (mejor.get("external_ids") or {}).get("isrc", ""),
                                 "album": (mejor.get("album") or {}).get("name", ""),
                                 "fecha": (mejor.get("album") or {}).get("release_date", "")}
            else:
                faltan += 1
                cat.pop(it["id"], None)
            time.sleep(0.15)
    except Exception as e:  # noqa: BLE001
        return req.send({"ok": False, "error": str(e)})
    cat["_fecha"] = time.strftime("%Y-%m-%d %H:%M")
    _escribir(Path(ctx.datos) / "spotify_catalogo.json", cat)
    req.send({"ok": True, "encontradas": hallados, "no_encontradas": faltan, "spotify": _spotify_resumen(ctx)})


ROUTES = {
    "GET datos": datos,
    "POST informe_guardar": informe_guardar,
    "POST informe_borrar": informe_borrar,
    "POST perfiles_guardar": perfiles_guardar,
    "POST alias_guardar": alias_guardar,
    "POST spotify_guardar": spotify_guardar,
    "POST spotify_olvidar": spotify_olvidar,
    "POST spotify_probar": spotify_probar,
    "POST spotify_consultar": spotify_consultar,
}
