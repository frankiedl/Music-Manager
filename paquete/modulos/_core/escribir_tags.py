"""Writes the author's OWN metadata (credits, tags, cover) on a SAFE COPY of an audio file, leaving the sound bit-exact.

    etiquetar(src, dst, poner, creditos, conservar, caratula, ffmpeg, simular=True) -> dict
    registrar(datos_modulo, rel_src, rel_dst, res)  -> id          (hash registry, journal line and before/after report)

Policy (decided with the author): CLEAN everything foreign by default and write ONLY what the author declares; `conservar` lists what the
author ticks to keep. The original is never touched; the copy is written next to a temporary name and moved into place only if the
STRICT verification passes: `sha256_audio` identical (the sound), decoded-audio MD5 identical when ffmpeg is there, the declared fields read
back with the same values, nothing foreign left, kept blocks identical. Otherwise nothing is delivered.

  MP3   Python  new ID3v2.3 tag + the original frames untouched
  WAV   Python  fmt/fact + kept chunks + LIST/INFO + 'id3 ' chunk + the data chunk copied byte by byte
  FLAC  Python  STREAMINFO (+SEEKTABLE) + VORBIS_COMMENT + PICTURE + kept blocks + the original frames untouched
  M4A   ffmpeg  `-c copy -map_metadata -1 +bitexact` with the standard fields only (free '----' atoms: v2)
  other formats, damaged files and MP4 with video: read-only (`escritura_no_soportada`).

Nothing here decides or claims anything about authorship: it writes what the author declares. Standard library (+ optional ffmpeg).
"""
import hashlib
import json
import os
import re
import secrets
import struct
import subprocess
import time
from pathlib import Path

try:
    import inspeccion as I
except ImportError:                                   # works whether or not _core is on sys.path
    import importlib.util
    _sp = importlib.util.spec_from_file_location("inspeccion", Path(__file__).with_name("inspeccion.py"))
    I = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(I)

_NOCONSOLA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CAMPOS = ("title", "artist", "album", "album_artist", "date", "genre", "track", "disc", "composer", "lyricist", "publisher", "copyright", "isrc",
          "comment", "lyrics", "language")
ROLES = {"letra": "Letra", "musica": "Música", "arreglos": "Arreglos", "produccion": "Producción", "grabacion": "Grabación", "mezcla": "Mezcla",
         "masterizacion": "Masterización", "asistencia": "Asistencia", "otro": "Otro"}
ROL_VORBIS = {"arreglos": "ARRANGER", "mezcla": "MIXER", "produccion": "PRODUCER", "grabacion": "ENGINEER", "asistencia": "CONTRIBUTOR"}
ROL_IPLS = {"arreglos": "arranger", "mezcla": "mix", "produccion": "producer", "grabacion": "engineer", "masterizacion": "mastering", "asistencia": "assistant", "otro": "other"}
RESERVADAS = set(I.NORM_VORBIS) | set(ROL_VORBIS.values()) | {"CREDITS", "VENDOR"}
# field → (ID3v2.3 frame, RIFF INFO subchunk, Vorbis key, ffmpeg key for MP4)
MAPA = {"title": ("TIT2", "INAM", "TITLE", "title"), "artist": ("TPE1", "IART", "ARTIST", "artist"), "album": ("TALB", "IPRD", "ALBUM", "album"),
        "album_artist": ("TPE2", None, "ALBUMARTIST", "album_artist"), "date": ("TYER", "ICRD", "DATE", "date"), "genre": ("TCON", "IGNR", "GENRE", "genre"),
        "track": ("TRCK", "ITRK", "TRACKNUMBER", "track"), "disc": ("TPOS", None, "DISCNUMBER", "disc"), "composer": ("TCOM", None, "COMPOSER", "composer"),
        "lyricist": ("TEXT", None, "LYRICIST", None), "publisher": ("TPUB", None, "PUBLISHER", None), "copyright": ("TCOP", "ICOP", "COPYRIGHT", "copyright"),
        "isrc": ("TSRC", "ISRC", "ISRC", None), "comment": ("COMM", "ICMT", "COMMENT", "comment"), "lyrics": ("USLT", None, "LYRICS", "lyrics"),
        "language": ("TLAN", None, "LANGUAGE", None)}
ATOMO_MP4 = {"title": "©nam", "artist": "©ART", "album": "©alb", "album_artist": "aART", "date": "©day", "genre": "©gen", "track": "trkn", "disc": "disk",
             "composer": "©wrt", "copyright": "cprt", "comment": "©cmt", "lyrics": "©lyr"}
ERRORES_ORIGEN = {"chunk_truncado", "tag_truncado", "sin_frames"}      # besides every level-«error» warning
MAX_CARATULA = 8 << 20


# ---------------------------------------------------------------------------------------------- lo declarado por el autor
def _limpia(s, multilinea=False):
    s = str(s).replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    s = s if multilinea else s.replace("\n", " ").replace("\t", " ")
    return s.strip()


def normalizar(poner, creditos):
    """Validates what the author declares → ({campos, personalizados, creditos}, [errores])."""
    err, campos, custom, cred = [], {}, {}, []
    for k, v in (poner or {}).items():
        if k == "personalizados":
            continue
        if k not in CAMPOS:
            err.append("Campo desconocido: «%s»." % k)
            continue
        if v is None or str(v).strip() == "":
            continue
        t = _limpia(v, multilinea=k in ("comment", "lyrics"))
        if len(t) > (200000 if k == "lyrics" else 4000 if k == "comment" else 500):
            err.append("«%s» es demasiado largo." % k)
        elif k == "date" and not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", t):
            err.append("La fecha debe ser AAAA, AAAA-MM o AAAA-MM-DD.")
        elif k in ("track", "disc") and not re.fullmatch(r"\d{1,3}(/\d{1,3})?", t):
            err.append("«%s» debe ser N o N/M." % k)
        elif k == "language" and not re.fullmatch(r"[a-z]{3}", t):
            err.append("El idioma debe ser un código de 3 letras (por ejemplo spa).")
        elif k == "isrc":
            t = re.sub(r"[\s-]", "", t).upper()
            if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}\d{7}", t):
                err.append("El ISRC no tiene el formato CC-XXX-AA-NNNNN.")
            else:
                campos[k] = t
        else:
            campos[k] = t
    for n, v in ((poner or {}).get("personalizados") or {}).items():
        n, t = str(n).strip(), _limpia(v)
        if not re.fullmatch(r"[A-Za-z0-9_ -]{1,40}", n):
            err.append("Nombre de campo propio no válido: «%s» (letras, números, espacio, _ y -)." % n[:40])
        elif n.upper() in RESERVADAS or n.upper() in {c.upper() for c in CAMPOS}:
            err.append("«%s» es un campo reservado: usa su campo propio." % n)
        elif t and len(t) <= 1000:
            custom[n] = t
    for x in creditos or []:
        rol, nombre = str((x or {}).get("rol") or ""), _limpia((x or {}).get("nombre") or "")
        tipo, nota = (x or {}).get("tipo") or "persona", _limpia((x or {}).get("nota") or "")
        if rol not in ROLES:
            err.append("Rol de crédito no válido: «%s»." % rol[:30])
        elif not nombre or len(nombre) > 120 or len(nota) > 200 or tipo not in ("persona", "herramienta"):
            err.append("Crédito no válido (nombre vacío o demasiado largo): «%s»." % nombre[:30])
        else:
            cred.append({"rol": rol, "nombre": nombre, "tipo": tipo, "nota": nota})
    if len(cred) > 30:
        err.append("Demasiados créditos (máximo 30).")
    return {"campos": campos, "personalizados": custom, "creditos": cred[:30]}, err


def derivar(decl):
    """What is really written: effective fields (credits for letra/música fill lyricist/composer), role keys, people list and credits text."""
    ef = dict(decl["campos"])
    por_rol = {}
    for x in decl["creditos"]:
        extra = [e for e in (("herramienta" if x["tipo"] == "herramienta" else ""), x["nota"]) if e]
        por_rol.setdefault(x["rol"], []).append(x["nombre"] + (" (%s)" % ", ".join(extra) if extra else ""))
    for rol, campo in (("letra", "lyricist"), ("musica", "composer")):
        nombres = [x["nombre"] for x in decl["creditos"] if x["rol"] == rol]
        if nombres:
            previo = ef.get(campo)
            ef[campo] = " / ".join(([previo] if previo else []) + [n for n in nombres if not previo or n not in previo])
    return {"efectivos": ef,
            "vorbis": {ROL_VORBIS[r]: "; ".join(v) for r, v in por_rol.items() if r in ROL_VORBIS},
            "ipls": [(ROL_IPLS[x["rol"]], x["nombre"]) for x in decl["creditos"] if x["rol"] in ROL_IPLS],
            "texto": "; ".join("%s: %s" % (ROLES[r], ", ".join(por_rol[r])) for r in ROLES if r in por_rol),
            "tiene_creditos": bool(decl["creditos"])}


# ---------------------------------------------------------------------------------------------- selección de lo que se conserva
def _seleccion(conservar):
    s = {"etiqueta": set(), "binario": set(), "bloque": set(), "caratula": set()}
    for c in conservar or []:
        t = str((c or {}).get("tipo") or "")
        if t == "etiqueta":
            s["etiqueta"].add((c.get("bloque"), c.get("clave")))
        elif t == "binario":
            s["binario"].add((c.get("bloque"), c.get("id"), c.get("propietario")))
        elif t == "bloque":
            s["bloque"].add(c.get("bloque"))
        elif t == "caratula":
            s["caratula"].add(int(c.get("indice", -1)))
    return s


def _recorre(src):
    R = I._R()
    R.capturar = True
    ext = Path(src).suffix.lower()
    with open(src, "rb") as f:
        I._recorrer(R, f, os.fstat(f.fileno()).st_size, ext)
    return R


def _danado(avisos):
    return [a for a in avisos if a["nivel"] == "error" or a["codigo"] in ERRORES_ORIGEN]


def _clasificar(R, fam, decl, deriv, sel, caratula_nueva):
    """Every element found in the original → what happens to it (quitar / conservar / sustituir / regenerar) + what the writers must keep."""
    ef = deriv["efectivos"]
    tipos = {b["id"]: b["tipo"] for b in R.bloques}
    acc, keep = [], {"items": [], "frames": [], "bloques": [], "caratulas": []}
    declarados = set(ef) | ({"credits"} if deriv["tiene_creditos"] else set())
    for i in R.items:
        clave, norm, b = i["clave_original"], i["clave_normalizada"], i["bloque"]
        tipo_b = tipos.get(b, "")
        a = {"tipo": "etiqueta", "bloque": b, "clave": clave, "valor": i["valor"] if i["tipo_valor"] != "binario" else None, "accion": "quitar", "como": "etiqueta"}
        marcada = (b, clave) in sel["etiqueta"]
        if clave in ("IPLS", "TIPL", "TMCL"):
            a.update(accion="regenerar" if deriv["ipls"] else "quitar", motivo="la lista de colaboradores se genera desde los créditos")
        elif clave == "VENDOR":
            a["motivo"] = "se escribe vacío (sin rastro de programa)"
        elif tipo_b.startswith(("RIFF bext", "RIFF iXML", "RIFF axml")):
            a["accion"] = "conservar" if b in sel["bloque"] else "quitar"
            a["como"] = "bloque"
            a["motivo"] = "forma parte del bloque «%s»: se conserva o se quita entero" % tipo_b
        elif i["tipo_valor"] == "binario":
            a["motivo"] = "contenido binario: no se puede reescribir" if marcada else None
            a["conservable"] = False
        elif fam == "mp4" and not (norm in ATOMO_MP4):
            a["conservable"] = False
            a["motivo"] = "M4A v1: solo campos estándar (los átomos libres llegan en v2)" if marcada else None
        elif marcada:
            if norm and norm in ef:
                a.update(accion="sustituir", motivo="lo declarado lo reemplaza")
            else:
                a["accion"] = "conservar"
                keep["items"].append(i)
        a["conservable"] = a.get("conservable", True) if clave not in ("IPLS", "TIPL", "TMCL", "VENDOR") else False
        acc.append(a)
    for d in R.binarios:
        a = {"tipo": "binario", "bloque": d["bloque"], "id": d["id"], "propietario": d["propietario"], "bytes": d["bytes"], "accion": "quitar", "conservable": True,
             "como": "binario" if "_cuerpo" in d else "bloque"}
        if d["id"] == "SEEKTABLE":
            a.update(accion="conservar", conservable=False, motivo="estructural (índice de búsqueda), no es una etiqueta")
            keep["bloques"].append(next(x for x in R.bloques if x["id"] == d["bloque"]))
        elif "_cuerpo" in d:
            if (d["bloque"], d["id"], d["propietario"]) in sel["binario"]:
                a["accion"] = "conservar"
                keep["frames"].append((d["_fid"], d["_cuerpo"]))
            if fam == "mp4":
                a["conservable"] = False
        elif d["bloque"] in sel["bloque"] and tipos.get(d["bloque"], "").startswith(("RIFF", "FLAC")):
            a["accion"] = "conservar"
            keep["bloques"].append(next(x for x in R.bloques if x["id"] == d["bloque"]))
        acc.append(a)
    for n, c in enumerate(R.caratulas):
        a = {"tipo": "caratula", "indice": n, "clave": c["origen"], "bytes": c["bytes"], "accion": "quitar", "conservable": True, "como": "caratula"}
        if n in sel["caratula"]:
            a["accion"] = "sustituir" if caratula_nueva else "conservar"
            if caratula_nueva:
                a["motivo"] = "la carátula nueva la reemplaza"
            else:
                keep["caratulas"].append(c)
        acc.append(a)
    for b in R.bloques:                                           # bext chunks etc. that hold only items
        if b["tipo"].startswith(("RIFF bext",)) and b["id"] in sel["bloque"]:
            keep["bloques"].append(b)
    keep["bloques"] = [b for n, b in enumerate(keep["bloques"]) if b not in keep["bloques"][:n]]
    return acc, keep


def _destinos(fam, deriv, decl, caratula, keep):
    """Where each declared field goes in this container, and what cannot (or only partly) be written."""
    ef, out = deriv["efectivos"], []
    col = {"mp3": 0, "wav": 0, "flac": 2, "mp4": 3}[fam]
    for k in CAMPOS:
        if k not in ef:
            continue
        m = MAPA[k]
        dest = {"mp3": m[0], "wav": " + ".join(x for x in ((("INFO:" + m[1]) if m[1] else None), m[0]) if x), "flac": m[2], "mp4": m[3] and ATOMO_MP4[k]}[fam]
        d = {"campo": k, "valor": ef[k] if k != "lyrics" else "%d caracteres" % len(ef[k]), "destino": dest, "estado": "ok"}
        if fam == "mp4" and not dest:
            d.update(estado="plegado" if k == "lyricist" else "no_soportado", destino="©cmt (comentario)" if k == "lyricist" else None,
                     motivo="M4A v1: solo campos estándar; la autoría de la letra se añade al comentario" if k == "lyricist" else "M4A v1: solo campos estándar (átomos libres en v2)")
        out.append(d)
    for n, v in decl["personalizados"].items():
        d = {"campo": "personalizado:" + n, "valor": v, "destino": {"mp3": "TXXX:" + n, "wav": "TXXX:" + n, "flac": n.upper(), "mp4": None}[fam], "estado": "ok"}
        if fam == "mp4":
            d.update(estado="no_soportado", motivo="M4A v1: solo campos estándar (átomos libres en v2)")
        out.append(d)
    if deriv["tiene_creditos"]:
        dest = {"mp3": "TXXX:CREDITS + IPLS", "wav": "id3: TXXX:CREDITS + IPLS (+ INFO:IENG)", "flac": "CREDITS + " + "/".join(sorted(deriv["vorbis"])), "mp4": "©cmt (comentario)"}[fam]
        out.append({"campo": "creditos", "valor": deriv["texto"], "destino": dest, "estado": "plegado" if fam == "mp4" else "ok",
                    **({"motivo": "M4A v1: los créditos viajan como texto en el comentario"} if fam == "mp4" else {})})
    if caratula:
        out.append({"campo": "caratula", "valor": "%s, %d KB" % (caratula[1], len(caratula[0]) // 1024), "destino": {"mp3": "APIC", "wav": "id3: APIC", "flac": "PICTURE", "mp4": "covr"}[fam], "estado": "ok"})
    return out


# ---------------------------------------------------------------------------------------------- constructores
def _ss(n):
    return bytes([(n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127])


def _enc(*textos):
    for t in textos:
        try:
            t.encode("latin-1")
        except UnicodeEncodeError:
            return 1
    return 0


def _txt(enc, s):
    return s.encode("latin-1") if enc == 0 else b"\xff\xfe" + s.encode("utf-16-le")


def _cad(enc, s):
    return _txt(enc, s) + (b"\0" if enc == 0 else b"\0\0")


def _frame_texto(fid, s):
    e = _enc(s)
    return fid, bytes([e]) + _txt(e, s)


def _frames_id3(deriv, decl, caratulas, keep, lang):
    """ID3v2.3 frames [(id, body)] + the manifest of what a reader must find."""
    ef, fr, man = deriv["efectivos"], [], []
    for k in CAMPOS:
        if k not in ef:
            continue
        fid, v = MAPA[k][0], ef[k]
        if k in ("comment", "lyrics"):
            e = _enc(v)
            fr.append((fid, bytes([e]) + lang.encode() + _cad(e, "") + _txt(e, v)))
            man.append({"clave": fid, "norm": k, "valor": v})
        elif k == "date":
            fr.append(_frame_texto("TYER", v[:4]))
            man.append({"clave": "TYER", "norm": "date", "valor": v[:4]})
            if len(v) > 4:
                e = _enc(v)
                fr.append(("TXXX", bytes([e]) + _cad(e, "DATE") + _txt(e, v)))
                man.append({"clave": "TXXX:DATE", "norm": None, "valor": v})
        else:
            fr.append(_frame_texto(fid, v))
            man.append({"clave": fid, "norm": k, "valor": v})
    for n, v in decl["personalizados"].items():
        e = _enc(n, v)
        fr.append(("TXXX", bytes([e]) + _cad(e, n) + _txt(e, v)))
        man.append({"clave": "TXXX:" + n, "norm": None, "valor": v})
    if deriv["tiene_creditos"]:
        e = _enc(deriv["texto"])
        fr.append(("TXXX", bytes([e]) + _cad(e, "CREDITS") + _txt(e, deriv["texto"])))
        man.append({"clave": "TXXX:CREDITS", "norm": None, "valor": deriv["texto"]})
        if deriv["ipls"]:
            cad = [s for p in deriv["ipls"] for s in p]
            e = _enc(*cad)
            fr.append(("IPLS", bytes([e]) + b"".join(_cad(e, s) for s in cad)))
            man.append({"clave": "IPLS", "norm": None, "valor": "; ".join("%s: %s" % p for p in deriv["ipls"])})
    for i in keep["items"]:                                       # kept text frames, re-serialised
        if i["bloque"] and i["clave_original"].startswith("INFO:"):
            continue
        c, v = i["clave_original"], i.get("_completo", i["valor"])
        if c.startswith("ID3v1:") and i["clave_normalizada"] in MAPA:
            fid = MAPA[i["clave_normalizada"]][0]
            fr.append((fid, b"\x00" + v.encode("latin-1", "replace")) if fid not in ("COMM", "USLT") else ("COMM", b"\x00" + lang.encode() + b"\0" + v.encode("latin-1", "replace")))
            man.append({"clave": fid, "norm": i["clave_normalizada"], "valor": v})
        elif c.startswith("TXXX:"):
            e = _enc(c[5:], v)
            fr.append(("TXXX", bytes([e]) + _cad(e, c[5:]) + _txt(e, v)))
            man.append({"clave": c, "norm": i["clave_normalizada"], "valor": v})
        elif c.split(":")[0] in ("COMM", "USLT"):
            e = _enc(v, i.get("descripcion") or "")
            fr.append((c.split(":")[0], bytes([e]) + (i.get("idioma") or lang).encode() + _cad(e, i.get("descripcion") or "") + _txt(e, v)))
            man.append({"clave": c, "norm": i["clave_normalizada"], "valor": v})
        elif re.fullmatch(r"T[A-Z0-9]{3}", c):
            fr.append(_frame_texto(c, v))
            man.append({"clave": c, "norm": i["clave_normalizada"], "valor": v})
        elif re.fullmatch(r"W[A-Z0-9]{3}", c):
            fr.append((c, v.encode("latin-1", "replace")))
            man.append({"clave": c, "norm": None, "valor": v})
    for fid, body in keep["frames"]:
        fr.append((fid, body))
    for d, mime, _ in caratulas:
        fr.append(("APIC", b"\x00" + mime.encode() + b"\0\x03\0" + d))
    return fr, man


def _tag_id3(frames):
    cuerpo = b"".join(f.encode("ascii") + struct.pack(">I", len(b)) + b"\0\0" + b for f, b in frames)
    return b"ID3\x03\x00\x00" + _ss(len(cuerpo)) + cuerpo


def _pares_vorbis(deriv, decl, keep):
    ef, out, man = deriv["efectivos"], [], []
    for k in CAMPOS:
        if k in ef:
            out.append((MAPA[k][2], ef[k]))
            man.append({"clave": MAPA[k][2], "norm": k, "valor": ef[k]})
    for k, v in sorted(deriv["vorbis"].items()):
        out.append((k, v))
        man.append({"clave": k, "norm": None, "valor": v})
    if deriv["tiene_creditos"]:
        out.append(("CREDITS", deriv["texto"]))
        man.append({"clave": "CREDITS", "norm": None, "valor": deriv["texto"]})
    for n, v in decl["personalizados"].items():
        out.append((n.upper(), v))
        man.append({"clave": n.upper(), "norm": None, "valor": v})
    ya = {k for k, _ in out}
    for i in keep["items"]:
        c = i["clave_original"]
        if c not in ya and re.fullmatch(r"[\x20-\x3c\x3e-\x7d]+", c):
            v = i.get("_completo", i["valor"])
            out.append((c, v))
            man.append({"clave": c, "norm": i["clave_normalizada"], "valor": v})
    return out, man


def _bloque_flac(tipo, cuerpo, ultimo=False):
    return bytes([(0x80 if ultimo else 0) | tipo]) + struct.pack(">I", len(cuerpo))[1:] + cuerpo


def _picture(d, mime):
    w, h, _ = I._img_info(d)
    return (struct.pack(">I", 3) + struct.pack(">I", len(mime)) + mime.encode() + struct.pack(">I", 0) +
            struct.pack(">IIII", w or 0, h or 0, 24 if mime == "image/jpeg" else 0, 0) + struct.pack(">I", len(d)) + d)


def _copiar(f, o, ini, n):
    f.seek(ini)
    while n > 0:
        b = f.read(min(1 << 20, n))
        if not b:
            raise ValueError("archivo cortado mientras se copiaba")
        o.write(b)
        n -= len(b)


# ---------------------------------------------------------------------------------------------- escritores por formato
def _escribir_mp3(src, dst, R, deriv, decl, caratulas, keep, lang):
    fr, man = _frames_id3(deriv, decl, caratulas, keep, lang)
    ini, fin = R.rangos[0]
    with open(src, "rb") as f, open(dst, "wb") as o:
        if fr:
            o.write(_tag_id3(fr))
        _copiar(f, o, ini, fin - ini)
    return man


def _escribir_wav(src, dst, R, deriv, decl, caratulas, keep, lang):
    ef, man = deriv["efectivos"], []
    with open(src, "rb") as f, open(dst, "wb") as o:
        tam = os.fstat(f.fileno()).st_size
        trozos, pos = [], 12
        while pos + 8 <= tam:
            f.seek(pos)
            cid, n = struct.unpack("<4sI", f.read(8))
            real = min(n, tam - pos - 8)
            trozos.append((cid, pos, real))
            pos += 8 + real + (real & 1)
        o.write(b"\0" * 12)
        total = 4

        def copia(p, real):
            nonlocal total
            _copiar(f, o, p, 8 + real)
            if real & 1:
                o.write(b"\0")
            total += 8 + real + (real & 1)

        def chunk(cid, cuerpo):
            nonlocal total
            o.write(cid + struct.pack("<I", len(cuerpo)) + cuerpo + (b"\0" if len(cuerpo) & 1 else b""))
            total += 8 + len(cuerpo) + (len(cuerpo) & 1)

        for cid, p, real in trozos:
            if cid in (b"fmt ", b"fact"):
                copia(p, real)
        for b in keep["bloques"]:
            for cid, p, real in trozos:
                if p == b["offset"]:
                    copia(p, real)
        info = []
        for k in ("title", "artist", "album", "date", "genre", "track", "comment", "copyright", "isrc"):
            if k in ef:
                info.append((MAPA[k][1], ef[k]))
                man.append({"clave": "INFO:" + MAPA[k][1], "norm": k, "valor": ef[k]})
        eng = "; ".join(v for r, v in sorted(deriv["vorbis"].items()) if r in ("MIXER", "ENGINEER"))
        if eng:
            info.append(("IENG", eng))
            man.append({"clave": "INFO:IENG", "norm": None, "valor": eng})
        ya = {c for c, _ in info}
        for i in keep["items"]:
            if i["clave_original"].startswith("INFO:") and i["clave_original"][5:] not in ya:
                info.append((i["clave_original"][5:], i["valor"]))
                man.append({"clave": i["clave_original"], "norm": i["clave_normalizada"], "valor": i["valor"]})
        if info:
            chunk(b"LIST", b"INFO" + b"".join(c.encode() + struct.pack("<I", len(v.encode()) + 1) + v.encode() + b"\0" + (b"\0" if (len(v.encode()) + 1) & 1 else b"") for c, v in info))
        fr, m2 = _frames_id3(deriv, decl, caratulas, keep, lang)
        if fr:
            chunk(b"id3 ", _tag_id3(fr))
            man += m2
        for cid, p, real in trozos:
            if cid == b"data":
                copia(p, real)
        o.seek(0)
        o.write(b"RIFF" + struct.pack("<I", total) + b"WAVE")
    return man


def _escribir_flac(src, dst, R, deriv, decl, caratulas, keep, lang):
    pares, man = _pares_vorbis(deriv, decl, keep)
    with open(src, "rb") as f:
        tam = os.fstat(f.fileno()).st_size
        ini = 0
        h = f.read(10)
        if h[:3] == b"ID3":
            ini = 10 + ((h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9])
        pos, blocs = ini + 4, []
        while True:
            f.seek(pos)
            h = f.read(4)
            ultimo, tipo, n = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:4], "big")
            blocs.append((tipo, pos, f.read(n)))
            pos += 4 + n
            if ultimo:
                break
        salida = [(0, next(b for t, p, b in blocs if t == 0))]
        for t, p, b in blocs:
            if t == 3 or (t in (2, 5) and any(k["offset"] == p for k in keep["bloques"])):
                salida.append((t, b))
        coms = [(k + "=" + v).encode("utf-8") for k, v in pares]
        vc = struct.pack("<I", 0) + struct.pack("<I", len(coms)) + b"".join(struct.pack("<I", len(c)) + c for c in coms)      # empty vendor string
        if pares:
            salida.append((4, vc))
        for d, mime, _ in caratulas:
            salida.append((6, _picture(d, mime)))
        with open(dst, "wb") as o:
            o.write(b"fLaC")
            for n, (t, b) in enumerate(salida):
                o.write(_bloque_flac(t, b, n == len(salida) - 1))
            _copiar(f, o, R.rangos[0][0], tam - R.rangos[0][0])
    return man


def _escribir_mp4(src, dst, R, deriv, decl, caratulas, keep, lang, ffmpeg):
    ef = dict(deriv["efectivos"])
    man, meta = [], []
    extra = [t for t in (deriv["texto"] if deriv["tiene_creditos"] else "",
                         ("Letra: " + decl["campos"]["lyricist"]) if "lyricist" in decl["campos"] and "Letra:" not in deriv["texto"] else "") if t]
    if extra:
        ef["comment"] = " | ".join(([ef["comment"]] if ef.get("comment") else []) + extra)
    for i in keep["items"]:
        if i["clave_normalizada"] in ATOMO_MP4 and i["clave_normalizada"] not in ef:
            ef[i["clave_normalizada"]] = i.get("_completo", i["valor"])
    for k, atomo in ATOMO_MP4.items():
        if k in ef:
            meta += ["-metadata", "%s=%s" % (MAPA[k][3], ef[k])]
            man.append({"clave": atomo, "norm": k, "valor": ef[k]})
    cmd = [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(src)]
    tmp_img = None
    if caratulas:
        d, mime, _ = caratulas[0]
        tmp_img = Path(str(dst) + ".cover" + (".png" if mime == "image/png" else ".jpg"))
        tmp_img.write_bytes(d)
        cmd += ["-i", str(tmp_img)]
    cmd += ["-map", "0:a"] + (["-map", "1:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"] if tmp_img else []) + \
           ["-map_metadata", "-1", "-map_chapters", "-1", "-c:a", "copy", "-fflags", "+bitexact", "-flags:a", "+bitexact", *meta, str(dst)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=900, creationflags=_NOCONSOLA)
    finally:
        if tmp_img:
            tmp_img.unlink(missing_ok=True)
    if r.returncode or not Path(dst).exists():
        raise ValueError("ffmpeg no pudo escribir la copia: " + (r.stderr or "")[-200:])
    return man


# ---------------------------------------------------------------------------------------------- verificación estricta
def md5_decodificado(ffmpeg, ruta):
    """MD5 of the decoded audio (ffmpeg -f md5): the same sound gives the same MD5 whatever the tags. None if it cannot be computed."""
    if not ffmpeg:
        return None
    try:
        r = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(ruta), "-map", "0:a", "-f", "md5", "-"], capture_output=True, text=True,
                           timeout=900, creationflags=_NOCONSOLA)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"MD5=([0-9a-f]{32})", r.stdout or "")
    return m.group(1) if m and not r.returncode else None


def _coincide(esp, it):
    v, n = esp["valor"], esp["norm"]
    if it is None:
        return False
    if n == "lyrics":
        return it.get("caracteres") == len(v) and it["valor"] == I._extracto(v)
    if n in ("track", "disc"):
        return str(it["valor"]).split("/")[0].lstrip("0") == str(v).split("/")[0].lstrip("0")
    if n == "date":
        return it["valor"] == v or (len(it["valor"]) == 4 and v.startswith(it["valor"]))
    return str(it["valor"]).strip() == str(v).strip()


def verificar(antes, despues, man, keep, md5_a, md5_d, n_caratulas):
    """Strict checks of the copy against the original. `ok` only if everything holds."""
    v = {"ok": False, "errores": [], "sha256_audio_igual": None, "md5_decodificado_igual": None, "lectura_de_vuelta": {"ok": True, "faltan": [], "distintos": []},
         "etiquetas_inesperadas": [], "bloques_conservados_ok": True, "caratulas_ok": True}
    if not despues.get("ok"):
        v["errores"].append("No se puede leer la copia escrita.")
        return v
    sa, sd = antes["archivo"]["sha256_audio"], despues["archivo"]["sha256_audio"]
    v["sha256_audio_igual"] = bool(sa) and sa == sd
    if not v["sha256_audio_igual"]:
        v["errores"].append("El sha256 del audio no coincide: la onda NO está intacta.")
    if md5_a is not None and md5_d is not None:
        v["md5_decodificado_igual"] = md5_a == md5_d
        if not v["md5_decodificado_igual"]:
            v["errores"].append("El audio decodificado no coincide.")
    if despues["errores"]:
        v["errores"].append("Fallo al leer la copia con las herramientas estándar: " + "; ".join(despues["errores"])[:160])
    nuevos = [a["codigo"] for a in despues["avisos"] if a["nivel"] == "error" and a["codigo"] not in {x["codigo"] for x in antes["avisos"]}]
    if nuevos:
        v["errores"].append("La copia tiene avisos graves nuevos: " + ", ".join(nuevos))
    items = despues["etiquetas"]
    por = {}
    for it in items:
        por.setdefault(it["clave_original"], []).append(it)
    for esp in man:
        cand = por.get(esp["clave"]) or [None]
        if cand[0] is None:
            v["lectura_de_vuelta"]["faltan"].append(esp["clave"])
        elif not any(_coincide(esp, c) for c in cand):
            v["lectura_de_vuelta"]["distintos"].append(esp["clave"])
    v["lectura_de_vuelta"]["ok"] = not (v["lectura_de_vuelta"]["faltan"] or v["lectura_de_vuelta"]["distintos"])
    perm = {m["clave"] for m in man} | {"VENDOR"}
    for b in keep["bloques"]:
        perm |= {i["clave_original"] for i in antes["etiquetas"] if i["bloque"] == b["id"]}
    v["etiquetas_inesperadas"] = sorted({it["clave_original"] for it in items if it["clave_original"] not in perm})
    for b in keep["bloques"]:
        if not any(x["tipo"] == b["tipo"] and x["bytes"] == b["bytes"] for x in despues["bloques_etiqueta"]):
            v["bloques_conservados_ok"] = False
    v["caratulas_ok"] = len(despues["incrustados"]["caratulas"]) == n_caratulas
    if not v["lectura_de_vuelta"]["ok"]:
        v["errores"].append("Lo escrito no se lee de vuelta igual (faltan o difieren campos).")
    if v["etiquetas_inesperadas"]:
        v["errores"].append("Quedan etiquetas que nadie declaró: " + ", ".join(v["etiquetas_inesperadas"]))
    if not v["bloques_conservados_ok"]:
        v["errores"].append("Un bloque conservado no quedó idéntico.")
    if not v["caratulas_ok"]:
        v["errores"].append("El número de carátulas no es el esperado.")
    v["ok"] = not v["errores"]
    return v


# ---------------------------------------------------------------------------------------------- API
def _caratula(caratula):
    if not caratula:
        return None
    d = caratula[0] if isinstance(caratula, tuple) else caratula
    w, h, mime = I._img_info(d)
    if mime not in ("image/jpeg", "image/png") or len(d) > MAX_CARATULA:
        raise ValueError("La carátula debe ser JPEG o PNG de menos de 8 MB.")
    return d, mime, (w, h)


def _compacta(r):
    return {"sha256": r["archivo"]["sha256"], "sha256_audio": r["archivo"]["sha256_audio"], "tamano_bytes": r["archivo"]["tamano_bytes"],
            "etiquetas": len(r["etiquetas"]), "caratulas": len(r["incrustados"]["caratulas"]), "bloques_binarios": len(r["incrustados"]["bloques_binarios"])}


def _cambios(antes, despues):
    a = {(i["clave_original"], str(i["valor"])) for i in antes["etiquetas"]}
    d = {(i["clave_original"], str(i["valor"])) for i in despues["etiquetas"]}
    f = lambda s: [{"clave": c, "valor": v[:80]} for c, v in sorted(s)]  # noqa: E731
    return {"quitadas": f(a - d), "escritas": f(d - a), "iguales": f(a & d)}


def etiquetar(src, dst, poner=None, creditos=None, conservar=None, caratula=None, ffmpeg=None, simular=True):
    """simular=True → the plan only (nothing is written). Otherwise writes `dst` (must not exist) after the strict verification."""
    src = Path(src)
    decl, errores = normalizar(poner, creditos)
    try:
        cara = _caratula(caratula)
    except ValueError as e:
        errores.append(str(e))
        cara = None
    if errores:
        return {"ok": False, "error": "Hay datos que corregir.", "campos_invalidos": errores}
    antes = I.inspeccionar(src, ffprobe="auto", ffmpeg=ffmpeg or None)
    if not antes.get("ok"):
        return {"ok": False, "error": "No se puede abrir el archivo."}
    R = _recorre(src)
    fam, avisos = R.familia, []
    deriv = derivar(decl)
    sel = _seleccion(conservar)
    acciones, keep = _clasificar(R, fam, decl, deriv, sel, cara)
    soporte = {"escritor": "ffmpeg" if fam == "mp4" else "python", "verificable": True}
    if _danado(antes["avisos"]):                                    # damaged first: an empty or corrupt «.wav» is not a «format without writer»
        soporte = {"escritor": None, "verificable": False}
        avisos.append({"codigo": "origen_danado", "nivel": "error", "mensaje": "El archivo está dañado o incompleto (%s): no se escribe sobre él." % ", ".join(a["codigo"] for a in _danado(antes["avisos"]))})
    elif fam not in ("mp3", "wav", "flac", "mp4"):
        soporte = {"escritor": None, "verificable": False}
        avisos.append({"codigo": "escritura_no_soportada", "nivel": "error", "mensaje": "Este formato es de solo lectura: no hay escritor seguro (se pueden inspeccionar sus etiquetas, no cambiarlas)."})
    elif fam == "mp4" and not ffmpeg:
        soporte = {"escritor": None, "verificable": False}
        avisos.append({"codigo": "sin_ffmpeg", "nivel": "error", "mensaje": "Para M4A hace falta ffmpeg (en v1 solo se escribe con ffmpeg)."})
    elif fam == "mp4" and R.noaudio:
        soporte = {"escritor": None, "verificable": False}
        avisos.append({"codigo": "escritura_no_soportada", "nivel": "error", "mensaje": "Este MP4 lleva pistas de vídeo u otras: de momento solo se escriben M4A de audio."})
    if soporte["escritor"] and not ffmpeg:
        avisos.append({"codigo": "md5_no_verificable", "nivel": "info", "mensaje": "Sin ffmpeg no se compara el audio decodificado; sí se exige el sha256 del audio."})
    se_escribira = _destinos(fam, deriv, decl, cara, keep) if soporte["escritor"] else []
    for d in se_escribira:
        if d["estado"] != "ok":
            avisos.append({"codigo": "campo_" + d["estado"], "nivel": "aviso", "campo": d["campo"], "mensaje": d.get("motivo", "")})
    plan = {"formato": fam, "soporte": soporte, "acciones": acciones, "se_escribira": se_escribira, "caratula": cara and {"mime": cara[1], "bytes": len(cara[0]), "ancho": cara[2][0], "alto": cara[2][1]},
            "avisos": avisos, "sha256_audio_origen": antes["archivo"]["sha256_audio"], "puede_aplicarse": bool(soporte["escritor"])}
    if simular:
        return {"ok": True, "simulacion": True, "plan": plan}
    if not soporte["escritor"]:
        return {"ok": False, "error": avisos[0]["mensaje"], "plan": plan}
    dst = Path(dst)
    if dst.exists() or dst.resolve() == src.resolve():
        return {"ok": False, "error": "El destino ya existe: no se sobrescribe nada."}
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp" + dst.suffix)
    lang = deriv["efectivos"].get("language") or "und"
    caratulas = [cara] if cara else [(c["_datos"], c["mime"] or "image/jpeg", None) for c in keep["caratulas"]]
    try:
        if fam == "mp3":
            man = _escribir_mp3(src, tmp, R, deriv, decl, caratulas, keep, lang)
        elif fam == "wav":
            man = _escribir_wav(src, tmp, R, deriv, decl, caratulas, keep, lang)
        elif fam == "flac":
            man = _escribir_flac(src, tmp, R, deriv, decl, caratulas, keep, lang)
        else:
            man = _escribir_mp4(src, tmp, R, deriv, decl, caratulas, keep, lang, ffmpeg)
        despues = I.inspeccionar(tmp, ffprobe="auto", ffmpeg=ffmpeg or None)
        ver = verificar(antes, despues, man, keep, md5_decodificado(ffmpeg, src), md5_decodificado(ffmpeg, tmp), len(caratulas))
        if not ver["ok"]:
            return {"ok": False, "error": "La verificación falló; no se entrega ninguna copia: " + " ".join(ver["errores"])[:300], "verificacion": ver, "plan": plan,
                    "antes": _compacta(antes), "despues": _compacta(despues) if despues.get("ok") else None}
        os.replace(tmp, dst)
    except (ValueError, OSError, struct.error, IndexError, StopIteration) as e:
        return {"ok": False, "error": "No se pudo escribir la copia: %s" % str(e)[:200], "plan": plan}
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True, "simulacion": False, "plan": plan, "verificacion": ver, "antes": _compacta(antes), "despues": _compacta(despues), "cambios": _cambios(antes, despues),
            "_informe": {"antes": antes, "despues": despues, "declarado": {"poner": decl, "conservar": conservar or []}}}


# ---------------------------------------------------------------------------------------------- registro
def registrar(datos_modulo, rel_src, rel_dst, res):
    """Hash registry (datos/modulos/huella/hashes.json), before/after report (…/etiquetado/<id>.json) and a journal line (op «etiquetar»)."""
    datos = Path(datos_modulo)
    rid, ahora = "etq-" + secrets.token_hex(5), time.strftime("%Y-%m-%d %H:%M:%S")
    inf = res["_informe"]
    antes, despues = inf["antes"], inf["despues"]
    (datos / "etiquetado").mkdir(parents=True, exist_ok=True)
    (datos / "etiquetado" / (rid + ".json")).write_text(json.dumps({"id": rid, "t": ahora, "origen": rel_src, "copia": rel_dst, "declarado": inf["declarado"], "cambios": res["cambios"],
                                                                      "verificacion": res["verificacion"], "antes": antes, "despues": despues}, ensure_ascii=False, indent=1), encoding="utf-8")
    ph = datos / "hashes.json"
    try:
        h = json.loads(ph.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        h = {}
    ficha = h.setdefault(antes["archivo"]["sha256_audio"], {"creado": ahora, "versiones": []})
    if not any(x["sha256"] == antes["archivo"]["sha256"] for x in ficha["versiones"]):
        ficha["versiones"].append({"id": None, "t": ahora, "p": rel_src, "sha256": antes["archivo"]["sha256"], "origen": True})
    ficha["versiones"].append({"id": rid, "t": ahora, "p": rel_dst, "sha256": despues["archivo"]["sha256"], "origen": False})
    tmp = ph.with_name("hashes.json.tmp")
    tmp.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ph)
    with open(datos.parent.parent / "diario_movimientos.jsonl", "a", encoding="utf-8") as j:
        j.write(json.dumps({"id": rid, "t": ahora, "op": "etiquetar", "src": rel_src, "dst": rel_dst, "sha256_audio": antes["archivo"]["sha256_audio"],
                            "sha256_antes": antes["archivo"]["sha256"], "sha256_despues": despues["archivo"]["sha256"], "quitadas": len(res["cambios"]["quitadas"]),
                            "escritas": [c["clave"] for c in res["cambios"]["escritas"]]}, ensure_ascii=False) + "\n")
    return rid
