#!/usr/bin/env python3
"""Music manager (local, for Windows, Mac and Linux). It only listens on your own computer (127.0.0.1).

- Serves the UI (index.html) and your music with Range support so it can be played in the browser.
- Saves your work in datos/estado.json (tags, stars, notes). It only moves files when you ask,
  and every move is logged in datos/diario_movimientos.jsonl (it can be undone with deshacer.py).

Usage:  python3 gestor.py            (the first time it asks which folder is your library)
        python3 gestor.py --setup    (choose the library, the name or the copyright owner again)
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
import zlib
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

HERE = C.CODE
DATOS = C.DATOS
STATE = DATOS / "estado.json"
MSTATE = DATOS / "medios_estado.json"
DATA = DATOS / "data.json"
LETRAS = DATOS / "letras.json"
MEDIOS = DATOS / "medios.json"
THUMBS = DATOS / "thumbs"
DECISIONES = DATOS / "decisiones.csv"
DIARIO = DATOS / "diario_movimientos.jsonl"
AUDIO_EXT = C.AUDIO
MEDIA_EXT = AUDIO_EXT | {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm", ".m4v"}
LOCK = threading.Lock()
JOBS = {}
CFG = {}
ROOT = None
PORT = 8765
MODDIR = C.RES / "modulos"
sys.path.insert(0, str(MODDIR / "_core"))
try:
    import acceso
    import modulos_core
except ImportError:  # without the module core the manager works the same
    acceso = modulos_core = None
REG = None
AGENTE = {"token": "", "origenes": []}


# ---------------------------------------------------------------- utilidades
def run_script(name, *args, timeout=None):
    """Runs one of the scripts in the gestor/ folder isolated and with UTF-8 output on any system."""
    cmd = [sys.executable, "--run-script", name, *args] if C.FROZEN else [sys.executable, "-X", "utf8", "-I", str(HERE / name), *args]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def safe_media(rel):
    p = (ROOT / rel).resolve()
    try:
        p.relative_to(ROOT.resolve())
    except ValueError:
        return None
    if p.suffix.lower() not in MEDIA_EXT or not p.is_file():
        return None
    return p


def inside_root(rel):
    p = (ROOT / rel).resolve()
    try:
        p.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return p


def folder_signature():
    """Cheap fingerprint of the music and ARTE folders: number of files + sum of dates. Changes if you add or touch something."""
    n = t = 0
    stack = [ROOT / d for d in ("published", "prereleased", "unreleased", "ARTE")]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                        t += zlib.crc32(e.path.encode("utf-8", "ignore"))  # renaming a folder changes the fingerprint
                    else:
                        n += 1
                        t += int(e.stat().st_mtime) + zlib.crc32(e.name.encode("utf-8", "ignore"))
        except OSError:
            pass
    return f"{n}-{t}"


def safe_name(x, default="mixtape"):
    import re
    x = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(x).replace("\n", " ")).strip(" .")
    return x or default


def log_decision(*row):
    import csv
    import time
    DATOS.mkdir(parents=True, exist_ok=True)
    new = not DECISIONES.exists()
    with LOCK, open(DECISIONES, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["tipo", "a", "b", "nota", "detalle", "fecha"])
        w.writerow([*row, time.strftime("%Y-%m-%d")])


def find_ffmpeg():
    import glob
    import shutil
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    for c in (C.APP / "ffmpeg", C.APP / "ffmpeg.exe", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
              "/snap/bin/ffmpeg", "C:/ffmpeg/bin/ffmpeg.exe"):
        if Path(c).is_file():
            return str(c)
    hits = glob.glob(str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/*/ffmpeg*/bin/ffmpeg.exe"))
    return hits[0] if hits else None


def reveal(p):
    """Opens the folder (or reveals the file) in Explorer, Finder or the Linux file manager."""
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", str(p)] if p.is_file() else ["explorer", str(p)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p.parent if p.is_file() else p)])


IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".psd", ".ai", ".tif", ".tiff", ".svg"}
VID_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".aep", ".drp", ".prproj"}
AUD_EXT = C.AUDIO
STEMW = {"vocals": "vocal", "vocal": "vocal", "voice": "vocal", "voz": "vocal", "vox": "vocal", "drums": "drums", "drum": "drums",
         "bateria": "drums", "bass": "bass", "bajo": "bass", "guitar": "guitar", "guitars": "guitar", "guitarra": "guitar",
         "keys": "keys", "teclas": "keys", "synth": "synth", "strings": "strings", "backing": "backing", "percussion": "perc",
         "perc": "perc", "fx": "fx", "other": "other", "lead": "lead", "choir": "choir", "coro": "choir"}


def _words(n):
    import re
    import unicodedata
    n = "".join(c for c in unicodedata.normalize("NFD", n.lower()) if unicodedata.category(c) != "Mn")
    return [w for w in re.split(r"[^a-z0-9]+", n) if w]


def classify_drop(name, title, lote):
    """Returns (type, subfolder inside the song | None if it goes to ARTE)."""
    import re
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    own = set(_words(title))
    if ext in IMG_EXT:
        return "arte", None
    if ext in VID_EXT:
        return "vídeo", None
    if ext in AUD_EXT:
        tk = _words(stem)
        mine = [w for w in tk if w in STEMW and w not in own]
        if re.search(r"(^|[\s_.\-()])track[\s_\-]*\d+", stem, re.I):
            return "track suelto", "otros/tracks"
        if "stem" in tk or "stems" in tk:
            return "stem", "stems"
        if mine and "mixdown" not in tk:
            kinds = {STEMW[w] for n in (lote or []) for w in _words(os.path.splitext(n)[0]) if w in STEMW and w not in own}
            last = [w for w in tk if not w.isdigit()]
            if len(kinds) >= 2 or all(w in STEMW or w.isdigit() for w in tk) or (last and last[-1] in mine):
                return "stem", "stems"
        if re.search(r"master|masteriz|remaster", stem, re.I):
            return "máster", "master"
        return "versión", "versiones"
    if ext == ".sesx":
        return "sesión de Audition", "sesiones/" + safe_name(stem)
    if ext in (".zip", ".rar", ".7z"):
        return ("stems (comprimidos)", "stems") if re.search(r"stem", stem, re.I) else ("archivo comprimido", "otros")
    if ext in (".mid", ".midi"):
        return "MIDI", "midi"
    if ext in (".txt", ".docx", ".pdf", ".doc", ".rtf", ".md"):
        return "documento", "docs"
    return "otro archivo", "otros"


def mix_cache_dir(mixid):
    import re
    return ROOT / "MIXTAPES" / "_versiones" / re.sub(r"[^A-Za-z0-9_-]", "_", str(mixid or "sin_id"))


def mix_convert(mixid, sid, rel, kbps):
    """Creates (if it does not exist yet) the MP3 version of a song at the mixtape quality. Saved in MIXTAPES/_versiones/<mixtape>/."""
    import hashlib
    import re
    import subprocess
    src = (ROOT / rel).resolve()
    try:
        src.relative_to(ROOT.resolve())
    except ValueError:
        raise RuntimeError("ruta no válida")
    if not src.is_file():
        raise RuntimeError("no encuentro el audio de la canción")
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("No encuentro ffmpeg en este equipo.")
    kbps = int(kbps or 192)
    st = src.stat()
    key = hashlib.md5(f"{rel}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")).hexdigest()[:8]
    d = mix_cache_dir(mixid)
    d.mkdir(parents=True, exist_ok=True)
    sid_s = re.sub(r"[^A-Za-z0-9_-]", "_", str(sid))
    out = d / f"{sid_s}_{kbps}_{key}.mp3"
    if out.exists() and out.stat().st_size > 0:
        return out
    import uuid
    tmp = d / f"{out.stem}.{uuid.uuid4().hex[:8]}.tmp.mp3"
    r = subprocess.run([ff, "-y", "-i", str(src), "-vn", "-map_metadata", "-1", "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg falló: " + (r.stderr or "")[-200:])
    import time
    for intento in range(20):  # Dropbox or the antivirus may keep the just-created file open for a moment
        try:
            os.replace(tmp, out)
            break
        except PermissionError:
            if intento == 19:
                raise
            time.sleep(0.4)
    for old in d.glob(f"{sid_s}_*.mp3"):  # an old version of the same song (other quality or other file) is no longer valid
        if old != out and ".tmp." not in old.name:
            old.unlink(missing_ok=True)
    return out


def run_mixtape(jid, data):
    """Converts each song to MP3 (with lyrics in the tag) and builds the ZIP (HTML + Canciones/ + Letras/) or a single HTML."""
    import base64
    import mixtape_pkg
    lang = data.get("_lang", "es")
    T = (lambda x: modulos_core.traducir(x, lang)) if modulos_core else (lambda x: x)
    job = JOBS[jid]
    try:
        ff = find_ffmpeg()
        if not ff:
            raise RuntimeError("No encuentro ffmpeg en este equipo. Instálalo (ver LEEME) y vuelve a intentarlo.")
        songs = {x["id"]: x for x in json.loads(DATA.read_text(encoding="utf-8"))["songs"]}
        artist = CFG.get("artista") or ""
        name = safe_name(data.get("nombre") or "Mixtape")
        kbps = int(data.get("kbps") or 192)
        owner = (data.get("titular") or CFG.get("titular") or artist).strip()
        pd = data.get("portada") or ""
        try:
            cover = base64.b64decode(pd.split(",", 1)[1]) if pd.startswith("data:image/") and "," in pd else None
        except Exception:  # noqa: BLE001
            cover = None
        items = data.get("items") or []
        for i, it in enumerate(items, 1):
            src = inside_root(it.get("p", ""))
            if src is None:
                raise RuntimeError("ruta no válida")
            if it.get("id") not in songs or not src.is_file():
                raise RuntimeError(f"No encuentro el audio de la canción {i}")
        res = mixtape_pkg.construir(
            job, ff=ff, lang=lang, tr=T, songs=songs, items=items, base=ROOT / "MIXTAPES", name=name, nombre=data.get("nombre") or name,
            artist=artist, owner=owner, con_copy=bool(data.get("copyright", True)) and bool(owner), con_safe=bool(data.get("safe", False)),
            letras=bool(data.get("letras", True)), kbps=kbps, cover_bytes=cover, root=ROOT, safe_name=safe_name,
            convertir=lambda it: mix_convert(data.get("id"), it.get("id"), it.get("p", ""), kbps),
            ruta_letra=lambda song: inside_root(song["letra"]), onefile=bool(data.get("onefile", False)))
        job.update(estado="listo", **res)
    except Exception as e:  # noqa: BLE001
        job.update(estado="error", error=str(e))


def read_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- servidor
class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, reusing the address would let us "steal" a port another program is using: require exclusive use.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            import socket
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class H(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def allowed(self):
        """Only serves requests from this very page or from an authorized origin with its token (see modulos/_core/acceso.py)."""
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            return False
        return acceso.autorizar(self, AGENTE, PORT) if acceso else True

    def end_headers(self):  # the UI published on another website (authorized origin) may read the responses
        if acceso:
            for k, v in acceso.cabeceras_cors(self, AGENTE):
                self.send_header(k, v)
        super().end_headers()

    def do_OPTIONS(self):
        host = (self.headers.get("Host") or "").lower()
        if acceso and host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            return acceso.preflight(self, AGENTE)
        return self.send_error(HTTPStatus.FORBIDDEN)

    def do_GET(self):
        if not self.allowed():
            return self.send_error(HTTPStatus.FORBIDDEN)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if REG is not None:  # modules: list, static files and server routes
            if u.path == "/api/modulos":
                return self.send_json(REG.listar())
            if u.path.startswith("/mod/"):
                partes = unquote(u.path[5:]).split("/", 1)
                mp = REG.estatico(partes[0], partes[1]) if len(partes) == 2 else None
                if not mp:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                return self.file(mp, mimetypes.guess_type(mp.name)[0] or "application/octet-stream")
            if u.path.startswith("/api/mod/") and REG.despachar(self, "GET", self.path):
                return
        if u.path in ("/", "/index.html"):
            return self.file(HERE / "index.html", "text/html; charset=utf-8")
        if u.path == "/api/config":
            return self.send_json({"artista": CFG.get("artista", ""), "titular": CFG.get("titular", ""), "biblioteca": ROOT.name})
        if u.path == "/api/data":
            d = read_json(DATA, {"songs": []})
            return self.send_json({"songs": d["songs"], "state": read_json(STATE, {})})
        if u.path == "/api/firma":
            return self.send_json({"firma": folder_signature()})
        if u.path == "/api/mixtape_estado":
            return self.send_json(JOBS.get(q.get("id", [""])[0], {"estado": "desconocido"}))
        if u.path == "/api/archivos":
            song = self._song(q.get("id", [""])[0])
            out = []
            if song and song.get("dir"):
                base = ROOT / song["dir"].replace("\n", " ")
                skip = {"versiones", "master", "arte", "video"}
                for dp, _, fns in os.walk(base):
                    rel = Path(dp).relative_to(base).parts
                    role = rel[0] if rel else "otros"
                    if role in skip:
                        continue
                    for f in fns:
                        if f.lower() == "letra.txt" or f.startswith("."):
                            continue
                        fp = Path(dp) / f
                        try:
                            mb = round(fp.stat().st_size / 1e6, 1)
                        except OSError:
                            continue
                        out.append({"p": C.posix(fp.relative_to(ROOT)), "n": f, "role": role, "mb": mb})
                        if len(out) >= 800:
                            break
            return self.send_json(sorted(out, key=lambda x: (x["role"], x["n"].lower())))
        if u.path == "/api/letras":
            return self.send_json(read_json(LETRAS, {}))
        if u.path == "/api/medios":
            return self.send_json({"owners": read_json(MEDIOS, {"owners": []})["owners"], "state": read_json(MSTATE, {})})
        if u.path == "/thumb":
            p = THUMBS / Path(unquote(q.get("f", [""])[0])).name
            if not p.is_file():
                return self.send_error(HTTPStatus.NOT_FOUND)
            head = p.read_bytes()[:4]
            ctype = "image/png" if head.startswith(b"\x89PNG") else "image/gif" if head.startswith(b"GIF") else "image/webp" if head.startswith(b"RIFF") else "image/jpeg"
            return self.file(p, ctype)
        if u.path == "/api/letra":
            p = inside_root(unquote(q.get("f", [""])[0]))
            if p is None or p.suffix.lower() != ".txt":
                return self.send_error(HTTPStatus.FORBIDDEN)
            if not p.is_file():
                return self.send_error(HTTPStatus.NOT_FOUND)
            return self.file(p, "text/plain; charset=utf-8")
        if u.path.startswith("/assets/"):  # UI images (cassettes for mixtape covers)
            ap = (HERE / "assets" / unquote(u.path[len("/assets/"):])).resolve()
            try:
                ap.relative_to((HERE / "assets").resolve())
            except ValueError:
                return self.send_error(HTTPStatus.FORBIDDEN)
            if not ap.is_file() or ap.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".svg"):
                return self.send_error(HTTPStatus.NOT_FOUND)
            return self.file(ap, mimetypes.guess_type(ap.name)[0] or "image/jpeg")
        if u.path == "/descargar":  # download a mixtape ZIP (only inside MIXTAPES)
            dp = (ROOT / unquote(q.get("p", [""])[0])).resolve()
            try:
                dp.relative_to((ROOT / "MIXTAPES").resolve())
            except ValueError:
                return self.send_error(HTTPStatus.FORBIDDEN)
            if dp.suffix.lower() != ".zip" or not dp.is_file():
                return self.send_error(HTTPStatus.NOT_FOUND)
            return self.download(dp)
        if u.path == "/audio":
            p = safe_media(unquote(q.get("p", [""])[0]))
            if not p:
                return self.send_error(HTTPStatus.NOT_FOUND)
            return self.audio(p)
        self.send_error(HTTPStatus.NOT_FOUND)

    def unir(self, data):
        try:
            return self._unir(data)
        except Exception as ex:  # let the screen show the real reason instead of a silent error
            import traceback
            return self.send_json({"ok": False, "error": f"{type(ex).__name__}: {ex} · {traceback.format_exc().splitlines()[-3].strip()}"}, 500)

    def _unir(self, data):
        """Merges a "song" that is really part of another (stems, version…): moves its files and logs it."""
        import re
        songs = {s["id"]: s for s in read_json(DATA, {"songs": []})["songs"]}
        a, b = songs.get(data.get("desde")), songs.get(data.get("hacia"))
        if not a or not b or a["id"] == b["id"]:
            return self.send_json({"ok": False, "error": "canciones no válidas"}, 400)
        moved = 0
        if a.get("dir") and b.get("dir") and a["dir"] != b["dir"]:  # same folder: nothing to move
            r = run_script("mover_carpetas.py", f"{a['dir'].replace(chr(10), ' ')}={b['dir'].replace(chr(10), ' ')}", "--apply")
            if r.returncode != 0:
                return self.send_json({"ok": False, "error": (r.stderr or "")[-300:]}, 500)
            m = re.search(r"(\d+) archivos", r.stdout or "")
            moved = int(m.group(1)) if m else 0
        # if the absorbed entry has lyrics and the target song has none, it takes them (letra.txt next to the song)
        if a.get("letra") and not b.get("letra") and b.get("dir"):
            src_l = inside_root(a["letra"])
            dst_l = ROOT / b["dir"].replace("\n", " ") / "letra.txt"
            if src_l and src_l.is_file() and not dst_l.exists():
                dst_l.parent.mkdir(parents=True, exist_ok=True)
                dst_l.write_text(src_l.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        log_decision("unir", a["id"], b["id"], "unir", f"{a['title']} -> {b['title']}".replace("\n", " "))
        run_script("build_data.py")
        return self.send_json({"ok": True, "movidos": moved})

    def abrir(self, data):
        p = inside_root(data.get("p", ""))
        if p is None:
            return self.send_json({"ok": False}, 403)
        if not p.exists():
            return self.send_json({"ok": False, "error": "no existe"}, 404)
        try:
            reveal(p)
        except OSError as ex:
            return self.send_json({"ok": False, "error": str(ex)}, 500)
        return self.send_json({"ok": True})

    def mover_version(self, data):
        """Moves a file to the versiones/ folder of another song (journaled, undoable)."""
        import time
        songs = {s["id"]: s for s in read_json(DATA, {"songs": []})["songs"]}
        dest = songs.get(data.get("hacia"))
        src = inside_root(data.get("p", ""))
        if src is None:
            return self.send_json({"ok": False}, 403)
        if not dest or not dest.get("dir") or not src.is_file():
            return self.send_json({"ok": False, "error": "canción o archivo no válidos"}, 400)
        folder = ROOT / dest["dir"].replace("\n", " ") / "versiones"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / src.name
        n = 2
        while target.exists():
            target = folder / f"{src.stem} ({n}){src.suffix}"
            n += 1
        DATOS.mkdir(parents=True, exist_ok=True)
        with LOCK:
            nid = (sum(1 for _ in open(DIARIO, encoding="utf-8")) if DIARIO.exists() else 0) + 1
            os.rename(src, target)
            with open(DIARIO, "a", encoding="utf-8") as j:
                j.write(json.dumps({"id": nid, "t": time.strftime("%Y-%m-%d %H:%M:%S"), "op": "move",
                                    "src": C.posix(src.relative_to(ROOT.resolve())), "dst": C.posix(target.relative_to(ROOT.resolve())),
                                    "song": "(movido desde el gestor)"}, ensure_ascii=False) + "\n")
        run_script("build_data.py")
        return self.send_json({"ok": True})

    def _song(self, sid):
        return {x["id"]: x for x in read_json(DATA, {"songs": []})["songs"]}.get(sid)

    def letra_guardar(self, data):
        """Saves lyrics typed or pasted in the app as letra.txt in the song folder (the previous one goes to docs/)."""
        import time
        song = self._song(data.get("id"))
        texto = (data.get("texto") or "").replace("\r\n", "\n").strip()
        if not song or not texto or not song.get("dir"):
            return self.send_json({"ok": False, "error": "falta la canción o el texto"}, 400)
        title = song["title"].replace("\n", " ")
        if not texto.lower().startswith(title.lower()):
            texto = f"{title}\n\n{texto}"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        with LOCK:
            d = ROOT / song["dir"].replace("\n", " ")
            d.mkdir(parents=True, exist_ok=True)
            f = d / "letra.txt"
            if f.exists() and f.read_text(encoding="utf-8", errors="ignore").strip() != texto.strip():
                (d / "docs").mkdir(exist_ok=True)
                os.replace(f, d / "docs" / f"letra_anterior_{stamp}.txt")
            f.write_text(texto + "\n", encoding="utf-8")
        run_script("build_data.py")
        return self.send_json({"ok": True})

    def subir(self):
        """Receives an artwork/video file and saves it in the song or album folder."""
        import re
        q = parse_qs(urlparse(self.path).query)
        song = self._song(q.get("id", [""])[0])
        ambito = q.get("ambito", ["cancion"])[0]
        akey = unquote(q.get("key", [""])[0]).strip()
        if akey.startswith("unreleased/") and akey.count("/") == 1 and ".." not in akey:  # new album with no songs yet
            song = {"id": "", "dir": akey}
            ambito = "album-key"
        name = os.path.basename(unquote(q.get("nombre", [""])[0]))
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
        ext = os.path.splitext(name)[1].lower()
        img = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".psd", ".ai", ".tif", ".tiff"}
        vid = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".aep", ".drp", ".prproj"}
        if not song or not song.get("dir") or not name or ext not in img | vid:
            return self.send_json({"ok": False, "error": "tipo de archivo no admitido"}, 400)
        import arte_map as am
        parts = akey.split("/") if ambito == "album-key" else song["dir"].replace("\n", " ").split("/")
        projects = {parts[1]} if (len(parts) == 3 or ambito == "album-key") and parts[0] == "unreleased" else set()
        if ambito == "album":
            parts = parts[:-1]
            if not am.is_album_owner(parts, projects):
                return self.send_json({"ok": False, "error": "esta canción no pertenece a un álbum"}, 400)
        base_parts = am.base_for(parts, projects)
        if not base_parts:
            return self.send_json({"ok": False, "error": "no sé dónde guardarlo"}, 400)
        names = am.ALB if ambito in ("album", "album-key") else am.SONG
        folder = ROOT.joinpath("ARTE", *base_parts, names["arte"] if ext in img else names["video"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        n = 2
        while target.exists():
            target = folder / f"{os.path.splitext(name)[0]} ({n}){ext}"
            n += 1
        left = int(self.headers.get("Content-Length", 0))
        with open(target, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            target.unlink(missing_ok=True)
            return self.send_json({"ok": False, "error": "subida incompleta"}, 400)
        run_script("build_medios.py")
        return self.send_json({"ok": True, "p": C.posix(target.relative_to(ROOT))})

    def refrescar(self, data):
        """Re-reads the folders: new audio, new songs, new artwork and video."""
        for sc in ("build_data.py", "build_medios.py"):
            run_script(sc)
        return self.send_json({"ok": True, "firma": folder_signature()})

    def mix_convertir(self, data):
        try:
            out = mix_convert(data.get("mixid"), data.get("id"), data.get("p", ""), data.get("kbps") or 192)
        except Exception as ex:  # noqa: BLE001
            return self.send_json({"ok": False, "error": str(ex)}, 500)
        return self.send_json({"ok": True, "mb": round(out.stat().st_size / 1e6, 1)})

    def mix_borrar(self, data):
        """Deletes a mixtape's working MP3s (or those of one song in it). Never touches your music or the ZIPs."""
        import re
        import shutil
        d = mix_cache_dir(data.get("mixid"))
        if d.is_dir():
            if data.get("id"):
                for f in d.glob(re.sub(r"[^A-Za-z0-9_-]", "_", str(data["id"])) + "_*.mp3"):
                    f.unlink(missing_ok=True)
            else:
                shutil.rmtree(d, ignore_errors=True)
        return self.send_json({"ok": True})

    def album_crear(self, data):
        """Creates the folder of a new album (unreleased/<name>). Songs are added to it later without moving them."""
        nombre = safe_name(data.get("nombre") or "", "Álbum nuevo")
        (ROOT / "unreleased" / nombre).mkdir(parents=True, exist_ok=True)
        return self.send_json({"ok": True, "nombre": nombre})

    def album_borrar(self, data):
        """Removes an album folder only if it is empty. Never deletes files."""
        nombre = safe_name(data.get("nombre") or "", "")
        d = ROOT / "unreleased" / nombre if nombre else None
        if d is not None and d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
        return self.send_json({"ok": True})

    def mixtape(self, data):
        import uuid
        if not data.get("items"):
            return self.send_json({"ok": False, "error": "El mixtape está vacío"}, 400)
        jid = uuid.uuid4().hex[:8]
        data["_lang"] = modulos_core.idioma_de(self) if modulos_core else "es"
        JOBS[jid] = {"estado": "empezando", "done": 0, "total": len(data["items"])}
        threading.Thread(target=run_mixtape, args=(jid, data), daemon=True).start()
        return self.send_json({"ok": True, "id": jid})

    def soltar(self):
        """Receives a file dropped on a song, classifies it and puts it in its place."""
        import hashlib
        import re
        q = parse_qs(urlparse(self.path).query)
        nueva = unquote(q.get("nueva", [""])[0]).strip()
        if nueva:  # song that does not exist yet: its folder is created (unreleased/ or prereleased/) and the manager picks it up on refresh
            donde = q.get("donde", ["unreleased"])[0]
            donde = donde if donde in ("unreleased", "prereleased") else "unreleased"
            carpeta = safe_name(nueva, "canción nueva")
            song = {"id": "N" + hashlib.md5(f"{donde}/{carpeta}".encode("utf-8")).hexdigest()[:6], "title": nueva,
                    "dir": f"{donde}/{carpeta}", "letra": "x" if (ROOT / donde / carpeta / "letra.txt").exists() else ""}
        else:
            song = self._song(q.get("id", [""])[0])
        name = os.path.basename(unquote(q.get("nombre", [""])[0]))
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
        try:
            lote = json.loads(unquote(q.get("lote", ["[]"])[0]))
        except ValueError:
            lote = []
        left = int(self.headers.get("Content-Length", 0))
        if not song or not name:
            return self.send_json({"ok": False, "error": "canción o archivo no válidos"}, 400)
        title = song["title"].replace("\n", " ")
        tipo, sub = classify_drop(name, title, lote)
        ext = os.path.splitext(name)[1].lower()
        base = ROOT / (song["dir"].replace("\n", " ") if song.get("dir") else f"unreleased/{safe_name(title)}")
        if sub is None:  # artwork / video -> ARTE folder
            import arte_map as am
            parts = song["dir"].replace("\n", " ").split("/") if song.get("dir") else ["unreleased", safe_name(title)]
            projects = {parts[1]} if len(parts) == 3 and parts[0] == "unreleased" else set()
            bp = am.base_for(parts, projects)
            if not bp:
                return self.send_json({"ok": False, "error": "no sé dónde guardarlo"}, 400)
            folder = ROOT.joinpath("ARTE", *bp, am.SONG["arte"] if ext in IMG_EXT else am.SONG["video"])
        else:
            folder = base.joinpath(*sub.split("/"))
        # a loose lyrics file (.txt) on a song without lyrics becomes its lyrics
        as_lyric = ext == ".txt" and not song.get("letra") and left < 400_000
        if as_lyric:
            raw = self.rfile.read(left)
            try:
                texto = raw.decode("utf-8")
            except UnicodeDecodeError:
                texto = raw.decode("latin-1")
            texto = texto.replace("\r\n", "\n").strip()
            if texto and not texto.lower().startswith(title.lower()):
                texto = f"{title}\n\n{texto}"
            base.mkdir(parents=True, exist_ok=True)
            with LOCK:
                (base / "letra.txt").write_text(texto + "\n", encoding="utf-8")
            return self.send_json({"ok": True, "tipo": "letra", "id": song["id"], "destino": C.posix((base / "letra.txt").relative_to(ROOT))})
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        n = 2
        while target.exists():
            target = folder / f"{os.path.splitext(name)[0]} ({n}){ext}"
            n += 1
        with open(target, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            target.unlink(missing_ok=True)
            return self.send_json({"ok": False, "error": "subida incompleta"}, 400)
        return self.send_json({"ok": True, "tipo": tipo, "id": song["id"], "destino": C.posix(target.relative_to(ROOT))})

    def do_POST(self):
        if not self.allowed():
            return self.send_error(HTTPStatus.FORBIDDEN)
        if REG is not None and urlparse(self.path).path.startswith("/api/mod/") and REG.despachar(self, "POST", self.path):
            return
        path = urlparse(self.path).path
        if path == "/api/soltar":
            return self.soltar()
        if path == "/api/subir":
            return self.subir()
        route = {"/api/refrescar": self.refrescar, "/api/mixtape": self.mixtape, "/api/album_crear": self.album_crear, "/api/album_borrar": self.album_borrar, "/api/mix_convertir": self.mix_convertir, "/api/mix_borrar": self.mix_borrar, "/api/letra_guardar": self.letra_guardar,
                 "/api/abrir": self.abrir, "/api/mover_version": self.mover_version, "/api/unir": self.unir}.get(path)
        if route:
            n = int(self.headers.get("Content-Length", 0))
            try:
                return route(json.loads(self.rfile.read(n).decode("utf-8")))
            except ValueError:
                return self.send_error(HTTPStatus.BAD_REQUEST)
        target = {"/api/state": STATE, "/api/medios_estado": MSTATE}.get(path)
        if target is None:
            return self.send_error(HTTPStatus.NOT_FOUND)
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return self.send_error(HTTPStatus.BAD_REQUEST)
        with LOCK:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, target)
        self.send_json({"ok": True})

    def file(self, p, ctype):
        b = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def download(self, p):
        import re as _re
        from urllib.parse import quote
        size = p.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(size))
        ascii_name = _re.sub(r"[^A-Za-z0-9._ -]", "_", p.name)
        self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(p.name)}")
        self.end_headers()
        try:
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def audio(self, p):
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "audio/wav"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        code = 200
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            try:
                start = int(a) if a else max(0, size - int(b))
                end = int(b) if (a and b) else size - 1
            except ValueError:
                start, end = 0, size - 1
            end = min(end, size - 1)
            code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


# ---------------------------------------------------------------- primera vez
def ask_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        p = filedialog.askdirectory(title="Elige la carpeta de tu biblioteca de música (puede estar vacía)")
        r.destroy()
        if p:
            return p
    except Exception:  # noqa: BLE001  (no tkinter or no display: ask in the terminal)
        pass
    try:
        return input("Escribe o arrastra aquí la carpeta de tu biblioteca de música y pulsa Enter: ").strip().strip('"').strip("'")
    except EOFError:
        return ""


def setup(force=False):
    cfg = C.load_config()
    arg = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--biblioteca=")), "")
    if arg:
        cfg["biblioteca"] = arg
    need = force or not cfg.get("biblioteca") or not Path(cfg["biblioteca"]).expanduser().is_dir()
    if need:
        print("\n=== Primera configuración ===")
        while True:
            p = ask_folder()
            if p and Path(p).expanduser().is_dir():
                cfg["biblioteca"] = str(Path(p).expanduser().resolve())
                break
            print("Esa carpeta no existe. Inténtalo de nuevo.")
        try:
            cfg["artista"] = input(f"Tu nombre artístico [{cfg.get('artista', '')}]: ").strip() or cfg.get("artista", "")
            cfg["titular"] = input(f"Titular del copyright, para los mixtapes [{cfg.get('titular') or cfg['artista']}]: ").strip() or cfg.get("titular") or cfg["artista"]
        except EOFError:
            pass
        C.save_config(cfg)
    elif arg:
        C.save_config(cfg)
    return cfg


def cambiar_biblioteca(ruta):
    """Switches the library folder live: saved in config.json and everything is re-read."""
    global ROOT
    p = Path(str(ruta)).expanduser().resolve()
    if not p.is_dir():
        raise ValueError("esa carpeta no existe")
    CFG["biblioteca"] = str(p)
    C.save_config(CFG)
    ROOT = p
    C.layout_dirs(ROOT)
    if REG is not None:
        REG.ctx_base["root"] = ROOT
    for sc in ("build_data.py", "build_medios.py"):
        run_script(sc)
    return str(p)


def main():
    global CFG, ROOT, PORT, REG, AGENTE
    CFG = setup(force="--setup" in sys.argv)
    ROOT = C.root()
    C.layout_dirs(ROOT)
    DATOS.mkdir(parents=True, exist_ok=True)
    if not DATA.exists():
        print("Leyendo tu biblioteca…")
        run_script("build_data.py")
        run_script("build_medios.py")
    if modulos_core:
        AGENTE = acceso.cargar(DATOS)

        def songs():
            return read_json(DATA, {"songs": []})["songs"]
        REG = modulos_core.Registro(MODDIR, dict(root=ROOT, datos=DATOS, cfg=CFG, songs=songs, song=lambda sid: next((x for x in songs() if x["id"] == sid), None),
                                                 ffmpeg=find_ffmpeg, safe_name=safe_name, run_script=run_script, modulos=MODDIR, agente=AGENTE,
                                                 guardar_cfg=lambda d: (CFG.update(d), C.save_config(CFG)), cambiar_biblioteca=cambiar_biblioteca))
        REG.cargar()
        print("Módulos cargados:", ", ".join(REG.mods) or "ninguno")
        if AGENTE.get("web"):  # link to pair the published website with this agent (opens in the browser)
            print(f"Enlace de emparejamiento: {AGENTE['web'].rstrip('/')}/#agente=http://127.0.0.1:{PORT}&token={AGENTE['token']}")
    srv = None
    for port in range(int(CFG.get("puerto") or 8765), int(CFG.get("puerto") or 8765) + 20):
        try:
            PORT = port
            srv = Servidor(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if srv is None:
        print("No he podido abrir ningún puerto libre. Cierra otros programas y vuelve a intentarlo.")
        return 1
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Gestor de música en {url}  (cierra esta ventana o pulsa Ctrl+C para parar)")
    print(f"Biblioteca: {ROOT}")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
