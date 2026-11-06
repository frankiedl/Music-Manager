"""Builds a mixtape package (shared by the personal manager and the distributable one).

ZIP:  Abrir.html (name depends on language) · Canciones/NN - Title.mp3 · Letras/NN - Title.txt · COPYRIGHT.txt · Portada.jpg (name depends on language)
HTML: a single file, no libraries or Internet; lyrics embedded as JSON; audio through relative paths
      (or base64 inside the HTML itself with the "everything in a single HTML" option).
The lyrics also go into the MP3 tag (USLT, unsynchronized lyrics)."""
import base64
import datetime
import html as _html
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

LIMITE_UNICO = 25 * 1024 * 1024   # size cap of the all-in-one HTML

# name of the HTML and of the folders depending on the mixtape language
NOMBRES = {
    "es": ("Abrir.html", "Canciones", "Letras"),
    "en": ("Open.html", "Songs", "Lyrics"),
    "de": ("Oeffnen.html", "Lieder", "Liedtexte"),
    "pt": ("Abrir.html", "Musicas", "Letras"),
}
# cover file name by language
PORTADA = {"es": "Portada.jpg", "pt": "Capa.jpg", "de": "Cover.jpg", "en": "Cover.jpg"}
# player texts and server messages (they do not go through the UI dictionary)
UI = {
    "es": dict(tracks="Pistas", lyrics="Letra", nolyrics="Esta pista no tiene letra.", play="Reproducir", pause="Pausa",
               prev="Anterior", next="Siguiente", vol="Volumen", seek="Posición", noaudio="No se pudo reproducir este audio.",
               peso="Pesa {mb} MB y el límite para un solo HTML es {lim} MB. Usa el ZIP normal (desmarca «Todo en un solo HTML»)."),
    "en": dict(tracks="Tracks", lyrics="Lyrics", nolyrics="This track has no lyrics.", play="Play", pause="Pause",
               prev="Previous", next="Next", vol="Volume", seek="Position", noaudio="This audio could not be played.",
               peso="It weighs {mb} MB and the limit for a single HTML is {lim} MB. Use the normal ZIP (untick “Everything in one HTML”)."),
    "de": dict(tracks="Titel", lyrics="Liedtext", nolyrics="Dieser Titel hat keinen Liedtext.", play="Abspielen", pause="Pause",
               prev="Zurück", next="Weiter", vol="Lautstärke", seek="Position", noaudio="Dieses Audio konnte nicht abgespielt werden.",
               peso="Es wiegt {mb} MB, das Limit für eine einzelne HTML-Datei ist {lim} MB. Nimm das normale ZIP (Haken bei „Alles in einer HTML“ entfernen)."),
    "pt": dict(tracks="Faixas", lyrics="Letra", nolyrics="Esta faixa não tem letra.", play="Tocar", pause="Pausar",
               prev="Anterior", next="Próxima", vol="Volume", seek="Posição", noaudio="Não foi possível tocar este áudio.",
               peso="Pesa {mb} MB e o limite para um único HTML é {lim} MB. Use o ZIP normal (desmarque «Tudo em um único HTML»)."),
}


ISO3 = {"es": "spa", "en": "eng", "de": "deu", "pt": "por"}


def poner_uslt(path, texto, lang):
    """Writes the lyrics as a USLT frame (unsynchronized lyrics) of the MP3's ID3v2.3 tag.
    ffmpeg can only store them as a TXXX named "USLT", which players do not recognize."""
    path = Path(path)
    b = path.read_bytes()
    if b[:3] != b"ID3" or b[3] != 3:
        raise RuntimeError("etiqueta ID3v2.3 no encontrada")
    tam = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
    cuerpo, resto = b[10:10 + tam], b[10 + tam:]
    frames, i = [], 0
    while i + 10 <= len(cuerpo) and cuerpo[i] != 0:
        n = int.from_bytes(cuerpo[i + 4:i + 8], "big")
        f = cuerpo[i:i + 10 + n]
        i += 10 + n
        d = f[10:]
        if f[:4] == b"TXXX" and d[:1] == b"\x01" and d[1:].decode("utf-16", "ignore").split("\x00")[0].lower() in ("uslt", "lyrics"):
            continue
        frames.append(f)
    t = texto.replace("\r\n", "\n").replace("\r", "\n")
    bom = b"\xff\xfe"
    datos = b"\x01" + ISO3.get(lang, "eng").encode("ascii") + bom + b"\x00\x00" + bom + t.encode("utf-16-le") + b"\x00\x00"
    frames.append(b"USLT" + len(datos).to_bytes(4, "big") + b"\x00\x00" + datos)
    nuevo = b"".join(frames)
    sz = len(nuevo)
    cab = b"ID3\x03\x00" + bytes([b[5] & 0x7F, (sz >> 21) & 0x7F, (sz >> 14) & 0x7F, (sz >> 7) & 0x7F, sz & 0x7F])
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(cab + nuevo + resto)
    tmp.replace(path)


def _json_seguro(obj):
    s = json.dumps(obj, ensure_ascii=False)
    for a, b in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        s = s.replace(a, b)
    return s


def html_reproductor(lang, nombre, artist, tracks, portada, audios=None):
    """tracks: [{n,title,file,lyrics,notice}]; portada (cover): relative path or data URI ('' if none);
    audios: list of base64 strings (all-in-one mode) or None."""
    plantilla = (Path(__file__).parent / "mixtape_plantilla.html").read_text(encoding="utf-8")
    ui = UI.get(lang, UI["en"])
    carpeta = NOMBRES.get(lang, NOMBRES["en"])[1]
    datos = {"lang": lang, "name": nombre, "artist": artist, "cover": portada, "dir": carpeta, "ui": {k: v for k, v in ui.items() if k != "peso"},
             "tracks": [{k: t[k] for k in ("n", "title", "file", "lyrics", "notice")} for t in tracks], "inline": audios is not None}
    bloques = ""
    if audios is not None:
        bloques = "".join(f'<script type="text/plain" id="a{i}">{b}</script>\n' for i, b in enumerate(audios))
    titulo = _html.escape(nombre + (f" — {artist}" if artist else ""))
    return (plantilla.replace("%%LANG%%", _html.escape(lang)).replace("%%TITLE%%", titulo)
            .replace("%%AUDIOS%%", bloques).replace("%%DATA%%", _json_seguro(datos)))


def _cuerpo_letra(txt, title):
    lineas = txt.split("\n")
    return "\n".join(lineas[1:]).strip() if lineas and lineas[0].strip().lower() == title.lower() else txt


def construir(job, *, ff, lang, tr, songs, items, base, name, nombre, artist, owner, con_copy, con_safe, letras, kbps,
              cover_bytes, root, safe_name, convertir, ruta_letra, onefile=False):
    """Builds the package. convertir(it) → Path of the already converted MP3; ruta_letra(song) → Path|None.
    Returns a dict with zip (deliverable), carpeta (folder) and mb."""
    nom_html, d_can, d_let = NOMBRES.get(lang, NOMBRES["en"])
    ui = UI.get(lang, UI["en"])
    base = Path(base)
    if onefile:
        folder = Path(tempfile.mkdtemp(prefix="mixtape_"))
    else:
        folder = base / name
        n = 2
        while folder.exists():
            folder = base / f"{name} ({n})"
            n += 1
        folder.mkdir(parents=True, exist_ok=True)
    try:
        (folder / d_can).mkdir(exist_ok=True)
        if letras:
            (folder / d_let).mkdir(exist_ok=True)
        cover = None
        if cover_bytes:
            cover = folder / PORTADA.get(lang, "Cover.jpg")
            cover.write_bytes(cover_bytes)
        job.update(total=len(items), done=0, estado="convirtiendo")
        avisos, pistas = [], []
        for i, it in enumerate(items, 1):
            song = songs.get(it.get("id"))
            if not song:
                raise RuntimeError(f"No encuentro el audio de la canción {i}")
            title = song["title"].replace("\n", " ")
            year = int(it.get("year") or song.get("anio") or datetime.date.today().year)
            notice = ""
            if con_copy:
                notice = f"© {year} {owner}"
                if con_safe:
                    notice += f" · {tr('Registrado en Safe Creative')}" + (f" {tr('nº')} {song['safe']}" if song.get("safe") else "")
            avisos.append((i, title, notice))
            stem = f"{i:02d} - {safe_name(title)}"
            out = folder / d_can / (stem + ".mp3")
            body = ""
            if letras and song.get("letra"):
                lf = ruta_letra(song)
                if lf and lf.is_file():
                    txt = lf.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").strip()
                    (folder / d_let / (stem + ".txt")).write_text(txt + ("\n\n" + notice if notice else "") + "\n", encoding="utf-8")
                    body = _cuerpo_letra(txt, title)
            meta = ["-metadata", f"title={title}", "-metadata", f"album={nombre}", "-metadata", f"track={i}/{len(items)}"]
            if artist:
                meta += ["-metadata", f"artist={artist}"]
            cached = convertir(it)
            cmd = [ff, "-y", "-i", str(cached)] + (["-i", str(cover)] if cover else [])
            cmd += (["-map", "0:a", "-map", "1:v", "-c:v", "copy", "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"] if cover else ["-vn"])
            cmd += ["-map_metadata", "-1", "-codec:a", "copy", "-id3v2_version", "3", *meta]
            if notice:
                cmd += ["-metadata", f"copyright={notice}", "-metadata", f"date={year}"]
            cmd.append(str(out))
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode or not out.exists():
                raise RuntimeError(f"ffmpeg falló con «{title}»: {r.stderr[-200:]}")
            if body:
                poner_uslt(out, body, lang)
            pistas.append({"n": i, "title": title, "file": out.name, "lyrics": (body + ("\n\n" + notice if notice and body else "")), "notice": notice})
            job["done"] = i
        head = nombre + (f" — {artist}" if artist else "")
        if con_copy:
            lines = [head, "", tr("Aviso de copyright"), "=" * len(tr("Aviso de copyright")), ""]
            lines += [f"{i:02d}. {t}  —  {n}" for i, t, n in avisos]
            lines += ["", tr("Todas las obras de este envío son de su titular. No se permite su uso, copia ni distribución sin su autorización."), ""]
            (folder / "COPYRIGHT.txt").write_text("\n".join(lines), encoding="utf-8")
        job["estado"] = "comprimiendo"
        root = Path(root)
        if onefile:
            audios = [base64.b64encode((folder / d_can / p["file"]).read_bytes()).decode("ascii") for p in pistas]
            portada = ("data:image/jpeg;base64," + base64.b64encode(cover_bytes).decode("ascii")) if cover_bytes else ""
            doc = html_reproductor(lang, nombre, artist, pistas, portada, audios)
            peso = len(doc.encode("utf-8"))
            if peso > LIMITE_UNICO:
                raise RuntimeError(ui["peso"].format(mb=round(peso / 1048576, 1), lim=25))
            destino = base / (name + ".html")
            k = 2
            while destino.exists():
                destino = base / f"{name} ({k}).html"
                k += 1
            base.mkdir(parents=True, exist_ok=True)
            destino.write_text(doc, encoding="utf-8")
            return dict(zip=destino.relative_to(root).as_posix(), carpeta=base.relative_to(root).as_posix(), mb=round(destino.stat().st_size / 1e6, 1))
        (folder / nom_html).write_text(html_reproductor(lang, nombre, artist, pistas, PORTADA.get(lang, "Cover.jpg") if cover_bytes else ""), encoding="utf-8")
        zp = base / (folder.name + ".zip")
        archivos = [f for f in folder.rglob("*") if f.is_file()]
        archivos.sort(key=lambda f: (f.parent != folder, f.name != nom_html, str(f.relative_to(folder)).lower()))
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in archivos:
                z.write(f, f.relative_to(folder).as_posix(), compress_type=zipfile.ZIP_STORED if f.suffix.lower() in (".mp3", ".jpg") else zipfile.ZIP_DEFLATED)
        return dict(zip=zp.relative_to(root).as_posix(), carpeta=folder.relative_to(root).as_posix(), mb=round(zp.stat().st_size / 1e6, 1))
    finally:
        if onefile:
            shutil.rmtree(folder, ignore_errors=True)
