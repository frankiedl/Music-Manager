#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera un PDF por idioma: Manual_ESP.pdf, Manual_ENG.pdf, Manual_DEUT.pdf, Manual_PORT.pdf. Uso: python hacer_manual.py [carpeta_salida] [ESP ENG DEUT PORT]
Solo necesita reportlab (pip install reportlab). El contenido está en CONTENIDO (abajo): edítalo y vuelve a ejecutar."""
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
IDIOMAS = [a.upper() for a in sys.argv[2:]] or ["ESP", "ENG", "DEUT", "PORT"]
sys.path.insert(0, str(Path(__file__).parent))
VERSION = "1.0"
ss = getSampleStyleSheet()
BASE = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=10, leading=14.2, spaceAfter=5)
H1 = ParagraphStyle("h1", parent=BASE, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceBefore=14, spaceAfter=7, textColor=colors.HexColor("#1b2a4a"))
H2 = ParagraphStyle("h2", parent=BASE, fontName="Helvetica-Bold", fontSize=12, leading=15, spaceBefore=9, spaceAfter=3, textColor=colors.HexColor("#2d4a7a"))
LI = ParagraphStyle("li", parent=BASE, leftIndent=14, bulletIndent=3, spaceAfter=2)
COD = ParagraphStyle("c", parent=BASE, fontName="Courier", fontSize=8.8, leading=11.5, backColor=colors.HexColor("#f0f2f6"), leftIndent=6, borderPadding=4, spaceAfter=8)
TIT = ParagraphStyle("t", parent=H1, fontSize=30, leading=36, spaceBefore=120, alignment=1)
SUB = ParagraphStyle("s", parent=BASE, fontSize=13, leading=18, alignment=1, textColor=colors.HexColor("#444444"))
C = "<font name='Courier'>%s</font>"

# Formato: ("h1", texto) ("h2", texto) ("p", texto) ("li", [items]) ("cod", texto) ("tabla", [[fila]...]) ("salto",)
CONTENIDO = [
    ("h1", "1. Qué es"),
    ("p", "El <b>Gestor de música</b> es un programa para ordenar tu propia música en tu ordenador: canciones, letras, versiones, másters, stems, portadas y vídeos. "
          "Lo escuchas en el navegador, marcas bocetos, fusionas duplicados, preparas álbumes y mixtapes en MP3 con sus letras, y puedes masterizar con efectos."),
    ("p", "Todo ocurre <b>en tu equipo</b>: el programa solo atiende a tu propio ordenador (dirección 127.0.0.1), no tiene cuentas, no envía estadísticas y tu música "
          "no se copia a ningún sitio; se lee desde tu carpeta. <b>No necesitas instalar Python</b> ni nada más."),
    ("p", "La carpeta que recibes contiene solo esto: el ejecutable (" + C % "GestorMusica.exe" + " en Windows, " + C % "GestorMusica.app" + " en Mac), "
          "una carpeta de soporte (" + C % "_internal" + " en Windows; no la toques), una carpeta " + C % "datos" + " vacía y este manual."),

    ("h1", "2. Instalación y primer arranque"),
    ("h2", "Windows 10 y Windows 11"),
    ("li", ["Descomprime el zip en una carpeta tuya, por ejemplo <i>Documentos\\GestorMusica</i>. No lo ejecutes desde dentro del zip y evita carpetas protegidas como <i>Archivos de programa</i>.",
            "Haz doble clic en <b>GestorMusica.exe</b>. Se abre una ventana de texto pequeña (es el motor del programa: <b>ciérrala para salir</b>) y a los pocos segundos se abre el navegador.",
            "<b>Aviso de Windows (SmartScreen):</b> como el programa no está firmado, puede salir «Windows protegió su PC». Pulsa <b>Más información</b> y luego <b>Ejecutar de todas formas</b>. "
            "Si el zip viene de internet, antes de descomprimir puedes hacer clic derecho en el zip, <i>Propiedades</i> y marcar <b>Desbloquear</b>.",
            "Si el antivirus lo bloquea por error (pasa a veces con programas sin firmar), añade la carpeta como excepción.",
            "El cortafuegos de Windows puede preguntar si permites el acceso: el programa solo usa tu propio equipo; puedes cancelar y funciona igual."]),
    ("h2", "Mac (Intel y Apple Silicon)"),
    ("li", ["Hay dos versiones: <b>apple-silicon</b> (Macs M1, M2, M3, M4…) e <b>intel</b>. Si no sabes cuál tienes: menú Apple > <i>Acerca de este Mac</i>; si dice «Chip Apple», usa apple-silicon.",
            "Descomprime el zip (doble clic) y mueve la carpeta a, por ejemplo, <i>Documentos</i>. Tus datos se guardan <b>junto al .app</b>, así que no lo dejes dentro de <i>Aplicaciones</i> "
            "(si no se puede escribir ahí, se usa <i>~/Library/Application Support/GestorMusica</i>).",
            "<b>Aviso de Gatekeeper:</b> la aplicación no está firmada por Apple. La primera vez, haz <b>clic derecho (o Control+clic) sobre GestorMusica.app > Abrir > Abrir</b>. "
            "Solo hace falta una vez. Si macOS dice que está «dañada», abre Terminal y escribe (cambia la ruta por la tuya):"]),
    ("cod", "xattr -dr com.apple.quarantine /ruta/a/GestorMusica.app"),
    ("li", ["Al abrirla no verás ventana propia: se abre el navegador con el gestor. Para salir, clic derecho en el icono del Dock > <i>Salir</i>."]),
    ("h2", "La primera vez"),
    ("p", "Aparece un cuadro para <b>elegir la carpeta de tu biblioteca</b> de música (puede ser una carpeta nueva y vacía). En Windows el programa además te pregunta, en la ventana de texto, "
          "tu nombre artístico y el titular del copyright (para los mixtapes); en Mac puedes ponerlos luego en <b>Ajustes</b>. Todo se guarda en " + C % "config.json" +
          ", junto al ejecutable. Después se abre el navegador en " + C % "http://127.0.0.1:8765/" + ". Si ese puerto está ocupado, prueba los siguientes y la ventana de texto muestra la dirección correcta."),

    ("h1", "3. La biblioteca y su estructura"),
    ("p", "El gestor entiende esta estructura y la crea solo dentro de tu carpeta:"),
    ("cod", "tu-biblioteca/\n  unreleased/            canciones sin publicar\n     Mi cancion/\n     Mi proyecto/        carpeta con varias canciones = proyecto o album en preparacion\n"
           "        01 Cancion A/\n  prereleased/           adelantos\n  published/\n     Singles/Mi single/\n     Albumes/Mi album/01 Cancion A/\n"
           "  ARTE/                  portadas, imagenes y videos\n  MIXTAPES/              mixtapes generados"),
    ("p", "Dentro de cada carpeta de canción:"),
    ("cod", "letra.txt      la letra (la primera linea puede ser el titulo)\naudio suelto   .wav .mp3 .m4a .flac .aif\nversiones/     versiones y mezclas\nmaster/        el master\n"
           "stems/         pistas separadas\nsesiones/ docs/ midi/ otros/"),
    ("li", ["Las carpetas cuyo nombre empieza por <b>_</b> o <b>.</b> se ignoran.",
            "El título sale del nombre de la carpeta (un número inicial como «01 » se quita).",
            "No hace falta crearlo a mano: usa <b>+ Añadir canciones</b> o la sección <b>Importar</b> y el gestor clasifica cada archivo.",
            "Si mueves una carpeta a mano, pulsa <b>Actualizar</b>: la canción se reconoce por su letra y su audio y conserva sus estrellas, notas y marcas.",
            "Tu trabajo en el gestor (estrellas, notas, nombres, bocetos…) vive en la carpeta <b>datos</b>, junto al ejecutable; <b>no</b> dentro de tu biblioteca."]),

    ("h1", "4. Las secciones"),
    ("h2", "Álbumes"),
    ("p", "Álbumes, singles, adelantos y proyectos, con su avance. <b>+ Nuevo álbum</b> crea uno: añade canciones arrastrándolas desde la lista de la izquierda, ordénalas arrastrándolas entre sí "
          "y quítalas con la X (la canción no se borra ni se mueve de su carpeta). «Cambiar portada» sube una imagen o elige otra ya existente; «Recortar» prepara 1:1, 4:3, 3:4, 16:9 y 9:16 sin tocar el original."),
    ("h2", "Canciones"),
    ("p", "Todas las canciones, con búsqueda y filtros (pulsa otra vez un filtro para quitarlo, o <b>Borrar filtros</b>). En cada una: reproducir versiones, estrellas, notas, renombrar "
          "(solo cambia el nombre en el gestor, no tus carpetas) y <b>fusionar duplicados</b> (selecciona varias con Ctrl/Mayús, clic derecho > Fusionar). "
          "Teclado: flechas arriba/abajo cambian de canción; la barra espaciadora reproduce o pausa."),
    ("h2", "Letras"),
    ("p", "Lee y busca dentro de las letras, también por temática."),
    ("h2", "Bocetos"),
    ("p", "Marca letras que no son para compartir (arrástralas al botón <i>Bocetos</i>). No entran en los mixtapes."),
    ("h2", "Mixtape"),
    ("p", "Necesita <b>ffmpeg</b> (sección 5). Crea los mixtapes que quieras con nombre, calidad (128, 192 o 320 kbps) y aviso de copyright. Arrastra canciones al mixtape o usa «Añadir a un mixtape…»: "
          "se crea su versión MP3 en <i>MIXTAPES/_versiones</i> (tu música original no se toca). Lleva portada de casete con el título y el © con tu nombre y año. "
          "<b>Enviar</b> crea un ZIP con este contenido: un archivo HTML (<i>Abrir.html</i>) que el destinatario abre con doble clic, sin instalar nada ni conexión a internet, con la portada, la lista de pistas, un reproductor y la letra de la pista que suena; la carpeta <i>Canciones</i> con los MP3 (<i>NN - Título.mp3</i>); la carpeta <i>Letras</i> con un .txt por canción; <i>COPYRIGHT.txt</i> y <i>Portada.jpg</i>. La letra va también dentro de la etiqueta de cada MP3 (letra no sincronizada). Los nombres del HTML y de las carpetas siguen el idioma elegido en Ajustes. La casilla <b>Todo en un solo HTML</b> mete el audio dentro del propio HTML (un único archivo), solo para mixtapes pequeños: si pasa de unos 25 MB, el gestor avisa y recomienda el ZIP normal."),
    ("h2", "Pendientes"),
    ("p", "Lo que falta por canción o álbum: sin letra, sin máster, sin portada, etc."),
    ("h2", "Arte y vídeo"),
    ("p", "Portadas, imágenes y clips de cada canción o álbum. Las miniaturas se guardan en <i>datos/thumbs</i>."),
    ("h2", "Estado (dentro de Inicio)"),
    ("p", "Debajo de la información de Inicio verás «Estado de tu música»: el avance de tu música: letra, versión, stems, máster, portada y publicada; qué falta; y, si los importas desde un CSV, informes de plataformas (por mes, plataforma, país, canción). "
          "Los informes se leen en tu equipo. «Conexiones» incluye un conector opcional de Spotify que solo consulta el catálogo público si tú lo activas."),
    ("h2", "Importar (dentro de Ajustes)"),
    ("p", "Se abre en Ajustes (la rueda ⚙), en «Mi música», con «Importar música de otras carpetas…». Es un asistente de 4 pasos (Elegir carpeta > Buscar > Revisar > Copiar) para organizar bocetos, versiones, stems, directos y proyectos de tu DAW desde cualquier carpeta. "
          "<b>Copia</b> a <i>unreleased/&lt;Título&gt;</i>; nunca mueve ni borra el origen ni sobrescribe (añade « (2)»). Detecta duplicados y agrupa por título parecido. "
          "Cada copia queda en un diario y puede deshacerse."),
    ("h2", "Ajustes (la rueda ⚙ junto a «Mi música»)"),
    ("p", "Arriba a la izquierda, junto a «Mi música». Aquí cambias la carpeta de la biblioteca (se vuelve a leer todo al momento), tu nombre artístico, el titular del copyright y las carpetas extra donde buscar plugins de efectos, con el botón <b>Volver a escanear plugins</b>. También encontrarás aquí la importación de música."),
    ("h2", "Masterización y efectos"),
    ("p", "Hay tres sitios: la pestaña <b>Masterización</b> de cada álbum, el botón <b>Masterizar</b> en la ficha de cada canción y el botón <b>Masterizar</b> en la página de cada mixtape."),
    ("p", "En cada álbum, la pestaña <b>Masterización</b> mide el volumen (LUFS), iguala las canciones (cada una, o relativo al álbum), aplica limitador de picos, recortes, fundidos y silencios, "
          "escribe etiquetas (ID3), añade la carátula y exporta un ZIP, o guarda los másters en la biblioteca (<i>master/NN - Título (máster).wav</i>; nunca sobrescribe y pide confirmación). "
          "El cálculo se hace en tu navegador."),
    ("p", "Dentro de la masterización hay un panel <b>Efectos</b>: una cadena de efectos (internos y tus plugins VST3) que se aplica antes del limitador, igual para todas las pistas o distinta por pista. En un mixtape, los másters se guardan en <i>MIXTAPES/_masters</i> (nunca en las carpetas de tus canciones) y puedes usarlos en ese mixtape o volver a las versiones originales. "
          "Se puede guardar el resultado como versión nueva, sin sobrescribir nada. Los efectos usan la librería <b>pedalboard</b>, que <b>no viene incluida</b> (sección 5)."),

    ("h1", "5. Programas opcionales: ffmpeg y pedalboard"),
    ("p", "No van dentro del programa por sus licencias. Sin ellos todo funciona salvo los mixtapes MP3 (ffmpeg) y el panel de efectos (pedalboard)."),
    ("h2", "ffmpeg (mixtapes)"),
    ("li", ["<b>Windows:</b> en PowerShell escribe " + C % "winget install Gyan.FFmpeg" + ", o descarga ffmpeg de ffmpeg.org y deja <b>ffmpeg.exe junto a GestorMusica.exe</b>.",
            "<b>Mac:</b> instala Homebrew (brew.sh) y escribe " + C % "brew install ffmpeg" + "; o deja el archivo <b>ffmpeg</b> en la carpeta junto a GestorMusica.app.",
            "Reinicia el gestor después de instalarlo."]),
    ("h2", "pedalboard (efectos)"),
    ("p", "pedalboard (licencia GPL-3.0) necesita un Python normal instalado en el equipo (3.9 a 3.12, de python.org). Instálalo, abre una terminal y escribe " + C % "python -m pip install pedalboard" +
          " (en Mac " + C % "python3 -m pip install pedalboard" + "). Después, en el panel <b>Efectos</b> de la masterización, usa «Instalar soporte de plugins» o, si hace falta, indica la ruta de ese Python (en Windows suele ser "
          "<i>C:\\Users\\tu-usuario\\AppData\\Local\\Programs\\Python\\Python312\\python.exe</i>; en Mac, <i>/usr/local/bin/python3</i> o <i>/opt/homebrew/bin/python3</i>). "
          "La instalación automática instala en ese Python, no en el ejecutable."),

    ("h1", "6. Copias de seguridad y deshacer"),
    ("li", ["Haz copia de seguridad de <b>dos cosas</b>: tu carpeta de biblioteca, y la carpeta <b>datos</b> junto con <i>config.json</i> (están junto al ejecutable).",
            "Para pasar el programa a otro ordenador: copia la carpeta del programa con <i>datos</i> y <i>config.json</i>, y en Ajustes apunta a la biblioteca nueva.",
            "El gestor <b>nunca borra</b> tus archivos. Cuando mueve algo (fusionar, mover una versión, importar) lo anota en <i>datos/diario_movimientos.jsonl</i>, y se puede deshacer. "
            "La sección Importar tiene su propio deshacer. Para el diario general, abre una terminal en la carpeta del programa y escribe:"]),
    ("cod", "Windows:  GestorMusica.exe --run-script deshacer.py            (solo simula)\n          GestorMusica.exe --run-script deshacer.py --apply    (deshace)\n"
            "Mac:      GestorMusica.app/Contents/MacOS/GestorMusica --run-script deshacer.py --apply"),
    ("li", ["Al actualizar a una versión nueva, sustituye la carpeta del ejecutable pero conserva <i>datos</i> y <i>config.json</i>."]),

    ("h1", "7. Privacidad y seguridad"),
    ("li", ["El servidor solo atiende a tu propio equipo (127.0.0.1) y rechaza peticiones que no vengan de su propia página.",
            "No hay cuentas, estadísticas ni telemetría. Tu música, letras y datos no salen de tu equipo.",
            "Lo único que puede usar internet, y solo si tú lo pides: el conector opcional de Spotify (catálogo público) y la instalación de pedalboard con pip.",
            "El token de <i>datos/agente.json</i> sirve solo para emparejar una web publicada con tu programa; si no la usas, ignóralo y no lo compartas."]),

    ("h1", "8. Solución de problemas"),
    ("tabla", [["Problema", "Qué hacer"],
               ["Windows dice «protegió su PC»", "Más información > Ejecutar de todas formas (sección 2)."],
               ["Mac: «no se puede abrir» o «dañada»", "Clic derecho > Abrir; si persiste, el comando xattr de la sección 2."],
               ["El navegador no se abre", "Abre a mano la dirección de la ventana de texto (normalmente http://127.0.0.1:8765/)."],
               ["«Puerto ocupado»", "El gestor prueba los siguientes puertos; usa la dirección que muestra. Cierra copias antiguas."],
               ["Biblioteca vacía o desactualizada", "Pulsa Actualizar; comprueba la carpeta en Ajustes."],
               ["Una canción no aparece", "Revisa que su carpeta no empiece por _ o . y que tenga audio o letra."],
               ["Mixtapes: «No encuentro ffmpeg»", "Instala ffmpeg (sección 5) y reinicia el gestor."],
               ["Efectos: pedalboard no instalado", "Instala un Python y pedalboard, y usa «Instalar soporte de plugins» en el panel de efectos (sección 5)."],
               ["Mac: no guarda datos o pide permisos", "Mueve la carpeta a Documentos (no a Aplicaciones) y concede el acceso a carpetas si macOS lo pide."],
               ["Algo raro tras actualizar", "Cierra el programa, borra datos/thumbs y ábrelo de nuevo (se regenera). No borres el resto de datos."],
               ["Quiero empezar de cero", "Cierra el programa y renombra la carpeta datos; tu música no se toca."]]),

]


TEXTOS_ESP = dict(titulo="Gestor de música", subtitulo="Manual de uso", version="Versión {v} - para Windows 10, Windows 11 y Mac",
                  lema="Tu música, ordenada, en tu propio equipo.<br/>Sin cuentas, sin internet, sin instalar Python.", pie="Gestor de música - Manual",
                  pagina="Página {n}", problema="Problema", que_hacer="Qué hacer")


def construir(codigo, textos, contenido):
    destino = SALIDA / f"Manual_{codigo}.pdf"

    def pie(c, doc):
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(2 * cm, 1.2 * cm, textos["pie"])
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, textos["pagina"].format(n=doc.page))
        c.restoreState()

    doc = BaseDocTemplate(str(destino), pagesize=A4, title=textos["pie"], author=textos["titulo"], leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")], onPage=pie)])
    st = [Paragraph(textos["titulo"], TIT), Paragraph(textos["subtitulo"], SUB), Spacer(1, 10),
          Paragraph(textos["version"].format(v=VERSION), SUB), Spacer(1, 30), Paragraph(textos["lema"], SUB), PageBreak()]
    for it in contenido:
        k = it[0]
        if k in ("h1", "h2", "p"):
            st.append(Paragraph(it[1], {"h1": H1, "h2": H2, "p": BASE}[k]))
        elif k == "li":
            st += [Paragraph(x, LI, bulletText="•") for x in it[1]] + [Spacer(1, 4)]
        elif k == "cod":
            st.append(Preformatted(it[1], COD))
        elif k == "tabla":
            rows = [[Paragraph(f"<b>{c}</b>" if i == 0 else c, BASE) for c in r] for i, r in enumerate(it[1])]
            t = Table(rows, colWidths=[6 * cm, doc.width - 6 * cm], repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe6f2")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b5bccb")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            st += [t, Spacer(1, 6)]
        elif k == "salto":
            st.append(PageBreak())
    doc.build(st)
    print("Manual:", destino)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    for cod in IDIOMAS:
        if cod == "ESP":
            construir("ESP", TEXTOS_ESP, CONTENIDO)
        else:
            m = __import__("manual_" + cod.lower())
            construir(cod, m.TEXTOS, m.CONTENIDO)


if __name__ == "__main__":
    main()
