"""Módulo «Importar»: ayuda a organizar música repartida por carpetas COPIÁNDOLA a la biblioteca.

Reglas que este archivo cumple siempre:
  · La carpeta de origen se abre SOLO para leer (nunca se escribe, mueve ni borra nada en ella).
  · En la biblioteca solo se crean carpetas/archivos NUEVOS (si el nombre existe se añade « (2)»); nunca se sobrescribe.
  · «Deshacer» solo borra archivos que esa importación creó y que siguen idénticos a lo copiado.
Todo con la biblioteca estándar de Python. Los trabajos largos van en hilos y se consultan por sondeo (GET estado?job=).
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
from pathlib import Path

# ───────────────────────── constantes ─────────────────────────
DAWS = {".als": "Ableton Live", ".alp": "Ableton Live", ".flp": "FL Studio", ".logicx": "Logic Pro", ".logic": "Logic Pro",
        ".cpr": "Cubase", ".npr": "Nuendo", ".rpp": "Reaper", ".ptx": "Pro Tools", ".ptf": "Pro Tools", ".song": "Studio One",
        ".band": "GarageBand", ".reason": "Reason", ".bwproject": "Bitwig", ".aup3": "Audacity", ".sesx": "Audition"}
PAQUETES = {".logicx", ".logic", ".band"}                       # en Mac son carpetas que se comportan como un archivo
AUDIO_GESTOR = {".wav", ".mp3", ".m4a", ".flac", ".aif", ".aiff"}  # lo que el gestor sabe catalogar y reproducir
AUDIO = AUDIO_GESTOR | {".ogg", ".opus", ".aac", ".wma", ".amr", ".caf", ".3gp"}
MIDI = {".mid", ".midi"}
TEXTO = {".txt", ".md"}
DOCS = {".doc", ".docx", ".odt", ".pdf", ".rtf"}
IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
VIDEO = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
BASURA = {".asd", ".reapeaks", ".pkf", ".peak", ".bak", ".tmp", ".ds_store", ".cfa", ".sfk", ".db", ".ini", ".lnk", ".icloud"}
CARPETAS_SALTAR = {"system volume information", "$recycle.bin", "__macosx", "node_modules", "recycler", "lost+found"}
CONVENCIONALES = {"samples", "audio", "audio files", "backup", "backups", "freeze", "freezes", "media", "bounces", "ableton project info",
                  "recorded", "imported", "project files", "waves", "autosave", "auto-backup", "freeze files", "renders", "export", "exports"}
LISTABLES = re.compile(r"^(bounces?|bounced files|exports?|exported|renders?|rendered|mixes|mixdowns?|mezclas?|versiones|versions|masters?|mastering|"
                       r"stems?|pistas|tracks|multitracks?|multipistas?|tomas|takes|directos?|live|conciertos?|ensayos?|bocetos?|demos?|ideas|"
                       r"final|finales|musica|letras?|docs?|midi)$")
EXCLUIDAS_LIGERAS = re.compile(r"^(backups?|freezes?|freeze files|bounced files|cach[eé]s?|peaks?|auto-?backup|autosaves?|time machine|undo|temp|tmp|"
                               r".*\.nosync|ableton cache|.*cache)$", re.I)

LARGO_DIRECTO = 15 * 60       # segundos: un audio más largo suele ser un directo o un ensayo
CORTO_BOCETO = 30             # segundos: un audio más corto suele ser una idea
LIMITE_COMPLETO = int(os.environ.get("GESTOR_IMPORTAR_LIMITE_COMPLETO", 2 * 1024 ** 3))  # por encima: verificación por muestreo
BLOQUE = 4 * 1024 * 1024
MARGEN_ESPACIO = 64 * 1024 * 1024

JOBS = {}
_LOCK = threading.RLock()
_JLOCK = threading.Lock()


class Cancelado(Exception):
    pass


class Rechazado(ValueError):
    """Archivo que NO debe copiarse (fuera del origen, enlace…): no se reintenta."""


# ───────────────────────── utilidades ─────────────────────────
def _lp(p):
    """Ruta larga de Windows (más de 260 caracteres); en Mac/Linux no hace nada."""
    p = str(p)
    if os.name != "nt":
        return p
    p = os.path.abspath(p)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def _plano(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s)


def _clave(s):
    return re.sub(r"[^a-z0-9]+", "", _plano(s))


def _vista(s):
    """Texto seguro para enviar por JSON (nombres con bytes raros)."""
    return str(s).encode("utf-8", "replace").decode("utf-8")


def _ext(n):
    return os.path.splitext(n)[1].lower()


def _seguro(n, mx=120, archivo=False):
    n = re.sub("[\ud800-\udfff]", "_", str(n))
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", n)
    ext = ""
    if archivo:
        stem, ext = os.path.splitext(n)
        if len(ext) > 12:
            stem, ext = n, ""
        n = stem
    n = n.strip(" .") or "sin nombre"
    if re.match(r"^(con|prn|aux|nul|com\d|lpt\d)$", n, re.I):
        n = "_" + n
    return n[:mx].rstrip(" .") + ext


def _fmt_bytes(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def _oculta(e):
    if e.name.startswith("."):
        return True
    if os.name == "nt":
        try:
            return bool(e.stat(follow_symlinks=False).st_file_attributes & 6)  # oculto o de sistema
        except (OSError, AttributeError):
            return False
    return False


def _jdiario(ctx):
    return Path(ctx.datos) / "diario.jsonl"


def _escribir_diario(ctx, obj):
    with _JLOCK:
        with open(_jdiario(ctx), "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


# ───────────────────────── explorador de carpetas ─────────────────────────
def _unidades():
    out = []
    if os.name == "nt":
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if mask & (1 << i):
                    letra = chr(65 + i)
                    tipo = ctypes.windll.kernel32.GetDriveTypeW(f"{letra}:\\")
                    if tipo in (2, 3, 4, 6):  # extraíble, fijo, red, RAM (se salta el lector de CD)
                        out.append({"n": f"Unidad {letra}:" + (" (externa)" if tipo == 2 else " (red)" if tipo == 4 else ""), "ruta": f"{letra}:\\"})
        except Exception:  # noqa: BLE001
            out = [{"n": f"Unidad {c}:", "ruta": f"{c}:\\"} for c in "CDEFGH" if os.path.isdir(f"{c}:\\")]
    else:
        out.append({"n": "Todo el equipo (/)", "ruta": "/"})
        for base in ("/Volumes", "/media", "/mnt", "/run/media"):
            try:
                for d in sorted(Path(base).iterdir()):
                    if d.is_dir() and not d.name.startswith("."):
                        if base in ("/media", "/run/media"):
                            for dd in sorted(d.iterdir()):
                                if dd.is_dir():
                                    out.append({"n": f"Disco «{dd.name}»", "ruta": str(dd)})
                        else:
                            out.append({"n": f"Disco «{d.name}»", "ruta": str(d)})
            except OSError:
                pass
    return out


def _atajos():
    h = Path.home()
    out = [{"n": "Mi carpeta personal", "ruta": str(h)}]
    for nombres, etiqueta in ((("Music", "Música"), "Música"), (("Documents", "Documentos"), "Documentos"), (("Desktop", "Escritorio"), "Escritorio"),
                              (("Downloads", "Descargas"), "Descargas"), (("Dropbox",), "Dropbox")):
        for n in nombres:
            if (h / n).is_dir():
                out.append({"n": etiqueta, "ruta": str(h / n)})
                break
    return out


def carpetas(req, ctx):
    """GET carpetas?ruta=  → solo SUBCARPETAS (nombres), nunca el contenido de los archivos."""
    ruta = req.arg("ruta", "").strip()
    if not ruta:
        return req.send({"ok": True, "ruta": "", "migas": [], "padre": None, "unidades": _unidades(), "atajos": _atajos(), "subcarpetas": []})
    p = Path(ruta)
    if not p.is_dir():
        return req.send({"ok": False, "error": "Esa carpeta no existe o no se puede abrir."})
    subs, truncado = [], False
    try:
        with os.scandir(_lp(p)) as it:
            for e in it:
                try:
                    if e.is_dir() and not _oculta(e) and e.name.lower() not in CARPETAS_SALTAR:
                        n = _vista(e.name)
                        if "�" in n and n != e.name:
                            continue
                        subs.append({"n": n, "ruta": str(p / e.name)})
                except OSError:
                    continue
                if len(subs) >= 3000:
                    truncado = True
                    break
    except OSError as ex:
        return req.send({"ok": False, "error": f"No tengo permiso para abrir esa carpeta ({ex.strerror or ex})."})
    subs.sort(key=lambda x: x["n"].lower())
    migas, acum = [], None
    for parte in p.parts:
        acum = Path(parte) if acum is None else acum / parte
        migas.append({"n": parte.rstrip("\\/") or parte, "ruta": str(acum)})
    padre = str(p.parent) if p.parent != p else ""
    return req.send({"ok": True, "ruta": str(p), "migas": migas, "padre": padre, "subcarpetas": subs, "truncado": truncado})


# ───────────────────────── limpieza de títulos y heurísticas ─────────────────────────
_RUIDO = (r"mixdown|mix|mezcla|mezclado|master(?:ed|izado|izada|izacion)?|mastering|m[aá]ster|premaster|final(?:\s*mix)?|bounce[d]?|render(?:ed)?|export(?:ed)?|"
          r"demo|boceto|idea|rough|draft|borrador|take|toma|stems?|v\s?\d+|ver\s?\d+|versi[oó]n(?:\s?\d+)?|rev\s?\d+|copy|copia|nuevo|new|old|wip|"
          r"preview|test|prueba|edit|alt|instrumental|a?\s?cappella|acapella|letra|letras|lyrics|live|directo|ensayo|concierto|rehearsal|soundcheck|gig|\d+\s?bpm|\d+(?:\.\d+)?\s?k(?:hz)?|\d+\s?bit|\d+\s?kbps|-?\d+\s?lufs")
_RE_SUFIJO = re.compile(r"(?:[\s\-_.,]*[(\[]\s*\d+\s*[)\]]|[\s\-_.,(\[]+(?:" + _RUIDO + r")(?:[\s\-_.]*\d{1,3})?[\s)\]]*|\s*[(\[][^()\[\]]*?\b(?:" + _RUIDO + r")\b[^()\[\]]*[)\]])\s*$", re.I)
_RE_PREFIJO = re.compile(r"^\s*(?:demo|boceto|idea|draft|borrador|rough|wip)\s*[-:–_ ]+(?=\S)", re.I)
_RE_FECHA = re.compile(r"\b(?:19|20)\d{2}[-_. ]?[01]\d[-_. ]?[0-3]\d\b|\b[0-3]?\d[-_.][01]?\d[-_.](?:\d{4}|\d{2})\b|\bat \d{1,2}[.:]\d{2}[.:]\d{2}\b", re.I)
_RE_INDICE = re.compile(r"^\s*(?:\d{1,3}\s*[-.)_]\s*|\d{1,3}\s+)(?=\D)")
_GENERICOS = {"mix", "audio", "track", "pista", "untitled", "sintitulo", "nuevo", "new", "recording", "grabacion", "notadevoz", "voz", "master", "final",
              "bounce", "demo", "idea", "project", "proyecto", "song", "cancion", "nuevacancion", "newsong", "tema", "cancion", "export", "render", "stem",
              "stems", "bocetos", "bounces", "mixes", "mezclas", "version", "versiones", "samples", "music", "musica", "documentos", "documents", "escritorio",
              "desktop", "descargas", "downloads", "varios", "otros", "backup", "freeze", "copia", "carpetasintitulo", "nuevacarpeta", "newfolder", "directo", "live", "vocal", "vocals",
              "guitar", "guitarra", "bajo", "bass", "drums", "bateria", "piano", "keys", "synth", "pad", "lead", "fx", "click", "mono", "stereo", "sesion"}
_GEN_NUM = {"mix", "audio", "track", "pista", "untitled", "sintitulo", "nuevo", "new", "recording", "grabacion", "master", "final", "bounce", "demo", "idea", "export", "render",
           "stem", "version", "take", "toma", "project", "proyecto", "vocal", "vocals", "guitar", "guitarra", "bajo", "bass", "drums", "bateria", "piano", "keys", "synth", "pad", "lead", "fx"}
_RE_TELEFONO = re.compile(r"^(nota de voz|notas de voz|voice memo|voice note|voice|new recording|recording|grabacion|grabaciones|audio|aud|ptt|whatsapp audio|vn|rec|memo|record|"
                          r"sin titulo|untitled|sonido|audio nuevo|audio record)\b[\s\-_0-9().,a-z:]*$")
_RE_MASTER = re.compile(r"\b(master|mastered|masterizado|masterizada|masterizacion|mastering|premaster)\b")
_RE_STEM = re.compile(r"\b(stem|stems|pistas|multipista|multipistas|multitrack|multitracks)\b")
_RE_DIRECTO = re.compile(r"\b(live|directo|directos|en vivo|concierto|conciertos|concert|gig|ensayo|ensayos|rehearsal|soundcheck|actuacion|bolo)\b")
_RE_TOMA = re.compile(r"\b(take|takes|toma|tomas)\b")
_RE_BOCETO = re.compile(r"\b(demo|demos|boceto|bocetos|idea|ideas|sketch|rough|draft|borrador|borradores|scratch|esbozo|apunte|nota de voz|notas de voz|voice memo|voice note)\b")
_RE_MIX = re.compile(r"\b(mix|mixdown|mezcla|bounce|bounced|render|rendered|export|exported|final|v\d+|ver\d+|version)\b")
_RE_NOLETRA = re.compile(r"\b(readme|licen[cs]e|licencia|notes?|notas?|todo|info|credits?|creditos|contrato|contract|factura|invoice|splits?)\b")
_RE_FECHA_NOMBRE = re.compile(r"^\W*(?:(?:19|20)\d{2}[-_. ]?[01]\d[-_. ]?[0-3]\d|[0-3]?\d[-_.][01]?\d[-_.](?:\d{4}|\d{2}))")


def limpiar_titulo(nombre, texto=False):
    s = unicodedata.normalize("NFC", re.sub("[\ud800-\udfff]", "?", nombre))
    s = s.replace("_", " ")
    s = _RE_FECHA.sub(" ", s)
    s = _RE_INDICE.sub("", s)
    prev = None
    while prev != s:
        prev = s
        t = _RE_SUFIJO.sub("", s)
        if len(t.strip(" -_.,")) >= 2:
            s = t
        t = _RE_PREFIJO.sub("", s)
        if len(t.strip(" -_.,")) >= 2:
            s = t
    return re.sub(r"\s{2,}", " ", s).strip(" -_.,")


def es_generico(titulo):
    k = _clave(titulo)
    return len(k) < 2 or k.isdigit() or k in _GENERICOS or re.sub(r"\d+$", "", k) in _GEN_NUM or bool(_RE_TELEFONO.match(_plano(titulo).strip()))


def duracion_wav(ruta, tam):
    """Duración exacta de un WAV leyendo solo su cabecera. None si no se entiende."""
    try:
        with open(_lp(ruta), "rb") as f:
            cab = f.read(12)
            if len(cab) < 12 or cab[:4] not in (b"RIFF", b"RF64") or cab[8:12] != b"WAVE":
                return None
            byterate = data = None
            pos = 12
            while pos < tam and (byterate is None or data is None):
                f.seek(pos)
                h = f.read(8)
                if len(h) < 8:
                    break
                cid, n = h[:4], int.from_bytes(h[4:], "little")
                if cid == b"fmt ":
                    d = f.read(16)
                    byterate = int.from_bytes(d[8:12], "little") if len(d) >= 12 else None
                elif cid == b"data":
                    data = n if n != 0xFFFFFFFF else max(0, tam - pos - 8)
                    break
                pos += 8 + n + (n & 1)
            if byterate and data is not None:
                return data / byterate
    except OSError:
        return None
    return None


BYTES_POR_SEG = {".mp3": 16000, ".m4a": 12000, ".aac": 12000, ".ogg": 12000, ".opus": 8000, ".wma": 16000, ".amr": 1600, ".3gp": 4000, ".caf": 176400,
                 ".flac": 88000, ".aif": 176400, ".aiff": 176400, ".wav": 176400}


def duracion(ruta, tam, ext):
    if ext == ".wav":
        d = duracion_wav(ruta, tam)
        if d is not None:
            return d, False
    return tam / BYTES_POR_SEG.get(ext, 16000), True


def _fmt_dur(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def clasificar_audio(f, antepasados):
    """→ (categoría, motivo). `antepasados`: nombres (planos) de las carpetas que contienen el archivo, dentro del origen."""
    n = _plano(os.path.splitext(f["nombre"])[0]).replace("_", " ")
    dur, est = f.get("dur"), f.get("est")
    a = lambda rx: next((x for x in antepasados if rx.search(x)), None)  # noqa: E731
    if _RE_MASTER.search(n):
        return "master", "el nombre incluye «master»"
    d = next((x for x in antepasados if re.match(r"^(masters?|mastering|masterizado|masterizados)$", x)), None)
    if d:
        return "master", f"está en una carpeta «{d}»"
    if _RE_STEM.search(n):
        return "stem", "el nombre incluye «stem/pistas»"
    d = a(_RE_STEM)
    if d:
        return "stem", f"está en la carpeta «{d}»"
    if _RE_DIRECTO.search(n):
        return "directo", "el nombre indica directo/ensayo"
    d = a(_RE_DIRECTO)
    if d:
        return "directo", f"está en la carpeta «{d}»"
    if dur and dur >= LARGO_DIRECTO:
        return "directo", f"dura {'≈' if est else ''}{_fmt_dur(dur)}: un audio tan largo suele ser un directo o un ensayo"
    if dur and dur >= 8 * 60 and _RE_FECHA_NOMBRE.match(n):
        return "directo", f"nombre con fecha y duración larga ({'≈' if est else ''}{_fmt_dur(dur)})"
    if _RE_TOMA.search(n) or a(re.compile(r"^(tomas|takes)$")):
        return "toma", "el nombre o su carpeta habla de «tomas»"
    if _RE_BOCETO.search(n):
        return "boceto", "el nombre indica boceto/demo/idea/nota de voz"
    d = a(re.compile(r"^(bocetos?|demos?|ideas|borradores|notas de voz|voice memos?)$"))
    if d:
        return "boceto", f"está en la carpeta «{d}»"
    if _RE_TELEFONO.match(n.strip()):
        return "boceto", "su nombre es típico de una nota de voz del móvil"
    if _RE_MIX.search(n):
        return "version", "el nombre incluye mix/bounce/final/versión"
    if dur is not None and dur < CORTO_BOCETO:
        return "boceto", f"dura solo {'≈' if est else ''}{_fmt_dur(dur)}: parece una idea corta"
    if f["ext"] in (".m4a", ".amr", ".3gp", ".caf", ".opus"):
        return "boceto", f"formato {f['ext']}: suele ser una grabación de móvil"
    return "version", "audio sin marcas especiales: lo propongo como versión"


# ───────────────────────── escaneo ─────────────────────────
def _nuevo_job(tipo):
    j = {"id": uuid.uuid4().hex[:10], "tipo": tipo, "estado": "corriendo", "cancel": threading.Event(), "inicio": time.time(), "avisos": [], "error": ""}
    with _LOCK:
        JOBS[j["id"]] = j
        viejos = [k for k, v in JOBS.items() if v["estado"] != "corriendo" and v is not j]
        for k in viejos[:-6]:
            JOBS.pop(k, None)
    return j


def _publico(j):
    ocultar = {"cancel", "res", "rutas", "sesiones_srv", "origen_real", "plan", "usados", "res_origen", "proyectos", "lista"}
    d = {k: v for k, v in j.items() if k not in ocultar}
    d["avisos"] = [str(a) for a in j["avisos"][-25:]]
    d["n_avisos"] = len(j["avisos"])
    d["seg"] = round((j.get("fin") or time.time()) - j["inicio"], 1)
    return d


def estado(req, ctx):
    j = JOBS.get(req.arg("job"))
    if not j:
        return req.send({"ok": False, "error": "No encuentro esa tarea (¿se reinició el gestor?)."})
    return req.send({"ok": True, **_publico(j)})


def _medir_dir(S, P, absdir, excl=False, profundidad=0):
    """Suma el tamaño de una carpeta de proyecto/paquete (sin enlaces simbólicos)."""
    if S["cancel"].is_set():
        raise Cancelado()
    try:
        with os.scandir(_lp(absdir)) as it:
            for e in it:
                try:
                    if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                        S["enlaces"] += 1
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if profundidad < 40:
                            _medir_dir(S, P, os.path.join(absdir, e.name), excl or bool(EXCLUIDAS_LIGERAS.match(e.name)), profundidad + 1)
                    elif e.is_file(follow_symlinks=False):
                        t = e.stat(follow_symlinks=False).st_size
                        P["tam"] += t
                        P["n"] += 1
                        if not excl and _ext(e.name) not in BASURA:
                            P["tam_ligero"] += t
                        S["archivos"] += 1
                        S["bytes"] += t
                except OSError:
                    continue
    except OSError as ex:
        S["avisos"].append(f"No pude leer «{_vista(absdir)}»: {ex.strerror or ex}")


def _contabilizar(P, tam, nombre, excl):
    P["tam"] += tam
    P["n"] += 1
    if not excl and _ext(nombre) not in BASURA:
        P["tam_ligero"] += tam


def _recorrer(S, absdir, partes, proj, modo, excl):
    if S["cancel"].is_set():
        raise Cancelado()
    S["carpetas"] += 1
    S["actual"] = _vista("/".join(partes[-3:]) or os.path.basename(S["origen"]) or S["origen"])
    try:
        with os.scandir(_lp(absdir)) as it:
            ents = list(it)
    except OSError as ex:
        S["avisos"].append(f"No pude leer la carpeta «{_vista('/'.join(partes) or absdir)}»: {ex.strerror or ex}")
        return
    ents.sort(key=lambda e: e.name.lower())
    archivos, dirs = [], []
    for e in ents:
        try:
            if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                S["enlaces"] += 1
                continue
            if e.is_dir(follow_symlinks=False):
                dirs.append(e)
            elif e.is_file(follow_symlinks=False):
                archivos.append(e)
        except OSError:
            continue

    # ¿hay proyectos de DAW en esta carpeta?
    lones = {}
    if modo is None:
        paquetes = [e for e in dirs if _ext(e.name) in PAQUETES]
        sesiones = [e for e in archivos if _ext(e.name) in DAWS]
        for e in paquetes:
            P = _nuevo_proyecto(S, DAWS[_ext(e.name)], "paquete", "/".join(partes + (e.name,)), os.path.splitext(e.name)[0], [e.name], e.name)
            _medir_dir(S, P, os.path.join(absdir, e.name))
        if sesiones:
            claves = {_clave(limpiar_titulo(os.path.splitext(e.name)[0])) for e in sesiones}
            nombres_sub = {_plano(e.name) for e in dirs}
            conv = bool(nombres_sub & CONVENCIONALES) or _plano(os.path.basename(absdir)).endswith(("project", "proyecto"))
            pocas = len([e for e in dirs if _ext(e.name) not in PAQUETES]) <= 8
            es_proj = len(claves) == 1 and (conv or (bool(partes) and pocas))
            if es_proj:
                nombre = os.path.basename(absdir) if partes else (os.path.basename(S["origen"].rstrip("\\/")) or "proyecto")
                proj = _nuevo_proyecto(S, DAWS[_ext(sesiones[0].name)], "carpeta", "/".join(partes), nombre, [e.name for e in sesiones], sesiones[0].name)
                proj["sesiones_extra"] = len(sesiones)
            else:
                for e in sesiones:
                    t = e.stat(follow_symlinks=False).st_size
                    P = _nuevo_proyecto(S, DAWS[_ext(e.name)], "suelto", "/".join(partes + (e.name,)), os.path.splitext(e.name)[0], [e.name], e.name)
                    P["tam"] = P["tam_ligero"] = t
                    P["n"] = 1
                    lones[e.name] = P

    for e in archivos:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        S["archivos"] += 1
        S["bytes"] += st.st_size
        ext = _ext(e.name)
        if proj is not None:
            _contabilizar(proj, st.st_size, e.name, excl)
        if e.name in lones or (ext in DAWS and proj is not None and proj.get("tipo") == "carpeta" and modo is None and ext in DAWS):
            continue  # el archivo de proyecto no se lista como archivo suelto: va como «sesión»
        if modo == "interno":
            if ext in AUDIO:
                proj["n_audio"] += 1
            continue
        if e.name.startswith(".") or ext in BASURA:
            S["basura"] += 1
            continue
        kind = ("audio" if ext in AUDIO else "midi" if ext in MIDI else "texto" if ext in TEXTO else "doc" if ext in DOCS
                else "img" if ext in IMG else "video" if ext in VIDEO else None)
        if not kind:
            S["ignorados"][ext or "(sin extensión)"] = S["ignorados"].get(ext or "(sin extensión)", 0) + 1
            continue
        fid = "f%d" % (len(S["lista"]) + 1)
        f = {"id": fid, "rel": "/".join(partes + (e.name,)), "nombre": e.name, "ext": ext, "tam": st.st_size, "mt": int(st.st_mtime), "kind": kind,
             "partes": partes, "proj": proj["id"] if proj else None}
        if kind == "audio":
            f["dur"], f["est"] = duracion(os.path.join(absdir, e.name), st.st_size, ext)
        S["lista"].append(f)
        S["rutas"][fid] = os.path.join(absdir, e.name)

    for d in dirs:
        nombre = d.name
        if (nombre.startswith(".") or nombre.lower() in CARPETAS_SALTAR or _oculta(d) or _ext(nombre) in PAQUETES):
            continue
        ruta = os.path.join(absdir, nombre)
        try:
            if os.path.realpath(ruta) == S["root_real"]:
                S["avisos"].append("He saltado tu propia biblioteca, que está dentro de esta carpeta.")
                continue
        except OSError:
            pass
        hijo_modo, hijo_excl = modo, excl or bool(EXCLUIDAS_LIGERAS.match(nombre))
        if proj is not None:
            if modo == "interno":
                hijo_modo = "interno"
            else:
                hijo_modo = None if LISTABLES.match(_plano(nombre)) else "interno"
        _recorrer(S, ruta, partes + (nombre,), proj, hijo_modo, hijo_excl)


def _nuevo_proyecto(S, daw, tipo, rel, nombre, principales, primer):
    P = {"id": "p%d" % (len(S["proyectos"]) + 1), "daw": daw, "tipo": tipo, "rel": rel, "nombre": nombre, "principales": principales, "primer": primer,
         "tam": 0, "tam_ligero": 0, "n": 0, "n_audio": 0}
    S["proyectos"].append(P)
    return P


def escanear(req, ctx):
    d = req.json()
    ruta = str(d.get("ruta", "")).strip().strip('"')
    p = Path(ruta).expanduser() if ruta else None
    if not p or not p.is_dir():
        return req.send({"ok": False, "error": "No encuentro esa carpeta. Compruébala o elígela con el explorador."})
    try:
        p = p.resolve()
        root = Path(ctx.root).resolve()
    except OSError as ex:
        return req.send({"ok": False, "error": str(ex)})
    if p == root or root in p.parents:
        return req.send({"ok": False, "error": "Esa carpeta está dentro de tu propia biblioteca. Elige la carpeta donde tienes la música SIN organizar."})
    j = _nuevo_job("escaneo")
    j.update(origen=str(p), root_real=os.path.realpath(root), carpetas=0, archivos=0, bytes=0, actual="", enlaces=0, basura=0, ignorados={}, lista=[],
             rutas={}, proyectos=[], fase="Leyendo carpetas")
    threading.Thread(target=_hilo_escaneo, args=(j,), daemon=True).start()
    return req.send({"ok": True, "job": j["id"]})


def _hilo_escaneo(j):
    try:
        _recorrer(j, j["origen"], (), None, None, False)
        j["fase"] = "Proponiendo una organización"
        j["res"] = _proponer(j)
        j["estado"] = "listo"
        for k in ("lista",):
            j.pop(k, None)
    except Cancelado:
        j["estado"] = "cancelado"
    except Exception as ex:  # noqa: BLE001
        import traceback
        print("[importar] error al escanear:\n" + traceback.format_exc())
        j["estado"] = "error"
        j["error"] = f"{type(ex).__name__}: {ex}"
    j["fin"] = time.time()


# ───────────────────────── propuesta de canciones ─────────────────────────
def _proponer(S):
    lista, proyectos = S["lista"], {p["id"]: p for p in S["proyectos"]}
    # 1) cada proyecto es una semilla de canción
    semillas = {}  # clave -> dict

    def semilla(clave, titulo, razon):
        s = semillas.get(clave)
        if not s:
            s = semillas[clave] = {"clave": clave, "titulos": {}, "archivos": [], "sesiones": [], "razones": []}
        s["titulos"][titulo] = s["titulos"].get(titulo, 0) + 1
        if razon and razon not in s["razones"]:
            s["razones"].append(razon)
        return s

    proj_clave = {}
    for P in S["proyectos"]:
        t = limpiar_titulo(os.path.splitext(P["primer"])[0])
        razon = f"proyecto de {P['daw']} «{_vista(P['primer'])}»"
        if es_generico(t):
            td = limpiar_titulo(P["nombre"])
            if not es_generico(td):
                t, razon = td, razon + " (el nombre del archivo es genérico: uso el de su carpeta)"
            else:
                t = t or "Proyecto sin título"
        c = _clave(t) or "proyecto"
        proj_clave[P["id"]] = c
        semilla(c, t, razon)["sesiones"].append(P["id"])

    # 2) archivos
    origen_nombre = os.path.basename(S["origen"].rstrip("\\/")) or "Canciones importadas"
    pendientes = []
    for f in lista:
        ant = [_plano(x) for x in f["partes"]]
        ant_ruta = list(f["partes"])
        f["motivo_cancion"] = ""
        if f["kind"] == "audio":
            f["cat"], f["motivo"] = clasificar_audio(f, ant)
        elif f["kind"] == "midi":
            f["cat"], f["motivo"] = "midi", "archivo MIDI"
        elif f["kind"] == "texto":
            n = _plano(f["nombre"])
            if _RE_NOLETRA.search(n):
                f["cat"], f["motivo"] = "doc", "texto que no parece una letra (notas/info): lo guardo en docs"
            else:
                f["cat"], f["motivo"] = "letra", "archivo de texto: lo propongo como letra"
        elif f["kind"] == "doc":
            f["cat"], f["motivo"] = "doc", "documento (el gestor solo lee la letra en .txt: se guarda en docs)"
        elif f["kind"] == "img":
            f["cat"], f["motivo"] = "arte", "imagen"
        else:
            f["cat"], f["motivo"] = "video", "vídeo"
        if f["ext"] not in AUDIO_GESTOR and f["kind"] == "audio":
            f["motivo"] += f" · formato {f['ext']} (el gestor no lo reproduce: va a «otros/audio»)"

        # ¿a qué canción pertenece?
        if f["proj"]:
            P = proyectos[f["proj"]]
            semillas[proj_clave[P["id"]]]["archivos"].append(f)
            f["motivo_cancion"] = f"está dentro de la carpeta del proyecto «{_vista(P['nombre'])}»"
            continue
        stem = os.path.splitext(f["nombre"])[0]
        es_texto = f["kind"] in ("texto", "doc")
        # carpeta de stems: la canción es la de la carpeta
        idx_stem = next((i for i, a in enumerate(ant) if _RE_STEM.search(a)), None)
        if f["cat"] == "stem" and idx_stem is not None:
            nombre_dir = re.sub(r"(?i)\b(stems?|pistas|multipistas?|multitracks?)\b", " ", ant_ruta[idx_stem])
            t = limpiar_titulo(nombre_dir)
            if es_generico(t):
                t = _titulo_de_carpetas(ant_ruta[:idx_stem])
            if t:
                f["motivo_cancion"] = f"está en una carpeta de stems: canción «{_vista(t)}»"
                pendientes.append((f, t, True))
                continue
        t = limpiar_titulo(stem, es_texto)
        if es_texto:
            t = re.sub(r"(?i)[\s\-_]*\b(letra|letras|lyrics|texto)\b\s*$", "", t).strip(" -_.")
        if f["cat"] == "boceto" and (es_generico(t) or _RE_TELEFONO.match(_plano(stem).strip())):
            pendientes.append((f, "Notas de voz y bocetos", "coleccion"))
            f["motivo_cancion"] = "boceto sin título propio: lo junto con las demás notas de voz"
            continue
        if es_generico(t):
            td = _titulo_de_carpetas(ant_ruta)
            if td:
                f["motivo_cancion"] = f"su nombre es genérico («{_vista(stem)}»): uso el de su carpeta"
                t = td
            else:
                t = origen_nombre
                f["motivo_cancion"] = "no hay ninguna pista en el nombre: uso el nombre de la carpeta de origen"
        else:
            f["motivo_cancion"] = "por el nombre del archivo"
        pendientes.append((f, t, False))

    # los no-audio con nombre genérico (portadas, fotos) siguen a la canción de su carpeta
    por_dir = {}
    for f, t, _x in pendientes:
        if f["kind"] == "audio":
            por_dir.setdefault(tuple(f["partes"]), {}).setdefault(_clave(t), 0)
            por_dir[tuple(f["partes"])][_clave(t)] += 1
    for f, t, especial in pendientes:
        if f["kind"] in ("img", "video", "doc", "midi") and not especial and es_generico(limpiar_titulo(os.path.splitext(f["nombre"])[0])):
            cand = por_dir.get(tuple(f["partes"]))
            if cand:
                k = max(cand, key=cand.get)
                f["motivo_cancion"] = "nombre genérico: lo pongo con los audios de su misma carpeta"
                semilla(k, t, "").setdefault("archivos", []).append(f)
                continue
        semilla(_clave(t) or "sin titulo", t, "")["archivos"].append(f)
        if especial == "coleccion":
            semillas[_clave(t)]["coleccion"] = True

    # 3) fundir parecidos
    claves = [k for k in semillas if not semillas[k].get("coleccion")]
    padre = {k: k for k in claves}

    def raiz(k):
        while padre[k] != k:
            padre[k] = padre[padre[k]]
            k = padre[k]
        return k
    cubos = {}
    for k in claves:
        cubos.setdefault(k[:2], []).append(k)
    fusiones = {}
    for k in claves:
        for k2 in [x for b in {k[:2]} for x in cubos.get(b, [])]:
            if k2 <= k or len(k) < 5 or len(k2) < 5 or raiz(k) == raiz(k2):
                continue
            if re.sub(r"\D", "", k) != re.sub(r"\D", "", k2):
                continue  # «Tema 1» y «Tema 2» NO son la misma canción
            if abs(len(k) - len(k2)) > max(3, len(k) // 3):
                continue
            r = difflib.SequenceMatcher(None, k, k2).ratio()
            if r >= 0.88:
                padre[raiz(k2)] = raiz(k)
                fusiones.setdefault(raiz(k), []).append((k2, r))
    grupos = {}
    for k in claves:
        grupos.setdefault(raiz(k), []).append(k)
    final = []
    for r, ks in grupos.items():
        base = semillas[r]
        for k2 in ks:
            if k2 == r:
                continue
            o = semillas[k2]
            for t, n in o["titulos"].items():
                base["titulos"][t] = base["titulos"].get(t, 0) + n
            base["archivos"] += o["archivos"]
            base["sesiones"] += o["sesiones"]
            sim = next((x for x in fusiones.get(r, []) if x[0] == k2), None)
            base["razones"].append(f"junto «{_vista(next(iter(o['titulos'])))}» porque el nombre es muy parecido" + (f" ({round(sim[1] * 100)} %)" if sim else ""))
        final.append(base)
    final += [semillas[k] for k in semillas if semillas[k].get("coleccion")]
    # canciones que solo tienen papeles/imágenes/MIDI (sin audio, sin letra ni sesión): se juntan aparte y se proponen sin marcar
    sueltas = [s for s in final if s["archivos"] and not s["sesiones"] and all(f["cat"] in ("doc", "arte", "video", "midi") for f in s["archivos"])]
    if sueltas:
        final = [s for s in final if s not in sueltas]
        todo = [f for s in sueltas for f in s["archivos"]]
        final.append({"clave": "__sueltos__", "titulos": {"Archivos sueltos sin canción": 1}, "archivos": todo, "sesiones": [], "sueltos": True,
                      "razones": ["no encontré ningún audio ni letra con el mismo nombre; los dejo sin marcar por si quieres asignarlos a una canción (con «Mover»)"]})

    # 4) duplicados exactos (mismo nombre y tamaño)
    vistos = {}
    canciones, n_arch = [], 0
    final.sort(key=lambda s: _plano(max(s["titulos"], key=lambda t: (s["titulos"][t], -len(t)))))
    for i, s in enumerate(final, 1):
        titulo = max(s["titulos"], key=lambda t: (s["titulos"][t], -len(t)))
        if s.get("coleccion"):
            titulo = "Notas de voz y bocetos"
        s["archivos"].sort(key=lambda f: (ORDEN_CAT.get(f["cat"], 99), f["nombre"].lower()))
        fl = []
        for f in s["archivos"]:
            cand_dup = f["kind"] == "audio" and f["tam"] > 100 * 1024
            dup = vistos.get((f["nombre"].lower(), f["tam"])) if cand_dup else None
            if dup is None and cand_dup:
                vistos[(f["nombre"].lower(), f["tam"])] = f["rel"]
            fl.append({"id": f["id"], "rel": _vista(f["rel"]), "nombre": _vista(f["nombre"]), "ext": f["ext"], "tam": f["tam"], "mt": f["mt"],
                       "dur": round(f["dur"]) if f.get("dur") is not None else None, "est": bool(f.get("est")), "cat": f["cat"], "motivo": f["motivo"],
                       "porque": f["motivo_cancion"], "excluir": bool(dup) or bool(s.get("sueltos")), "dup": _vista(dup) if dup else ""})
        n_arch += len(fl)
        audios = [f for f in fl if f["cat"] in ("version", "master", "stem", "directo", "boceto", "toma")]
        boceto = bool(audios) and all(f["cat"] in ("boceto", "toma") for f in audios) and not s["sesiones"] or bool(s.get("coleccion"))
        razon = s["razones"][:]
        if len(s["titulos"]) > 1:
            razon.append("el título se ha sacado de: " + ", ".join(f"«{_vista(t)}»" for t in list(s["titulos"])[:4]))
        sesiones = []
        for pid in s["sesiones"]:
            P = proyectos[pid]
            sesiones.append({"id": pid, "daw": P["daw"], "tipo": P["tipo"], "nombre": _vista(P["nombre"]), "principales": [_vista(x) for x in P["principales"]],
                             "rel": _vista(P["rel"]), "tam": P["tam"], "tam_ligero": P["tam_ligero"], "n": P["n"], "n_audio": P["n_audio"],
                             "porque": "detectado por la extensión del archivo de proyecto" + (" (es un paquete: la carpeta entera ES el proyecto)" if P["tipo"] == "paquete"
                                                                                      else " y su carpeta hermana" if P["tipo"] == "carpeta" else " (suelto: no hay carpeta propia)")})
        canciones.append({"id": f"c{i}", "titulo": _vista(titulo), "razon": razon, "boceto": boceto, "sueltos": bool(s.get("sueltos")), "archivos": fl, "sesiones": sesiones})
    huerfanas = [c for c in canciones if not c["archivos"] and not c["sesiones"]]
    canciones = [c for c in canciones if c not in huerfanas]
    # carpetas llenas de audios cortos (¿librerías de samples?): se proponen excluidas
    por_carpeta = {}
    for c in canciones:
        for f in c["archivos"]:
            if f["cat"] in ("version", "boceto", "stem", "toma") and f["tam"] < 3 * 1024 * 1024:
                por_carpeta.setdefault(f["rel"].rsplit("/", 1)[0] if "/" in f["rel"] else "", []).append(f)
    for _d, fs in por_carpeta.items():
        if len(fs) >= 60:
            for f in fs:
                f["excluir"] = True
                f["motivo"] += f" · ⚠ hay {len(fs)} audios cortos en su carpeta: ¿librería de samples? (excluido; márcalo si es tuyo)"
    S["sesiones_srv"] = proyectos
    ign = sorted(S["ignorados"].items(), key=lambda kv: -kv[1])
    return {"origen": _vista(S["origen"]), "nombre": _vista(origen_nombre), "canciones": canciones,
            "resumen": {"archivos_vistos": S["archivos"], "bytes_vistos": S["bytes"], "carpetas": S["carpetas"], "proyectos": len(S["proyectos"]),
                        "archivos_propuestos": n_arch, "enlaces_omitidos": S["enlaces"], "basura": S["basura"],
                        "ignorados": [{"ext": _vista(k), "n": v} for k, v in ign[:12]], "n_ignorados": sum(v for _k, v in ign)}}


ORDEN_CAT = {"master": 0, "version": 1, "directo": 2, "boceto": 3, "toma": 4, "stem": 5, "letra": 6, "midi": 7, "doc": 8, "arte": 9, "video": 10, "otro": 11}


def _titulo_de_carpetas(partes):
    for x in reversed(partes):
        t = limpiar_titulo(x)
        if not es_generico(t):
            return t
    return ""


def propuesta(req, ctx):
    j = JOBS.get(req.arg("job"))
    if not j or "res" not in j:
        return req.send({"ok": False, "error": "La propuesta ya no está en memoria. Vuelve a escanear la carpeta."})
    return req.send({"ok": True, "job": j["id"], **j["res"]})


# ───────────────────────── plan de copia ─────────────────────────
SUBDIR_CAT = {"version": ("versiones",), "master": ("master",), "stem": ("stems",), "directo": ("versiones", "directos"), "boceto": ("versiones", "bocetos"),
              "toma": ("otros", "tomas"), "midi": ("midi",), "doc": ("docs",), "arte": ("arte",), "video": ("video",), "otro": ("otros",)}


def _caminar_sesion(S, base_abs, ligera):
    """[(partes_relativas, ruta_abs, tam)] de una carpeta de proyecto, sin enlaces simbólicos."""
    out = []

    def rec(absd, partes, prof):
        if prof > 40:
            return
        try:
            with os.scandir(_lp(absd)) as it:
                ents = sorted(it, key=lambda e: e.name.lower())
        except OSError:
            S["avisos"].append(f"No pude leer «{_vista(absd)}»")
            return
        for e in ents:
            try:
                if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                    continue
                if e.is_dir(follow_symlinks=False):
                    if ligera and EXCLUIDAS_LIGERAS.match(e.name):
                        continue
                    rec(os.path.join(absd, e.name), partes + (e.name,), prof + 1)
                elif e.is_file(follow_symlinks=False):
                    if ligera and _ext(e.name) in BASURA:
                        continue
                    out.append((partes + (e.name,), os.path.join(absd, e.name), e.stat(follow_symlinks=False).st_size))
            except OSError:
                continue
    rec(base_abs, (), 0)
    return out


def _resolver_plan(j, plan, detallado):
    """Convierte lo que decidió la persona en una lista de operaciones. Todo origen debe ser un archivo ya escaneado dentro del origen."""
    if "res" not in j:
        raise ValueError("escaneo no terminado")
    rutas, proyectos = j["rutas"], j["sesiones_srv"]
    origen_real = os.path.realpath(j["origen"])
    ops, total, n_dircopy_bytes = [], 0, 0
    titulos = []
    for ci, c in enumerate(plan.get("canciones", [])):
        titulo = str(c.get("titulo", "")).strip() or "Sin título"
        song = {"titulo": titulo, "boceto": bool(c.get("boceto")), "ops": [], "idx": ci}
        letra_usada = False
        for a in c.get("archivos", []):
            fid = a.get("id")
            src = rutas.get(fid)
            if not src:
                continue
            cat = a.get("cat") if a.get("cat") in SUBDIR_CAT or a.get("cat") == "letra" else "otro"
            nombre = _seguro(str(a.get("nombre") or os.path.basename(src)), archivo=True)
            ext = _ext(src)
            if cat == "letra":
                if ext == ".txt" or ext == ".md":
                    if not letra_usada:
                        letra_usada, sub, nombre = True, (), "letra.txt"
                    else:
                        sub = ("docs",)
                else:
                    sub = ("docs",)
            else:
                sub = SUBDIR_CAT[cat]
                if cat in ("version", "master", "stem", "directo", "boceto") and ext not in AUDIO_GESTOR:
                    sub = ("otros", "audio")
            try:
                tam = os.stat(_lp(src)).st_size
            except OSError:
                tam = int(a.get("tam", 0) or 0)
            song["ops"].append({"src": src, "sub": sub, "nombre": nombre, "tam": tam})
            total += tam
        for s in c.get("sesiones", []):
            P = proyectos.get(s.get("id"))
            modo = s.get("modo")
            if not P or modo not in ("archivo", "completa"):
                continue
            daw = _seguro(P["daw"])
            origen_dir = os.path.join(j["origen"], *P["rel"].split("/")) if P["rel"] else j["origen"]
            if P["tipo"] == "paquete" or (modo == "completa" and P["tipo"] == "carpeta"):
                ligera = bool(s.get("ligera"))
                if detallado:
                    nombre_dir = _seguro(P["nombre"] if P["tipo"] == "carpeta" else os.path.basename(origen_dir))
                    for partes, absf, t in _caminar_sesion(j, origen_dir, ligera):
                        song["ops"].append({"src": absf, "sub": ("sesiones", daw, nombre_dir) + tuple(_seguro(x) for x in partes[:-1]), "nombre": _seguro(partes[-1], archivo=True),
                                            "tam": t, "raiz_unica": ("sesiones", daw, nombre_dir)})
                        total += t
                else:
                    total += P["tam_ligero"] if ligera else P["tam"]
            else:  # solo el/los archivos de proyecto
                carpeta = origen_dir if P["tipo"] == "carpeta" else os.path.dirname(origen_dir)
                for nom in P["principales"]:
                    absf = os.path.join(carpeta, nom)
                    try:
                        t = os.stat(_lp(absf)).st_size
                    except OSError:
                        continue
                    song["ops"].append({"src": absf, "sub": ("sesiones", daw), "nombre": _seguro(nom, archivo=True), "tam": t})
                    total += t
        # defensa: nada fuera del origen (rutas relativas ya escaneadas, pero se vuelve a comprobar en cada copia)
        for o in song["ops"]:
            o["origen_real"] = origen_real
        if song["ops"]:
            titulos.append(song)
    return titulos, total


def presupuesto(req, ctx):
    d = req.json()
    j = JOBS.get(str(d.get("job", "")))
    if not j or "res" not in j:
        return req.send({"ok": False, "error": "Vuelve a escanear la carpeta."})
    try:
        songs, total = _resolver_plan(j, d, detallado=False)
    except ValueError as ex:
        return req.send({"ok": False, "error": str(ex)})
    root = Path(ctx.root)
    try:
        libre = shutil.disk_usage(str(root if root.exists() else root.parent)).free
    except OSError:
        libre = None
    nec = total + MARGEN_ESPACIO
    return req.send({"ok": True, "bytes": total, "archivos": sum(len(s["ops"]) for s in songs), "canciones": len(songs), "libre": libre,
                     "cabe": libre is None or nec <= libre, "disco": _vista(root.anchor or str(root))})


# ───────────────────────── copia verificada ─────────────────────────
def _huella(ruta, tam, modo):
    h = hashlib.sha256()
    with open(_lp(ruta), "rb") as f:
        if modo == "c":
            while True:
                b = f.read(BLOQUE)
                if not b:
                    break
                h.update(b)
        else:
            for off, ln in _muestras(tam):
                f.seek(off)
                h.update(f.read(ln))
    return h.hexdigest()


def _muestras(tam):
    """Zonas que se comparan en archivos enormes: principio, final y 32 bloques repartidos."""
    M = 1024 * 1024
    z = {(0, min(4 * M, tam))}
    if tam > 4 * M:
        z.add((max(0, tam - 4 * M), 4 * M))
    if tam > 40 * M:
        for i in range(32):
            z.add((i * (tam - M) // 31, M))
    return sorted(z)


def _reservar(S, ruta):
    """Devuelve una ruta que no exista ni esté ya reservada, añadiendo « (2)», « (3)»… antes de la extensión."""
    base, ext = os.path.splitext(ruta)
    cand, n = ruta, 1
    while cand.lower() in S["usados"] or os.path.lexists(_lp(cand)):
        n += 1
        cand = f"{base} ({n}){ext}"
    S["usados"].add(cand.lower())
    return cand


def _es_bloqueo(ex):
    return isinstance(ex, PermissionError) or getattr(ex, "errno", None) in (13, 16, 26, 32, 33) or getattr(ex, "winerror", None) in (32, 33)


def _copiar_uno(S, o, dst):
    """Copia por bloques, verifica y renombra. Devuelve (modo_hash, sha). Lanza Cancelado / OSError / ValueError."""
    src = o["src"]
    real = os.path.realpath(src)
    if not (real == o["origen_real"] or real.startswith(o["origen_real"].rstrip("\\/") + os.sep)) or os.path.islink(src):
        raise Rechazado("el archivo está fuera de la carpeta de origen o es un enlace: no se copia")
    tmp = dst + ".importando"
    inicio_bytes = S["bytes_hechos"]
    try:
        st0 = os.stat(_lp(src))
        completo = st0.st_size <= LIMITE_COMPLETO
        h = hashlib.sha256()
        copiado = 0
        with open(_lp(src), "rb") as fi, open(_lp(tmp), "xb") as fo:
            while True:
                if S["cancel"].is_set():
                    raise Cancelado()
                b = fi.read(BLOQUE)
                if not b:
                    break
                fo.write(b)
                if completo:
                    h.update(b)
                copiado += len(b)
                S["bytes_hechos"] += len(b)
            fo.flush()
            os.fsync(fo.fileno())
        st1 = os.stat(_lp(src))
        if st1.st_size != copiado or st1.st_mtime_ns != st0.st_mtime_ns:
            raise ValueError("el archivo cambió mientras se copiaba (¿lo está usando otro programa?)")
        if os.stat(_lp(tmp)).st_size != copiado:
            raise ValueError("el tamaño de la copia no coincide")
        S["actual_fase"] = "verificando"
        modo = "c" if completo else "m"
        sha_o = h.hexdigest() if completo else _huella(src, copiado, "m")
        sha_d = _huella(tmp, copiado, modo)
        if sha_o != sha_d:
            raise ValueError("la verificación falló: la copia no es idéntica")
        os.utime(_lp(tmp), ns=(st0.st_atime_ns, st0.st_mtime_ns))  # conserva la fecha original
        if os.path.lexists(_lp(dst)):
            raise FileExistsError("el destino ya existe")
        os.rename(_lp(tmp), _lp(dst))
        return modo, sha_d, copiado
    except BaseException:
        S["bytes_hechos"] = inicio_bytes
        try:
            if os.path.lexists(_lp(tmp)):
                os.remove(_lp(tmp))
        except OSError:
            pass
        raise


def copiar(req, ctx):
    d = req.json()
    j0 = JOBS.get(str(d.get("job", "")))
    if not j0 or "res" not in j0:
        return req.send({"ok": False, "error": "Vuelve a escanear la carpeta."})
    with _LOCK:
        if any(v["tipo"] in ("copia", "deshacer") and v["estado"] == "corriendo" for v in JOBS.values()):
            return req.send({"ok": False, "error": "Ya hay una importación en marcha."})
        j = _nuevo_job("copia")
    j.update(origen=j0["origen"], fase="Preparando", bytes_total=0, bytes_hechos=0, archivos_total=0, archivos_hechos=0, actual="", actual_fase="",
             bloqueados=[], fallidos=[], omitidos=0, usados=set(), plan=d, res_origen=j0)
    threading.Thread(target=_hilo_copia, args=(j, j0, ctx), daemon=True).start()
    return req.send({"ok": True, "job": j["id"]})


def _hilo_copia(j, j0, ctx):
    iid = time.strftime("imp-%Y%m%d-%H%M%S-") + j["id"][:4]
    j["import_id"] = iid
    root = Path(ctx.root)
    creadas, verif = [], {"c": 0, "m": 0}
    copiados = 0
    iniciado = False
    try:
        av0, j0["avisos"] = j0["avisos"], []
        songs, _ = _resolver_plan(j0, j["plan"], detallado=True)
        j["avisos"] += j0["avisos"]
        j0["avisos"] = av0
        j["archivos_total"] = sum(len(s["ops"]) for s in songs)
        j["bytes_total"] = sum(o["tam"] for s in songs for o in s["ops"])
        try:
            libre = shutil.disk_usage(str(root)).free
            if j["bytes_total"] + MARGEN_ESPACIO > libre:
                raise ValueError(f"No hay espacio suficiente: hacen falta {_fmt_bytes(j['bytes_total'])} y quedan {_fmt_bytes(libre)} libres en el disco de la biblioteca.")
        except OSError:
            pass
        (root / "unreleased").mkdir(parents=True, exist_ok=True)
        _escribir_diario(ctx, {"t": "inicio", "id": iid, "ts": time.time(), "origen": j["origen"], "archivos": j["archivos_total"], "bytes": j["bytes_total"]})
        iniciado = True
        j["fase"] = "Copiando"
        for s in songs:
            if j["cancel"].is_set():
                raise Cancelado()
            carpeta = _crear_unica(root / "unreleased", _seguro(s["titulo"], 100))
            rel_carpeta = carpeta.relative_to(root).as_posix()
            _escribir_diario(ctx, {"t": "carpeta", "id": iid, "dir": rel_carpeta})
            info = {"titulo": s["titulo"], "carpeta": rel_carpeta, "boceto": s["boceto"], "archivos": 0}
            creadas.append(info)
            raices = {}
            for o in s["ops"]:
                if j["cancel"].is_set():
                    raise Cancelado()
                partes = list(o["sub"])
                if o.get("raiz_unica"):  # carpeta de proyecto copiada entera: su nombre también evita chocar con otra
                    k = tuple(o["raiz_unica"])
                    if k not in raices:
                        nuevo = _reservar(j, str(carpeta.joinpath(*k)))
                        raices[k] = os.path.basename(nuevo)
                    partes[len(k) - 1] = raices[k]
                dst_dir = carpeta.joinpath(*partes) if partes else carpeta
                os.makedirs(_lp(dst_dir), exist_ok=True)
                dst = _reservar(j, str(dst_dir / o["nombre"]))
                j["actual"] = _vista(os.path.basename(o["src"]))
                j["actual_fase"] = "copiando"
                ok = False
                for intento in range(3):
                    try:
                        modo, sha, n = _copiar_uno(j, o, dst)
                        ok = True
                        break
                    except Cancelado:
                        raise
                    except (OSError, ValueError) as ex:
                        if isinstance(ex, OSError) and _es_bloqueo(ex) and intento < 2:
                            j["actual_fase"] = "archivo en uso, reintentando"
                            for _ in range(intento + 1):
                                if j["cancel"].is_set():
                                    raise Cancelado()
                                time.sleep(1)
                            continue
                        if isinstance(ex, ValueError) and not isinstance(ex, Rechazado) and intento < 1:
                            continue
                        if isinstance(ex, OSError) and _es_bloqueo(ex):
                            j["bloqueados"].append(_vista(os.path.basename(o["src"])))
                            j["avisos"].append(f"Archivo bloqueado, lo he omitido: {_vista(os.path.basename(o['src']))}")
                        else:
                            msg = ex.strerror if isinstance(ex, OSError) and ex.strerror else str(ex)
                            j["fallidos"].append({"n": _vista(os.path.basename(o["src"])), "error": _vista(msg)})
                            j["avisos"].append(f"No se copió {_vista(os.path.basename(o['src']))}: {_vista(msg)}")
                        break
                if ok:
                    verif[modo] += 1
                    copiados += 1
                    info["archivos"] += 1
                    j["archivos_hechos"] = copiados
                    _escribir_diario(ctx, {"t": "archivo", "id": iid, "dst": Path(dst).relative_to(root).as_posix(), "tam": n, "m": modo, "sha": sha,
                                           "src": _vista(o["src"])})
                else:
                    j["omitidos"] += 1
        j["estado"] = "listo"
    except Cancelado:
        j["estado"] = "cancelado"
    except Exception as ex:  # noqa: BLE001
        import traceback
        print("[importar] error al copiar:\n" + traceback.format_exc())
        j["estado"] = "error"
        j["error"] = str(ex) if isinstance(ex, ValueError) else f"{type(ex).__name__}: {ex}"
    for info in creadas:  # carpetas de canción que quedaron vacías (todo omitido o cancelado): se quitan, solo si no tienen ningún archivo
        if info["archivos"] == 0:
            for dp, _dn, _fn in os.walk(str(root / info["carpeta"]), topdown=False):
                try:
                    os.rmdir(_lp(dp))
                except OSError:
                    pass
    j["resumen"] = {"copiados": copiados, "bytes": j["bytes_hechos"], "omitidos": j["omitidos"], "bloqueados": j["bloqueados"], "fallidos": j["fallidos"],
                    "verificacion_completa": verif["c"], "verificacion_muestreo": verif["m"], "canciones": [c for c in creadas if c["archivos"]],
                    "import_id": iid, "limite_completo": LIMITE_COMPLETO}
    if iniciado:
        try:
            _escribir_diario(ctx, {"t": "fin", "id": iid, "ts": time.time(), "estado": j["estado"], "copiados": copiados, "omitidos": j["omitidos"]})
        except OSError:
            pass
    j["actual"], j["actual_fase"] = "", ""
    j["fin"] = time.time()


def _crear_unica(padre, nombre):
    n, cand = 1, padre / nombre
    while True:
        try:
            os.mkdir(_lp(cand))
            return cand
        except FileExistsError:
            n += 1
            cand = padre / f"{nombre} ({n})"


def cancelar(req, ctx):
    j = JOBS.get(req.arg("job"))
    if j:
        j["cancel"].set()
    return req.send({"ok": bool(j)})


# ───────────────────────── diario y deshacer ─────────────────────────
def _leer_diario(ctx):
    p = _jdiario(ctx)
    if not p.exists():
        return
    with open(p, encoding="utf-8") as f:
        for ln in f:
            try:
                yield json.loads(ln)
            except ValueError:
                continue


def diario(req, ctx):
    imps = {}
    for r in _leer_diario(ctx):
        i = imps.setdefault(r.get("id"), {"id": r.get("id"), "ts": 0, "origen": "", "archivos": 0, "bytes": 0, "estado": "en curso", "deshecha": False, "carpetas": []})
        t = r.get("t")
        if t == "inicio":
            i["ts"], i["origen"] = r.get("ts", 0), r.get("origen", "")
        elif t == "archivo":
            i["archivos"] += 1
            i["bytes"] += r.get("tam", 0)
        elif t == "carpeta":
            i["carpetas"].append(r.get("dir"))
        elif t == "fin":
            i["estado"] = {"listo": "completa", "cancelado": "cancelada a medias", "error": "con error"}.get(r.get("estado"), r.get("estado"))
        elif t == "deshecho":
            i["deshecha"] = True
            i["deshecho"] = {k: r.get(k) for k in ("borrados", "conservados", "ausentes")}
    lista = sorted(imps.values(), key=lambda x: -x["ts"])
    for i in lista:
        i["origen"] = _vista(os.path.basename(i["origen"].rstrip("\\/")) or i["origen"])
    return req.send({"ok": True, "importaciones": lista[:30]})


def deshacer(req, ctx):
    iid = str(req.json().get("id", ""))
    with _LOCK:
        if any(v["tipo"] in ("copia", "deshacer") and v["estado"] == "corriendo" for v in JOBS.values()):
            return req.send({"ok": False, "error": "Hay otra tarea en marcha. Espera a que termine."})
        j = _nuevo_job("deshacer")
    regs = [r for r in _leer_diario(ctx) if r.get("id") == iid]
    if not regs or any(r.get("t") == "deshecho" for r in regs):
        j["estado"] = "error"
        j["error"] = "No encuentro esa importación o ya estaba deshecha."
        return req.send({"ok": False, "error": j["error"]})
    j.update(fase="Comprobando y quitando", archivos_total=sum(1 for r in regs if r.get("t") == "archivo"), archivos_hechos=0, borrados=0, conservados=[], ausentes=0, actual="")
    threading.Thread(target=_hilo_deshacer, args=(j, regs, iid, ctx), daemon=True).start()
    return req.send({"ok": True, "job": j["id"]})


def _hilo_deshacer(j, regs, iid, ctx):
    root = Path(ctx.root).resolve()
    carpetas = []
    try:
        for r in regs:
            if j["cancel"].is_set():
                raise Cancelado()
            if r.get("t") == "carpeta":
                carpetas.append(r["dir"])
            if r.get("t") != "archivo":
                continue
            j["archivos_hechos"] += 1
            p = (root / r["dst"])
            try:
                real = p.resolve()
                real.relative_to(root)  # nunca fuera de la biblioteca
            except (ValueError, OSError):
                j["conservados"].append({"n": _vista(r["dst"]), "por": "ruta no válida"})
                continue
            j["actual"] = _vista(p.name)
            if not os.path.lexists(_lp(p)):
                j["ausentes"] += 1
                continue
            try:
                if os.path.islink(p) or os.stat(_lp(p)).st_size != r["tam"] or _huella(p, r["tam"], r["m"]) != r["sha"]:
                    j["conservados"].append({"n": _vista(r["dst"]), "por": "lo has modificado después de importarlo"})
                    continue
                os.remove(_lp(p))
                j["borrados"] += 1
            except OSError as ex:
                j["conservados"].append({"n": _vista(r["dst"]), "por": _vista(ex.strerror or str(ex))})
        # carpetas: solo las que esa importación creó y solo si quedaron vacías (rmdir nunca borra contenido)
        dirs = set()
        for c in carpetas:
            base = root / c
            if base.is_dir():
                for dp, dn, _fn in os.walk(str(base), topdown=False):
                    dirs.add(dp)
                dirs.add(str(base))
        for dp in sorted(dirs, key=len, reverse=True):
            try:
                if Path(dp).resolve() != root and root in Path(dp).resolve().parents:
                    os.rmdir(_lp(dp))
            except OSError:
                pass
        _escribir_diario(ctx, {"t": "deshecho", "id": iid, "ts": time.time(), "borrados": j["borrados"], "conservados": len(j["conservados"]), "ausentes": j["ausentes"]})
        j["estado"] = "listo"
    except Cancelado:
        j["estado"] = "cancelado"
    except Exception as ex:  # noqa: BLE001
        j["estado"] = "error"
        j["error"] = f"{type(ex).__name__}: {ex}"
    j["actual"] = ""
    j["fin"] = time.time()


def info(req, ctx):
    root = Path(ctx.root)
    try:
        u = shutil.disk_usage(str(root))
        libre, total = u.free, u.total
    except OSError:
        libre = total = None
    return req.send({"ok": True, "biblioteca": _vista(root.name), "libre": libre, "total": total, "windows": os.name == "nt"})


ROUTES = {
    "GET carpetas": carpetas,
    "POST escanear": escanear,
    "GET estado": estado,
    "GET propuesta": propuesta,
    "POST presupuesto": presupuesto,
    "POST copiar": copiar,
    "POST cancelar": cancelar,
    "GET diario": diario,
    "POST deshacer": deshacer,
    "GET info": info,
}
