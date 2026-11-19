"""Tests of paquete/modulos/_core/inspeccion.py, _core/senal.py and the «inspeccionar» route of the huella module.

Run from the repository root (standard library only):

    python3 -m unittest discover -s tests -v

Most tests build their audio in pure Python (tests/muestras.py) and run with ffprobe/ffmpeg switched off, so they pass on any
machine. The ones that compare against real tools (loudness, a real MP3 low-pass, ffprobe) are skipped when ffmpeg/ffprobe
are not installed.
"""
import hashlib
import importlib.util
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
CORE = RAIZ / "paquete" / "modulos" / "_core"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import inspeccion as I  # noqa: E402
import limpiar_tags  # noqa: E402
import muestras as M  # noqa: E402
import senal as S  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _codigos(r, donde=None):
    return [a["codigo"] for a in (donde if donde is not None else r["avisos"])]


def _items(r, clave):
    return [i for i in r["etiquetas"] if i["clave_original"] == clave]


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="gm_test_insp_")
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def f(self, nombre, datos):
        p = self.d / nombre
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
        return p

    def insp(self, nombre, datos, **kw):
        kw.setdefault("ffprobe", False)
        kw.setdefault("ffmpeg", None)
        return I.inspeccionar(self.f(nombre, datos), **kw)


# ==================================================================================================== esquema y hashes
class TestEsquema(Base):
    CLAVES = {"schema", "ok", "inspeccionado_en", "herramientas", "archivo", "contenedor", "audio", "campos_origen", "bloques_etiqueta",
              "etiquetas", "resumen_etiquetas", "incrustados", "senal", "avisos", "errores"}

    def test_claves_siempre_presentes(self):
        for nombre, datos in (("a.wav", M.wav(M.seno(440, 0.5, 1))), ("a.mp3", M.mp3()), ("a.flac", M.flac()), ("a.m4a", M.m4a())):
            r = self.insp(nombre, datos)
            self.assertEqual(set(r), self.CLAVES, nombre)
            self.assertEqual(r["schema"], "huella.inspeccion/1")
            self.assertEqual(set(r["incrustados"]), {"caratulas", "letras", "streams_no_audio", "capitulos", "bloques_binarios"})
            self.assertIsNone(r["senal"])          # not requested → null

    def test_hash_archivo_y_tamano(self):
        datos = M.wav(M.seno(440, 0.5, 1))
        r = self.insp("a.wav", datos)
        self.assertEqual(r["archivo"]["tamano_bytes"], len(datos))
        self.assertEqual(r["archivo"]["sha256"], hashlib.sha256(datos).hexdigest())
        self.assertEqual(r["archivo"]["nombre"], "a.wav")

    def test_sha256_audio_estable_con_otras_etiquetas(self):
        pcm = M.seno(440, 0.5, 1)
        a, b = self.insp("a.wav", M.wav(pcm, "UNO")), self.insp("b.wav", M.wav(pcm, "OTRO", orig="Otro"))
        self.assertNotEqual(a["archivo"]["sha256"], b["archivo"]["sha256"])
        self.assertEqual(a["archivo"]["sha256_audio"], hashlib.sha256(pcm).hexdigest())
        self.assertEqual(a["archivo"]["sha256_audio"], b["archivo"]["sha256_audio"])
        a, b = self.insp("a.mp3", M.mp3("UNO")), self.insp("b.mp3", M.mp3("OTRO", apilado=True))
        self.assertNotEqual(a["archivo"]["sha256"], b["archivo"]["sha256"])
        self.assertEqual(a["archivo"]["sha256_audio"], b["archivo"]["sha256_audio"])

    def test_sha256_audio_igual_en_copia_limpia_de_limpiar_tags(self):
        for nombre, datos in (("a.wav", M.wav(M.seno(440, 0.5, 1))), ("a.mp3", M.mp3()), ("a.flac", M.flac())):
            src = self.f(nombre, datos)
            dst = self.d / ("limpia_" + nombre)
            limpiar_tags.limpiar_copia(src, dst)
            x, y = I.inspeccionar(src, ffprobe=False, ffmpeg=None), I.inspeccionar(dst, ffprobe=False, ffmpeg=None)
            self.assertEqual(x["archivo"]["sha256_audio"], y["archivo"]["sha256_audio"], nombre)
            self.assertNotEqual(x["archivo"]["sha256"], y["archivo"]["sha256"], nombre)
            self.assertEqual(y["etiquetas"], [], nombre)

    def test_sin_ffprobe_avisa_y_usa_python(self):
        r = self.insp("a.wav", M.wav(M.seno(440, 0.5, 1)))
        self.assertIn("sin_ffprobe", _codigos(r))
        self.assertIsNone(r["herramientas"]["ffprobe"])
        self.assertAlmostEqual(r["contenedor"]["duracion_s"], 1.0, places=3)
        self.assertEqual((r["audio"]["tasa_muestreo_hz"], r["audio"]["canales"], r["audio"]["bits_por_muestra"], r["audio"]["codec"]), (44100, 2, 16, "pcm_s16le"))
        self.assertTrue(r["audio"]["sin_perdida"])
        self.assertEqual(r["campos_origen"]["audio.tasa_muestreo_hz"], "python")


# ==================================================================================================== WAV
class TestWav(Base):
    def test_bext_info_ixml_y_chunk_propio(self):
        r = self.insp("a.wav", M.wav(M.seno(440, 0.5, 1)))
        self.assertEqual(_items(r, "bext:Description")[0]["valor"], "Demo sintetica")
        self.assertEqual(_items(r, "bext:Originator")[0]["valor"], "TestStudio")
        self.assertEqual(_items(r, "INFO:INAM")[0]["clave_normalizada"], "title")
        self.assertEqual(_items(r, "INFO:ISRC")[0]["clave_normalizada"], "isrc")
        self.assertEqual(_items(r, "iXML:PROJECT")[0]["valor"], "Peli X")
        self.assertFalse(_items(r, "iXML:USER_X")[0]["estandar"])
        self.assertFalse(_items(r, "bext:BextVersion")[0]["editable"])        # container info, not editable
        self.assertEqual(r["resumen_etiquetas"]["title"], "Mi cancion")
        ids = {b["id"]: b for b in r["incrustados"]["bloques_binarios"]}
        self.assertEqual(set(ids), {"iXML", "cust"})
        self.assertEqual(ids["cust"]["bytes"], 5)
        self.assertFalse(ids["cust"]["editable"])
        self.assertIn("bytes_tras_data", _codigos(r))

    def test_wav_vacio_no_es_formato_sin_recorrido(self):
        r = self.insp("vacio.wav", b"")
        c = _codigos(r)
        self.assertIn("archivo_vacio", c)
        self.assertNotIn("formato_sin_recorrido", c)
        self.assertTrue(r["ok"])
        self.assertEqual(next(a for a in r["avisos"] if a["codigo"] == "archivo_vacio")["nivel"], "error")

    def test_wav_con_contenido_que_no_es_wav(self):
        r = self.insp("basura.wav", b"NOPE" * 500)
        c = _codigos(r)
        self.assertIn("cabecera_no_coincide", c)
        self.assertNotIn("formato_sin_recorrido", c)

    def test_wav_sin_fmt_o_sin_data(self):
        cuerpo = b"WAVE" + struct.pack("<4sI", b"data", 4) + b"\0\0\0\0"
        r = self.insp("sinfmt.wav", b"RIFF" + struct.pack("<I", len(cuerpo)) + cuerpo)
        self.assertIn("wav_sin_fmt", _codigos(r))
        fmt = struct.pack("<HHIIHH", 1, 2, 44100, 176400, 4, 16)
        cuerpo = b"WAVE" + struct.pack("<4sI", b"fmt ", 16) + fmt
        r = self.insp("sindata.wav", b"RIFF" + struct.pack("<I", len(cuerpo)) + cuerpo)
        self.assertIn("wav_sin_data", _codigos(r))

    def test_wav_cortado_avisa_chunk_truncado(self):
        datos = M.wav(M.seno(440, 0.5, 2))
        r = self.insp("cortado.wav", datos[:len(datos) // 2])
        self.assertIn("chunk_truncado", _codigos(r))


# ==================================================================================================== MP3
class TestMp3(Base):
    def test_etiquetas_caratula_letra_e_id3v1(self):
        r = self.insp("a.mp3", M.mp3())
        self.assertEqual(r["resumen_etiquetas"]["title"], "Mi cancion")
        self.assertEqual(r["resumen_etiquetas"]["isrc"], "ESXXX2600001")
        self.assertEqual(_items(r, "TXXX:Suno-Model")[0]["valor"], "v4")
        self.assertFalse(_items(r, "TXXX:Suno-Model")[0]["estandar"])
        self.assertEqual(_items(r, "ID3v1:title")[0]["valor"], "Mi cancion")
        c = r["incrustados"]["caratulas"]
        self.assertEqual((len(c), c[0]["ancho"], c[0]["alto"], c[0]["tipo_imagen"], c[0]["mime"]), (1, 64, 48, "front cover", "image/jpeg"))
        self.assertEqual(r["incrustados"]["letras"][0]["origen"], "USLT")
        self.assertTrue(r["resumen_etiquetas"]["lyrics"])
        self.assertEqual((r["audio"]["codec"], r["audio"]["tasa_muestreo_hz"], r["audio"]["bitrate_bps"]), ("mp3", 44100, 128000))
        self.assertIn("id3v1_y_id3v2", _codigos(r))
        self.assertIn("duracion_estimada", _codigos(r))
        self.assertEqual(r["campos_origen"]["contenedor.duracion_s"], "python_estimado")

    def test_priv_y_geob_opacos_solo_en_bloques_binarios(self):
        r = self.insp("a.mp3", M.mp3())
        claves = [i["clave_original"] for i in r["etiquetas"]]
        self.assertFalse([k for k in claves if k.startswith(("PRIV", "GEOB"))], claves)       # not duplicated as text tags
        b = {x["id"]: x for x in r["incrustados"]["bloques_binarios"]}
        self.assertEqual(b["PRIV"]["propietario"], "www.example.com")
        self.assertEqual((b["GEOB"]["nombre_archivo"], b["GEOB"]["descripcion"], b["GEOB"]["bytes"]), ("datos.bin", "descr", 32))
        for x in b.values():
            self.assertFalse(x["texto_legible"])
            self.assertFalse(x["editable"])
            self.assertEqual(len(x["sha256"]), 64)
            self.assertTrue(x["bloque"].startswith("b"))

    def test_priv_con_texto_legible_se_copia_como_no_editable(self):
        r = self.insp("a.mp3", M.mp3(priv_legible=True))
        it = _items(r, "PRIV:texto.example")
        self.assertEqual(len(it), 1)
        self.assertEqual(it[0]["valor"], "Esto es texto legible")
        self.assertFalse(it[0]["editable"])
        self.assertFalse(it[0]["estandar"])
        b = [x for x in r["incrustados"]["bloques_binarios"] if x["propietario"] == "texto.example"]
        self.assertTrue(b and b[0]["texto_legible"])
        self.assertFalse(_items(r, "PRIV:www.example.com"))          # the opaque one stays out

    def test_tags_apilados_en_conflicto(self):
        r = self.insp("a.mp3", M.mp3(apilado=True))
        self.assertIn("id3v2_apilados", _codigos(r))
        conf = [a["mensaje"] for a in r["avisos"] if a["codigo"] == "etiquetas_en_conflicto"]
        self.assertTrue(any("title" in m and "Titulo DISTINTO" in m for m in conf), conf)
        self.assertEqual(len([b for b in r["bloques_etiqueta"] if b["tipo"].startswith("ID3v2")]), 2)

    def test_mp3_sin_frames_avisa(self):
        r = self.insp("a.mp3", M.id3v2([M.t8("TIT2", "x")]) + b"\0" * 5000)
        self.assertIn("sin_frames", _codigos(r))

    def test_tag_truncado(self):
        r = self.insp("a.mp3", M.mp3()[:500])
        self.assertIn("tag_truncado", _codigos(r))


# ==================================================================================================== FLAC
class TestFlac(Base):
    def test_bloques_completos(self):
        r = self.insp("a.flac", M.flac())
        self.assertEqual(r["resumen_etiquetas"]["isrc"], "ESXXX2600001")
        self.assertEqual(_items(r, "SUNO_MODEL")[0]["valor"], "v4")
        self.assertEqual(r["incrustados"]["caratulas"][0]["origen"], "PICTURE")
        self.assertEqual((r["audio"]["codec"], r["audio"]["tasa_muestreo_hz"], r["audio"]["canales"], r["audio"]["bits_por_muestra"]), ("flac", 44100, 2, 16))
        self.assertAlmostEqual(r["contenedor"]["duracion_s"], 3.0, places=3)
        tipos = [b["tipo"] for b in r["bloques_etiqueta"]]
        self.assertIn("FLAC APPLICATION", tipos)
        self.assertIn("FLAC PADDING", tipos)
        self.assertNotIn("flac_truncado", _codigos(r))
        self.assertIsNotNone(r["archivo"]["sha256_audio"])
        app = next(b for b in r["incrustados"]["bloques_binarios"] if b["id"] == "APPLICATION")
        self.assertEqual((app["propietario"], app["bytes"], app["editable"]), ("MMgr", 30, False))

    def test_flac_truncado_avisa_y_no_da_hash_de_audio(self):
        for corte in (30, 100, 300):
            r = self.insp("t.flac", M.flac(truncar_en=corte))
            self.assertTrue(r["ok"])
            self.assertIn("flac_truncado", _codigos(r), corte)
            self.assertEqual(next(a for a in r["avisos"] if a["codigo"] == "flac_truncado")["nivel"], "error")
            self.assertIsNone(r["archivo"]["sha256_audio"], corte)
            self.assertEqual(r["errores"], [], corte)

    def test_flac_con_extension_equivocada(self):
        r = self.insp("falso.wav", M.flac())
        self.assertEqual(r["contenedor"]["familia"], "flac")
        self.assertIn("extension_no_coincide", _codigos(r))


# ==================================================================================================== M4A
class TestM4a(Base):
    def test_etiquetas_covr_y_atomos_libres(self):
        r = self.insp("a.m4a", M.m4a())
        self.assertEqual(r["resumen_etiquetas"]["title"], "Mi cancion")
        self.assertEqual(r["resumen_etiquetas"]["isrc"], "ESXXX2600001")
        self.assertEqual(_items(r, "----:com.apple.iTunes:SUNO_MODEL")[0]["valor"], "v4")
        self.assertEqual(r["incrustados"]["caratulas"][0]["origen"], "covr")
        self.assertEqual((r["audio"]["codec"], r["audio"]["tasa_muestreo_hz"], r["audio"]["canales"]), ("aac", 44100, 2))
        self.assertAlmostEqual(r["contenedor"]["duracion_s"], 3.0, places=3)
        self.assertEqual(_codigos(r).count("mp4_sin_moov"), 0)
        self.assertIsNotNone(r["archivo"]["sha256_audio"])

    def test_m4a_sin_moov(self):
        r = self.insp("a.m4a", M.m4a(con_moov=False))
        self.assertIn("mp4_sin_moov", _codigos(r))
        self.assertEqual(next(a for a in r["avisos"] if a["codigo"] == "mp4_sin_moov")["nivel"], "error")
        self.assertEqual(r["etiquetas"], [])
        self.assertTrue(r["ok"])

    def test_m4a_con_atomo_truncado(self):
        r = self.insp("a.m4a", M.m4a(con_moov=False, mdat_declara_de_mas=1000))
        c = _codigos(r)
        self.assertIn("mp4_atomo_truncado", c)
        self.assertIn("mp4_sin_moov", c)


# ==================================================================================================== formatos y robustez
class TestFormatos(Base):
    def test_ogg_y_aac_son_formato_sin_recorrido(self):
        self.assertIn("formato_sin_recorrido", _codigos(self.insp("a.ogg", b"OggS" + bytes(200))))
        self.assertIn("formato_sin_recorrido", _codigos(self.insp("a.aac", bytes(200))))
        self.assertIn("formato_sin_recorrido", _codigos(self.insp("a.aiff", b"FORM" + struct.pack(">I", 8) + b"AIFF" + bytes(20))))

    def test_extension_desconocida(self):
        c = _codigos(self.insp("a.xyz", b"hola" * 100))
        self.assertIn("formato_desconocido", c)
        self.assertNotIn("formato_sin_recorrido", c)

    def test_archivo_inexistente(self):
        r = I.inspeccionar(self.d / "no_existe.mp3", ffprobe=False, ffmpeg=None)
        self.assertFalse(r["ok"])
        self.assertTrue(r["errores"])

    def test_archivos_cortados_nunca_lanzan_excepcion(self):
        for nombre, datos in (("a.wav", M.wav(M.seno(440, 0.5, 1))), ("a.mp3", M.mp3()), ("a.flac", M.flac()), ("a.m4a", M.m4a())):
            for corte in (0, 1, 7, 12, 40, 200, len(datos) // 3, len(datos) - 1):
                r = self.insp("c_" + nombre, datos[:corte])
                self.assertTrue(r["ok"], (nombre, corte))
                self.assertEqual(set(r), TestEsquema.CLAVES, (nombre, corte))


# ==================================================================================================== señal
class TestSenal(Base):
    def senal(self, pcm, nombre="s.wav", **kw):
        r = self.insp(nombre, M.wav(pcm, extra=False, **kw), senal=True)
        return r, r["senal"]

    def test_nivel_y_picos_de_un_seno(self):
        r, s = self.senal(M.seno(1000, 0.5, 2))
        self.assertTrue(s["disponible"])
        self.assertEqual(s["fuente_decodificacion"], "python_wav")
        self.assertIn("no son un diagnóstico", s["nota_interpretacion"])
        n = s["niveles"]
        self.assertAlmostEqual(n["pico_muestra_dbfs"], -6.02, delta=0.1)
        self.assertAlmostEqual(n["rms_dbfs"], -9.03, delta=0.15)
        self.assertAlmostEqual(n["cresta_db"], 3.0, delta=0.2)
        self.assertEqual(n["muestras_en_fondo_de_escala"], 0)
        self.assertEqual(len(n["pico_por_canal_dbfs"]), 2)
        self.assertAlmostEqual(s["analizado"]["segundos"], 2.0, places=1)
        f = [p["frecuencia_hz"] for p in s["espectro"]["picos_tonales"]]
        self.assertTrue(any(abs(x - 1000) < 8 for x in f), f)
        self.assertEqual({b["id"] for b in s["espectro"]["bandas"]}, {"sub", "graves", "medios", "presencia", "brillo", "aire", "alta", "ultrasonica"})
        self.assertAlmostEqual(sum(b["energia_pct"] for b in s["espectro"]["bandas"] if b["disponible"]), 100.0, delta=0.5)

    def test_sin_ffmpeg_sonoridad_es_null_con_aviso(self):
        r, s = self.senal(M.seno(1000, 0.5, 2))
        self.assertIsNone(s["sonoridad"])
        self.assertIn("sonoridad_sin_ffmpeg", _codigos(r, s["avisos"]))

    def test_silencios_con_marca_de_tiempo(self):
        pcm = M.seno(1000, 0.5, 1) + M.silencio(2) + M.seno(1000, 0.9, 1)
        r, s = self.senal(pcm)
        sil = s["niveles"]["silencios"]
        self.assertEqual(len(sil), 1)
        self.assertAlmostEqual(sil[0]["inicio_s"], 1.0, delta=0.15)
        self.assertAlmostEqual(sil[0]["fin_s"], 3.0, delta=0.15)
        self.assertAlmostEqual(sil[0]["duracion_s"], 2.0, delta=0.2)
        self.assertEqual(s["niveles"]["silencio_inicial_s"], 0.0)
        self.assertGreaterEqual(s["niveles"]["pico_muestra_en_s"], 3.0)      # the loud tone is the last second
        self.assertAlmostEqual(s["niveles"]["pico_muestra_dbfs"], -0.92, delta=0.1)
        self.assertTrue(s["niveles"]["momentos_pico"])
        self.assertGreaterEqual(s["niveles"]["momentos_pico"][0]["t_s"], 3.0)

    def test_silencio_inicial_y_final(self):
        r, s = self.senal(M.silencio(1) + M.seno(1000, 0.5, 2) + M.silencio(1))
        n = s["niveles"]
        self.assertAlmostEqual(n["silencio_inicial_s"], 1.0, delta=0.15)
        self.assertAlmostEqual(n["silencio_final_s"], 1.0, delta=0.15)

    def test_saturacion(self):
        r, s = self.senal(M.saturado(1))
        self.assertGreater(s["niveles"]["pico_muestra_dbfs"], -0.01)
        self.assertGreater(s["niveles"]["muestras_en_fondo_de_escala"], 1000)

    def test_silencio_digital(self):
        r, s = self.senal(M.silencio(2))
        self.assertTrue(s["disponible"])
        self.assertIsNone(s["niveles"]["rms_dbfs"])
        self.assertIn("senal_silencio_digital", _codigos(r, s["avisos"]))
        self.assertIsNone(s["espectro"])
        self.assertIn("espectro_sin_frames", _codigos(r, s["avisos"]))

    def test_pico_tonal_estrecho_en_alta_frecuencia_es_un_indicio(self):
        r, s = self.senal(M.ruido_y_tono(4, 19000, 0.04))       # noise floor per bin ≈ −53 dB, tone ≈ −28 dB → ~25 dB of prominence
        hf = [i for i in s["indicios"] if i["codigo"] == "pico_tonal_hf"]
        self.assertEqual(len(hf), 1, s["indicios"])
        self.assertAlmostEqual(hf[0]["evidencia"]["frecuencia_hz"], 19000, delta=60)
        self.assertEqual(hf[0]["tipo"], "indicio_tecnico")
        self.assertEqual(hf[0]["zona"], "alta")
        self.assertGreaterEqual(hf[0]["evidencia"]["persistencia_pct"], 70)
        self.assertNotIn("diagnóstico", hf[0]["descripcion"].lower().replace("no es un diagnóstico", ""))
        p = next(x for x in s["espectro"]["picos_tonales"] if abs(x["frecuencia_hz"] - 19000) < 60)
        self.assertEqual(p["zona"], "alta")

    def test_ruido_sin_tono_no_da_pico_tonal(self):
        r, s = self.senal(M.ruido_y_tono(4, 19000, 0.0))
        self.assertEqual([i for i in s["indicios"] if i["codigo"] == "pico_tonal_hf"], [])

    def test_armonicos_de_cuantizacion_no_son_indicio(self):
        r, s = self.senal(M.seno(1000, 0.5, 3))
        self.assertEqual([i for i in s["indicios"] if i["codigo"] in ("pico_tonal_hf", "picos_equiespaciados_hf")], [])

    def test_ruido_blanco_tiene_energia_ultrasonica(self):
        r, s = self.senal(M.ruido_y_tono(4, 1000, 0.0))
        self.assertIn("energia_ultrasonica_notable", [i["codigo"] for i in s["indicios"]])
        self.assertTrue(s["espectro"]["bandas"][-1]["disponible"])

    def test_tasa_baja_deja_bandas_altas_no_disponibles(self):
        pcm = M.seno(500, 0.5, 3, sr=16000)
        r, s = self.senal(pcm, sr=16000)
        por = {b["id"]: b for b in s["espectro"]["bandas"]}
        self.assertFalse(por["alta"]["disponible"])
        self.assertIsNone(por["alta"]["energia_pct"])
        self.assertFalse(por["ultrasonica"]["disponible"])
        self.assertTrue(por["medios"]["disponible"])
        self.assertIsNone(s["espectro"]["piso_hf_mediana_db"])

    def _wav_bits(self, bits):
        n = 44100
        amp = (1 << (bits - 1)) - 1
        import math
        v = [int(0.5 * amp * math.sin(2 * math.pi * 1000 * i / 44100)) for i in range(n)]
        if bits == 8:
            b = bytes(x + 128 for x in v for _ in range(2))
        else:
            b = b"".join(x.to_bytes(bits // 8, "little", signed=True) * 2 for x in v)
        return b

    def test_wav_24_y_8_bits_sin_ffmpeg(self):
        for bits in (24, 8):
            r, s = self.senal(self._wav_bits(bits), bits=bits)
            self.assertTrue(s["disponible"], bits)
            self.assertAlmostEqual(s["niveles"]["pico_muestra_dbfs"], -6.02, delta=0.3, msg=bits)

    def test_formato_no_wav_sin_ffmpeg_deja_senal_no_disponible(self):
        for nombre, datos in (("a.mp3", M.mp3()), ("a.flac", M.flac()), ("a.m4a", M.m4a())):
            r = self.insp(nombre, datos, senal=True)
            s = r["senal"]
            self.assertFalse(s["disponible"], nombre)
            self.assertIn("senal_sin_decodificador", _codigos(r, s["avisos"]))
            for k in ("niveles", "sonoridad", "espectro", "analizado"):
                self.assertIsNone(s[k], (nombre, k))
            self.assertEqual(s["indicios"], [])

    def test_archivo_vacio_con_senal(self):
        r = self.insp("v.wav", b"", senal=True)
        self.assertFalse(r["senal"]["disponible"])
        self.assertIn("senal_archivo_vacio", _codigos(r, r["senal"]["avisos"]))

    def test_senal_no_solicitada_es_null(self):
        self.assertIsNone(self.insp("a.wav", M.wav(M.seno(440, 0.5, 1)))["senal"])


@unittest.skipUnless(FFMPEG, "ffmpeg no está instalado")
class TestConFfmpeg(Base):
    def lavfi(self, nombre, entrada, *extra):
        p = self.d / nombre
        r = subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", entrada, "-ac", "2", *extra, str(p)], capture_output=True, text=True)
        if r.returncode:
            self.skipTest("ffmpeg no pudo generar la muestra: " + r.stderr[:100])
        return p

    def test_sonoridad_lufs_y_pico_real(self):
        p = self.f("a.wav", M.wav(M.seno(997, 0.1, 3), extra=False))
        r = I.inspeccionar(p, ffprobe=False, senal=True, ffmpeg=FFMPEG)
        s = r["senal"]
        self.assertEqual(s["fuente_decodificacion"], "ffmpeg")
        self.assertIsNotNone(s["sonoridad"])
        self.assertTrue(-26 < s["sonoridad"]["integrada_lufs"] < -16, s["sonoridad"])
        self.assertAlmostEqual(s["sonoridad"]["pico_real_dbtp"], -20.0, delta=1.0)
        self.assertNotIn("sonoridad_sin_ffmpeg", _codigos(r, s["avisos"]))
        self.assertAlmostEqual(s["niveles"]["pico_muestra_dbfs"], -20.0, delta=0.2)

    def test_ffmpeg_y_python_dan_los_mismos_niveles_en_wav(self):
        p = self.f("a.wav", M.wav(M.seno(440, 0.5, 2) + M.silencio(1) + M.seno(880, 0.25, 1), extra=False))
        a = I.inspeccionar(p, ffprobe=False, senal=True, ffmpeg=FFMPEG)["senal"]
        b = I.inspeccionar(p, ffprobe=False, senal=True, ffmpeg=None)["senal"]
        self.assertEqual((a["fuente_decodificacion"], b["fuente_decodificacion"]), ("ffmpeg", "python_wav"))
        self.assertAlmostEqual(a["niveles"]["pico_muestra_dbfs"], b["niveles"]["pico_muestra_dbfs"], delta=0.05)
        self.assertAlmostEqual(a["niveles"]["rms_dbfs"], b["niveles"]["rms_dbfs"], delta=0.05)
        self.assertEqual([(x["inicio_s"], x["fin_s"]) for x in a["niveles"]["silencios"]], [(x["inicio_s"], x["fin_s"]) for x in b["niveles"]["silencios"]])

    def test_corte_espectral_de_un_mp3_real(self):
        try:
            p = self.lavfi("ruido.mp3", "anoisesrc=d=5:c=white:a=0.3:r=44100:seed=7", "-c:a", "libmp3lame", "-b:a", "128k")
        except unittest.SkipTest:
            raise
        r = I.inspeccionar(p, ffprobe=False, senal=True, ffmpeg=FFMPEG)
        s = r["senal"]
        self.assertTrue(s["disponible"], s["avisos"])
        corte = s["espectro"]["corte_espectral_hz"]
        self.assertIsNotNone(corte)
        self.assertTrue(15000 <= corte <= 18500, corte)
        ind = [i for i in s["indicios"] if i["codigo"] == "corte_espectral"]
        self.assertEqual(len(ind), 1)
        self.assertEqual(ind[0]["tipo"], "indicio_tecnico")
        self.assertIn("no indica cuál", ind[0]["descripcion"])
        self.assertEqual(r["audio"]["codec"], "mp3")

    def test_senal_de_m4a_aac_y_flac_reales(self):
        for ext, extra in ((".m4a", ("-c:a", "aac")), (".flac", ("-c:a", "flac"))):
            p = self.lavfi("t" + ext, "sine=f=1000:d=3:r=44100", *extra)
            r = I.inspeccionar(p, ffprobe=False, senal=True, ffmpeg=FFMPEG)
            self.assertTrue(r["senal"]["disponible"], ext)
            # lavfi's sine is −18 dBFS and mono→stereo costs 3 dB more; the codec adds a little
            self.assertTrue(-24 < r["senal"]["niveles"]["pico_muestra_dbfs"] < -16, (ext, r["senal"]["niveles"]["pico_muestra_dbfs"]))
            self.assertIsNotNone(r["senal"]["sonoridad"], ext)


@unittest.skipUnless(FFPROBE, "ffprobe no está instalado")
class TestConFfprobe(Base):
    def test_ffprobe_y_python_coinciden_en_lo_tecnico(self):
        p = self.f("a.wav", M.wav(M.seno(440, 0.5, 2)))
        a = I.inspeccionar(p, ffprobe=FFPROBE, ffmpeg=None)
        b = I.inspeccionar(p, ffprobe=False, ffmpeg=None)
        self.assertIsNotNone(a["herramientas"]["ffprobe"])
        for k in ("tasa_muestreo_hz", "canales", "codec", "bits_por_muestra"):
            self.assertEqual(a["audio"][k], b["audio"][k], k)
        self.assertAlmostEqual(a["contenedor"]["duracion_s"], b["contenedor"]["duracion_s"], places=2)
        self.assertEqual(a["campos_origen"]["audio.tasa_muestreo_hz"], "ffprobe")
        self.assertNotIn("sin_ffprobe", _codigos(a))

    def test_ffprobe_se_encuentra_junto_a_ffmpeg(self):
        self.assertEqual(Path(I.buscar_ffprobe(FFMPEG or "/no/existe/ffmpeg")).name.lower().split(".")[0], "ffprobe")


# ==================================================================================================== ruta POST inspeccionar de Huella
class _Req:
    def __init__(self, cuerpo=None):
        self._c, self.resp = cuerpo, None

    def json(self):
        return self._c

    def arg(self, n):
        return None

    def send(self, d):
        self.resp = d


class TestRuta(Base):
    def setUp(self):
        super().setUp()
        sp = importlib.util.spec_from_file_location("huella_servidor_test", RAIZ / "paquete" / "modulos" / "huella" / "servidor.py")
        self.srv = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.srv)
        self.ctx = SimpleNamespace(root=self.d, datos=self.d / "datos", ffmpeg=lambda: None)
        (self.d / "unreleased" / "Cancion" / "master").mkdir(parents=True)
        self.rel = "unreleased/Cancion/master/a.wav"
        (self.d / self.rel).write_bytes(M.wav(M.seno(440, 0.5, 1)))

    def llama(self, cuerpo):
        r = _Req(cuerpo)
        self.srv.ROUTES["POST inspeccionar"](r, self.ctx)
        return r.resp

    def test_la_ruta_esta_registrada(self):
        self.assertIn("POST inspeccionar", self.srv.ROUTES)

    def test_inspecciona_un_archivo_de_la_biblioteca(self):
        r = self.llama({"p": self.rel})
        self.assertTrue(r["ok"])
        self.assertEqual(r["schema"], "huella.inspeccion/1")
        self.assertEqual(r["archivo"]["ruta_relativa"], self.rel)
        self.assertEqual(r["archivo"]["nombre"], "a.wav")
        self.assertIsNone(r["senal"])
        self.assertEqual(r["resumen_etiquetas"]["title"], "Mi cancion")

    def test_con_senal(self):
        r = self.llama({"p": self.rel, "senal": True})
        self.assertTrue(r["ok"])
        self.assertTrue(r["senal"]["disponible"])
        self.assertIn("espectro", r["senal"])

    def test_rechaza_rutas_fuera_de_la_biblioteca_y_no_audio(self):
        (self.d.parent / "fuera.wav").write_bytes(M.wav(M.seno(440, 0.5, 1)))
        (self.d / "nota.txt").write_text("hola")
        for p in ("../fuera.wav", "/etc/passwd", "nota.txt", "no_existe.wav", "", None):
            r = self.llama({"p": p})
            self.assertFalse(r["ok"], p)
            self.assertIn("error", r)
        self.assertFalse(self.llama(None)["ok"])
        (self.d.parent / "fuera.wav").unlink()

    def test_un_wav_vacio_se_inspecciona_con_aviso(self):
        (self.d / "vacio.wav").write_bytes(b"")
        r = self.llama({"p": "vacio.wav"})
        self.assertTrue(r["ok"])
        self.assertIn("archivo_vacio", _codigos(r))


if __name__ == "__main__":
    unittest.main()
