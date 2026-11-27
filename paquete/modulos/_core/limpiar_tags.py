"""Clean copies of audio files: everything that is not the sound itself is left out (title, artist, comment, software
or AI-generator tags such as the ones Suno writes, cover art, BWF/iXML data…). The audio is copied untouched, bit for bit.

    limpiar_copia(src, dst, ff=None)   writes the clean copy; raises ValueError if the format is unknown / unsafe
    etiquetas_restantes(path)          names of the tag blocks still found in a file (for checks)

WAV, AIFF, MP3 and FLAC are handled here in plain Python (no ffmpeg needed). Other formats (m4a…) go through ffmpeg
(-map_metadata -1, stream copy) when `ff` is given. Standard library only."""
import os
import struct
import subprocess
from pathlib import Path

BLOQUE = 1 << 20


def _copiar(f, o, n):
    while n > 0:
        b = f.read(min(BLOQUE, n))
        if not b:
            raise ValueError("archivo cortado")
        o.write(b)
        n -= len(b)


def _riff(f, o, formato, fin, keep, le):
    """RIFF (WAV, little endian) and FORM (AIFF, big endian): keep only the chunks in `keep`."""
    e = "<" if le else ">"
    cab = f.read(12)
    o.write(b"\0" * 12)                      # sizes are filled in at the end
    total = 4
    tam = os.fstat(f.fileno()).st_size
    while f.tell() + 8 <= tam:
        h = f.read(8)
        cid, n = h[:4], struct.unpack(e + "I", h[4:])[0]
        if n > tam - f.tell():
            n = tam - f.tell()               # truncated final chunk: keep what exists
        pad = n & 1
        if cid in keep:
            o.write(cid + struct.pack(e + "I", n))
            _copiar(f, o, n)
            if pad:
                o.write(b"\0")
            total += 8 + n + pad
        else:
            f.seek(n, 1)
        if pad:
            f.seek(1, 1)
    o.seek(0)
    o.write(cab[:4] + struct.pack(e + "I", total) + formato)


def _mp3(f, o):
    tam = os.fstat(f.fileno()).st_size
    ini = 0
    while True:                              # one or more ID3v2 tags at the beginning
        f.seek(ini)
        h = f.read(10)
        if h[:3] == b"ID3" and len(h) == 10:
            n = (h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9]
            ini += 10 + n + (10 if h[5] & 0x10 else 0)
        else:
            break
    fin = tam
    f.seek(max(fin - 128, 0))
    if fin - ini >= 128 and f.read(3) == b"TAG":
        fin -= 128                            # ID3v1
    if fin - ini >= 32:
        f.seek(fin - 32)
        h = f.read(32)
        if h[:8] == b"APETAGEX":              # APEv2 at the end
            n = struct.unpack("<I", h[12:16])[0]
            fin -= n + (32 if struct.unpack("<I", h[20:24])[0] & 0x80000000 else 0)
    f.seek(ini)
    _copiar(f, o, max(fin - ini, 0))


def _flac(f, o):
    tam = os.fstat(f.fileno()).st_size
    ini = 0
    h = f.read(10)
    if h[:3] == b"ID3":                       # an ID3v2 tag in front of the stream
        ini = 10 + ((h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9])
    f.seek(ini)
    if f.read(4) != b"fLaC":
        raise ValueError("no es FLAC")
    streaminfo = None
    while True:
        h = f.read(4)
        if len(h) < 4:
            raise ValueError("FLAC cortado")
        ultimo, tipo, n = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:4], "big")
        cuerpo = f.read(n)
        if tipo == 0 and streaminfo is None:
            streaminfo = cuerpo
        if ultimo:
            break
    if streaminfo is None:
        raise ValueError("FLAC sin STREAMINFO")
    o.write(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo)
    _copiar(f, o, tam - f.tell())


def _ffmpeg(src, dst, ff):
    if not ff:
        raise ValueError("formato sin soporte (hace falta ffmpeg)")
    r = subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-map", "0:a", "-map_metadata", "-1", "-c", "copy",
                        "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dst)],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode or not Path(dst).exists():
        raise ValueError("ffmpeg no pudo limpiar el archivo: " + (r.stderr or "")[-200:])


def _tipo(src):
    with open(src, "rb") as f:
        cab = f.read(12)
    ext = Path(src).suffix.lower()
    if cab[:4] == b"RIFF" and cab[8:12] == b"WAVE":
        return "wav"
    if cab[:4] == b"FORM" and cab[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if cab[:4] == b"fLaC" or (cab[:3] == b"ID3" and ext == ".flac"):
        return "flac"
    if ext == ".mp3" or cab[:3] == b"ID3" or cab[:2].hex() in ("fffb", "fff3", "fff2", "fffa"):
        return "mp3"
    return "otro"


def limpiar_copia(src, dst, ff=None):
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp" + dst.suffix)
    tipo = _tipo(src)
    try:
        if tipo == "otro":
            _ffmpeg(src, tmp, ff)
        else:
            with open(src, "rb") as f, open(tmp, "wb") as o:
                if tipo == "wav":
                    _riff(f, o, b"WAVE", None, {b"fmt ", b"fact", b"data"}, True)
                elif tipo == "aiff":
                    f.seek(8)
                    fm = f.read(4)
                    f.seek(0)
                    _riff(f, o, fm, None, {b"COMM", b"SSND", b"FVER"}, False)
                elif tipo == "mp3":
                    _mp3(f, o)
                else:
                    _flac(f, o)
        os.replace(tmp, dst)
        return dst
    finally:
        tmp.unlink(missing_ok=True)


def etiquetar(path, tags, ff):
    """Removes every tag of the file and writes only `tags` ({title, artist, lyricist}); the audio is copied bit for bit (ffmpeg -c copy).
    The file is replaced only if ffmpeg succeeds. Returns True/False. WAV cannot hold a «lyricist» field: it goes in the comment."""
    path = Path(path)
    if not ff or not path.is_file():
        return False
    t = {k: str(v).strip() for k, v in (tags or {}).items() if v and str(v).strip()}
    if not t:
        return False
    ext = path.suffix.lower()
    meta = []
    for k in ("title", "artist"):
        if t.get(k):
            meta += ["-metadata", f"{k}={t[k]}"]
    if t.get("artist"):
        meta += ["-metadata", f"album_artist={t['artist']}"] if ext != ".wav" else []
    if t.get("lyricist"):
        meta += ["-metadata", (f"comment=Lyrics: {t['lyricist']}" if ext in (".wav", ".aif", ".aiff") else f"lyricist={t['lyricist']}")]
    tmp = path.with_name(path.stem + ".etq" + ext)
    cmd = [ff, "-y", "-i", str(path), "-map", "0:a", "-map_metadata", "-1", "-c", "copy", "-fflags", "+bitexact"]
    if ext == ".mp3":
        cmd += ["-id3v2_version", "3"]
    cmd += meta + [str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode or not tmp.exists() or tmp.stat().st_size < 100:
            tmp.unlink(missing_ok=True)
            return False
        os.replace(tmp, path)
        return True
    except OSError:
        tmp.unlink(missing_ok=True)
        return False


def etiquetas_restantes(path):
    """Names of the tag blocks found in a WAV/AIFF/MP3/FLAC file (empty list = clean)."""
    path = Path(path)
    b = path.read_bytes()
    out = []
    if b[:4] == b"RIFF":
        i, le = 12, "<"
        while i + 8 <= len(b):
            cid, n = b[i:i + 4], struct.unpack(le + "I", b[i + 4:i + 8])[0]
            if cid not in (b"fmt ", b"data", b"fact"):
                out.append(cid.decode("latin-1").strip())
            i += 8 + n + (n & 1)
    elif b[:4] == b"FORM":
        i = 12
        while i + 8 <= len(b):
            cid, n = b[i:i + 4], struct.unpack(">I", b[i + 4:i + 8])[0]
            if cid not in (b"COMM", b"SSND", b"FVER"):
                out.append(cid.decode("latin-1").strip())
            i += 8 + n + (n & 1)
    elif b[:3] == b"ID3":
        out.append("ID3v2")
    if b[-128:-125] == b"TAG":
        out.append("ID3v1")
    if b"APETAGEX" in b[-300:]:
        out.append("APEv2")
    if b[:4] == b"fLaC":
        i = 4
        while i + 4 <= len(b):
            ult, tipo, n = b[i] & 0x80, b[i] & 0x7F, int.from_bytes(b[i + 1:i + 4], "big")
            if tipo != 0:
                out.append("FLAC-bloque-%d" % tipo)
            i += 4 + n
            if ult:
                break
    return out
