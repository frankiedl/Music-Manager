"""Access to the manager's local agent from another website ("web app" mode).

Idea: your data and your music stay on your computer. The manager is a *local agent* (127.0.0.1). The UI can be loaded
from the agent itself (as always) or from a published website; in that case that website talks to your agent.
So that no other page can touch your library:

  · requests from another origin are accepted only if that origin is in the  origenes  list of  datos/agente.json
  · and they also carry the pairing token (X-Gestor-Token header, or ?t=… for images and audio).
  · requests from the agent's own page work as always, without a token.
"""
import json
import secrets
from pathlib import Path


def cargar(datos_dir):
    """Reads (or creates) datos/agente.json: {"token": "...", "origenes": ["https://your-site.example"]}."""
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
    """The request origin if it is an authorized website or a browser extension (in both cases the token is also required)."""
    o = (h.headers.get("Origin") or "").lower().rstrip("/")
    if o.startswith(EXTENSIONES):  # a web page cannot fake this origin; the token is required anyway
        return o
    return o if o and o in [x.lower().rstrip("/") for x in agente.get("origenes", [])] else ""


def autorizar(h, agente, puerto):
    """True if the request may be served. (The Host header was already checked.)"""
    o = (h.headers.get("Origin") or "").lower().rstrip("/")
    propios = (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}")
    if o in propios:
        return True
    if o:  # other origin: only if allowed and it carries the token
        return bool(origen_permitido(h, agente)) and _token_ok(h, agente, h.path)
    # no Origin (navigation, images, audio): if it comes from another site the token is required
    if (h.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
        return _token_ok(h, agente, h.path)
    return True


def cabeceras_cors(h, agente):
    """CORS headers for the allowed origin (empty if it is not allowed)."""
    o = origen_permitido(h, agente)
    if not o:
        return []
    return [("Access-Control-Allow-Origin", h.headers.get("Origin")),
            ("Vary", "Origin"),
            ("Access-Control-Allow-Private-Network", "true"),
            ("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length, Content-Disposition")]


def preflight(h, agente):
    """Answers OPTIONS. Returns True if it handled it."""
    o = origen_permitido(h, agente)
    h.send_response(204 if o else 403)
    if o:  # Allow-Origin, Vary and Private-Network are added by the manager's end_headers (do not repeat them here)
        h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Gestor-Token, Range")
        h.send_header("Access-Control-Max-Age", "600")
    h.send_header("Content-Length", "0")
    h.end_headers()
    return True
