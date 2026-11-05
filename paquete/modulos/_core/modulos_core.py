"""Núcleo de módulos del gestor (servidor). Lo comparten el gestor personal y el paquete distribuible.

Cada módulo vive en  modulos/<id>/  con un  modulo.json:

    {"id": "masterizado", "nombre": "Masterización", "descripcion": "…",
     "js": ["modulo.js"], "css": ["modulo.css"], "py": "servidor.py", "distribuir": true}

y, si tiene parte de servidor, un  servidor.py  con:

    ROUTES = {"GET estado": fn, "POST guardar": fn}      # /api/mod/<id>/estado  y  /api/mod/<id>/guardar
    def setup(ctx): ...                                   # opcional, se llama al cargar

Cada ruta es  fn(req, ctx).  El gestor NO se reinicia solo: tras tocar un servidor.py hay que reiniciar el gestor.
Las carpetas que empiezan por «_» (como _core y _plantilla) no se cargan como módulos.
"""
import importlib.util
import json
import mimetypes
import os
import traceback
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

STATIC_EXT = {".js", ".css", ".html", ".json", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".woff2", ".woff", ".ttf", ".wasm", ".txt", ".md"}


class Req:
    """Lo que recibe cada ruta de un módulo."""

    def __init__(self, h, q):
        self.h = h          # el manejador HTTP del gestor (por si hace falta algo muy especial)
        self.q = q          # parámetros de la URL: {"id": ["abc"]}

    def arg(self, nombre, defecto=""):
        return unquote(self.q.get(nombre, [defecto])[0])

    def tam(self):
        return int(self.h.headers.get("Content-Length", 0) or 0)

    def json(self):
        n = self.tam()
        raw = self.h.rfile.read(n).decode("utf-8") if n else ""
        return json.loads(raw) if raw.strip() else {}

    def body(self, limite=512 * 1024 * 1024):
        n = self.tam()
        if n > limite:
            raise ValueError("el archivo es demasiado grande")
        return self.h.rfile.read(n) if n else b""

    def guardar_en(self, destino):
        """Guarda el cuerpo de la petición (un archivo subido) en `destino` sin cargarlo entero en memoria. Devuelve los bytes."""
        n = self.tam()
        left = n
        with open(destino, "wb") as f:
            while left > 0:
                chunk = self.h.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            try:
                os.remove(destino)
            except OSError:
                pass
            raise ValueError("subida incompleta")
        return n

    def send(self, obj, code=200):
        self.h.send_json(obj, code)

    def file(self, ruta, ctype=None, descarga=None):
        """Envía un archivo (con nombre de descarga si se indica)."""
        ruta = Path(ruta)
        size = ruta.stat().st_size
        self.h.send_response(200)
        self.h.send_header("Content-Type", ctype or mimetypes.guess_type(ruta.name)[0] or "application/octet-stream")
        self.h.send_header("Content-Length", str(size))
        if descarga:
            import re
            from urllib.parse import quote
            self.h.send_header("Content-Disposition", f"attachment; filename=\"{re.sub(r'[^A-Za-z0-9._ -]', '_', descarga)}\"; filename*=UTF-8''{quote(descarga)}")
        self.h.end_headers()
        try:
            with open(ruta, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    self.h.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Registro:
    def __init__(self, carpeta, ctx_base):
        """carpeta: la carpeta modulos/.  ctx_base: dict con lo que el gestor ofrece a los módulos
        (root, datos, cfg, songs, song, ffmpeg, safe_name, run_script, log…). Cada módulo recibe una copia con su propia carpeta de datos."""
        self.carpeta = Path(carpeta)
        self.ctx_base = ctx_base
        self.mods = {}

    def cargar(self):
        self.mods = {}
        if not self.carpeta.is_dir():
            return
        for d in sorted(self.carpeta.iterdir()):
            if not d.is_dir() or d.name.startswith(("_", ".")) or not (d / "modulo.json").exists():
                continue
            try:
                man = json.loads((d / "modulo.json").read_text(encoding="utf-8"))
                mid = man.get("id") or d.name
                rutas, setup = {}, None
                if man.get("py"):
                    spec = importlib.util.spec_from_file_location("gmod_" + mid, d / man["py"])
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    rutas, setup = getattr(mod, "ROUTES", {}), getattr(mod, "setup", None)
                self.mods[mid] = {"man": man, "dir": d, "rutas": rutas}
                if setup:
                    setup(self.ctx(mid))
            except Exception:  # un módulo roto no tumba el gestor
                print(f"[módulos] no se pudo cargar «{d.name}»:\n{traceback.format_exc()}")
                self.mods.pop(d.name, None)

    def ctx(self, mid):
        c = dict(self.ctx_base)
        datos = Path(c["datos"]) / "modulos" / mid
        datos.mkdir(parents=True, exist_ok=True)
        c["datos"] = datos
        c["id"] = mid
        raiz = Path(self.ctx_base["datos"])
        fa = raiz / "ajustes.json"

        def ajustes():
            try:
                return json.loads(fa.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}

        def guardar_ajustes(d):
            cur = ajustes()
            cur.update(d)
            raiz.mkdir(parents=True, exist_ok=True)
            fa.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            return cur
        c["ajustes"], c["guardar_ajustes"] = ajustes, guardar_ajustes   # preferencias compartidas por todos los módulos
        return SimpleNamespace(**c)

    def listar(self):
        return [{"id": mid, "nombre": m["man"].get("nombre", mid), "descripcion": m["man"].get("descripcion", ""),
                 "js": m["man"].get("js", []), "css": m["man"].get("css", [])} for mid, m in self.mods.items()]

    def estatico(self, mid, rel):
        """Ruta de un archivo estático de un módulo (o de _core). None si no es válido."""
        base = (self.carpeta / "_core") if mid == "_core" else (self.mods.get(mid) or {}).get("dir")
        if not base:
            return None
        p = (Path(base) / rel).resolve()
        try:
            p.relative_to(Path(base).resolve())
        except ValueError:
            return None
        return p if p.is_file() and p.suffix.lower() in STATIC_EXT else None

    def despachar(self, h, metodo, ruta_url):
        """/api/mod/<id>/<ruta>?… → la función del módulo. Devuelve False si no hay ruta."""
        u = urlparse(ruta_url)
        partes = u.path[len("/api/mod/"):].split("/", 1)
        if len(partes) != 2 or partes[0] not in self.mods:
            return False
        fn = self.mods[partes[0]]["rutas"].get(f"{metodo} {partes[1]}")
        if not fn:
            return False
        try:
            fn(Req(h, parse_qs(u.query)), self.ctx(partes[0]))
        except Exception as ex:  # noqa: BLE001
            print(f"[módulos] error en {partes[0]}/{partes[1]}:\n{traceback.format_exc()}")
            try:
                h.send_json({"ok": False, "error": f"{type(ex).__name__}: {ex}"}, 500)
            except Exception:  # noqa: BLE001
                pass
        return True


# ---------------------------------------------------------------------------------------------------------------
# Traducción en el servidor (textos que se escriben en archivos: COPYRIGHT.txt, letras de mixtape…).
# Mismo diccionario que la interfaz: modulos/_core/idiomas/<xx>.json. El idioma llega en la cabecera X-Lang.
_DICC = {}


def idioma_de(h):
    """Idioma pedido por el navegador (es/en/de/pt); es por defecto."""
    try:
        l = (h.headers.get("X-Lang") or "es").lower()[:2]
    except Exception:  # noqa: BLE001
        return "es"
    return l if l in ("es", "en", "de", "pt") else "es"


def traducir(texto, lang):
    """Traduce una frase exacta de la interfaz; si no está en el diccionario, la deja igual."""
    if not lang or lang == "es" or not texto:
        return texto
    d = _DICC.get(lang)
    if d is None:
        try:
            import json
            d = json.loads((Path(__file__).resolve().parent / "idiomas" / f"{lang}.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            d = {}
        _DICC[lang] = d
    return d.get("exactas", {}).get(texto, texto)
