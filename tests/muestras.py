"""Synthetic audio files for the tests, built byte by byte in pure Python (no ffmpeg, no binary fixtures in the repo).

Everything is invented: tags, covers and audio. The files are valid enough for the container walkers of `_core/inspeccion.py`
(they are not always decodable: the MP3/FLAC/M4A "audio" is filler bytes, which is all the tag/hash tests need).
"""
import math
import random
import struct

SR = 44100


# ---------------------------------------------------------------------------------------------- PCM
def seno(freq, amp, seg, sr=SR, canales=2):
    """16-bit little-endian PCM of a sine wave."""
    n = int(seg * sr)
    v = [int(max(-1.0, min(1.0, amp * math.sin(2 * math.pi * freq * i / sr))) * 32767) for i in range(n)]
    return struct.pack("<%dh" % (n * canales), *[x for x in v for _ in range(canales)])


def silencio(seg, sr=SR, canales=2):
    return b"\0" * (int(seg * sr) * canales * 2)


def ruido_y_tono(seg, tono_hz, tono_amp, ruido_amp=0.1, sr=SR, semilla=1):
    """Uniform white noise + a stationary sine (stereo, 16 bit)."""
    r = random.Random(semilla)
    n = int(seg * sr)
    v = [int((ruido_amp * r.uniform(-1, 1) + tono_amp * math.sin(2 * math.pi * tono_hz * i / sr)) * 32767) for i in range(n)]
    return struct.pack("<%dh" % (n * 2), *[x for x in v for _ in range(2)])


def tonos(seg, lista, ruido_amp=0.002, sr=SR, semilla=3):
    """Several stationary sines [(freq_hz, amp), …] over a very quiet noise floor (stereo, 16 bit)."""
    r = random.Random(semilla)
    n = int(seg * sr)
    w = [2 * math.pi * f / sr for f, _ in lista]
    a = [x for _, x in lista]
    v = [int((ruido_amp * r.uniform(-1, 1) + sum(a[k] * math.sin(w[k] * i) for k in range(len(w)))) * 32767) for i in range(n)]
    return struct.pack("<%dh" % (n * 2), *[x for x in v for _ in range(2)])


def saturado(seg, sr=SR):
    """A sine at 3× full scale, hard-clipped."""
    return seno(440, 3.0, seg, sr)


# ---------------------------------------------------------------------------------------------- WAV
def _chunk(cid, body):
    return cid + struct.pack("<I", len(body)) + body + (b"\0" if len(body) & 1 else b"")


def wav(pcm, titulo="Mi cancion", orig="TestStudio", sr=SR, canales=2, bits=16, extra=True):
    fmt = struct.pack("<HHIIHH", 1, canales, sr, sr * canales * bits // 8, canales * bits // 8, bits)
    cuerpo = b"WAVE" + _chunk(b"fmt ", fmt)
    if extra:
        bext = (b"Demo sintetica".ljust(256, b"\0") + orig.encode().ljust(32, b"\0") + b"REF0001".ljust(32, b"\0") + b"2026-11-19" + b"14:30:00"
                + struct.pack("<Q", 0) + struct.pack("<H", 2) + b"\0" * 64 + struct.pack("<5H", 0, 0, 0, 0, 0) + b"\0" * 180 + b"A=PCM,F=44100\r\n")
        sub = lambda i, t: _chunk(i, t.encode() + b"\0")  # noqa: E731
        info = b"INFO" + sub(b"INAM", titulo) + sub(b"IART", "Artista Demo") + sub(b"ICOP", "(P) 2026 Demo") + sub(b"ISRC", "ESXXX2600001") + sub(b"ISFT", "SynthGen 1.0")
        cuerpo += _chunk(b"bext", bext) + _chunk(b"LIST", info)
    cuerpo += _chunk(b"data", pcm)
    if extra:
        cuerpo += _chunk(b"iXML", b'<?xml version="1.0"?><BWFXML><PROJECT>Peli X</PROJECT><USER><USER_X>v4</USER_X></USER></BWFXML>') + _chunk(b"cust", b"\x01\x02\x03\x04\x05")
    return b"RIFF" + struct.pack("<I", len(cuerpo)) + cuerpo


# ---------------------------------------------------------------------------------------------- carátula
def jpeg(ancho=64, alto=48):
    """Header-only JPEG (enough to read the size)."""
    return b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", alto, ancho) + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01" + b"\xff\xd9"


# ---------------------------------------------------------------------------------------------- MP3 (ID3v2.4 + frames MPEG1-L3 128 kbps de relleno)
def _ss(n):
    return bytes([(n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127])


def fr(fid, body):
    return fid.encode() + _ss(len(body)) + b"\0\0" + body


def t8(fid, s):
    return fr(fid, b"\x03" + s.encode())


def id3v2(frames, padding=64):
    cuerpo = b"".join(frames) + b"\0" * padding
    return b"ID3\x04\x00\x00" + _ss(len(cuerpo)) + cuerpo


def mp3(titulo="Mi cancion", priv_legible=False, apilado=False, id3v1=True, n_frames=100, tags=True):
    frames_tag = [t8("TIT2", titulo), t8("TPE1", "Artista Demo"), t8("TALB", "Album Demo"), t8("TDRC", "2026"), t8("TSRC", "ESXXX2600001"),
                  t8("TCOP", "2026 Demo Records"), t8("TENC", "EncoderDemo"),
                  fr("TXXX", b"\x03" + b"Suno-Model\0" + b"v4"),
                  fr("COMM", b"\x03" + b"spa" + b"\0" + "comentario".encode()),
                  fr("USLT", b"\x03" + b"spa" + b"\0" + "Verso uno\nVerso dos".encode()),
                  fr("PRIV", b"www.example.com\0" + bytes(range(40))),
                  fr("GEOB", b"\x03" + b"application/octet-stream\0" + b"datos.bin\0" + b"descr\0" + b"\xde\xad\xbe\xef" * 8),
                  fr("APIC", b"\x03" + b"image/jpeg\0" + b"\x03" + b"Portada\0" + jpeg())]
    if priv_legible:
        frames_tag.append(fr("PRIV", b"texto.example\0" + "Esto es texto legible".encode()))
    out = id3v2(frames_tag) if tags else b""
    if apilado:
        out += id3v2([t8("TIT2", "Titulo DISTINTO"), t8("TPE1", "Otro Artista")])
    out += (b"\xff\xfb\x90\x00" + bytes(413)) * n_frames
    if id3v1 and tags:
        out += b"TAG" + titulo.encode().ljust(30, b"\0")[:30] + b"Artista Demo".ljust(30, b"\0") + b"Album Demo".ljust(30, b"\0") + b"2026" + b"nota".ljust(28, b"\0") + b"\0\x01\x0c"
    return out


# ---------------------------------------------------------------------------------------------- FLAC
def _bloque_flac(tipo, cuerpo, ultimo=False):
    return bytes([(0x80 if ultimo else 0) | tipo]) + struct.pack(">I", len(cuerpo))[1:] + cuerpo


def flac(titulo="Mi cancion", muestras=44100 * 3, sr=SR, canales=2, bits=16, truncar_en=None):
    """FLAC with STREAMINFO, VORBIS_COMMENT, PICTURE, APPLICATION and PADDING + filler frames. `truncar_en` cuts the file at that many bytes."""
    v = (sr << 44) | ((canales - 1) << 41) | ((bits - 1) << 36) | muestras
    streaminfo = struct.pack(">HH", 4096, 4096) + b"\0" * 6 + v.to_bytes(8, "big") + bytes(16)
    vendor = b"synthgen 1.0"
    comentarios = ["TITLE=" + titulo, "ARTIST=Artista Demo", "ALBUM=Album Demo", "DATE=2026", "ISRC=ESXXX2600001", "COPYRIGHT=(P) 2026 Demo",
                   "ENCODED-BY=EncoderDemo", "SUNO_MODEL=v4", "LYRICS=Verso uno\nVerso dos"]
    vorbis = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comentarios)) + b"".join(struct.pack("<I", len(c.encode())) + c.encode() for c in comentarios)
    img = jpeg()
    pic = struct.pack(">I", 3) + struct.pack(">I", 10) + b"image/jpeg" + struct.pack(">I", 7) + b"Portada" + struct.pack(">IIII", 64, 48, 24, 0) + struct.pack(">I", len(img)) + img
    out = (b"fLaC" + _bloque_flac(0, streaminfo) + _bloque_flac(2, b"MMgr" + bytes(range(30))) + _bloque_flac(4, vorbis) + _bloque_flac(6, pic)
           + _bloque_flac(1, bytes(2048), ultimo=True) + (b"\xff\xf8\xc9\x18" + bytes(996)) * 50)
    return out[:truncar_en] if truncar_en else out


# ---------------------------------------------------------------------------------------------- M4A
def _at(tipo, cuerpo):
    return struct.pack(">I4s", 8 + len(cuerpo), tipo) + cuerpo


def _datos(tipo_dato, v):
    return _at(b"data", struct.pack(">II", tipo_dato, 0) + v)


def m4a(titulo="Mi cancion", con_moov=True, mdat_declara_de_mas=0):
    """M4A: ftyp + mdat + moov (mvhd, one audio trak, udta/meta/ilst with ©nam, ©lyr, covr and '----' atoms)."""
    ftyp = _at(b"ftyp", b"M4A \0\0\2\0M4A isomiso2")
    carga = bytes(5000)
    mdat = struct.pack(">I4s", 8 + len(carga) + mdat_declara_de_mas, b"mdat") + carga
    if not con_moov:
        return ftyp + mdat
    mvhd = _at(b"mvhd", b"\0\0\0\0" + bytes(8) + struct.pack(">II", 1000, 3000) + bytes(80))
    entrada = struct.pack(">I", 36) + b"mp4a" + bytes(6) + struct.pack(">H", 1) + bytes(8) + struct.pack(">HHHH", 2, 16, 0, 0) + struct.pack(">I", SR << 16)
    stsd = _at(b"stsd", b"\0\0\0\0" + struct.pack(">I", 1) + entrada)
    trak = _at(b"trak", _at(b"mdia", _at(b"hdlr", bytes(8) + b"soun" + bytes(12)) + _at(b"minf", _at(b"stbl", stsd))))
    libre = lambda mean, nombre, val: _at(b"----", _at(b"mean", bytes(4) + mean) + _at(b"name", bytes(4) + nombre) + _datos(1, val))  # noqa: E731
    ilst = _at(b"ilst", _at(b"\xa9nam", _datos(1, titulo.encode())) + _at(b"\xa9ART", _datos(1, b"Artista Demo")) + _at(b"cprt", _datos(1, "(P) 2026 Demo".encode()))
               + _at(b"\xa9lyr", _datos(1, b"Verso uno\nVerso dos")) + _at(b"covr", _datos(13, jpeg()))
               + libre(b"com.apple.iTunes", b"ISRC", b"ESXXX2600001") + libre(b"com.apple.iTunes", b"SUNO_MODEL", b"v4"))
    udta = _at(b"udta", _at(b"meta", bytes(4) + ilst))
    return ftyp + mdat + _at(b"moov", mvhd + trak + udta)
