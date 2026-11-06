"""«derechos» module server: reads an uploaded registration sheet (CSV or .xlsx) and returns its rows.
Standard library only (csv, zipfile, xml). Nothing is written: matching, preview and applying happen in the UI."""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
LIMITE = 20 * 1024 * 1024
MAX_FILAS = 20000


def _texto(b):
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            t = b.decode(enc)
            if enc == "utf-16" and not b.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            return t
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1", "replace")


def leer_csv(b):
    t = _texto(b).lstrip("﻿")
    lineas = t.splitlines()
    sep = None
    if lineas and re.match(r"^sep=(.)\s*$", lineas[0], re.I):  # Excel's «sep=;» hint line
        sep = lineas[0][4]
        t = "\n".join(lineas[1:])
    if not sep:
        cab = re.sub(r'"[^"]*"', "", lineas[0] if lineas else "")
        sep = max([";", ",", "\t"], key=cab.count)
        if not cab.count(sep):
            sep = ","
    return [fila for _, fila in zip(range(MAX_FILAS), csv.reader(io.StringIO(t), delimiter=sep))]


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def leer_xlsx(b):
    z = zipfile.ZipFile(io.BytesIO(b))
    nombres = set(z.namelist())
    comp = []
    if "xl/sharedStrings.xml" in nombres:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            comp.append("".join(x.text or "" for x in si.iter("{%s}t" % NS["m"])))
    hoja = "xl/worksheets/sheet1.xml"
    try:  # the first sheet of the workbook, wherever it is
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = wb.find("m:sheets/m:sheet", NS).get("{%s}id" % NS["r"])
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for r in rels.findall("rel:Relationship", NS):
            if r.get("Id") == rid:
                tg = r.get("Target").lstrip("/")
                hoja = tg if tg.startswith("xl/") else "xl/" + tg
    except (KeyError, AttributeError, ET.ParseError):
        pass
    if hoja not in nombres:
        raise ValueError("El Excel no tiene ninguna hoja")
    filas = []
    for row in ET.fromstring(z.read(hoja)).iter("{%s}row" % NS["m"]):
        fila = []
        for i, c in enumerate(row.findall("m:c", NS)):
            j = _col(c.get("r")) if c.get("r") else len(fila)
            t, v = c.get("t"), c.find("m:v", NS)
            if t == "s" and v is not None:
                val = comp[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif t == "b" and v is not None:
                val = "TRUE" if v.text == "1" else "FALSE"
            else:
                val = v.text if v is not None and v.text else ""
                if t != "str" and re.fullmatch(r"-?\d+\.0+", val):
                    val = val.split(".")[0]
            while len(fila) < j:
                fila.append("")
            fila.append(val)
        filas.append(fila)
        if len(filas) >= MAX_FILAS:
            break
    return filas


def leer(req, ctx):
    nombre = req.arg("nombre").lower()
    b = req.body(limite=LIMITE)
    if not b:
        return req.send({"ok": False, "error": "El archivo está vacío"})
    try:
        if nombre.endswith((".xlsx", ".xlsm")) or b[:2] == b"PK":
            filas = leer_xlsx(b)
        elif nombre.endswith(".xls"):
            return req.send({"ok": False, "error": "Guarda la hoja como .xlsx o .csv"})
        else:
            filas = leer_csv(b)
    except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError, IndexError):
        return req.send({"ok": False, "error": "No es una hoja válida (CSV o Excel .xlsx)"})
    req.send({"ok": True, "filas": filas})


ROUTES = {"POST leer": leer}
