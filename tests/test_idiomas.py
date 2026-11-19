"""Guards the project rule «every new UI string goes into the dictionaries» for the Huella inspection / tagging feature.

    python3 -m unittest discover -s tests -v

Checks: the dictionaries are valid JSON and sorted, their patterns keep the same placeholders in every language, and EVERY message the
server writes (warnings, errors, trait descriptions of _core/inspeccion.py, senal.py and escribir_tags.py) has a translation in en/de/pt.
It does not check the texts written in huella/modulo.js (the browser run of that is described in huella/NOTAS.md).
"""
import ast
import json
import re
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "paquete" / "modulos" / "_core"
IDIOMAS = CORE / "idiomas"
LANGS = ("en", "de", "pt")


def _mensajes():
    """Every literal message the server code builds (aviso(), _aviso(), fallo(), «mensaje»/«descripcion»/«error» keys, validation errors)."""
    out = []
    for f in ("inspeccion.py", "senal.py", "escribir_tags.py"):
        for n in ast.walk(ast.parse((CORE / f).read_text(encoding="utf-8"))):
            m = None
            if isinstance(n, ast.Call):
                name = getattr(n.func, "attr", getattr(n.func, "id", ""))
                a = n.args
                if name == "aviso" and len(a) >= 3:
                    m = a[2]
                elif name == "_aviso" and len(a) >= 4:
                    m = a[3]
                elif name == "fallo" and len(a) >= 2:
                    m = a[1]
                elif name == "append" and isinstance(getattr(n.func, "value", None), ast.Name) and n.func.value.id in ("err", "errores") and a:
                    m = a[0]
            elif isinstance(n, ast.Dict):
                ks = [k.value if isinstance(k, ast.Constant) else None for k in n.keys]
                for k in ("mensaje", "descripcion", "error"):
                    if k in ks:
                        m = n.values[ks.index(k)]
            if m is None:
                continue
            try:
                s = ast.literal_eval(m) if isinstance(m, ast.Constant) else (ast.literal_eval(m.left) if isinstance(m, ast.BinOp) else None)
            except (ValueError, SyntaxError):
                s = None
            if s and not s.endswith(": "):                      # «…: » + a runtime list: covered by its own «{a}» pattern
                out.append(s)
    return list(dict.fromkeys(out))


def _textos_interfaz():
    """Static texts of the new block of huella/modulo.js: text between tags, placeholder/title/aria-label, labels of the lists, ask() and toast()."""
    js = (CORE.parent / "huella" / "modulo.js").read_text(encoding="utf-8")
    blk = js[js.index("/* ================= Inspección y etiquetado"):js.index("GM.register({id:ID")]
    t = set(m.group(1).strip() for m in re.finditer(r">([^<>`$\n{}]{2,}?)<", blk))
    t |= set(m.group(1).strip() for m in re.finditer(r'(?:placeholder|title|aria-label)="([^"$]+)"', blk))
    for m in re.finditer(r"GM\.ui\.ask\('([^']+)','([^']+)','([^']+)'", blk):
        t |= set(m.groups())
    t |= set(m.group(1) for m in re.finditer(r"GM\.ui\.toast\('([^']+)'", blk))
    t |= set(m.group(2) for m in re.finditer(r"\['(\w+)','([^']+)'\]", blk))
    t |= set(x for m in re.finditer(r"\w+:\['([^']+)','([^']+)'\]", blk) for x in m.groups())
    cam = blk[blk.index("const CAMPO="):blk.index("const campoTxt")]
    t |= set(m.group(1) for m in re.finditer(r"\w+:'([^']+)'(?=[,}])", cam))
    tecnico = {"OK", "sha256_audio", "_etiquetados/", "diario_movimientos.jsonl", "hashes.json", "ISRC", "Copyright", ":", ","}
    # fragments that end in «: » are completed at run time (toast('Copia creada: '+ruta)): their full text is covered by a «{a}» pattern (see DINAMICOS)
    return sorted(x for x in t if re.search(r"[A-Za-zÀ-ÿ]{2}", x) and not re.search(r"[=()\[\]]|\.join|E\(", x) and x not in tecnico and not x.endswith(": "))


DINAMICOS = ["OK · Con avisos (2)", "Atención · 1 problema de integridad", "Atención · 3 problemas de integridad", "+1.8 dB sobre el umbral", "4.2 dB bajo el umbral",
             "+2 picos sobre el umbral", "1 pico bajo el umbral", "1 pico", "5 picos", "≥ 3 picos", "cerca de 15350 Hz", "a 19000 Hz · persistencia 100 %",
             "no cuenta: su nivel (-118.4 dBFS) está por debajo del mínimo (-85 dBFS)", "no cuenta: aparece en el 40 % del tiempo (mínimo 70 %)",
             "8 etiquetas quitadas · 15 escritas", "Campo propio: Proyecto", "69 caracteres", "Copia creada: _etiquetados/tema.wav", "Carátula (APIC)",
             "forma parte del bloque «RIFF bext»: se conserva o se quita entero"]


def _regex(es):
    partes = re.split(r"\{(\w+)\}", es)
    return re.compile("^" + "".join(r"([\s\S]+?)" if i % 2 else re.escape(p) for i, p in enumerate(partes)) + "$")


class TestDiccionarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.D = {l: json.loads((IDIOMAS / (l + ".json")).read_text(encoding="utf-8")) for l in ("es",) + LANGS}

    def test_validos_y_ordenados(self):
        for l, d in self.D.items():
            self.assertEqual(set(d), {"exactas", "patrones"}, l)
            ex = list(d["exactas"])
            self.assertEqual(ex, sorted(ex), "las claves «exactas» van ordenadas (%s)" % l)
            self.assertTrue(all(isinstance(v, str) and v for v in d["exactas"].values()), l)

    def test_los_patrones_no_inventan_marcadores(self):
        """A translation may drop a marker (e.g. the plural suffix «{d}» does not exist in English) but never add one the Spanish text lacks."""
        for l in LANGS:
            for es, tr in self.D[l]["patrones"]:
                self.assertLessEqual(set(re.findall(r"\{(\w+)\}", tr)), set(re.findall(r"\{(\w+)\}", es)), (l, es))

    def _cubierto(self, l, t):
        d = self.D[l]
        return t in d["exactas"] or any(_regex(es).match(t) for es, _ in d["patrones"])

    def test_los_textos_de_la_interfaz_estan_traducidos(self):
        textos = _textos_interfaz()
        self.assertGreater(len(textos), 100, "la extracción de textos de modulo.js debería encontrar más de 100")
        for l in LANGS:
            falta = [t for t in textos if not self._cubierto(l, t)]
            self.assertEqual(falta, [], "textos de huella/modulo.js sin traducir al «%s»: añádelos a idiomas/%s.json" % (l, l))

    def test_los_textos_con_numeros_tienen_patron(self):
        for l in LANGS:
            falta = [t for t in DINAMICOS if not self._cubierto(l, t)]
            self.assertEqual(falta, [], l)
            for t in DINAMICOS:                      # and the translation is not the Spanish source (except words that are the same, e.g. «picos» in Portuguese)
                if l != "pt":
                    self.assertNotEqual(self._traducir(l, t), t, (l, t))

    def _traducir(self, l, t):
        d = self.D[l]
        if t in d["exactas"]:
            return d["exactas"][t]
        for es, tr in d["patrones"]:
            m = _regex(es).match(t)
            if m:
                nombres = re.findall(r"\{(\w+)\}", es)
                for n, v in zip(nombres, m.groups()):
                    tr = tr.replace("{%s}" % n, v)
                return tr
        return t

    def test_cada_mensaje_del_servidor_esta_traducido(self):
        msgs = _mensajes()
        self.assertGreater(len(msgs), 60)
        for l in LANGS:
            pats = [_regex(es) for es, _ in self.D[l]["patrones"]]
            ex = self.D[l]["exactas"]
            falta = []
            for m in msgs:
                t = re.sub(r"%(\.\d+)?[sdrf]", "X", m)
                if re.match(r"^(recorrido_python|ffprobe_fallo)", t) or t == "X: X":     # technical lines, never shown as prose
                    continue
                if t not in ex and not any(p.match(t) for p in pats):
                    falta.append(m)
            self.assertEqual(falta, [], "mensajes del servidor sin traducir al «%s»: añádelos a idiomas/%s.json" % (l, l))


if __name__ == "__main__":
    unittest.main()
