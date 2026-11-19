"""Tests of paquete/modulos/_core/escribir_tags.py and the «etiquetar» route of the huella module.

    python3 -m unittest discover -s tests -v

The core invariant of the whole feature: the sound is never altered (sha256 of the audio identical), the original is never touched,
and nothing is delivered unless the strict verification passes. Most tests use pure-Python samples; the ones with real ffmpeg
encodings are skipped when ffmpeg is not installed.
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "paquete" / "modulos" / "_core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import escribir_tags as E  # noqa: E402
import inspeccion as I  # noqa: E402
import muestras as M  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
CRED = [{"rol": "letra", "nombre": "Autora Demo"}, {"rol": "musica", "nombre": "Autora Demo"}, {"rol": "arreglos", "nombre": "Ana Pérez"},
        {"rol": "mezcla", "nombre": "Luis Gómez"}, {"rol": "asistencia", "nombre": "Estudio X", "tipo": "persona", "nota": "asistente de mezcla"}]
PONER = {"title": "Mi canción", "artist": "Autora Demo", "date": "2026-11-19", "copyright": "2026 Autora Demo", "isrc": "ES-XXX-26-00001",
         "lyrics": "Verso uno\nVerso dos", "personalizados": {"Proyecto": "Demo"}}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="gm_test_etq_")
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def f(self, nombre, datos):
        p = self.d / nombre
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
        return p

    def muestras(self):
        return {"mp3": self.f("a.mp3", M.mp3()), "wav": self.f("a.wav", M.wav(M.seno(440, 0.5, 1))), "flac": self.f("a.flac", M.flac())}

    def aplicar(self, src, **kw):
        dst = self.d / "salida" / ("copia" + Path(src).suffix)
        kw.setdefault("poner", PONER)
        kw.setdefault("creditos", CRED)
        return E.etiquetar(src, dst, simular=False, **kw), dst

    @staticmethod
    def elegir(plan, **crit):
        return next(a for a in plan["acciones"] if all(a.get(k) == v for k, v in crit.items()))

    def clave(self, r):
        return {i["clave_original"]: i for i in I.inspeccionar(r, ffprobe=False, ffmpeg=None)["etiquetas"]}


# ==================================================================================================== lo declarado
class TestNormalizar(unittest.TestCase):
    def test_acepta_y_normaliza(self):
        d, err = E.normalizar(PONER, CRED)
        self.assertEqual(err, [])
        self.assertEqual(d["campos"]["isrc"], "ESXXX2600001")
        self.assertEqual(d["campos"]["lyrics"], "Verso uno\nVerso dos")
        self.assertEqual(d["personalizados"], {"Proyecto": "Demo"})
        self.assertEqual(len(d["creditos"]), 5)

    def test_rechaza_datos_incorrectos(self):
        casos = [({"date": "26"}, []), ({"isrc": "XX"}, []), ({"track": "a/b"}, []), ({"language": "es"}, []), ({"inventado": "x"}, []),
                 ({"personalizados": {"TITLE": "x"}}, []), ({"personalizados": {"mal=nombre": "x"}}, []),
                 ({}, [{"rol": "dios", "nombre": "x"}]), ({}, [{"rol": "mezcla", "nombre": ""}]), ({}, [{"rol": "mezcla", "nombre": "x", "tipo": "robot"}])]
        for poner, cred in casos:
            self.assertTrue(E.normalizar(poner, cred)[1], (poner, cred))

    def test_vacios_se_ignoran_y_se_limpian_controles(self):
        d, err = E.normalizar({"title": "  ", "comment": "hola\x00\x07 mundo\r\nlinea 2"}, [])
        self.assertEqual(err, [])
        self.assertEqual(d["campos"], {"comment": "hola mundo\nlinea 2"})

    def test_derivar_creditos_a_campos_y_texto(self):
        dv = E.derivar(E.normalizar({"composer": "Otra"}, CRED)[0])
        self.assertEqual(dv["efectivos"]["lyricist"], "Autora Demo")
        self.assertEqual(dv["efectivos"]["composer"], "Otra / Autora Demo")
        self.assertEqual(dv["vorbis"]["CONTRIBUTOR"], "Estudio X (asistente de mezcla)")
        self.assertIn(("arranger", "Ana Pérez"), dv["ipls"])
        self.assertTrue(dv["texto"].startswith("Letra: Autora Demo; Música: Autora Demo; Arreglos: Ana Pérez; Mezcla: Luis Gómez"))


# ==================================================================================================== simular
class TestSimular(Base):
    def test_no_escribe_nada_y_describe_el_plan(self):
        m = self.muestras()
        antes = sorted(p.name for p in self.d.rglob("*"))
        for fam, src in m.items():
            r = E.etiquetar(src, None, PONER, CRED, simular=True)
            self.assertTrue(r["ok"] and r["simulacion"], fam)
            p = r["plan"]
            self.assertTrue(p["puede_aplicarse"], fam)
            self.assertEqual(p["soporte"]["escritor"], "python")
            self.assertTrue(p["sha256_audio_origen"])
            campos = {x["campo"] for x in p["se_escribira"]}
            self.assertTrue({"title", "lyricist", "composer", "isrc", "creditos", "personalizado:Proyecto"} <= campos, (fam, campos))
            json.dumps(r)                                           # the plan is plain JSON (no bytes leaking)
        self.assertEqual(sorted(p.name for p in self.d.rglob("*")), antes)

    def test_por_defecto_todo_lo_ajeno_se_quita(self):
        r = E.etiquetar(self.muestras()["mp3"], None, PONER, CRED, simular=True)
        acc = r["plan"]["acciones"]
        self.assertTrue(acc)
        self.assertEqual({a["accion"] for a in acc} - {"regenerar"}, {"quitar"})

    def test_destinos_por_formato(self):
        m = self.muestras()
        dest = lambda fam, campo: next(x["destino"] for x in E.etiquetar(m[fam], None, PONER, CRED, simular=True)["plan"]["se_escribira"] if x["campo"] == campo)  # noqa: E731
        self.assertEqual(dest("mp3", "lyricist"), "TEXT")
        self.assertEqual(dest("flac", "lyricist"), "LYRICIST")
        self.assertEqual(dest("wav", "title"), "INFO:INAM + TIT2")
        self.assertEqual(dest("flac", "creditos"), "CREDITS + ARRANGER/CONTRIBUTOR/MIXER")

    def test_datos_invalidos_no_producen_plan(self):
        r = E.etiquetar(self.muestras()["mp3"], None, {"isrc": "mal"}, [], simular=True)
        self.assertFalse(r["ok"])
        self.assertTrue(r["campos_invalidos"])


# ==================================================================================================== escribir: lo esencial
class TestEscribir(Base):
    def test_el_audio_no_cambia_y_el_original_no_se_toca(self):
        for fam, src in self.muestras().items():
            h0 = sha(src)
            mt = src.stat().st_mtime_ns
            r, dst = self.aplicar(src)
            self.assertTrue(r["ok"], (fam, r.get("error")))
            v = r["verificacion"]
            self.assertTrue(v["ok"] and v["sha256_audio_igual"], fam)
            self.assertEqual(r["antes"]["sha256_audio"], r["despues"]["sha256_audio"])
            self.assertNotEqual(r["antes"]["sha256"], r["despues"]["sha256"])
            self.assertEqual((sha(src), src.stat().st_mtime_ns), (h0, mt), "the original must stay untouched")
            self.assertTrue(dst.is_file())
            self.assertFalse(list(dst.parent.glob("*.tmp*")), "no temporary file left behind")

    def test_se_escribe_lo_declarado_y_nada_ajeno(self):
        for fam, src in self.muestras().items():
            r, dst = self.aplicar(src)
            self.assertTrue(r["ok"], (fam, r.get("error")))
            insp = I.inspeccionar(dst, ffprobe=False, ffmpeg=None)
            res = insp["resumen_etiquetas"]
            self.assertEqual((res["title"], res["isrc"], res["copyright"]), ("Mi canción", "ESXXX2600001", "2026 Autora Demo"), fam)
            self.assertEqual(res["composer"], "Autora Demo", fam)
            self.assertTrue(res["lyrics"], fam)
            self.assertEqual(insp["incrustados"]["caratulas"], [], fam)
            self.assertEqual(insp["incrustados"]["bloques_binarios"], [], fam)          # PRIV / GEOB / APPLICATION / iXML / cust are gone
            claves = {i["clave_original"] for i in insp["etiquetas"]}
            self.assertFalse({c for c in claves if "Suno" in c or c.startswith(("ID3v1", "TENC", "TSSE", "bext"))}, (fam, claves))
            self.assertEqual(r["verificacion"]["etiquetas_inesperadas"], [], fam)
            self.assertIn("Arreglos: Ana Pérez", " ".join(str(i["valor"]) for i in insp["etiquetas"]), fam)

    def test_creditos_legibles_y_estructurados(self):
        r, dst = self.aplicar(self.muestras()["mp3"])
        t = self.clave(dst)
        self.assertEqual(t["TEXT"]["valor"], "Autora Demo")
        self.assertIn("Mezcla: Luis Gómez", t["TXXX:CREDITS"]["valor"])
        self.assertIn("Asistencia: Estudio X (asistente de mezcla)", t["TXXX:CREDITS"]["valor"])
        self.assertEqual(t["IPLS"]["valor"], "arranger: Ana Pérez; mix: Luis Gómez; assistant: Estudio X")
        self.assertEqual(t["TXXX:Proyecto"]["valor"], "Demo")
        _, dst = self.aplicar(self.muestras()["flac"])
        t = self.clave(dst)
        self.assertEqual((t["ARRANGER"]["valor"], t["MIXER"]["valor"], t["LYRICIST"]["valor"]), ("Ana Pérez", "Luis Gómez", "Autora Demo"))

    def test_sin_declarar_nada_es_una_copia_limpia(self):
        for fam, src in self.muestras().items():
            r, dst = self.aplicar(src, poner={}, creditos=[])
            self.assertTrue(r["ok"], fam)
            insp = I.inspeccionar(dst, ffprobe=False, ffmpeg=None)
            self.assertEqual(insp["etiquetas"], [], fam)
            self.assertEqual(insp["archivo"]["sha256_audio"], I.inspeccionar(src, ffprobe=False, ffmpeg=None)["archivo"]["sha256_audio"], fam)

    def test_caratula_nueva(self):
        for fam, src in self.muestras().items():
            r, dst = self.aplicar(src, caratula=M.jpeg(120, 90))
            self.assertTrue(r["ok"], (fam, r.get("error")))
            c = I.inspeccionar(dst, ffprobe=False, ffmpeg=None)["incrustados"]["caratulas"]
            self.assertEqual((len(c), c[0]["ancho"], c[0]["alto"], c[0]["mime"]), (1, 120, 90, "image/jpeg"), fam)
            self.assertTrue(r["verificacion"]["caratulas_ok"])

    def test_caratula_invalida(self):
        r = E.etiquetar(self.muestras()["mp3"], None, PONER, CRED, caratula=b"no soy una imagen", simular=True)
        self.assertFalse(r["ok"])
        self.assertIn("JPEG o PNG", r["campos_invalidos"][0])

    def test_no_sobrescribe_ni_escribe_sobre_si_mismo(self):
        src = self.muestras()["mp3"]
        r, dst = self.aplicar(src)
        r2 = E.etiquetar(src, dst, PONER, CRED, simular=False)
        self.assertFalse(r2["ok"])
        self.assertIn("no se sobrescribe", r2["error"])
        self.assertFalse(E.etiquetar(src, src, PONER, CRED, simular=False)["ok"])


# ==================================================================================================== conservar
class TestConservar(Base):
    def plan(self, src, **kw):
        return E.etiquetar(src, None, kw.pop("poner", PONER), kw.pop("creditos", CRED), simular=True)["plan"]

    def test_mp3_conserva_etiqueta_binario_y_caratula_elegidos(self):
        src = self.muestras()["mp3"]
        p = self.plan(src)
        suno = self.elegir(p, clave="TXXX:Suno-Model")
        priv = self.elegir(p, tipo="binario", id="PRIV")
        cons = [{"tipo": "etiqueta", "bloque": suno["bloque"], "clave": suno["clave"]},
                {"tipo": "binario", "bloque": priv["bloque"], "id": "PRIV", "propietario": priv["propietario"]}, {"tipo": "caratula", "indice": 0}]
        r, dst = self.aplicar(src, conservar=cons)
        self.assertTrue(r["ok"], r.get("error"))
        insp = I.inspeccionar(dst, ffprobe=False, ffmpeg=None)
        self.assertEqual({i["clave_original"]: i["valor"] for i in insp["etiquetas"]}["TXXX:Suno-Model"], "v4")
        antes = I.inspeccionar(src, ffprobe=False, ffmpeg=None)
        sha_priv = next(b["sha256"] for b in antes["incrustados"]["bloques_binarios"] if b["id"] == "PRIV")
        self.assertEqual([b["sha256"] for b in insp["incrustados"]["bloques_binarios"]], [sha_priv])       # byte-identical
        self.assertEqual(insp["incrustados"]["caratulas"][0]["sha256"], antes["incrustados"]["caratulas"][0]["sha256"])
        self.assertNotIn("GEOB", {b["id"] for b in insp["incrustados"]["bloques_binarios"]})             # not ticked → gone
        self.assertTrue(r["verificacion"]["ok"])

    def test_wav_conserva_bloques_bext_y_cust(self):
        src = self.muestras()["wav"]
        p = self.plan(src)
        bext = self.elegir(p, clave="bext:Description")
        cust = self.elegir(p, tipo="binario", id="cust")
        r, dst = self.aplicar(src, conservar=[{"tipo": "bloque", "bloque": bext["bloque"]}, {"tipo": "bloque", "bloque": cust["bloque"]}])
        self.assertTrue(r["ok"], r.get("error"))
        t = self.clave(dst)
        self.assertEqual(t["bext:Description"]["valor"], "Demo sintetica")
        self.assertEqual({b["id"] for b in I.inspeccionar(dst, ffprobe=False, ffmpeg=None)["incrustados"]["bloques_binarios"]}, {"cust"})
        self.assertTrue(r["verificacion"]["bloques_conservados_ok"])

    def test_flac_conserva_application(self):
        src = self.muestras()["flac"]
        app = self.elegir(self.plan(src), tipo="binario", id="APPLICATION")
        r, dst = self.aplicar(src, conservar=[{"tipo": "bloque", "bloque": app["bloque"]}])
        self.assertTrue(r["ok"], r.get("error"))
        b = I.inspeccionar(dst, ffprobe=False, ffmpeg=None)["incrustados"]["bloques_binarios"]
        self.assertEqual([(x["id"], x["propietario"], x["bytes"]) for x in b], [("APPLICATION", "MMgr", 30)])

    def test_lo_declarado_gana_a_lo_conservado(self):
        src = self.muestras()["flac"]
        titulo = self.elegir(self.plan(src), clave="TITLE")
        r, dst = self.aplicar(src, conservar=[{"tipo": "etiqueta", "bloque": titulo["bloque"], "clave": "TITLE"}])
        self.assertTrue(r["ok"])
        self.assertEqual(self.clave(dst)["TITLE"]["valor"], "Mi canción")
        self.assertEqual(self.elegir(self.plan(src), clave="TITLE")["accion"], "quitar")        # not ticked in the plan
        p = E.etiquetar(src, None, PONER, CRED, [{"tipo": "etiqueta", "bloque": titulo["bloque"], "clave": "TITLE"}], simular=True)["plan"]
        self.assertEqual(self.elegir(p, clave="TITLE")["accion"], "sustituir")

    def test_letra_conservada_completa_y_no_truncada(self):
        larga = "linea de la letra " * 30
        src = self.f("l.flac", M.flac())
        # the sample's lyrics are short; write a copy with long lyrics first, then keep them through a second pass
        r1, c1 = self.aplicar(src, poner={"lyrics": larga}, creditos=[])
        self.assertTrue(r1["ok"])
        letra = self.elegir(E.etiquetar(c1, None, {}, [], simular=True)["plan"], clave="LYRICS")
        dst = self.d / "salida" / "segunda.flac"
        r2 = E.etiquetar(c1, dst, {}, [], [{"tipo": "etiqueta", "bloque": letra["bloque"], "clave": "LYRICS"}], simular=False)
        self.assertTrue(r2["ok"], r2.get("error"))
        it = self.clave(dst)["LYRICS"]
        self.assertEqual(it["caracteres"], len(larga.strip()))

    def test_cada_elemento_dice_como_se_marca_y_esa_marca_funciona(self):
        """The UI builds `conservar` from the plan alone: {como, bloque, clave|id+propietario|indice}."""
        for fam, src in self.muestras().items():
            plan = E.etiquetar(src, None, {}, [], simular=True)["plan"]
            self.assertTrue(plan["acciones"], fam)
            self.assertTrue(all(a["como"] in ("etiqueta", "binario", "bloque", "caratula") for a in plan["acciones"]), fam)
            cons = []
            for a in plan["acciones"]:
                if not a["conservable"] or a["accion"] != "quitar":
                    continue
                e = {"tipo": a["como"], "bloque": a.get("bloque")}
                if a["como"] == "etiqueta":
                    e["clave"] = a["clave"]
                elif a["como"] == "binario":
                    e.update(id=a["id"], propietario=a["propietario"])
                elif a["como"] == "caratula":
                    e["indice"] = a["indice"]
                cons.append(e)
            self.assertTrue(cons, fam)
            r, dst = self.aplicar(src, poner={}, creditos=[], conservar=cons)
            self.assertTrue(r["ok"], (fam, r.get("error")))
            self.assertTrue(r["verificacion"]["ok"], fam)
            self.assertEqual(r["verificacion"]["etiquetas_inesperadas"], [], fam)
            kept = E.etiquetar(src, None, {}, [], cons, simular=True)["plan"]
            self.assertFalse([a for a in kept["acciones"] if a["conservable"] and a["accion"] == "quitar" and a["como"] != "etiqueta"], fam)

    def test_lo_no_conservable_se_marca(self):
        p = self.plan(self.muestras()["mp3"])
        self.assertFalse(self.elegir(p, clave="IPLS")["conservable"] if any(a.get("clave") == "IPLS" for a in p["acciones"]) else False)


# ==================================================================================================== verificación estricta
class TestVerificacionEstricta(Base):
    def prueba(self, escritor, cambio):
        src = self.muestras()["mp3"]
        orig = getattr(E, escritor)
        with mock.patch.object(E, escritor, side_effect=lambda *a, **k: cambio(orig, *a, **k)):
            r, dst = self.aplicar(src)
        self.assertFalse(r["ok"])
        self.assertFalse(dst.exists(), "nothing is delivered when the verification fails")
        self.assertFalse(list(dst.parent.glob("*")), "no leftovers")
        return r["verificacion"]

    def test_audio_alterado(self):
        def malo(orig, src, dst, *a, **k):
            man = orig(src, dst, *a, **k)
            b = bytearray(Path(dst).read_bytes())
            b[-10] ^= 0xFF
            Path(dst).write_bytes(bytes(b))
            return man
        v = self.prueba("_escribir_mp3", malo)
        self.assertFalse(v["sha256_audio_igual"])
        self.assertIn("NO está intacta", " ".join(v["errores"]))

    def test_campo_declarado_que_no_se_escribio(self):
        def malo(orig, *a, **k):
            return orig(*a, **k) + [{"clave": "TXXX:FANTASMA", "norm": None, "valor": "x"}]
        v = self.prueba("_escribir_mp3", malo)
        self.assertEqual(v["lectura_de_vuelta"]["faltan"], ["TXXX:FANTASMA"])

    def test_valor_distinto_al_declarado(self):
        def malo(orig, *a, **k):
            return [dict(m, valor="otro") if m["clave"] == "TIT2" else m for m in orig(*a, **k)]
        v = self.prueba("_escribir_mp3", malo)
        self.assertEqual(v["lectura_de_vuelta"]["distintos"], ["TIT2"])

    def test_etiqueta_ajena_colada(self):
        orig_frames = E._frames_id3

        def con_extra(*a, **k):
            fr, man = orig_frames(*a, **k)
            return fr + [("TKEY", b"\x00Am")], man
        src = self.muestras()["mp3"]
        with mock.patch.object(E, "_frames_id3", side_effect=con_extra):
            r, dst = self.aplicar(src)
        self.assertFalse(r["ok"])
        self.assertEqual(r["verificacion"]["etiquetas_inesperadas"], ["TKEY"])
        self.assertFalse(dst.exists())

    def test_md5_decodificado_distinto(self):
        src = self.muestras()["mp3"]
        n = {"i": 0}

        def md5(ff, ruta):
            n["i"] += 1
            return "a" * 32 if n["i"] == 1 else "b" * 32
        with mock.patch.object(E, "md5_decodificado", side_effect=md5):
            r, dst = self.aplicar(src, ffmpeg=FFMPEG or "ffmpeg")
        self.assertFalse(r["ok"])
        self.assertFalse(r["verificacion"]["md5_decodificado_igual"])
        self.assertFalse(dst.exists())


# ==================================================================================================== formatos sin escritor seguro
class TestSinEscritor(Base):
    def test_formatos_de_solo_lectura(self):
        casos = {"a.ogg": b"OggS" + bytes(300), "a.aiff": b"FORM" + b"\0\0\0\x10AIFF" + bytes(30), "a.aac": bytes(300)}
        for nombre, datos in casos.items():
            src = self.f(nombre, datos)
            plan = E.etiquetar(src, None, PONER, CRED, simular=True)["plan"]
            self.assertFalse(plan["puede_aplicarse"], nombre)
            self.assertIn("escritura_no_soportada", [a["codigo"] for a in plan["avisos"]], nombre)
            r, dst = self.aplicar(src)
            self.assertFalse(r["ok"], nombre)
            self.assertFalse(dst.exists(), nombre)

    def test_origen_danado_no_se_toca(self):
        for nombre, datos in (("t.flac", M.flac(truncar_en=300)), ("v.wav", b""), ("t.m4a", M.m4a(con_moov=False)), ("c.wav", b"NOPE" * 300)):
            src = self.f(nombre, datos)
            plan = E.etiquetar(src, None, PONER, CRED, ffmpeg=FFMPEG or "ffmpeg", simular=True)["plan"]
            self.assertFalse(plan["puede_aplicarse"], nombre)
            self.assertEqual([a["codigo"] for a in plan["avisos"]][:1], ["origen_danado"], nombre)
            r, dst = self.aplicar(src, ffmpeg=FFMPEG or "ffmpeg")
            self.assertFalse(r["ok"], nombre)
            self.assertFalse(dst.exists(), nombre)

    def test_m4a_sin_ffmpeg(self):
        plan = E.etiquetar(self.f("a.m4a", M.m4a()), None, PONER, CRED, ffmpeg=None, simular=True)["plan"]
        self.assertFalse(plan["puede_aplicarse"])
        self.assertIn("sin_ffmpeg", [a["codigo"] for a in plan["avisos"]])


# ==================================================================================================== registro
class TestRegistro(Base):
    def test_hashes_informe_y_diario(self):
        datos = self.d / "DATOS"
        modulo = datos / "modulos" / "huella"
        modulo.mkdir(parents=True)
        (datos / "diario_movimientos.jsonl").write_text(json.dumps({"id": 1, "op": "move", "src": "a", "dst": "b"}) + "\n", encoding="utf-8")
        src = self.muestras()["flac"]
        r, dst = self.aplicar(src)
        rid = E.registrar(modulo, "unreleased/a.flac", "_etiquetados/copia.flac", r)
        h = json.loads((modulo / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(list(h), [r["antes"]["sha256_audio"]])
        v = h[r["antes"]["sha256_audio"]]["versiones"]
        self.assertEqual([(x["origen"], x["p"], x["sha256"]) for x in v], [(True, "unreleased/a.flac", r["antes"]["sha256"]), (False, "_etiquetados/copia.flac", r["despues"]["sha256"])])
        inf = json.loads((modulo / "etiquetado" / (rid + ".json")).read_text(encoding="utf-8"))
        self.assertEqual((inf["id"], inf["origen"], inf["copia"]), (rid, "unreleased/a.flac", "_etiquetados/copia.flac"))
        self.assertTrue(inf["antes"]["etiquetas"] and inf["despues"]["etiquetas"])
        self.assertTrue(inf["verificacion"]["ok"])
        lineas = [json.loads(x) for x in (datos / "diario_movimientos.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["op"] for x in lineas], ["move", "etiquetar"])                    # the previous journal line is untouched
        e = lineas[1]
        self.assertEqual((e["id"], e["sha256_audio"], e["sha256_antes"], e["sha256_despues"]), (rid, r["antes"]["sha256_audio"], r["antes"]["sha256"], r["despues"]["sha256"]))
        self.assertTrue(e["quitadas"] > 0 and "TITLE" in e["escritas"])

    def test_segunda_version_del_mismo_audio_comparte_ficha(self):
        modulo = self.d / "DATOS" / "modulos" / "huella"
        modulo.mkdir(parents=True)
        src = self.muestras()["mp3"]
        for n in range(2):
            dst = self.d / "salida" / ("c%d.mp3" % n)
            r = E.etiquetar(src, dst, {"title": "T%d" % n}, [], simular=False)
            E.registrar(modulo, "a.mp3", "_etiquetados/c%d.mp3" % n, r)
        h = json.loads((modulo / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(len(h), 1)
        self.assertEqual([x["origen"] for x in next(iter(h.values()))["versiones"]], [True, False, False])

    def test_el_resultado_publico_de_inspeccionar_no_lleva_bytes(self):
        r = I.inspeccionar(self.muestras()["mp3"], ffprobe=False, ffmpeg=None)
        txt = json.dumps(r)
        self.assertNotIn('"_datos"', txt)
        self.assertNotIn('"_cuerpo"', txt)
        self.assertNotIn('"_completo"', txt)


# ==================================================================================================== ruta POST etiquetar
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
        sp = importlib.util.spec_from_file_location("huella_servidor_etq", RAIZ / "paquete" / "modulos" / "huella" / "servidor.py")
        self.srv = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.srv)
        self.lib = self.d / "biblioteca"
        self.datos = self.d / "DATOS" / "modulos" / "huella"
        self.datos.mkdir(parents=True)
        self.ctx = SimpleNamespace(root=self.lib, datos=self.datos, ffmpeg=lambda: None)
        (self.lib / "unreleased" / "Cancion" / "master").mkdir(parents=True)
        self.rel = "unreleased/Cancion/master/tema.mp3"
        (self.lib / self.rel).write_bytes(M.mp3())
        (self.lib / "arte.jpg").write_bytes(M.jpeg(200, 200))

    def llama(self, cuerpo):
        r = _Req(cuerpo)
        self.srv.ROUTES["POST etiquetar"](r, self.ctx)
        return r.resp

    def test_registrada_y_simular_es_el_modo_por_defecto(self):
        self.assertIn("POST etiquetar", self.srv.ROUTES)
        antes = sorted(p.relative_to(self.d).as_posix() for p in self.d.rglob("*"))
        r = self.llama({"p": self.rel, "poner": PONER, "creditos": CRED})
        self.assertTrue(r["ok"] and r["simulacion"])
        self.assertTrue(r["plan"]["puede_aplicarse"])
        self.assertEqual(sorted(p.relative_to(self.d).as_posix() for p in self.d.rglob("*")), antes)

    def test_aplicar_crea_la_copia_en_etiquetados_sin_sobrescribir(self):
        h0 = sha(self.lib / self.rel)
        r = self.llama({"p": self.rel, "poner": PONER, "creditos": CRED, "simular": False})
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(r["copia"]["p"], "_etiquetados/tema.mp3")
        self.assertTrue((self.lib / "_etiquetados" / "tema.mp3").is_file())
        self.assertTrue(r["verificacion"]["sha256_audio_igual"])
        self.assertTrue(r["registro"]["ok"])
        self.assertNotIn("_informe", r)
        r2 = self.llama({"p": self.rel, "poner": PONER, "creditos": CRED, "simular": False})
        self.assertEqual(r2["copia"]["p"], "_etiquetados/tema (2).mp3")
        self.assertEqual(self.llama({"p": self.rel, "poner": {"title": "x"}, "simular": False, "nombre": "Mi tema"})["copia"]["p"], "_etiquetados/Mi tema.mp3")
        self.assertEqual(sha(self.lib / self.rel), h0)
        self.assertTrue((self.datos / "hashes.json").is_file())
        self.assertEqual(len(list((self.datos / "etiquetado").glob("etq-*.json"))), 3)
        ops = [json.loads(x)["op"] for x in (self.d / "DATOS" / "diario_movimientos.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(ops, ["etiquetar"] * 3)
        json.dumps(r)

    def test_caratula_de_la_biblioteca(self):
        r = self.llama({"p": self.rel, "poner": {"title": "x"}, "caratula": "arte.jpg", "simular": False})
        self.assertTrue(r["ok"], r.get("error"))
        c = I.inspeccionar(self.lib / r["copia"]["p"], ffprobe=False, ffmpeg=None)["incrustados"]["caratulas"]
        self.assertEqual((c[0]["ancho"], c[0]["alto"]), (200, 200))

    def test_rechaza_rutas_peligrosas(self):
        (self.d / "fuera.jpg").write_bytes(M.jpeg())
        (self.d / "fuera.mp3").write_bytes(M.mp3())
        for cuerpo in ({"p": "../fuera.mp3"}, {"p": "/etc/passwd"}, {"p": "nada.mp3"}, {"p": self.rel, "caratula": "../fuera.jpg"}, {"p": self.rel, "caratula": "no.jpg"}, {}, None):
            r = self.llama(dict(cuerpo, simular=False) if cuerpo else cuerpo)
            self.assertFalse(r["ok"], cuerpo)
        self.assertFalse((self.lib / "_etiquetados").exists())

    def test_datos_invalidos_y_formato_sin_escritor(self):
        self.assertFalse(self.llama({"p": self.rel, "poner": {"isrc": "mal"}, "simular": False})["ok"])
        (self.lib / "x.ogg").write_bytes(b"OggS" + bytes(200))
        self.assertFalse(self.srv.AUDIO and self.llama({"p": "x.ogg", "simular": False})["ok"])
        self.assertFalse((self.lib / "_etiquetados").exists())


# ==================================================================================================== con ffmpeg real
@unittest.skipUnless(FFMPEG, "ffmpeg no está instalado")
class TestConFfmpeg(Base):
    def real(self, nombre, *args, seg=3):
        p = self.d / nombre
        r = subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=%d:r=44100" % seg, "-f", "lavfi", "-i", "anoisesrc=d=%d:c=pink:a=0.05:r=44100" % seg,
                            "-filter_complex", "amix=inputs=2:normalize=0", "-ac", "2", *args, str(p)], capture_output=True, text=True)
        if r.returncode:
            self.skipTest("ffmpeg no pudo crear %s: %s" % (nombre, r.stderr[:80]))
        return p

    def test_formatos_reales_conservan_el_audio(self):
        for nombre, args in (("r.mp3", ("-c:a", "libmp3lame", "-b:a", "128k")), ("r.flac", ("-c:a", "flac")), ("r.wav", ()), ("r.m4a", ("-c:a", "aac", "-b:a", "128k"))):
            src = self.real(nombre, *args)
            r, dst = self.aplicar(src, ffmpeg=FFMPEG)
            self.assertTrue(r["ok"], (nombre, r.get("error")))
            v = r["verificacion"]
            self.assertTrue(v["sha256_audio_igual"], nombre)
            self.assertTrue(v["md5_decodificado_igual"], nombre)            # decoded sound identical too
            self.assertEqual(v["etiquetas_inesperadas"], [], nombre)

    def test_m4a_campos_estandar_y_avisos_de_lo_que_no_cabe(self):
        src = self.real("r.m4a", "-c:a", "aac", "-b:a", "128k")
        plan = E.etiquetar(src, None, PONER, CRED, ffmpeg=FFMPEG, simular=True)["plan"]
        est = {x["campo"]: x["estado"] for x in plan["se_escribira"]}
        self.assertEqual((est["title"], est["composer"], est["lyrics"]), ("ok", "ok", "ok"))
        self.assertEqual((est["lyricist"], est["isrc"], est["personalizado:Proyecto"], est["creditos"]), ("plegado", "no_soportado", "no_soportado", "plegado"))
        r, dst = self.aplicar(src, ffmpeg=FFMPEG)
        t = self.clave(dst)
        self.assertEqual(t["©nam"]["valor"], "Mi canción")
        self.assertIn("Arreglos: Ana Pérez", t["©cmt"]["valor"])          # credits travel as text in the comment
        self.assertNotIn("©too", t)                                      # +bitexact: no encoder trace
        self.assertEqual(len(r["verificacion"]["errores"]), 0)

    def test_m4a_con_caratula_y_ffprobe_lee_lo_escrito(self):
        src = self.real("r.m4a", "-c:a", "aac")
        r, dst = self.aplicar(src, ffmpeg=FFMPEG, caratula=M.jpeg(64, 64))
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(len(I.inspeccionar(dst, ffprobe=False, ffmpeg=None)["incrustados"]["caratulas"]), 1)
        if FFPROBE:
            tags = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_format", "-of", "json", str(dst)], capture_output=True, text=True).stdout)["format"]["tags"]
            self.assertEqual(tags["title"], "Mi canción")
            self.assertEqual(tags["composer"], "Autora Demo")

    @unittest.skipUnless(FFPROBE, "ffprobe no está instalado")
    def test_ffprobe_ve_los_creditos_en_mp3_wav_y_flac(self):
        for nombre, args, clave in (("r.mp3", ("-c:a", "libmp3lame"), "CREDITS"), ("r.wav", (), "CREDITS"), ("r.flac", ("-c:a", "flac"), "CREDITS")):
            src = self.real(nombre, *args)
            r, dst = self.aplicar(src, ffmpeg=FFMPEG)
            self.assertTrue(r["ok"], (nombre, r.get("error")))
            j = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_format", "-of", "json", str(dst)], capture_output=True, text=True).stdout)["format"]["tags"]
            low = {k.lower(): v for k, v in j.items()}
            self.assertIn("Mezcla: Luis Gómez", low["credits"], nombre)
            self.assertEqual(low["title"], "Mi canción", nombre)


if __name__ == "__main__":
    unittest.main()
