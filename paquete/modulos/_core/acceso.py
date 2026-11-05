"""Acceso desde otra web al agente local del gestor (modo «web app»).

Idea: tus datos y tu música se quedan en tu equipo. El gestor es un *agente local* (127.0.0.1). La interfaz puede cargarse
desde el propio agente (como hasta ahora) o desde una web publicada; en ese caso esa web habla con tu agente.
Para que ninguna otra página pueda tocar tu biblioteca:

  · solo se aceptan peticiones de otro origen si ese origen está en la lista  origenes  de  datos/agente.json
  · y además traen el token de emparejamiento (cabecera X-Gestor-Token, o ?t=… en imágenes y audio).
  · las peticiones de la propia página del agente funcionan como siempre, sin token.
"""
import json
import secrets
from pathlib import Path


def cargar(datos_dir):
    """Lee (o crea) datos/agente.json: {"token": "...", "origenes": ["https://tu-web.example"]}."""
    datos_dir = Path(datos_dir)
    datos_dir.mkdir(parents=True, exist_ok=True)
    p = datos_dir / "agente.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    cambiado = False
    if not d.get("token"):
        d["token"] = secrets.token_urlsafe(24)
        cambiado = True
    if not isinstance(d.get("origenes"), list):
        d["origenes"] = []
        cambiado = True
    if cambiado:
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def _token_ok(h, agente, query):
    from urllib.parse import parse_qs, urlparse
    t = h.headers.get("X-Gestor-Token") or parse_qs(urlparse(query).query).get("t", [""])[0]
    return bool(t) and secrets.compare_digest(t, agente["token"])


EXTENSIONES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def origen_permitido(h, agente):
    """El origen de la petición si es una web autorizada o una extensión de navegador (en ambos casos hace falta además el token)."""
    o = (h.headers.get("Origin") or "").lower().rstrip("/")
    if o.startswith(EXTENSIONES):  # una página web no puede falsear este origen; igualmente exige el token
        return o
    return o if o and o in [x.lower().rstrip("/") for x in agente.get("origenes", [])] else ""


def autorizar(h, agente, puerto):
    """True si la petición puede atenderse. (El Host ya se comprobó antes.)"""
    o = (h.headers.get("Origin") or "").lower().rstrip("/")
    propios = (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}")
    if o in propios:
        return True
    if o:  # otro origen: solo si está permitido y trae el token
        return bool(origen_permitido(h, agente)) and _token_ok(h, agente, h.path)
    # sin Origin (navegación, imágenes, audio): si viene de otro sitio hace falta el token
    if (h.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
        return _token_ok(h, agente, h.path)
    return True


def cabeceras_cors(h, agente):
    """Cabeceras CORS para el origen permitido (vacío si no lo es)."""
    o = origen_permitido(h, agente)
    if not o:
        return []
    return [("Access-Control-Allow-Origin", h.headers.get("Origin")),
            ("Vary", "Origin"),
            ("Access-Control-Allow-Private-Network", "true"),
            ("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length, Content-Disposition")]


def preflight(h, agente):
    """Responde a OPTIONS. Devuelve True si lo atendió."""
    o = origen_permitido(h, agente)
    h.send_response(204 if o else 403)
    if o:  # Allow-Origin, Vary y Private-Network los añade end_headers del gestor (no repetirlos aquí)
        h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Gestor-Token, Range")
        h.send_header("Access-Control-Max-Age", "600")
    h.send_header("Content-Length", "0")
    h.end_headers()
    return True
