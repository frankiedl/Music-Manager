"""Signal and spectrum analysis for the «senal» section of inspeccion.py (schema huella.inspeccion/1).

    analizar(ruta, tasa_hz, canales, duracion_s, ffmpeg=None, wav=None) -> dict

Standard library only (math, struct, subprocess). Audio is decoded in a stream, never loaded whole:
  * with ffmpeg (optional): any format → raw float32 over a pipe, at the file's own sample rate (so the ultrasonic band is kept);
    ffmpeg's `ebur128` filter also gives the loudness (LUFS / LRA / true peak);
  * without ffmpeg: only PCM WAV files (`wav=(inicio, fin, bits, es_float)` = location of the `data` chunk) are read in pure Python.
Whatever cannot be computed stays `null` and gets an entry in `avisos`.

Everything in «indicios» is a TECHNICAL HINT about the signal (a spectral cut-off, a narrow stationary tone…). It can have many
causes (codec, dither, oscillator noise, effects, the music itself) and is never a diagnosis of authorship, origin or of any
proprietary marker: `NOTA` travels with every result.
"""
import math
import re
import struct
import subprocess
import sys
import time
from operator import mul

VERSION = "1"
NOTA = ("Medidas técnicas del audio. Los «indicios» describen rasgos observables de la señal (un corte espectral, un pico tonal estrecho…) "
        "que pueden tener muchas causas (códec, dither, ruido de un oscilador, efectos, la propia música) y no son un diagnóstico de autoría, "
        "de origen ni de ninguna marca propietaria.")
SILENCIO_DB = -60.0          # RMS per window below this = silence
SILENCIO_MIN_S = 0.5
MAX_SILENCIOS = 50
K_FRAMES = 64                # spectral frames spread over the whole song
FRAME_MIN_DB = -70.0         # quieter frames do not enter the average spectrum
MAX_S = 1200                 # at most the first 20 minutes are analysed
TIEMPO_MAX_S = 300           # wall-clock budget
ZONA_ALTA_HZ = 16000
ZONA_ULTRA_HZ = 20000
BANDAS = [("sub", 0, 60), ("graves", 60, 250), ("medios", 250, 2000), ("presencia", 2000, 6000), ("brillo", 6000, 12000),
          ("aire", 12000, 16000), ("alta", 16000, 20000), ("ultrasonica", 20000, None)]
# thresholds of the hints (documented, deliberately conservative)
CORTE_MIN_CAIDA_DB = 25.0
PICO_MIN_PROMINENCIA_DB = 15.0
HF_MIN_PROMINENCIA_DB = 20.0
HF_MIN_PERSISTENCIA = 0.7
HF_MIN_NIVEL_DB = -85.0         # quieter spurs (e.g. 16-bit quantisation harmonics) are listed but not flagged
ULTRA_VS_MEDIOS_DB = -50.0
_NOCONSOLA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _db(x, piso=1e-20):
    return 10.0 * math.log10(x if x > piso else piso)


def _dbfs_amp(x, escala):
    return None if x <= 0 else round(20.0 * math.log10(x / escala), 2)


def _med(v):
    s = sorted(v)
    return s[len(s) // 2]


def _aviso(lista, codigo, nivel, mensaje):
    lista.append({"codigo": codigo, "nivel": nivel, "mensaje": mensaje})


def _zona(f):
    return "ultrasonica" if f >= ZONA_ULTRA_HZ else "alta" if f >= ZONA_ALTA_HZ else "audible"


# ---------------------------------------------------------------------------------------------- decodificación en streaming
def _ventanas_ffmpeg(ffmpeg, ruta, C, W, estado):
    """Yields (memoryview float32 interleaved, frames, escala=1.0) of W frames; estado['recortado'] if the time budget ran out."""
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(ruta), "-vn", "-sn", "-dn", "-t", str(MAX_S), "-f", "f32le", "-ac", str(C), "pipe:1"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_NOCONSOLA)
    except OSError:
        return
    try:
        while True:
            if time.monotonic() > estado["fin"]:
                estado["recortado"] = True
                p.kill()
                break
            b = p.stdout.read(W * C * 4)
            n = len(b) // (4 * C)
            if n == 0:
                break
            yield memoryview(b[:n * C * 4]).cast("f"), n, 1.0
    finally:
        try:
            p.stdout.close()
        except OSError:
            pass
        estado["rc"] = p.wait()


_U8 = bytes((i + 128) & 255 for i in range(256))      # unsigned 8-bit → signed


def _ventanas_wav(ruta, ini, fin, bits, es_float, C, W, estado):
    """Same as above for PCM/float WAV read directly from the file (pure Python)."""
    bps = bits // 8
    with open(ruta, "rb") as f:
        f.seek(ini)
        resto = fin - ini
        while resto > 0:
            if time.monotonic() > estado["fin"]:
                estado["recortado"] = True
                break
            b = f.read(min(resto, W * C * bps))
            resto -= len(b)
            n = len(b) // (C * bps)
            if n == 0:
                break
            b = b[:n * C * bps]
            if es_float:
                mv, esc = memoryview(b).cast("f" if bps == 4 else "d"), 1.0
            elif bps == 1:
                mv, esc = memoryview(b.translate(_U8)).cast("b"), 128.0
            elif bps == 2:
                mv, esc = memoryview(b).cast("h"), 32768.0
            elif bps == 3:                              # 24 bit → left-aligned int32 without a Python loop
                o = bytearray(len(b) // 3 * 4)
                o[1::4], o[2::4], o[3::4] = b[0::3], b[1::3], b[2::3]
                mv, esc = memoryview(bytes(o)).cast("i"), 2147483648.0
            else:
                mv, esc = memoryview(b).cast("i"), 2147483648.0
            yield mv, n, esc


# ---------------------------------------------------------------------------------------------- FFT (radix-2, stdlib)
_PLANES = {}


def _plan(n):
    p = _PLANES.get(n)
    if p is None:
        bits = n.bit_length() - 1
        rev = [int(format(i, "0%db" % bits)[::-1], 2) for i in range(n)]
        tw = [complex(math.cos(2 * math.pi * k / n), -math.sin(2 * math.pi * k / n)) for k in range(n // 2)]
        hann = [0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n)]
        p = _PLANES[n] = (rev, tw, hann, sum(hann))
    return p


def _fft(z, n):
    rev, tw = _plan(n)[:2]
    z = [z[r] for r in rev]
    size = 2
    while size <= n:
        half, step = size // 2, n // size
        for start in range(0, n, size):
            k = 0
            for j in range(start, start + half):
                t = z[j + half] * tw[k]
                u = z[j]
                z[j] = u + t
                z[j + half] = u - t
                k += step
        size *= 2
    return z


def _espectros(frames, n):
    """Power spectra (bins 0..n/2) of real frames, two frames per complex FFT. Normalised so a sine of amplitude A peaks at A²."""
    hann, sw = _plan(n)[2], _plan(n)[3]
    norm = (sw / 2.0) ** 2
    out = []
    for i in range(0, len(frames), 2):
        a = frames[i]
        b = frames[i + 1] if i + 1 < len(frames) else [0.0] * n
        Z = _fft([complex(a[j] * hann[j], b[j] * hann[j]) for j in range(n)], n)
        pa, pb = [], []
        for k in range(n // 2 + 1):
            zk, zn = Z[k], Z[(-k) % n].conjugate()
            xa, xb = (zk + zn) / 2.0, (zk - zn) / 2j
            pa.append((xa.real * xa.real + xa.imag * xa.imag) / norm)
            pb.append((xb.real * xb.real + xb.imag * xb.imag) / norm)
        out.append(pa)
        if i + 1 < len(frames):
            out.append(pb)
    return out


# ---------------------------------------------------------------------------------------------- acumulador por ventanas
class _Acum:
    def __init__(s, C, W, N, sel):
        s.C, s.W, s.N, s.sel = C, W, N, sel
        s.i = 0
        s.frames_tot = 0
        s.pico = 0.0
        s.pico_t = 0.0
        s.pico_c = [0.0] * C
        s.dc = [0.0] * C
        s.suma2 = 0.0
        s.sat = 0
        s.esc = 1.0
        s.rms, s.pk = [], []         # per window (dBFS)
        s.frames = []

    def add(s, mv, n, esc, sr):
        C = s.C
        s.esc = esc
        total = n * C
        mx, mn = max(mv), min(mv)
        pk = max(mx, -mn)
        e = sum(map(mul, mv, mv))
        s.suma2 += e
        t0 = s.frames_tot / sr
        if pk > s.pico:
            s.pico = pk
            off = 0
            for j, x in enumerate(mv):          # exact position of the new overall peak (rare)
                if x == mx or x == mn:
                    off = j // C
                    break
            s.pico_t = t0 + off / sr
        thr = 0.9999 * esc
        if pk >= thr:
            s.sat += sum(1 for x in mv if x >= thr or x <= -thr)
        for c in range(C):
            ch = mv[c::C] if C > 1 else mv
            s.pico_c[c] = max(s.pico_c[c], max(max(ch), -min(ch)))
            s.dc[c] += sum(ch)
        s.rms.append(_db(e / total / (esc * esc)) if e > 0 else -200.0)
        s.pk.append(_db((pk / esc) ** 2) if pk > 0 else -200.0)
        if s.i in s.sel and n >= s.N:
            off = (n - s.N) // 2
            if C == 1:
                fr = [x / esc for x in mv[off:off + s.N]]
            else:
                cols = [mv[off * C + c:(off + s.N) * C:C] for c in range(C)]
                k = 1.0 / (C * esc)
                fr = [sum(t) * k for t in zip(*cols)]
            if sum(x * x for x in fr) / s.N > 1e-7:      # ≈ −70 dBFS
                s.frames.append(fr)
        s.i += 1
        s.frames_tot += n


# ---------------------------------------------------------------------------------------------- niveles, silencios
def _niveles(A, sr, W):
    wdur = W / sr
    nw = len(A.rms)
    esc = A.esc
    n_total = A.frames_tot
    tot_dur = n_total / sr
    rms_dbfs = _db(A.suma2 / (n_total * A.C) / (esc * esc)) if A.suma2 > 0 else None
    pico_dbfs = _dbfs_amp(A.pico, esc)
    # silences (windows below the threshold, at least SILENCIO_MIN_S long)
    sil, ini = [], None
    for i in range(nw + 1):
        mudo = i < nw and A.rms[i] < SILENCIO_DB
        if mudo and ini is None:
            ini = i
        elif not mudo and ini is not None:
            a, b = ini * wdur, min(i * wdur, tot_dur)
            if b - a >= SILENCIO_MIN_S:
                sil.append({"inicio_s": round(a, 2), "fin_s": round(b, 2), "duracion_s": round(b - a, 2)})
            ini = None
    recorte = len(sil) > MAX_SILENCIOS
    sil = sil[:MAX_SILENCIOS]
    activos = sorted(x for x in A.rms if x > SILENCIO_DB)
    p10 = activos[int(0.10 * (len(activos) - 1))] if len(activos) >= 10 else None
    p95 = activos[int(0.95 * (len(activos) - 1))] if len(activos) >= 10 else None
    # loudest windows, at least 1 s apart
    orden = sorted(range(nw), key=lambda i: -A.pk[i])
    momentos = []
    for i in orden:
        if A.pk[i] <= -200.0:
            break
        t = i * wdur
        if all(abs(t - m["t_s"]) >= 1.0 for m in momentos):
            momentos.append({"t_s": round(t, 2), "pico_dbfs": round(A.pk[i], 2)})
        if len(momentos) == 5:
            break
    return {
        "pico_muestra_dbfs": pico_dbfs,
        "pico_muestra_en_s": round(A.pico_t, 3) if A.pico > 0 else None,
        "pico_por_canal_dbfs": [_dbfs_amp(x, esc) for x in A.pico_c],
        "rms_dbfs": None if rms_dbfs is None else round(rms_dbfs, 2),
        "cresta_db": None if rms_dbfs is None or pico_dbfs is None else round(pico_dbfs - rms_dbfs, 2),
        "dc_offset": [round(x / n_total / esc, 6) for x in A.dc],
        "muestras_en_fondo_de_escala": A.sat,
        "rms_ventana_p10_dbfs": None if p10 is None else round(p10, 2),
        "rms_ventana_p95_dbfs": None if p95 is None else round(p95, 2),
        "rango_dinamico_ventanas_db": None if p10 is None else round(p95 - p10, 2),
        "ventana_s": round(wdur, 3),
        "momentos_pico": momentos,
        "umbral_silencio_dbfs": SILENCIO_DB,
        "silencios": sil,
        "silencio_inicial_s": sil[0]["fin_s"] if sil and sil[0]["inicio_s"] == 0 else 0.0,
        "silencio_final_s": round(tot_dur - sil[-1]["inicio_s"], 2) if sil and not recorte and sil[-1]["fin_s"] >= tot_dur - wdur else 0.0,
    }, recorte


# ---------------------------------------------------------------------------------------------- espectro
def _bandas(Pm, res, nyq):
    total = sum(Pm[1:]) or 1e-30
    out = []
    for nombre, d, h in BANDAS:
        hh = nyq if h is None else min(h, nyq)
        ks = [k for k in range(1, len(Pm)) if d <= k * res < hh or (h is None and k * res >= d)]
        ok = d < nyq and len(ks) >= 3
        out.append({"id": nombre, "desde_hz": d, "hasta_hz": round(hh) if ok else None, "disponible": ok,
                    "energia_pct": round(100.0 * sum(Pm[k] for k in ks) / total, 3) if ok else None,
                    "nivel_medio_bin_db": round(_db(sum(Pm[k] for k in ks) / len(ks)), 2) if ok else None})
    return out


def _corte(S, res, nyq):
    """Frequency of the steepest sustained drop of the spectrum above 8 kHz (typical of a low-pass), or (None, None)."""
    cw = max(1, int(round(250.0 / res)))
    C = [sum(S[i:i + cw]) / len(S[i:i + cw]) for i in range(1, len(S) - cw + 1, cw)]
    f0 = int(8000 / (cw * res))
    mejor, mi = 0.0, None
    for i in range(max(3, f0), len(C) - 2):
        a, b = C[i - 3:i], C[i + 1:i + 4]
        if len(b) < 2:
            continue
        caida = sum(a) / len(a) - sum(b) / len(b)
        if caida > mejor:
            mejor, mi = caida, i
    if mi is None or mejor < CORTE_MIN_CAIDA_DB:
        return None, None
    f = (1 + (mi + 1) * cw) * res
    if f > nyq - 500:
        return None, None
    return int(round(f / 50.0) * 50), round(mejor, 1)


def _picos(Pm, Pf, res):
    S = [_db(p) for p in Pm]
    n = len(S)
    cand = []
    for k in range(6, n - 6):
        s = S[k]
        if s > S[k - 1] and s >= S[k + 1] and s - S[k - 5] >= 10 and s - S[k + 5] >= 10:
            vec = S[max(1, k - 40):k - 4] + S[k + 5:k + 41]
            if len(vec) < 20:
                continue
            prom = s - _med(vec)
            if prom >= PICO_MIN_PROMINENCIA_DB:
                cand.append((k, s, prom))
    cand.sort(key=lambda c: -c[2])
    out = []
    for k, s, prom in cand[:30]:
        cnt = 0
        for P in Pf:
            vec = P[max(1, k - 40):k - 4] + P[k + 5:k + 41]
            if P[k] > 0 and P[k] >= 10.0 * _med(vec):
                cnt += 1
        a, b, c = S[k - 1], S[k], S[k + 1]
        den = a - 2 * b + c
        d = 0.5 * (a - c) / den if den else 0.0
        f = (k + max(-0.5, min(0.5, d))) * res
        out.append({"frecuencia_hz": round(f, 1), "nivel_db": round(s, 2), "prominencia_db": round(prom, 1),
                    "persistencia_pct": round(100.0 * cnt / len(Pf), 1), "zona": _zona(f)})
    return out[:12]


def _espectro_y_indicios(A, sr, nyq):
    avisos, indicios = [], []
    N = A.N
    res = sr / N
    if not A.frames:
        _aviso(avisos, "espectro_sin_frames", "aviso", "Audio demasiado corto o demasiado silencioso para calcular el espectro.")
        return None, indicios, avisos
    Pf = _espectros(A.frames, N)
    nf = len(Pf)
    Pm = [sum(P[k] for P in Pf) / nf for k in range(N // 2 + 1)]
    S = [_db(p) for p in Pm]
    bandas = _bandas(Pm, res, nyq)
    por = {b["id"]: b for b in bandas}
    corte, caida = _corte(S, res, nyq)
    picos = _picos(Pm, Pf, res)
    alta = por["alta"]
    piso_hf = None
    if alta["disponible"] or por["ultrasonica"]["disponible"]:
        ks = [k for k in range(1, len(Pm)) if k * res >= ZONA_ALTA_HZ]
        piso_hf = round(_db(_med([Pm[k] for k in ks])), 2) if len(ks) >= 3 else None
    esp = {"n_fft": N, "resolucion_hz": round(res, 2), "frecuencia_nyquist_hz": round(nyq), "frames": nf, "bandas": bandas,
           "corte_espectral_hz": corte, "caida_en_corte_db": caida, "piso_hf_mediana_db": piso_hf, "picos_tonales": picos}
    if corte:
        indicios.append({"codigo": "corte_espectral", "tipo": "indicio_tecnico", "zona": _zona(corte),
                         "descripcion": "El nivel cae de forma brusca por encima de %.1f kHz. Es típico de un filtro paso bajo (códec con pérdida, "
                                        "antialiasing…); por sí solo no indica cuál." % (corte / 1000.0),
                         "evidencia": {"frecuencia_hz": corte, "caida_db": caida}})
    hf = [p for p in picos if p["frecuencia_hz"] >= ZONA_ALTA_HZ and p["prominencia_db"] >= HF_MIN_PROMINENCIA_DB
          and p["nivel_db"] >= HF_MIN_NIVEL_DB and p["persistencia_pct"] >= HF_MIN_PERSISTENCIA * 100]
    for p in hf:
        indicios.append({"codigo": "pico_tonal_hf", "tipo": "indicio_tecnico", "zona": p["zona"],
                         "descripcion": "Pico tonal estrecho y estacionario a %.0f Hz (zona %s), %.0f dB por encima del piso vecino. Puede deberse al "
                                        "códec, al dither, a un oscilador u otros procesos." % (p["frecuencia_hz"], p["zona"], p["prominencia_db"]),
                         "evidencia": {k: p[k] for k in ("frecuencia_hz", "nivel_db", "prominencia_db", "persistencia_pct")}})
    hf_p = sorted(p["frecuencia_hz"] for p in picos if p["frecuencia_hz"] >= ZONA_ALTA_HZ and p["persistencia_pct"] >= 50)
    if len(hf_p) >= 3:
        d = [b - a for a, b in zip(hf_p, hf_p[1:])]
        m = _med(d)
        if m > 3 * res and all(abs(x - m) <= 2 * res for x in d):
            indicios.append({"codigo": "picos_equiespaciados_hf", "tipo": "indicio_tecnico", "zona": _zona(hf_p[0]),
                             "descripcion": "Varios picos tonales por encima de 16 kHz separados de forma regular (~%.0f Hz). Patrón atípico del piso de "
                                            "señal; puede tener causas técnicas diversas." % m,
                             "evidencia": {"frecuencias_hz": hf_p, "separacion_hz": round(m, 1)}})
    ul, me = por["ultrasonica"], por["medios"]
    if ul["disponible"] and me["disponible"] and ul["nivel_medio_bin_db"] - me["nivel_medio_bin_db"] > ULTRA_VS_MEDIOS_DB:
        indicios.append({"codigo": "energia_ultrasonica_notable", "tipo": "indicio_tecnico", "zona": "ultrasonica",
                         "descripcion": "Hay energía apreciable por encima de 20 kHz (poco habitual en material pasado por un códec con pérdida). "
                                        "Puede ser ruido, dither con modelado o una fuente de alta resolución.",
                         "evidencia": {"ultrasonica_db": ul["nivel_medio_bin_db"], "medios_db": me["nivel_medio_bin_db"]}})
    return esp, indicios, avisos


# ---------------------------------------------------------------------------------------------- sonoridad (ffmpeg ebur128)
def _sonoridad(ffmpeg, ruta, avisos):
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-t", str(MAX_S), "-i", str(ruta), "-vn", "-af",
                            "ebur128=peak=true:framelog=quiet", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=TIEMPO_MAX_S, creationflags=_NOCONSOLA)
    except (OSError, subprocess.SubprocessError):
        _aviso(avisos, "sonoridad_fallo", "aviso", "ffmpeg no pudo medir la sonoridad (ebur128).")
        return None
    t = r.stderr or ""
    i = t.rfind("Summary:")
    if r.returncode or i < 0:
        _aviso(avisos, "sonoridad_fallo", "aviso", "ffmpeg no pudo medir la sonoridad (ebur128).")
        return None
    t = t[i:]
    num = r"(-?\d+(?:\.\d+)?)"
    I = re.search(r"\bI:\s+" + num + r"\s+LUFS", t)
    L = re.search(r"\bLRA:\s+" + num + r"\s+LU\b", t)
    P = re.search(r"\bPeak:\s+" + num + r"\s+dBFS", t)
    return {"integrada_lufs": float(I.group(1)) if I else None, "rango_lu": float(L.group(1)) if L else None,
            "pico_real_dbtp": float(P.group(1)) if P else None, "herramienta": "ffmpeg ebur128"}


# ---------------------------------------------------------------------------------------------- API
def _vacia(avisos):
    return {"version": VERSION, "solicitada": True, "disponible": False, "nota_interpretacion": NOTA, "fuente_decodificacion": None,
            "analizado": None, "niveles": None, "sonoridad": None, "espectro": None, "indicios": [], "avisos": avisos}


def fallo(codigo, mensaje):
    """Result for «senal» when the analysis could not run at all."""
    av = []
    _aviso(av, codigo, "error", mensaje)
    return _vacia(av)


def analizar(ruta, tasa_hz, canales, duracion_s=None, ffmpeg=None, wav=None):
    """Signal analysis of one file. `wav` = (inicio, fin, bits, es_float) of a PCM WAV `data` chunk (used when ffmpeg is missing or fails)."""
    avisos = []
    if not tasa_hz or not canales:
        _aviso(avisos, "senal_sin_formato", "aviso", "No se conoce la tasa de muestreo o los canales: no se puede analizar la señal.")
        return _vacia(avisos)
    wav_ok = bool(wav) and sys.byteorder == "little" and wav[2] in (8, 16, 24, 32, 64) and (not wav[3] or wav[2] in (32, 64))
    if not ffmpeg and not wav_ok:
        _aviso(avisos, "senal_sin_decodificador", "aviso",
               "Sin ffmpeg solo se puede analizar la señal de archivos WAV PCM/float. Instala ffmpeg para el resto de formatos.")
        return _vacia(avisos)
    sr = int(tasa_hz)
    N = 8192 if sr >= 88200 else 4096 if sr >= 32000 else 2048
    W = max(sr // 10, N)
    nyq = sr / 2.0
    total_v = int(duracion_s * sr / W) + 1 if duracion_s else 0
    paso = max(1, total_v // K_FRAMES) if total_v else 20
    sel = set(range(paso // 2, total_v or 100000, paso))
    for fuente in (("ffmpeg",) if ffmpeg else ()) + (("python_wav",) if wav_ok else ()):
        C = min(int(canales), 2) if fuente == "ffmpeg" else int(canales)
        estado = {"fin": time.monotonic() + TIEMPO_MAX_S, "recortado": False, "rc": None}
        A = _Acum(C, W, N, sel)
        gen = _ventanas_ffmpeg(ffmpeg, ruta, C, W, estado) if fuente == "ffmpeg" else _ventanas_wav(ruta, wav[0], wav[1], wav[2], wav[3], C, W, estado)
        try:
            for mv, n, esc in gen:
                A.add(mv, n, esc, sr)
        except (OSError, ValueError, struct.error):
            pass
        if A.frames_tot:
            break
        _aviso(avisos, "senal_decodificacion_fallo", "aviso", "No se pudo decodificar el audio con %s." % fuente.replace("_", " "))
    else:
        return _vacia(avisos)
    if canales > 2 and fuente == "ffmpeg":
        _aviso(avisos, "senal_mezcla_canales", "info", "El archivo tiene %d canales; se analiza una mezcla a estéreo." % canales)
    if estado["recortado"] or (duracion_s and duracion_s > MAX_S):
        _aviso(avisos, "senal_recortada", "info", "Se analizó solo la parte inicial (máx. %d s o el tiempo disponible)." % MAX_S)
    niv, rec = _niveles(A, sr, W)
    if rec:
        _aviso(avisos, "silencios_recortados", "info", "Hay más de %d silencios; se listan los primeros." % MAX_SILENCIOS)
    if niv["rms_dbfs"] is None:
        _aviso(avisos, "senal_silencio_digital", "aviso", "Todas las muestras son cero: el archivo es silencio digital.")
    esp, ind, av2 = _espectro_y_indicios(A, sr, nyq)
    avisos += av2
    son = None
    if ffmpeg:
        son = _sonoridad(ffmpeg, ruta, avisos)
    else:
        _aviso(avisos, "sonoridad_sin_ffmpeg", "info", "LUFS, rango de sonoridad y pico real necesitan ffmpeg (filtro ebur128).")
    return {"version": VERSION, "solicitada": True, "disponible": True, "nota_interpretacion": NOTA, "fuente_decodificacion": fuente,
            "analizado": {"segundos": round(A.frames_tot / sr, 2), "ventanas": len(A.rms), "tasa_muestreo_hz": sr, "canales_analizados": A.C,
                          "recortado": bool(estado["recortado"] or (duracion_s and duracion_s > MAX_S))},
            "niveles": niv, "sonoridad": son, "espectro": esp, "indicios": ind, "avisos": avisos}
