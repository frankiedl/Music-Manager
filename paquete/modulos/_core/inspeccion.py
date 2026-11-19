"""Technical inspection of an audio file: everything that travels in the container besides the sound (schema huella.inspeccion/1).

    inspeccionar(ruta, ffprobe="auto", raiz=None, senal=False, ffmpeg="auto") -> dict

Layer A (always, standard library only): size, SHA-256 of the file and of the audio alone, and a walk of the container that reads
every tag block byte by byte: ID3v1/v2 (all frames, stacked tags included), RIFF/WAV (bext, LIST/INFO, iXML, unknown chunks), FLAC
(Vorbis comment, picture, application, padding) and MP4/M4A (ilst, '----' freeform atoms, covr).
Layer B (optional): `ffprobe -of json` for codec, sample rate, exact duration, streams and chapters. When it is missing the technical
fields come from layer A (some become `null` or estimated: see `campos_origen` and `avisos`).
Section «senal» (optional, `senal=True`): levels, loudness and spectrum, computed by senal.py. `null` when not requested.

Nothing here modifies the file. Every key of the schema always exists: what is absent is `null` or `[]`.
Tags are listed with `estandar` (known field of the format) and `editable` (a writer could change it); container data (codec, rate,
duration, offsets, hashes) is informative only. Opaque binary blocks (PRIV, GEOB, unknown chunks…) live in
`incrustados.bloques_binarios`; they are copied to `etiquetas` only when they carry readable text, and then as non-editable.
"""
import hashlib
import json
import re
import shutil
import struct
import subprocess
import time
from pathlib import Path

SCHEMA = "huella.inspeccion/1"
BLOQUE = 1 << 20
MAX_TAG = 64 << 20
_NOCONSOLA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------------------------- tablas
NORM_ID3 = {"TIT2": "title", "TPE1": "artist", "TALB": "album", "TPE2": "album_artist", "TDRC": "date", "TYER": "date", "TCON": "genre",
            "TRCK": "track", "TPOS": "disc", "TCOM": "composer", "TPUB": "publisher", "TSRC": "isrc", "TCOP": "copyright", "TENC": "encoded_by",
            "TSSE": "encoder", "COMM": "comment", "USLT": "lyrics", "SYLT": "lyrics", "TBPM": "bpm", "TKEY": "initial_key", "TLAN": "language"}
NORM_VORBIS = {"TITLE": "title", "ARTIST": "artist", "ALBUM": "album", "ALBUMARTIST": "album_artist", "DATE": "date", "GENRE": "genre",
               "TRACKNUMBER": "track", "DISCNUMBER": "disc", "COMPOSER": "composer", "PUBLISHER": "publisher", "ORGANIZATION": "publisher",
               "ISRC": "isrc", "COPYRIGHT": "copyright", "LICENSE": "copyright", "ENCODED-BY": "encoded_by", "ENCODER": "encoder",
               "COMMENT": "comment", "DESCRIPTION": "comment", "LYRICS": "lyrics", "UNSYNCEDLYRICS": "lyrics", "BPM": "bpm", "LANGUAGE": "language"}
NORM_INFO = {"INAM": "title", "IART": "artist", "IPRD": "album", "ICRD": "date", "IGNR": "genre", "ICMT": "comment", "ICOP": "copyright",
             "ISFT": "encoder", "ITCH": "encoded_by", "ISRC": "isrc", "ITRK": "track", "IPRT": "track", "ICMS": "publisher"}
NORM_MP4 = {"©nam": "title", "©ART": "artist", "©alb": "album", "aART": "album_artist", "©day": "date", "©gen": "genre", "gnre": "genre",
            "©cmt": "comment", "cprt": "copyright", "©too": "encoder", "©wrt": "composer", "©lyr": "lyrics", "trkn": "track", "disk": "disc",
            "tmpo": "bpm", "desc": "comment"}
CAT = {"title": "identificacion", "artist": "identificacion", "album": "identificacion", "album_artist": "identificacion", "date": "identificacion",
       "genre": "identificacion", "track": "identificacion", "disc": "identificacion", "comment": "identificacion", "lyrics": "identificacion",
       "language": "identificacion", "isrc": "derechos", "copyright": "derechos", "publisher": "derechos", "composer": "derechos",
       "encoded_by": "software", "encoder": "software", "bpm": "produccion", "initial_key": "produccion"}
APIC_TIPOS = ["other", "32x32 icon", "other icon", "front cover", "back cover", "leaflet", "media", "lead artist", "artist", "conductor", "band",
              "composer", "lyricist", "recording location", "during recording", "during performance", "video capture", "bright fish",
              "illustration", "band logo", "publisher logo"]
LOSSLESS = ("pcm_", "flac", "alac", "wavpack", "ape", "tta", "mlp", "truehd")
FORMATOS = {"wav": "WAV / Waveform Audio", "mp3": "MP2/3 (MPEG audio layer 2/3)", "flac": "raw FLAC", "mp4": "QuickTime / MOV (MP4)"}
FORMATO_CORTO = {"wav": "wav", "mp3": "mp3", "flac": "flac", "mp4": "mov,mp4,m4a,3gp,3g2,mj2"}
# what the extension promises → family (to tell "other format" from "corrupt file")
EXT_FAMILIA = {".wav": "wav", ".wave": "wav", ".mp3": "mp3", ".flac": "flac", ".m4a": "mp4", ".mp4": "mp4", ".m4b": "mp4", ".mov": "mp4",
               ".ogg": "ogg", ".oga": "ogg", ".opus": "ogg", ".aif": "aiff", ".aiff": "aiff", ".aifc": "aiff", ".wma": "wma"}
SIN_RECORRIDO = {"ogg", "aiff", "wma", "rf64"}                 # real formats without a walker of their own: only ffprobe tells their tags
EXT_SIN_RECORRIDO = {".aac", ".ac3", ".dts", ".ape", ".wv", ".mka", ".caf", ".amr", ".tta"}
NOMBRE_FAMILIA = {"wav": "WAV", "mp3": "MP3", "flac": "FLAC", "mp4": "MP4/M4A", "ogg": "Ogg", "aiff": "AIFF", "wma": "WMA/ASF", "rf64": "RF64"}


class _R:
    """Accumulator of what the layer-A walk finds."""
    def __init__(s):
        s.items, s.bloques, s.caratulas, s.letras, s.binarios, s.noaudio, s.avisos = [], [], [], [], [], [], []
        s.tech, s.audio, s.rangos, s.familia, s.padding, s.wav = {}, {}, [], None, 0, None
        s._n = 0

    def bloque(s, tipo, offset, nbytes):
        s._n += 1
        bid = "b%d" % s._n
        s.bloques.append({"id": bid, "tipo": tipo, "offset": offset, "bytes": nbytes})
        return bid

    def aviso(s, cod, nivel, msg):
        s.avisos.append({"codigo": cod, "nivel": nivel, "mensaje": msg})

    def item(s, bloque, orig, valor, norm=None, tipo="texto", desc=None, idioma=None, categoria=None, editable=True, estandar=None, **extra):
        d = {"bloque": bloque, "clave_original": orig, "clave_normalizada": norm, "valor": valor, "tipo_valor": tipo, "descripcion": desc,
             "idioma": idioma, "categoria": categoria or (CAT.get(norm) if norm else "personalizado"),
             "estandar": (norm is not None) if estandar is None else estandar, "editable": editable, "origen": "python"}
        d.update(extra)
        s.items.append(d)
        return d

    def binario(s, ident, bloque, datos=None, n=None, sha=None, propietario=None, descripcion=None, mime=None, nombre=None, clave=None):
        """Opaque block → incrustados.bloques_binarios. Also copied to `etiquetas` (as non-editable text) only if it carries readable text."""
        texto = _legible(datos) if datos is not None else None
        d = {"id": ident, "bloque": bloque, "propietario": propietario, "descripcion": descripcion, "mime": mime, "nombre_archivo": nombre,
             "bytes": len(datos) if datos is not None else n, "sha256": _sha(datos) if datos is not None else sha,
             "texto_legible": texto is not None, "editable": False}
        s.binarios.append(d)
        if texto is not None and clave:
            s.item(bloque, clave, _extracto(texto, 200), None, "texto", desc=descripcion or propietario, categoria="personalizado",
                   editable=False, estandar=False, caracteres=len(texto))
        return d


# ---------------------------------------------------------------------------------------------- utilidades
def _sha_rango(f, ini, fin, h=None):
    h = h or hashlib.sha256()
    f.seek(ini)
    n = fin - ini
    while n > 0:
        b = f.read(min(BLOQUE, n))
        if not b:
            break
        h.update(b)
        n -= len(b)
    return h


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _txt(b, enc="utf-8"):
    return b.decode(enc, "replace").rstrip("\x00").strip()


def _extracto(s, n=120):
    s = s.replace("\r", " ").replace("\n", " ⏎ ")
    return s if len(s) <= n else s[:n] + "…"


def _legible(b):
    """The text inside a binary payload if it is mostly printable (utf-8 or utf-16 with BOM), else None."""
    if not b or len(b) < 4:
        return None
    try:
        t = b.decode("utf-16") if b[:2] in (b"\xff\xfe", b"\xfe\xff") else b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    t = t.strip("\x00 \t\r\n")
    if len(t) < 4:
        return None
    ok = sum(1 for c in t if c.isprintable() or c in "\r\n\t")
    return t if ok / len(t) >= 0.9 else None


def _img_info(data):
    """(width, height, mime) of JPEG/PNG/GIF without libraries."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h, "image/png"
        if data[:3] == b"GIF":
            w, h = struct.unpack("<HH", data[6:10])
            return w, h, "image/gif"
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                m = data[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                n = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h, "image/jpeg"
                i += 2 + n
            return None, None, "image/jpeg"
    except struct.error:
        pass
    return None, None, None


def _caratula(R, origen, tipo_img, mime, data, stream_index=None, desc=None):
    w, h, m2 = _img_info(data)
    R.caratulas.append({"origen": origen, "stream_index": stream_index, "tipo_imagen": tipo_img, "mime": mime or m2, "ancho": w, "alto": h,
                        "bytes": len(data), "sha256": _sha(data), "descripcion": desc})


def _letra(R, origen, texto, sincronizada=False, idioma=None, desc=None):
    R.letras.append({"origen": origen, "sincronizada": sincronizada, "idioma": idioma, "descripcion": desc,
                     "caracteres": len(texto), "extracto": _extracto(texto)})


# ---------------------------------------------------------------------------------------------- ID3
def _ss(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _dec(enc, b, bom=None):
    """Decodes an ID3 string. bom = endianness inherited (some writers put the BOM only on the first string)."""
    if enc == 0:
        return b.decode("latin-1").rstrip("\x00")
    if enc == 3:
        return b.decode("utf-8", "replace").rstrip("\x00")
    if enc == 2:
        return b.decode("utf-16-be", "replace").rstrip("\x00")
    if b[:2] == b"\xff\xfe":
        return b[2:].decode("utf-16-le", "replace").rstrip("\x00")
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be", "replace").rstrip("\x00")
    return b.decode("utf-16-le" if bom != "be" else "utf-16-be", "replace").rstrip("\x00")


def _corta(enc, b):
    """Splits b into (string, rest) at the terminator of the encoding."""
    if enc in (1, 2):
        i = 0
        while i + 1 < len(b):
            if b[i] == 0 and b[i + 1] == 0 and i % 2 == 0:
                return b[:i], b[i + 2:]
            i += 1
        return b, b""
    i = b.find(b"\0")
    return (b, b"") if i < 0 else (b[:i], b[i + 1:])


def _id3v2(R, f, off, tam):
    f.seek(off)
    h = f.read(10)
    if len(h) < 10 or h[:3] != b"ID3":
        return 0
    ver, flags, size = h[3], h[5], _ss(h[6:10])
    total = 10 + size + (10 if flags & 0x10 else 0)
    if off + 10 + size > tam:
        R.aviso("tag_truncado", "aviso", "El tag ID3v2 declara más bytes de los que tiene el archivo: el archivo está cortado o el tag es incorrecto.")
        size = max(0, tam - off - 10)
    if size > MAX_TAG:
        R.aviso("tag_enorme", "aviso", "ID3v2 de más de 64 MB: no se lee.")
        return total
    data = f.read(size)
    bid = R.bloque("ID3v2.%d" % ver, off, total)
    if ver not in (3, 4):
        R.aviso("id3_version", "aviso", "ID3v2.%d no se analiza (solo 2.3 y 2.4)." % ver)
        return total
    if ver == 3 and flags & 0x80:
        data = data.replace(b"\xff\x00", b"\xff")
    pos = 0
    if flags & 0x40:
        pos = _ss(data[:4]) if ver == 4 else 4 + int.from_bytes(data[:4], "big")
    while pos + 10 <= len(data):
        fid = data[pos:pos + 4]
        if fid[0] == 0:
            R.padding += len(data) - pos
            break
        try:
            fid_s = fid.decode("ascii")
        except UnicodeDecodeError:
            R.aviso("frame_corrupto", "aviso", "Frame ID3 con identificador no ASCII: se detiene la lectura de ese tag.")
            break
        sz = _ss(data[pos + 4:pos + 8]) if ver == 4 else int.from_bytes(data[pos + 4:pos + 8], "big")
        fl = data[pos + 8:pos + 10]
        body = data[pos + 10:pos + 10 + sz]
        pos += 10 + sz
        if ver == 4:
            if fl[1] & 0x01:
                body = body[4:]
            if fl[1] & 0x02:
                body = body.replace(b"\xff\x00", b"\xff")
            opaco = bool(fl[1] & 0x0C)       # compressed / encrypted
        else:
            opaco = bool(fl[1] & 0xC0)
        _frame(R, bid, fid_s, body, opaco)
    return total


def _frame(R, bid, fid, body, opaco):
    N = NORM_ID3.get(fid)
    if opaco or not body:
        if body:
            R.aviso("frame_opaco", "info", "El frame %s está comprimido o cifrado: no se puede leer su contenido." % fid)
        R.item(bid, fid, None, N, "binario", bytes=len(body), sha256=_sha(body), editable=False)
        return
    enc = body[0]
    if fid in ("TXXX", "WXXX"):
        d, v = _corta(enc, body[1:])
        desc = _dec(enc, d)
        val = _dec(enc, v, "le") if fid == "TXXX" else v.decode("latin-1")
        n = NORM_VORBIS.get(desc.upper()) if fid == "TXXX" else None
        R.item(bid, "%s:%s" % (fid, desc), val, n, desc=desc)
    elif fid[0] == "T":
        partes = [_dec(enc, p) for p in (body[1:].split(b"\0\0" if enc in (1, 2) else b"\0"))]
        R.item(bid, fid, " / ".join(p for p in partes if p), N)
    elif fid[0] == "W":
        R.item(bid, fid, body.decode("latin-1").rstrip("\x00"), N)
    elif fid in ("COMM", "USLT"):
        lang = body[1:4].decode("latin-1")
        d, v = _corta(enc, body[4:])
        desc = _dec(enc, d)
        t = _dec(enc, v, "be" if body[4:6] == b"\xfe\xff" else "le")
        if fid == "USLT":
            _letra(R, "USLT", t, False, lang, desc or None)
            R.item(bid, "USLT:%s" % desc if desc else "USLT", _extracto(t), "lyrics", desc=desc or None, idioma=lang, caracteres=len(t))
        else:
            R.item(bid, "COMM:%s" % desc if desc else "COMM", t, "comment", desc=desc or None, idioma=lang)
    elif fid == "SYLT":
        lang = body[1:4].decode("latin-1")
        d, v = _corta(enc, body[6:])
        _letra(R, "SYLT", "", True, lang, _dec(enc, d) or None)
        R.item(bid, "SYLT", None, "lyrics", "binario", idioma=lang, bytes=len(v), sha256=_sha(v), editable=True)
    elif fid == "APIC":
        mime_b, resto = _corta(0, body[1:])
        tipo = resto[0]
        d, img = _corta(enc, resto[1:])
        _caratula(R, "APIC", APIC_TIPOS[tipo] if tipo < len(APIC_TIPOS) else "tipo %d" % tipo, mime_b.decode("latin-1"), img, None, _dec(enc, d) or None)
    elif fid == "PRIV":
        own, data = _corta(0, body)
        o = own.decode("latin-1")
        R.binario("PRIV", bid, data, propietario=o, clave="PRIV:" + o)
    elif fid == "GEOB":
        mime_b, r = _corta(0, body[1:])
        fn, r = _corta(enc, r)
        d, data = _corta(enc, r)
        desc = _dec(enc, d)
        R.binario("GEOB", bid, data, descripcion=desc or None, mime=mime_b.decode("latin-1") or None, nombre=_dec(enc, fn) or None, clave="GEOB:" + desc)
    elif fid == "UFID":
        own, data = _corta(0, body)
        R.item(bid, "UFID:%s" % own.decode("latin-1"), data.decode("latin-1", "replace"), None, desc=own.decode("latin-1"))
    else:
        R.binario(fid, bid, body, clave=fid)


def _id3v1(R, f, tam):
    if tam < 128:
        return False
    f.seek(tam - 128)
    b = f.read(128)
    if b[:3] != b"TAG":
        return False
    bid = R.bloque("ID3v1", tam - 128, 128)
    cam = [("title", b[3:33]), ("artist", b[33:63]), ("album", b[63:93]), ("date", b[93:97])]
    c = b[97:127]
    if c[28] == 0 and c[29] != 0:
        cam.append(("track", str(c[29]).encode()))
        c = c[:28]
    cam.append(("comment", c))
    for k, v in cam:
        t = _txt(v, "latin-1")
        if t:
            R.item(bid, "ID3v1:" + k, t, k)
    return True


# ---------------------------------------------------------------------------------------------- MP3
_BR1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
_BR2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
_SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3(R, f, tam):
    R.familia = "mp3"
    ini = 0
    while True:
        n = _id3v2(R, f, ini, tam)
        if not n:
            break
        ini += n
    fin = tam
    if _id3v1(R, f, tam):
        fin -= 128
    f.seek(max(0, fin - 32))
    if f.read(32)[:8] == b"APETAGEX":
        R.bloque("APEv2", fin - 32, 32)
        R.aviso("apev2", "aviso", "Hay un tag APEv2 al final: se excluye del audio pero su contenido no se analiza.")
    R.rangos.append((ini, fin))
    f.seek(ini)
    cab = f.read(65536)
    for i in range(len(cab) - 4):
        if cab[i] == 0xFF and cab[i + 1] & 0xE0 == 0xE0:
            h = struct.unpack(">I", cab[i:i + 4])[0]
            ver, layer, bri, sri = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3
            if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
                continue
            br = (_BR1 if ver == 3 else _BR2)[bri] * 1000
            sr = _SR[ver][sri]
            mono = ((h >> 6) & 3) == 3
            spf = 1152 if ver == 3 else 576
            R.audio.update({"codec": "mp3", "tasa_muestreo_hz": sr, "canales": 1 if mono else 2, "disposicion_canales": "mono" if mono else "stereo",
                            "bitrate_bps": br, "sin_perdida": False})
            lado = (17 if mono else 32) if ver == 3 else (9 if mono else 17)
            x = cab[i + 4 + lado:i + 4 + lado + 12]
            if x[:4] in (b"Xing", b"Info") and x[7] & 1:
                R.tech["duracion_s"] = struct.unpack(">I", x[8:12])[0] * spf / sr
                R.tech["duracion_origen"] = "python"
            else:
                R.tech["duracion_s"] = (fin - ini - i) * 8 / br
                R.tech["duracion_origen"] = "python_estimada"
                R.aviso("duracion_estimada", "info", "Sin cabecera Xing/Info: duración estimada por tamaño/bitrate (solo exacta en CBR).")
            R.tech["bitrate_bps"] = br
            return
    R.aviso("sin_frames", "aviso", "No encuentro ningún frame MPEG en los primeros 64 KB tras las etiquetas: el archivo no parece un MP3 válido.")


# ---------------------------------------------------------------------------------------------- WAV / RIFF
def _wav(R, f, tam):
    R.familia = "wav"
    f.seek(0)
    h = f.read(12)
    if len(h) < 12 or h[8:12] != b"WAVE":
        R.aviso("riff_no_wave", "error", "Contenedor RIFF que no es WAVE.")
        return
    pos, fmt, data_n, vio_data = 12, None, 0, False
    while pos + 8 <= tam:
        f.seek(pos)
        ch = f.read(8)
        cid, n = ch[:4], struct.unpack("<I", ch[4:])[0]
        ini = pos + 8
        real = min(n, tam - ini)
        if n > tam - ini:
            R.aviso("chunk_truncado", "aviso", "El chunk %s declara %d bytes pero el archivo termina antes: archivo cortado." % (cid.decode("latin-1"), n))
        sig = ini + real + (real & 1)
        nombre = cid.decode("latin-1")
        if cid == b"fmt ":
            fmt = _fmt(f, ini, real)
        elif cid == b"data":
            vio_data = True
            data_n = real
            R.rangos.append((ini, ini + real))
            R.wav_data = (ini, ini + real)
            if sig < tam:
                R.aviso("bytes_tras_data", "info", "Hay %d bytes de chunks detrás de 'data'." % (tam - sig))
        elif cid == b"bext":
            f.seek(ini)
            _bext(R, R.bloque("RIFF bext", pos, 8 + real + (real & 1)), f.read(real))
        elif cid == b"LIST":
            f.seek(ini)
            body = f.read(real)
            if body[:4] == b"INFO":
                bid = R.bloque("RIFF LIST/INFO", pos, 8 + real + (real & 1))
                p = 4
                while p + 8 <= len(body):
                    sid, sn = body[p:p + 4].decode("latin-1"), struct.unpack("<I", body[p + 4:p + 8])[0]
                    v = _txt(body[p + 8:p + 8 + sn])
                    nrm = NORM_INFO.get(sid)
                    R.item(bid, "INFO:" + sid, v, nrm, estandar=sid in NORM_INFO or sid == "IENG")
                    if nrm == "lyrics":
                        _letra(R, "INFO", v)
                    p += 8 + sn + (sn & 1)
            else:
                _opaco(R, f, "LIST/" + body[:4].decode("latin-1"), pos, ini, real)
        elif cid in (b"iXML", b"axml"):
            f.seek(ini)
            _ixml(R, R.bloque("RIFF " + nombre, pos, 8 + real + (real & 1)), nombre, f.read(real))
        elif cid in (b"id3 ", b"ID3 "):
            _id3v2(R, f, ini, tam)
        else:
            _opaco(R, f, nombre.strip(), pos, ini, real)
        pos = sig
    if fmt is None:
        R.aviso("wav_sin_fmt", "error", "El WAV no tiene chunk 'fmt ': no se puede saber cómo está codificado el audio (archivo corrupto o incompleto).")
        return
    if not vio_data:
        R.aviso("wav_sin_data", "error", "El WAV no tiene chunk 'data': no contiene audio (archivo corrupto o incompleto).")
    tag, ch_, sr, bps, align, bits = fmt
    codec = {1: "pcm_s%dle" % bits if bits > 8 else "pcm_u8", 3: "pcm_f%dle" % bits}.get(tag, "wav_0x%04x" % tag)
    R.audio.update({"codec": codec, "tasa_muestreo_hz": sr, "canales": ch_, "bits_por_muestra": bits, "bitrate_bps": bps * 8,
                    "disposicion_canales": {1: "mono", 2: "stereo"}.get(ch_), "sin_perdida": tag in (1, 3)})
    if tag in (1, 3) and vio_data:
        R.wav = (R.wav_data[0], R.wav_data[1], bits, tag == 3)
    if bps and vio_data:
        R.tech["duracion_s"] = data_n / bps
        R.tech["duracion_origen"] = "python"
        R.tech["bitrate_bps"] = bps * 8
        R.audio["n_muestras"] = data_n // align if align else None


def _fmt(f, ini, n):
    f.seek(ini)
    b = f.read(n)
    tag, ch, sr, bps, align, bits = struct.unpack("<HHIIHH", b[:16])
    if tag == 0xFFFE and len(b) >= 26:
        tag = struct.unpack("<H", b[24:26])[0]
    return tag, ch, sr, bps, align, bits


def _opaco(R, f, nombre, pos, ini, real):
    bid = R.bloque("RIFF " + nombre, pos, 8 + real + (real & 1))
    R.binario(nombre, bid, None, n=real, sha=_sha_rango(f, ini, ini + real).hexdigest())


def _bext(R, bid, b):
    if len(b) < 602:
        R.aviso("bext_corto", "aviso", "Chunk bext de %d bytes (mínimo 602)." % len(b))
        return
    ver = struct.unpack("<H", b[346:348])[0]
    campos = [("Description", _txt(b[0:256])), ("Originator", _txt(b[256:288])), ("OriginatorReference", _txt(b[288:320])),
              ("OriginationDate", _txt(b[320:330])), ("OriginationTime", _txt(b[330:338])),
              ("TimeReference", str(struct.unpack("<Q", b[338:346])[0])), ("CodingHistory", _txt(b[602:]))]
    if any(b[348:412]):
        campos.append(("UMID", b[348:412].hex()))
    for k, v in campos:
        if v:
            R.item(bid, "bext:" + k, v, None, categoria="produccion", estandar=True)
    R.item(bid, "bext:BextVersion", str(ver), None, categoria="tecnico", estandar=True, editable=False)


def _ixml(R, bid, nombre, b):
    t = _txt(b)
    n = 0
    for k, v in re.findall(r"<([A-Za-z_][A-Za-z0-9_]*)>([^<>]+)</\1>", t):
        R.item(bid, "iXML:" + k, v.strip(), None, categoria="produccion", estandar=not k.upper().startswith("USER"))
        n += 1
        if n >= 60:
            break
    d = R.binario(nombre, bid, b)
    d["texto_legible"] = True


# ---------------------------------------------------------------------------------------------- FLAC
def _flac(R, f, tam):
    R.familia = "flac"
    ini = 0
    while True:
        n = _id3v2(R, f, ini, tam)
        if not n:
            break
        ini += n
    f.seek(ini)
    if f.read(4) != b"fLaC":
        R.aviso("flac_cabecera", "error", "No encuentro la marca fLaC: el archivo no es un FLAC válido.")
        return
    pos, completo, primero = ini + 4, False, True
    while pos + 4 <= tam:
        f.seek(pos)
        h = f.read(4)
        ultimo, tipo, n = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:], "big")
        ini_b = pos + 4
        if ini_b + n > tam:
            break                                          # truncated block: the loop ends with `completo` False
        if primero and tipo != 0:
            R.aviso("flac_sin_streaminfo", "error", "El primer bloque del FLAC no es STREAMINFO: archivo corrupto.")
        primero = False
        f.seek(ini_b)
        body = f.read(n) if n <= MAX_TAG else b""
        nombre = {0: "STREAMINFO", 1: "PADDING", 2: "APPLICATION", 3: "SEEKTABLE", 4: "VORBIS_COMMENT", 5: "CUESHEET", 6: "PICTURE"}.get(tipo, "tipo%d" % tipo)
        if tipo == 0 and len(body) >= 34:
            v = int.from_bytes(body[10:18], "big")
            sr, ch, bps, total = v >> 44, ((v >> 41) & 7) + 1, ((v >> 36) & 31) + 1, v & ((1 << 36) - 1)
            R.audio.update({"codec": "flac", "tasa_muestreo_hz": sr, "canales": ch, "bits_por_muestra": bps, "sin_perdida": True,
                            "disposicion_canales": {1: "mono", 2: "stereo"}.get(ch), "n_muestras": total or None})
            if total and sr:
                R.tech["duracion_s"] = total / sr
                R.tech["duracion_origen"] = "python"
        elif tipo == 1:
            R.padding += n
            R.bloque("FLAC PADDING", pos, 4 + n)
        elif tipo == 4:
            _vorbis(R, R.bloque("Vorbis comment (FLAC)", pos, 4 + n), body)
        elif tipo == 6:
            R.bloque("FLAC PICTURE", pos, 4 + n)
            _picture(R, body)
        elif tipo == 2:
            bid = R.bloque("FLAC APPLICATION", pos, 4 + n)
            R.binario("APPLICATION", bid, body[4:], propietario=body[:4].decode("latin-1"), clave="APPLICATION:" + body[:4].decode("latin-1"))
        else:
            bid = R.bloque("FLAC " + nombre, pos, 4 + n)
            if tipo in (3, 5):
                R.binario(nombre, bid, body)
        pos = ini_b + n
        if ultimo:
            completo = True
            break
    if completo:
        R.rangos.append((pos, tam))
    else:
        R.aviso("flac_truncado", "error", "El FLAC está truncado: los bloques de metadatos no terminan dentro del archivo. Las etiquetas pueden faltar o "
                "estar incompletas y no se puede calcular el hash del audio.")


def _vorbis(R, bid, body):
    vl = struct.unpack("<I", body[:4])[0]
    R.item(bid, "VENDOR", _txt(body[4:4 + vl]), "encoder", categoria="software", editable=False)
    p = 4 + vl
    cnt = struct.unpack("<I", body[p:p + 4])[0]
    p += 4
    for _ in range(cnt):
        ln = struct.unpack("<I", body[p:p + 4])[0]
        c = body[p + 4:p + 4 + ln].decode("utf-8", "replace")
        p += 4 + ln
        k, _, val = c.partition("=")
        nrm = NORM_VORBIS.get(k.upper())
        R.item(bid, k, _extracto(val) if nrm == "lyrics" else val, nrm, **({"caracteres": len(val)} if nrm == "lyrics" else {}))
        if nrm == "lyrics":
            _letra(R, k.upper(), val)


def _picture(R, body):
    t, ml = struct.unpack(">II", body[:8])
    mime = body[8:8 + ml].decode("latin-1")
    p = 8 + ml
    dl = struct.unpack(">I", body[p:p + 4])[0]
    desc = body[p + 4:p + 4 + dl].decode("utf-8", "replace")
    p += 4 + dl + 16
    dn = struct.unpack(">I", body[p:p + 4])[0]
    _caratula(R, "PICTURE", APIC_TIPOS[t] if t < len(APIC_TIPOS) else "tipo %d" % t, mime, body[p + 4:p + 4 + dn], None, desc or None)


# ---------------------------------------------------------------------------------------------- MP4 / M4A
def _atoms(f, ini, fin, trunc=None):
    p = ini
    while p + 8 <= fin:
        f.seek(p)
        n, t = struct.unpack(">I4s", f.read(8))
        hl = 8
        if n == 1:
            n = struct.unpack(">Q", f.read(8))[0]
            hl = 16
        elif n == 0:
            n = fin - p
        if n < hl:
            return
        if n > fin - p and trunc is not None:
            trunc.append((t.decode("latin-1"), n))
        yield t, p, min(n, fin - p), hl
        p += n


def _mp4(R, f, tam):
    R.familia = "mp4"
    vio, trunc = set(), []
    for t, p, n, hl in _atoms(f, 0, tam, trunc):
        vio.add(t)
        if t == b"ftyp":
            f.seek(p + hl)
            R.tech["marca"] = f.read(4).decode("latin-1")
        elif t == b"mdat":
            R.rangos.append((p + hl, p + n))
        elif t == b"moov":
            _moov(R, f, p + hl, p + n)
        elif t in (b"free", b"skip", b"wide"):
            R.padding += n
    for nombre, n in trunc:
        R.aviso("mp4_atomo_truncado", "error", "El átomo «%s» declara %d bytes pero el archivo termina antes: archivo cortado o subida interrumpida." % (nombre, n))
    if b"moov" not in vio:
        R.aviso("mp4_sin_moov", "error", "No hay átomo «moov» (el índice del archivo): casi seguro que está cortado o incompleto. No se pueden leer "
                "etiquetas ni datos técnicos del audio.")
    if b"mdat" not in vio:
        R.aviso("mp4_sin_mdat", "error", "No hay átomo «mdat»: el archivo no contiene audio.")


def _moov(R, f, ini, fin):
    for t, p, n, hl in _atoms(f, ini, fin):
        if t == b"mvhd":
            f.seek(p + hl)
            b = f.read(32)
            ts, du = struct.unpack(">IQ", b[20:32]) if b[0] == 1 else struct.unpack(">II", b[12:20])
            if ts:
                R.tech["duracion_s"] = du / ts
                R.tech["duracion_origen"] = "python"
        elif t == b"trak":
            _trak(R, f, p + hl, p + n)
        elif t == b"udta":
            for t2, p2, n2, hl2 in _atoms(f, p + hl, p + n):
                if t2 == b"meta":
                    _meta(R, f, p2 + hl2, p2 + n2)


def _trak(R, f, ini, fin):
    tipo = stsd = None
    for t, p, n, hl in _atoms(f, ini, fin):
        if t != b"mdia":
            continue
        for t2, p2, n2, hl2 in _atoms(f, p + hl, p + n):
            if t2 == b"hdlr":
                f.seek(p2 + hl2 + 8)
                tipo = f.read(4).decode("latin-1")
            elif t2 == b"minf":
                for t3, p3, n3, hl3 in _atoms(f, p2 + hl2, p2 + n2):
                    if t3 == b"stbl":
                        for t4, p4, n4, hl4 in _atoms(f, p3 + hl3, p3 + n3):
                            if t4 == b"stsd":
                                f.seek(p4 + hl4 + 8)
                                stsd = f.read(36)
    if tipo == "soun" and stsd and len(stsd) >= 36 and "codec" not in R.audio:
        fmt4 = stsd[4:8].decode("latin-1")
        ch, bits = struct.unpack(">HH", stsd[24:28])
        sr = struct.unpack(">I", stsd[32:36])[0] >> 16
        R.audio.update({"codec": {"mp4a": "aac"}.get(fmt4, fmt4), "tasa_muestreo_hz": sr, "canales": ch, "disposicion_canales": {1: "mono", 2: "stereo"}.get(ch),
                        "bits_por_muestra": bits if fmt4 == "alac" else None, "sin_perdida": fmt4 == "alac"})
    elif tipo in ("vide", "text", "sbtl", "subt", "tmcd"):
        R.noaudio.append({"index": None, "tipo": "video" if tipo == "vide" else "subtitulo" if tipo in ("text", "sbtl", "subt") else "datos",
                          "codec": None, "disposicion": [], "bytes": None, "origen": "python"})


def _meta(R, f, ini, fin):
    f.seek(ini)
    if f.read(4) == b"\0\0\0\0":
        ini += 4
    for t, p2, n2, hl2 in _atoms(f, ini, fin):
        if t == b"ilst":
            bid = R.bloque("MP4 ilst", p2, n2)
            for t3, p3, n3, hl3 in _atoms(f, p2 + hl2, p2 + n2):
                _ilst_item(R, f, bid, t3, p3 + hl3, p3 + n3)


def _ilst_item(R, f, bid, tipo, ini, fin):
    clave = tipo.decode("latin-1")
    mean = name = None
    datos = []
    for t, p, n, hl in _atoms(f, ini, fin):
        f.seek(p + hl)
        b = f.read(n - hl)
        if t == b"mean":
            mean = _txt(b[4:])
        elif t == b"name":
            name = _txt(b[4:])
        elif t == b"data":
            datos.append((struct.unpack(">I", b[:4])[0] & 0xFFFFFF, b[8:]))
    if tipo == b"----":
        orig = "----:%s:%s" % (mean, name)
        nrm = NORM_VORBIS.get((name or "").upper()) if mean and mean.startswith("com.apple") else None
    else:
        orig, nrm = clave, NORM_MP4.get(clave)
    for dt, v in datos:
        if tipo == b"covr":
            _caratula(R, "covr", "front cover", {13: "image/jpeg", 14: "image/png"}.get(dt), v)
        elif dt == 1:
            t = v.decode("utf-8", "replace")
            if nrm == "lyrics":
                _letra(R, "©lyr", t)
                R.item(bid, orig, _extracto(t), nrm, caracteres=len(t))
            else:
                R.item(bid, orig, t, nrm, estandar=bool(nrm) or tipo != b"----" and clave[0] == "©")
        elif tipo in (b"trkn", b"disk") and len(v) >= 6:
            R.item(bid, orig, "%d/%d" % struct.unpack(">2xHH", v[:6]), nrm)
        elif dt in (21, 0) and 0 < len(v) <= 8:
            R.item(bid, orig, str(int.from_bytes(v, "big")), nrm, "numero")
        else:
            R.binario(clave, bid, v, propietario=mean, descripcion=name, clave=orig)


# ---------------------------------------------------------------------------------------------- capa B: ffprobe / ffmpeg
def buscar_ffmpeg():
    """ffmpeg in the PATH or None (inside the manager use ctx.ffmpeg(), which also looks in the usual places)."""
    return shutil.which("ffmpeg")


def buscar_ffprobe(ffmpeg=None):
    """ffprobe in the PATH or next to ffmpeg (same folder). None if it does not exist."""
    p = shutil.which("ffprobe")
    if p:
        return p
    if ffmpeg:
        d = Path(ffmpeg).parent
        for n in ("ffprobe", "ffprobe.exe"):
            if (d / n).is_file():
                return str(d / n)
    return None


def _ffprobe_raw(exe, ruta):
    """(version, ffprobe dict) or (version/None, None) if it fails."""
    try:
        v = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15, creationflags=_NOCONSOLA).stdout.split("\n")[0]
        m = re.search(r"version\s+(\S+)", v)
        r = subprocess.run([exe, "-v", "error", "-show_format", "-show_streams", "-show_chapters", "-of", "json", str(ruta)],
                           capture_output=True, text=True, timeout=60, creationflags=_NOCONSOLA)
        if r.returncode:
            return (m.group(1) if m else None), None
        return (m.group(1) if m else None), json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None


def _num(x, tipo=float):
    try:
        return tipo(x)
    except (TypeError, ValueError):
        return None


def _cargar_senal():
    """senal.py lives next to this file; works whether or not _core is on sys.path."""
    try:
        import senal
        return senal
    except ImportError:
        import importlib.util
        sp = importlib.util.spec_from_file_location("senal", Path(__file__).with_name("senal.py"))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m


# ---------------------------------------------------------------------------------------------- identificación del formato
def _identifica(cab, ext):
    """Family by magic bytes (None if unknown)."""
    if cab[:4] == b"RIFF" and cab[8:12] == b"WAVE":
        return "wav"
    if cab[:4] == b"RF64":
        return "rf64"
    if cab[:4] == b"fLaC" or (cab[:3] == b"ID3" and ext == ".flac"):
        return "flac"
    if cab[4:8] == b"ftyp":
        return "mp4"
    if cab[:4] == b"OggS":
        return "ogg"
    if cab[:4] == b"FORM" and cab[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if cab[:4] == b"\x30\x26\xb2\x75":
        return "wma"
    if cab[:3] == b"ID3" or (len(cab) >= 2 and cab[0] == 0xFF and cab[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


# ---------------------------------------------------------------------------------------------- API
def inspeccionar(ruta, ffprobe="auto", raiz=None, senal=False, ffmpeg="auto"):
    """Inspection of one file → dict (schema huella.inspeccion/1). ffprobe/ffmpeg: "auto", a path, or None/False to not use them."""
    ruta = Path(ruta)
    R = _R()
    errores = []
    try:
        st = ruta.stat()
        tam = st.st_size
    except OSError as e:
        return {"schema": SCHEMA, "ok": False, "errores": [str(e)]}
    ext = ruta.suffix.lower()
    # --- capa A
    try:
        f = open(ruta, "rb")
    except OSError as e:
        return {"schema": SCHEMA, "ok": False, "errores": [str(e)]}
    with f:
        cab = f.read(12)
        fam = _identifica(cab, ext)
        esperada = EXT_FAMILIA.get(ext)
        try:
            if tam == 0:
                R.aviso("archivo_vacio", "error", "El archivo está vacío (0 bytes).")
            elif fam in ("wav", "flac", "mp4", "mp3"):
                if esperada and esperada != fam and esperada not in SIN_RECORRIDO:
                    R.aviso("extension_no_coincide", "aviso", "La extensión «%s» no coincide con el contenido, que parece %s." % (ext, NOMBRE_FAMILIA[fam]))
                {"wav": _wav, "flac": _flac, "mp4": _mp4, "mp3": _mp3}[fam](R, f, tam)
            elif fam in SIN_RECORRIDO:
                R.aviso("formato_sin_recorrido", "aviso", "%s no tiene recorrido propio: las etiquetas y los datos técnicos solo salen de ffprobe." % NOMBRE_FAMILIA[fam])
            elif esperada == "mp3":
                _mp3(R, f, tam)
            elif esperada:
                R.aviso("cabecera_no_coincide", "error", "La extensión «%s» dice %s pero el contenido no lo es (empieza por %r): el archivo está corrupto, "
                        "incompleto o tiene otra extensión." % (ext, NOMBRE_FAMILIA[esperada], bytes(cab[:4])))
            elif ext in EXT_SIN_RECORRIDO:
                R.aviso("formato_sin_recorrido", "aviso", "Los archivos «%s» no tienen recorrido propio: solo se usa ffprobe." % ext)
            else:
                R.aviso("formato_desconocido", "aviso", "No reconozco el formato (extensión «%s», empieza por %r)." % (ext, bytes(cab[:4])))
        except (struct.error, IndexError, ValueError, OSError) as e:
            errores.append("recorrido_python: %s: %s" % (type(e).__name__, e))
        h = hashlib.sha256()
        _sha_rango(f, 0, tam, h)
        sha_arch = h.hexdigest()
        sha_audio = None
        if R.rangos:
            ha = hashlib.sha256()
            for a, b in R.rangos:
                _sha_rango(f, a, b, ha)
            sha_audio = ha.hexdigest()
    # --- capa B
    ffm = buscar_ffmpeg() if ffmpeg == "auto" else (ffmpeg or None)
    exe = buscar_ffprobe(ffm) if ffprobe == "auto" else (ffprobe or None)
    ver, probe = (_ffprobe_raw(exe, ruta) if exe and tam else (None, None))
    if exe and tam and probe is None:
        errores.append("ffprobe_fallo: ffprobe no pudo leer el archivo")
    if not exe:
        R.aviso("sin_ffprobe", "info", "ffprobe no disponible: los datos técnicos salen solo del recorrido Python.")
    origen = {}
    fmt = (probe or {}).get("format", {})
    streams = (probe or {}).get("streams", [])
    aud = next((s for s in streams if s.get("codec_type") == "audio"), {})

    def pick(campo, b, a):
        for fuente, v in (("ffprobe", b), ("python", a)):
            if v is not None:
                origen[campo] = fuente
                return v
        origen[campo] = None
        return None

    sin = aud["codec_name"].startswith(LOSSLESS) if aud.get("codec_name") else R.audio.get("sin_perdida")
    bits_b = _num(aud.get("bits_per_raw_sample"), int) or _num(aud.get("bits_per_sample"), int) or None
    contenedor = {
        "familia": R.familia,
        "formato": pick("contenedor.formato", fmt.get("format_name"), FORMATO_CORTO.get(R.familia)),
        "formato_largo": pick("contenedor.formato_largo", fmt.get("format_long_name"), FORMATOS.get(R.familia)),
        "duracion_s": pick("contenedor.duracion_s", _num(fmt.get("duration")), R.tech.get("duracion_s")),
        "bitrate_bps": pick("contenedor.bitrate_bps", _num(fmt.get("bit_rate"), int), R.tech.get("bitrate_bps")),
        "n_streams": pick("contenedor.n_streams", _num(fmt.get("nb_streams"), int), (1 if R.audio else 0) + len(R.noaudio) + len(R.caratulas)),
        "inicio_s": pick("contenedor.inicio_s", _num(fmt.get("start_time")), None),
    }
    dur_ = contenedor["duracion_s"]
    if dur_ and R.rangos:                                  # bitrates that neither ffprobe nor the header gave: bytes*8/duration
        if R.audio.get("bitrate_bps") is None and _num(aud.get("bit_rate"), int) is None:
            R.audio["bitrate_bps"] = int(sum(b - a for a, b in R.rangos) * 8 / dur_)
            R.tech["bitrate_estimado"] = True
        if contenedor["bitrate_bps"] is None:
            contenedor["bitrate_bps"] = int(tam * 8 / dur_)
            origen["contenedor.bitrate_bps"] = "python_estimado"
    if R.tech.get("duracion_origen") == "python_estimada" and origen.get("contenedor.duracion_s") == "python":
        origen["contenedor.duracion_s"] = "python_estimado"
    audio = {
        "stream_index": aud.get("index") if aud else (0 if R.audio else None),
        "codec": pick("audio.codec", aud.get("codec_name"), R.audio.get("codec")),
        "perfil": pick("audio.perfil", aud.get("profile"), None),
        "tasa_muestreo_hz": pick("audio.tasa_muestreo_hz", _num(aud.get("sample_rate"), int), R.audio.get("tasa_muestreo_hz")),
        "canales": pick("audio.canales", _num(aud.get("channels"), int), R.audio.get("canales")),
        "disposicion_canales": pick("audio.disposicion_canales", aud.get("channel_layout"), R.audio.get("disposicion_canales")),
        "bits_por_muestra": pick("audio.bits_por_muestra", bits_b, R.audio.get("bits_por_muestra")),
        "bitrate_bps": pick("audio.bitrate_bps", _num(aud.get("bit_rate"), int), R.audio.get("bitrate_bps")),
        "duracion_s": pick("audio.duracion_s", _num(aud.get("duration")), R.tech.get("duracion_s")),
        "n_muestras": R.audio.get("n_muestras"),
        "sin_perdida": sin,
    }
    if R.tech.get("bitrate_estimado"):
        origen["audio.bitrate_bps"] = "python_estimado"
    # non-audio streams (B) + link with the covers read by A
    noaudio = []
    for s in streams:
        if s.get("codec_type") == "audio":
            continue
        disp = [k for k, v in (s.get("disposition") or {}).items() if v]
        noaudio.append({"index": s.get("index"), "tipo": {"video": "video", "subtitle": "subtitulo", "attachment": "adjunto", "data": "datos"}.get(s.get("codec_type"), s.get("codec_type")),
                        "codec": s.get("codec_name"), "disposicion": disp, "bytes": None, "origen": "ffprobe"})
    carat = R.caratulas
    for c, n in zip(carat, [n for n in noaudio if "attached_pic" in n["disposicion"]]):
        c["stream_index"] = n["index"]
        n["bytes"] = c["bytes"]
    if not probe:
        noaudio = [{"index": None, "tipo": "video", "codec": None, "disposicion": ["attached_pic"], "bytes": c["bytes"], "origen": "python"} for c in carat] + R.noaudio
    # tags from ffprobe only where the walk did not run (Ogg, AIFF…)
    items = list(R.items)
    if probe and not R.familia:
        alltags = dict(fmt.get("tags") or {})
        for s in streams:
            if s.get("codec_type") == "audio":
                alltags.update({k: v for k, v in (s.get("tags") or {}).items() if k not in alltags})
        for k, v in alltags.items():
            items.append({"bloque": None, "clave_original": k, "clave_normalizada": NORM_VORBIS.get(k.upper()), "valor": v, "tipo_valor": "texto",
                          "descripcion": None, "idioma": None, "categoria": CAT.get(NORM_VORBIS.get(k.upper()), "personalizado"),
                          "estandar": k.upper() in NORM_VORBIS, "editable": True, "origen": "ffprobe"})
    chap = [{"inicio_s": _num(c.get("start_time")), "fin_s": _num(c.get("end_time")), "titulo": (c.get("tags") or {}).get("title")} for c in (probe or {}).get("chapters", [])]
    resumen = {k: None for k in ("title", "artist", "album", "date", "genre", "track", "isrc", "copyright", "publisher", "composer", "comment", "encoded_by", "encoder")}
    for i in items:
        n = i.get("clave_normalizada")
        if n in resumen and resumen[n] is None and i["valor"]:
            resumen[n] = i["valor"]
    resumen["lyrics"] = bool(R.letras)
    if R.familia == "mp3" and any(b["tipo"] == "ID3v1" for b in R.bloques) and any(b["tipo"].startswith("ID3v2") for b in R.bloques):
        R.aviso("id3v1_y_id3v2", "info", "El archivo lleva ID3v1 e ID3v2 a la vez.")
    v2 = [b for b in R.bloques if b["tipo"].startswith("ID3v2")]
    if len(v2) > 1:
        R.aviso("id3v2_apilados", "aviso", "Hay %d tags ID3v2 consecutivos; los lectores suelen mostrar solo el primero." % len(v2))
    por = {}
    for i in items:
        if i["origen"] == "python" and i["clave_normalizada"] and i["bloque"] and i["valor"] and i["clave_normalizada"] != "lyrics" \
                and not i["clave_original"].startswith("ID3v1"):
            por.setdefault(i["clave_normalizada"], {}).setdefault(i["valor"], set()).add(i["bloque"])
    for k, vals in por.items():
        if len(vals) > 1:
            R.aviso("etiquetas_en_conflicto", "aviso", "«%s» tiene valores distintos en el mismo archivo: %s" % (k, " | ".join(map(repr, vals))))
    if R.padding > 65536:
        R.aviso("padding_grande", "info", "Hay %d bytes de relleno (padding)." % R.padding)
    # --- sección «senal» (opcional)
    sen = None
    if senal:
        S = _cargar_senal()
        if tam == 0:
            sen = S.fallo("senal_archivo_vacio", "El archivo está vacío: no hay señal que analizar.")
        else:
            try:
                sen = S.analizar(ruta, audio["tasa_muestreo_hz"], audio["canales"], audio["duracion_s"], ffm, R.wav if R.familia == "wav" else None)
            except Exception as e:  # noqa: BLE001  the analysis must never take the inspection down
                sen = S.fallo("senal_error", "El análisis de señal falló (%s)." % type(e).__name__)
    return {
        "schema": SCHEMA, "ok": True, "inspeccionado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "herramientas": {"ffprobe": ver if probe else None, "ffmpeg": bool(ffm), "recorrido_python": "1", "mutagen": None},
        "archivo": {"nombre": ruta.name, "ruta_relativa": ruta.relative_to(raiz).as_posix() if raiz else None, "extension": ext,
                    "tamano_bytes": tam, "sha256": sha_arch, "sha256_audio": sha_audio,
                    "modificado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))},
        "contenedor": contenedor, "audio": audio, "campos_origen": origen,
        "bloques_etiqueta": R.bloques, "etiquetas": items, "resumen_etiquetas": resumen,
        "incrustados": {"caratulas": carat, "letras": R.letras, "streams_no_audio": noaudio, "capitulos": chap, "bloques_binarios": R.binarios},
        "senal": sen,
        "avisos": R.avisos, "errores": errores,
    }
