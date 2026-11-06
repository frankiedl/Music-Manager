"""«derechos» module server: reads an uploaded registration sheet (CSV or .xlsx) and returns its rows.
Standard library only (csv, zipfile, xml). Nothing is written: matching, preview and applying happen in the UI."""
import csv
import io
import re
import struct
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


def _ole_stream(b):
    """Return the Workbook stream of an old Excel (OLE2) file."""
    if b[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
        raise ValueError("no ole")
    sh, msh = struct.unpack_from("<HH", b, 30)
    ss, ms = 1 << sh, 1 << msh
    nfat, dirstart, _, cutoff, minifat, nminifat, difat, ndifat = struct.unpack_from("<8I", b, 44)
    sect = lambda n: b[512 + n * ss: 512 + (n + 1) * ss]
    ids = list(struct.unpack_from("<109I", b, 76))
    while difat < 0xFFFFFFFA and ndifat > 0:
        d = struct.unpack("<%dI" % (ss // 4), sect(difat))
        ids += d[:-1]
        difat, ndifat = d[-1], ndifat - 1
    fat = []
    for i in ids:
        if i < 0xFFFFFFFA:
            fat += struct.unpack("<%dI" % (ss // 4), sect(i))

    def cadena(n):
        out, vistos = [], 0
        while n < 0xFFFFFFFA and vistos < len(fat) + 1:
            out.append(sect(n))
            n, vistos = fat[n], vistos + 1
        return b"".join(out)

    dr = cadena(dirstart)
    ent = None
    for i in range(0, len(dr) - 127, 128):
        ln = struct.unpack_from("<H", dr, i + 64)[0]
        nom = dr[i:i + max(ln - 2, 0)].decode("utf-16le", "ignore")
        if nom in ("Workbook", "Book"):
            ent = (struct.unpack_from("<I", dr, i + 116)[0], struct.unpack_from("<I", dr, i + 120)[0])
        if i == 0:
            raiz = (struct.unpack_from("<I", dr, 116)[0], struct.unpack_from("<I", dr, 120)[0])
    if not ent:
        raise ValueError("no workbook")
    ini, tam = ent
    if tam >= cutoff:
        return cadena(ini)[:tam]
    mini = cadena(raiz[0])
    mf = struct.unpack("<%dI" % (len(cadena(minifat)) // 4), cadena(minifat))
    out, n = [], ini
    while n < 0xFFFFFFFA and len(out) < len(mf) + 1:
        out.append(mini[n * ms:(n + 1) * ms])
        n = mf[n]
    return b"".join(out)[:tam]


def _rk(v):
    if v & 2:
        x = v >> 2 if not v & 0x80000000 else (v >> 2) - (1 << 30)
        x = float(x)
    else:
        x = struct.unpack("<d", struct.pack("<Q", (v & 0xFFFFFFFC) << 32))[0]
    return x / 100 if v & 1 else x


def _num(x):
    return str(int(x)) if x == int(x) and abs(x) < 1e15 else repr(x)


def _sst(chunks):
    """Shared strings; chunks = the SST record and its CONTINUE records."""
    ci, pos, comp = 0, 8, []
    total = struct.unpack_from("<I", chunks[0], 4)[0]

    def leer_n(n):
        nonlocal ci, pos
        out = b""
        while n > 0 and ci < len(chunks):
            if pos >= len(chunks[ci]):
                ci, pos = ci + 1, 0
                continue
            t = chunks[ci][pos:pos + n]
            out, pos, n = out + t, pos + len(t), n - len(t)
        return out

    def cuerpo(n, ancho):
        # characters may cross a CONTINUE; each new chunk repeats the flag byte
        nonlocal ci, pos
        res = ""
        while n > 0 and ci < len(chunks):
            if pos >= len(chunks[ci]):
                ci, pos = ci + 1, 0
                if ci >= len(chunks):
                    break
                ancho = chunks[ci][0] & 1
                pos = 1
            disp = (len(chunks[ci]) - pos) // (2 if ancho else 1)
            k = min(n, disp)
            raw = chunks[ci][pos:pos + k * (2 if ancho else 1)]
            res += raw.decode("utf-16le" if ancho else "latin-1", "ignore")
            pos += len(raw)
            n -= k
        return res

    while len(comp) < total and ci < len(chunks):
        cab = leer_n(3)
        if len(cab) < 3:
            break
        n, fl = struct.unpack("<HB", cab)
        rich = struct.unpack("<H", leer_n(2))[0] if fl & 8 else 0
        ext = struct.unpack("<I", leer_n(4))[0] if fl & 4 else 0
        comp.append(cuerpo(n, fl & 1))
        leer_n(rich * 4 + ext)
    return comp


def leer_xls(b):
    d = _ole_stream(b)
    pos, comp, celdas, filas = 0, [], {}, []
    prof, hoja, fin, ult = 0, 0, False, None
    sst = None
    while pos + 4 <= len(d) and not fin:
        op, ln = struct.unpack_from("<HH", d, pos)
        r = d[pos + 4: pos + 4 + ln]
        pos += 4 + ln
        if op == 0x00FC:
            sst = [r]
            while pos + 4 <= len(d) and struct.unpack_from("<H", d, pos)[0] == 0x003C:
                l2 = struct.unpack_from("<H", d, pos + 2)[0]
                sst.append(d[pos + 4: pos + 4 + l2])
                pos += 4 + l2
            comp = _sst(sst)
            continue
        if op == 0x0809:
            prof += 1
            if hoja == 0 and struct.unpack_from("<H", r, 2)[0] == 0x0010:
                hoja = 1
            continue
        if op == 0x000A:
            prof -= 1
            if hoja == 1 and prof <= 0:
                fin = True
            continue
        if hoja != 1 or prof != 1:
            continue
        if op == 0x00FD and len(r) >= 10:
            f, c, _, i = struct.unpack_from("<HHHI", r)
            celdas[(f, c)] = comp[i] if i < len(comp) else ""
        elif op == 0x0203 and len(r) >= 14:
            f, c = struct.unpack_from("<HH", r)
            celdas[(f, c)] = _num(struct.unpack_from("<d", r, 6)[0])
        elif op == 0x027E and len(r) >= 10:
            f, c, _, v = struct.unpack_from("<HHHI", r)
            celdas[(f, c)] = _num(_rk(v))
        elif op == 0x00BD and len(r) >= 6:
            f, c0 = struct.unpack_from("<HH", r)
            for k in range((len(r) - 6) // 6):
                celdas[(f, c0 + k)] = _num(_rk(struct.unpack_from("<I", r, 4 + k * 6 + 2)[0]))
        elif op == 0x0204 and len(r) >= 8:
            f, c, _, n = struct.unpack_from("<HHHH", r)
            fl = r[8]
            celdas[(f, c)] = r[9:9 + n * (2 if fl & 1 else 1)].decode("utf-16le" if fl & 1 else "latin-1", "ignore")
        elif op == 0x0006 and len(r) >= 14:
            f, c = struct.unpack_from("<HH", r)
            if r[12:14] == bytes.fromhex("ffff") and r[6] == 0:
                ult = (f, c)
            else:
                celdas[(f, c)] = _num(struct.unpack_from("<d", r, 6)[0])
        elif op == 0x0207 and ult and len(r) >= 3:
            n, fl = struct.unpack_from("<HB", r)
            celdas[ult] = r[3:3 + n * (2 if fl & 1 else 1)].decode("utf-16le" if fl & 1 else "latin-1", "ignore")
    if not celdas:
        return []
    for f in range(min(max(k[0] for k in celdas) + 1, MAX_FILAS)):
        cs = [k[1] for k in celdas if k[0] == f]
        filas.append([celdas.get((f, c), "") for c in range(max(cs) + 1)] if cs else [])
    return filas


def leer(req, ctx):
    nombre = req.arg("nombre").lower()
    b = req.body(limite=LIMITE)
    if not b:
        return req.send({"ok": False, "error": "El archivo está vacío"})
    try:
        if nombre.endswith((".xlsx", ".xlsm")) or b[:2] == b"PK":
            filas = leer_xlsx(b)
        elif nombre.endswith(".xls") or b[:4] == bytes.fromhex("d0cf11e0"):
            filas = leer_xls(b)
        else:
            filas = leer_csv(b)
    except (struct.error, zipfile.BadZipFile, ET.ParseError, ValueError, KeyError, IndexError):
        return req.send({"ok": False, "error": "No es una hoja válida (CSV o Excel .xlsx)"})
    req.send({"ok": True, "filas": filas})


ROUTES = {"POST leer": leer}
