#!/usr/bin/env python3
"""Reads your library folder and generates datos/data.json and datos/letras.json for the manager.

It only READS your music: nothing is moved or deleted. It runs again every time you press "Actualizar" (Refresh).

Layout it understands ("Añadir canciones" / Add songs creates it automatically):
  unreleased/<song>/                     unreleased            (or unreleased/<project>/<song>/)
  prereleased/<song>/                    pre-releases
  published/Singles/<song>/              published singles
  published/Álbumes/<album>/<NN song>/
  inside each song: letra.txt (lyrics), versiones/, master/, stems/, sesiones/, docs/, midi/ and loose audio
  Folders starting with "_" or "." are ignored.
"""
import csv
import difflib
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

_re_num = re.compile(r"^\d{1,2}[\s.\-_]+")

LEX = {
    "Amor": ["amor", "amar", "amo ", "besa", "beso", "piel", "abraz", "enamor", "te quiero", "corazon", "pasion", "caricia", "deseo"],
    "Desamor y ruptura": ["adios", "dejaste", "olvid", "extran", "ausencia", "celos", "perdon", "se acabo", "te fuiste", "volver", "rompi"],
    "Soledad": ["soledad", "solo ", "sola ", "vacio", "silencio", "nadie", "sin ti", "aislad"],
    "Muerte y duelo": ["muert", "morir", "tumba", "funeral", "luto", "cementerio", "difunt", "entierr"],
    "Sanación y fuerza": ["sanar", "herida", "cicatriz", "curar", "fuerza", "valiente", "levant", "resist", "renac", "respiro", "respirar", "bocanada"],
    "Mente y ansiedad": ["ansiedad", "mente", "pensamiento", "miedo", "panico", "terapia", "locura", "cabeza", "insomnio", "angustia"],
    "Tiempo y nostalgia": ["tiempo", "recuerd", "memoria", "ayer", "pasado", "nostalgia", "anos ", "infancia", "momento"],
    "Sociedad y crítica": ["gobierno", "impuesto", "politic", "sistema", "dinero", "trabajo", "mundo", "mentira", "redes", "tele", "poder", "cliente", "justicia"],
    "Fiesta y baile": ["bail", "fiesta", "noche", "ritmo", "cadera", "cuerpo", "discoteca", "mueve", "moviendo"],
    "Naturaleza y espiritualidad": ["tierra", "cielo", "mar ", "luna", "sol ", "estrella", "dios", "alma", "universo", "semilla", "rio ", "montan", "viento", "flor"],
    "Familia y amistad": ["familia", "madre", "padre", "hijo", "amigo", "amiga", "abuela", "hermano", "casa"],
}


def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def plain(t):
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"[^a-z0-9ñ]+", " ", t) + " "


def visible(name):
    return not name.startswith((".", "_"))


def subdirs(d):
    try:
        return sorted((x for x in d.iterdir() if x.is_dir() and visible(x.name)), key=lambda x: x.name.lower())
    except OSError:
        return []


def role_dirs(d):
    """master / versiones / stems subfolders of a song (case-insensitive: Linux is case-sensitive)."""
    out = []
    try:
        for x in d.iterdir():
            if x.is_dir() and x.name.lower() in ("master", "versiones", "stems"):
                out.append((x.name.lower(), x))
    except OSError:
        pass
    return out


def audio_files(d):
    """[(path, role)] with a song's audio: master/, versiones/, stems/ and the loose files in its folder."""
    res = []
    try:
        for f in sorted(d.iterdir()):
            if f.is_file() and visible(f.name) and f.suffix.lower() in C.AUDIO:
                res.append((f, ""))
    except OSError:
        return res
    for role, sub in role_dirs(d):
        for dp, _dns, fns in os.walk(C.lp(sub)):
            dp = dp.replace("\\\\?\\", "")
            for fn in sorted(fns):
                if visible(fn) and os.path.splitext(fn)[1].lower() in C.AUDIO:
                    res.append((Path(dp) / fn, role))
    return res


def looks_song(d):
    return (d / "letra.txt").exists() or bool(audio_files(d)) or any((d / r).is_dir() for r in ("versiones", "master", "stems"))


def candidates(R):
    """[(key, folder)] of every folder that looks like a song."""
    cand = []
    un = R / "unreleased"
    for d in subdirs(un):
        subs = [x for x in subdirs(d) if x.name.lower() not in C.RESERVED]
        if not looks_song(d) and any(looks_song(x) for x in subs):  # project folder / album in preparation
            cand += [(f"unreleased/{d.name}/{x.name}", x) for x in subs]
        else:
            cand.append((f"unreleased/{d.name}", d))
    for d in subdirs(R / "prereleased"):
        cand.append((f"prereleased/{d.name}", d))
    pub = R / "published"
    for d in subdirs(pub):
        n = norm(d.name)
        if n == "singles":
            cand += [(f"published/{d.name}/{x.name}", x) for x in subdirs(d)]
        elif n == "albumes":
            for a in subdirs(d):
                cand += [(f"published/{d.name}/{a.name}/{x.name}", x) for x in subdirs(a) if x.name.lower() not in C.RESERVED]
    return cand


def read_text(p):
    try:
        raw = p.read_bytes()
    except OSError:
        return ""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def lyric_sig(text):
    return norm(text.split("\n", 1)[-1])[:700]


def category(key):
    p = key.split("/")
    if p[0] == "published":
        return "Singles" if norm(p[1]) == "singles" else "Álbum"
    if p[0] == "prereleased":
        return "Pre-released"
    return "Proyecto" if len(p) >= 3 else "Sin publicar"


def main():
    R = C.root()
    if not R or not R.is_dir():
        print("No hay biblioteca configurada.")
        return 1
    C.DATOS.mkdir(parents=True, exist_ok=True)

    # merges done from the manager (a = absorbed song, b = target)
    canon = {}
    dp = C.DATOS / "decisiones.csv"
    if dp.exists():
        for r in csv.reader(open(dp, encoding="utf-8", newline="")):
            if len(r) >= 3 and r[0] == "unir":
                canon[r[1]] = r[2]

    ids_path = C.DATOS / "ids.json"
    try:
        old = json.loads(ids_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}

    cand = candidates(R)
    cur = {k for k, _ in cand}
    vanished = {k: e for k, e in old.items() if k not in cur}
    used = set()
    lst, letras, newmap = [], {}, {}

    for key, d in cand:
        vs = audio_files(d)
        lf = d / "letra.txt"
        text = read_text(lf) if lf.exists() else ""
        if not vs and not text.strip():
            continue
        names = sorted({f.name.lower() for f, _ in vs})
        sig = lyric_sig(text) if text.strip() else ""
        sid = (old.get(key) or {}).get("id")
        if not sid:  # is it a renamed or moved folder (e.g. from unreleased to published)?
            hit = None
            for vk, e in vanished.items():
                if e["id"] in used:
                    continue
                if sig and len(sig) >= 40 and e.get("sig") and difflib.SequenceMatcher(None, sig, e["sig"]).ratio() >= 0.92:
                    hit = vk
                    break
                if names and set(names) & set(e.get("files", [])):
                    hit = vk
                    break
            if hit:
                sid = vanished[hit]["id"]
            else:
                sid = "N" + hashlib.md5(key.encode("utf-8")).hexdigest()[:6]
        if sid in used:
            sid = "N" + hashlib.md5((key + sid).encode("utf-8")).hexdigest()[:6]
        used.add(sid)
        newmap[key] = {"id": sid, "sig": sig, "files": names}
        if sid in canon:  # absorbed by a merge: its files are already in the target song
            continue

        title = _re_num.sub("", d.name).strip() or d.name
        versions = []
        for f, role in vs:
            try:
                st = os.stat(C.lp(f))
            except OSError:
                continue
            versions.append({"p": C.posix(f.relative_to(R)), "fmt": f.suffix.lower().lstrip("."), "mb": round(st.st_size / 1e6, 1), "seg": None,
                             "fecha": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)), "label": "master" if role == "master" else "",
                             "dup": "", "prop": False, "mt": int(st.st_mtime)})
        safe = ""
        docs = d / "docs"
        if docs.is_dir():
            for f in docs.rglob("certificate_*.pdf"):
                m = re.match(r"certificate_(\d{13})", f.name)
                if m:
                    safe = m.group(1)
                    break
        yr = 2000 + int(safe[:2]) if safe else None
        if yr is None:
            ys = [int(v["fecha"][:4]) for v in versions if v["fecha"][:4].isdigit()]
            yr = min(ys) if ys else None
        o = {"id": sid, "title": title, "origins": [key], "release": key.rsplit("/", 1)[0], "letra": C.posix(lf.relative_to(R)) if text.strip() else "",
             "sc": [], "versions": versions, "safe": safe, "anio": yr, "dir": key, "cat": category(key),
             "published": key.startswith("published/")}
        lst.append(o)
        if text.strip():
            body = plain(text)
            sc = []
            for theme, stems in LEX.items():
                n = sum(body.count(" " + s) for s in stems)
                if n >= 2:
                    sc.append((n, theme))
            sc.sort(reverse=True)
            letras[sid] = {"t": text, "th": [t for _, t in sc[:3]]}

    for k, e in vanished.items():  # remember folders that disappear for a while, in case they come back
        if e["id"] not in used:
            newmap.setdefault(k, e)
    lst.sort(key=lambda o: o["title"].lower())
    for name, obj in (("letras.json", letras), ("data.json", {"songs": lst}), ("ids.json", newmap)):
        tmp = C.DATOS / (name + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, C.DATOS / name)
    nv = sum(len(o["versions"]) for o in lst)
    print(f"datos/data.json: {len(lst)} canciones, {nv} versiones de audio, {len(letras)} letras")
    return 0


if __name__ == "__main__":
    sys.exit(main())
