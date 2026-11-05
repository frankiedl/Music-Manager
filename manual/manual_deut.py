# -*- coding: utf-8 -*-
"""Handbuch auf Deutsch (Manual_DEUT.pdf). Gleiche Struktur wie der spanische Inhalt in hacer_manual.py; Schaltflächen wie in der deutschen Oberfläche (Anrede: du)."""
C = "<font name='Courier'>%s</font>"
TEXTOS = dict(titulo="Musik-Manager", subtitulo="Benutzerhandbuch", version="Version {v} - für Windows 10, Windows 11 und Mac",
              lema="Deine Musik, geordnet, auf deinem eigenen Computer.<br/>Ohne Konten, ohne Internet, ohne Python zu installieren.",
              pie="Musik-Manager - Handbuch", pagina="Seite {n}")

CONTENIDO = [
    ("h1", "1. Was ist das?"),
    ("p", "Der <b>Musik-Manager</b> ist ein Programm, um deine eigene Musik auf deinem Computer zu ordnen: Songs, Songtexte, Versionen, Master, Stems, Cover und Videos. "
          "Du hörst sie im Browser, markierst Skizzen, führst Duplikate zusammen, bereitest Alben und MP3-Mixtapes mit ihren Songtexten vor und kannst mit Effekten mastern."),
    ("p", "Alles geschieht <b>auf deinem Computer</b>: Das Programm antwortet nur deinem eigenen Rechner (Adresse 127.0.0.1), hat keine Konten, sendet keine Statistiken, und deine Musik "
          "wird nirgendwohin kopiert; sie wird aus deinem Ordner gelesen. <b>Du musst weder Python noch sonst etwas installieren</b>."),
    ("p", "Der Ordner, den du erhältst, enthält nur Folgendes: die ausführbare Datei (" + C % "GestorMusica.exe" + " unter Windows, " + C % "GestorMusica.app" + " auf dem Mac), "
          "einen Hilfsordner (" + C % "_internal" + " unter Windows; nicht anfassen), einen leeren Ordner " + C % "datos" + " und dieses Handbuch."),

    ("h1", "2. Installation und erster Start"),
    ("h2", "Windows 10 und Windows 11"),
    ("li", ["Entpacke die Zip-Datei in einen eigenen Ordner, zum Beispiel <i>Dokumente\\GestorMusica</i>. Starte sie nicht aus dem Zip heraus und meide geschützte Ordner wie <i>Programme</i>.",
            "Doppelklicke auf <b>GestorMusica.exe</b>. Ein kleines Textfenster öffnet sich (es ist der Motor des Programms: <b>schließe es, um zu beenden</b>), und nach ein paar Sekunden öffnet sich dein Browser mit dem Manager.",
            "<b>Windows-Warnung (SmartScreen):</b> Weil das Programm nicht signiert ist, kann «Der Computer wurde durch Windows geschützt» erscheinen. Klicke auf <b>Weitere Informationen</b> und dann auf <b>Trotzdem ausführen</b>.",
            "Stammt das Zip aus dem Internet, kannst du vor dem Entpacken mit Rechtsklick auf das Zip <i>Eigenschaften</i> wählen und <b>Zulassen</b> ankreuzen.",
            "Blockiert dein Virenscanner es irrtümlich (das passiert manchmal bei unsignierten Programmen), füge den Ordner als Ausnahme hinzu.",
            "Die Windows-Firewall fragt eventuell, ob du den Zugriff erlaubst: Das Programm nutzt nur deinen eigenen Rechner; du kannst abbrechen, es funktioniert trotzdem."]),
    ("h2", "Mac (Intel und Apple Silicon)"),
    ("li", ["Es gibt zwei Versionen: <b>apple-silicon</b> (Macs mit M1, M2, M3, M4…) und <b>intel</b>. Weißt du nicht, welchen du hast: Apple-Menü > <i>Über diesen Mac</i>; steht dort Apple M…, nimm apple-silicon.",
            "Entpacke das Zip (Doppelklick) und verschiebe den Ordner zum Beispiel nach <i>Dokumente</i>. Deine Daten werden <b>neben der .app</b> gespeichert, lass sie also nicht im Ordner Programme "
            "(kann dort nicht geschrieben werden, wird <i>~/Library/Application Support/GestorMusica</i> verwendet).",
            "<b>Gatekeeper-Warnung:</b> Die Anwendung ist nicht von Apple signiert. Beim ersten Mal <b>Rechtsklick (oder Control-Klick) auf GestorMusica.app > Öffnen > Öffnen</b>. "
            "Das ist nur einmal nötig. Sagt macOS, sie sei «beschädigt», öffne das Terminal und gib ein (ersetze den Pfad durch deinen):"]),
    ("cod", "xattr -dr com.apple.quarantine /pfad/zu/GestorMusica.app"),
    ("li", ["Beim Öffnen siehst du kein eigenes Fenster: Der Browser öffnet sich mit dem Manager. Zum Beenden Rechtsklick auf das Dock-Symbol > <i>Beenden</i>."]),
    ("h2", "Beim ersten Mal"),
    ("p", "Ein Dialog erscheint, in dem du <b>den Ordner deiner Musikbibliothek wählst</b> (es kann ein neuer, leerer Ordner sein). Unter Windows fragt das Programm außerdem nach deinem Künstlernamen und dem Urheberrechtsinhaber (für Mixtapes); "
          "auf dem Mac kannst du sie später in den <b>Einstellungen</b> eintragen. Alles wird in " + C % "config.json" + " neben der ausführbaren Datei gespeichert. Danach öffnet sich der Browser unter " + C % "http://127.0.0.1:8765/" +
          ". Ist dieser Port belegt, werden die nächsten versucht, und das Textfenster zeigt die richtige Adresse."),

    ("h1", "3. Die Bibliothek und ihre Struktur"),
    ("p", "Der Manager versteht diese Struktur und legt sie selbst in deinem Ordner an:"),
    ("cod", "deine-bibliothek/\n  unreleased/            unveröffentlichte Songs\n     Mein Song/\n     Mein Projekt/       Ordner mit mehreren Songs = Projekt oder Album in Vorbereitung\n"
            "        01 Song A/\n  prereleased/           Vorab-Veröffentlichungen\n  published/\n     Singles/Meine Single/\n     Albumes/Mein Album/01 Song A/\n"
            "  ARTE/                  Cover, Bilder und Videos\n  MIXTAPES/              erzeugte Mixtapes"),
    ("p", "In jedem Song-Ordner:"),
    ("cod", "letra.txt      der Songtext (die erste Zeile kann der Titel sein)\nlose Audiodatei .wav .mp3 .m4a .flac .aif\nversiones/     Versionen und Mixe\nmaster/        der Master\n"
           "stems/         einzelne Spuren\nsesiones/ docs/ midi/ otros/"),
    ("li", ["Ordner, deren Name mit <b>_</b> oder <b>.</b> beginnt, werden ignoriert.",
            "Der Titel stammt aus dem Ordnernamen (eine vorangestellte Nummer wie «01 » wird entfernt).",
            "Du musst nichts von Hand anlegen: Nutze <b>+ Songs hinzufügen</b> oder den Bereich <b>Importieren</b>, und der Manager sortiert jede Datei.",
            "Verschiebst du einen Ordner von Hand, drücke <b>Aktualisieren</b>: Der Song wird an Songtext und Audio erkannt und behält seine Sterne, Notizen und Markierungen.",
            "Deine Arbeit im Manager (Sterne, Notizen, Namen, Skizzen…) liegt im Ordner <b>datos</b> neben der ausführbaren Datei; <b>nicht</b> in deiner Bibliothek."]),

    ("h1", "4. Die Bereiche"),
    ("h2", "Alben"),
    ("p", "Alben, Singles, Vorab-Veröffentlichungen und Projekte, mit ihrem Fortschritt. <b>+ Neues Album</b> legt eines an: Füge Songs hinzu, indem du sie aus der Liste links hineinziehst, sortiere sie durch Ziehen untereinander "
          "und entferne sie mit dem X (der Song wird weder gelöscht noch aus seinem Ordner verschoben). «Cover ändern» lädt ein Bild hoch oder wählt ein vorhandenes; «Zuschneiden» bereitet 1:1, 4:3, 3:4, 16:9 und 9:16 vor, ohne das Original anzufassen."),
    ("h2", "Songs"),
    ("p", "Alle Songs, mit Suche und Filtern (drücke einen Filter erneut, um ihn zu entfernen, oder <b>Filter löschen</b>). Bei jedem: Versionen abspielen, Sterne, Notizen, umbenennen "
          "(ändert nur den Namen im Manager, nicht deine Ordner) und <b>Duplikate zusammenführen</b> (mehrere mit Strg/Umschalt auswählen, Rechtsklick > Zusammenführen). "
          "Tastatur: Pfeil nach oben/unten wechselt den Song; die Leertaste spielt ab oder pausiert."),
    ("h2", "Songtexte"),
    ("p", "Songtexte lesen und durchsuchen, auch nach Thema."),
    ("h2", "Skizzen"),
    ("p", "Markiere Songtexte, die nicht zum Teilen gedacht sind (zieh sie auf die Schaltfläche <i>Skizzen</i>). Sie kommen nicht in Mixtapes."),
    ("h2", "Mixtape"),
    ("p", "Es braucht <b>ffmpeg</b> (Abschnitt 5). Erstelle beliebig viele Mixtapes mit Namen, Qualität (128, 192 oder 320 kbps) und Copyright-Vermerk. Zieh Songs auf das Mixtape oder nutze «Zu einem Mixtape hinzufügen…»: "
          "Seine MP3-Version entsteht in <i>MIXTAPES/_versiones</i> (deine Originalmusik bleibt unberührt). Es trägt ein Kassetten-Cover mit dem Titel und dem © mit deinem Namen und Jahr. "
          "<b>Senden</b> erstellt ein ZIP mit folgendem Inhalt: eine HTML-Datei (<i>Oeffnen.html</i>), die der Empfänger per Doppelklick öffnet – ohne Installation und ohne Internet – mit Cover, Titelliste, Player und dem Liedtext des laufenden Titels; der Ordner <i>Lieder</i> mit den MP3s (<i>NN - Titel.mp3</i>); der Ordner <i>Liedtexte</i> mit einer .txt-Datei pro Song; <i>COPYRIGHT.txt</i> und <i>Portada.jpg</i>. Der Liedtext steckt außerdem im Tag jeder MP3 (nicht synchronisierter Text). Die Namen der HTML-Datei und der Ordner richten sich nach der in den Einstellungen gewählten Sprache. Das Kästchen <b>Alles in einer HTML</b> packt das Audio in die HTML-Datei selbst (eine einzige Datei), nur für kleine Mixtapes: ab etwa 25 MB warnt der Manager und empfiehlt das normale ZIP."),
    ("h2", "Offen"),
    ("p", "Was pro Song oder Album fehlt: kein Songtext, kein Master, kein Cover usw."),
    ("h2", "Art und Video"),
    ("p", "Cover, Bilder und Clips jedes Songs oder Albums. Die Vorschaubilder liegen in <i>datos/thumbs</i>."),
    ("h2", "Status (innerhalb von Start)"),
    ("p", "Unter den Informationen auf Start siehst du «Status deiner Musik»: den Fortschritt deiner Musik: Songtext, Version, Stems, Master, Cover und veröffentlicht; was fehlt; und, wenn du sie aus einer CSV importierst, Plattform-Berichte (nach Monat, Plattform, Land, Song). "
          "Berichte werden auf deinem Computer gelesen. «Verbindungen» enthält einen optionalen Spotify-Konnektor, der nur den öffentlichen Katalog abfragt, wenn du ihn einschaltest."),
    ("h2", "Importieren (innerhalb der Einstellungen)"),
    ("p", "Es öffnet sich in den Einstellungen (das Zahnrad ⚙) unter «Meine Musik» mit «Musik aus anderen Ordnern importieren…». Es ist ein Assistent in 4 Schritten (Ordner wählen > Suchen > Prüfen > Kopieren), um Skizzen, Versionen, Stems, Live-Aufnahmen und DAW-Projekte aus beliebigen Ordnern zu ordnen. "
          "Er <b>kopiert</b> nach <i>unreleased/&lt;Titel&gt;</i>; er verschiebt oder löscht die Quelle nie und überschreibt nie (er hängt « (2)» an). Er erkennt Duplikate und gruppiert nach ähnlichem Titel. "
          "Jede Kopie wird in einem Protokoll festgehalten und kann rückgängig gemacht werden."),
    ("h2", "Einstellungen (das Zahnrad ⚙ neben «Meine Musik»)"),
    ("p", "Oben links, neben «Meine Musik». Hier änderst du den Bibliotheksordner (alles wird sofort neu gelesen), deinen Künstlernamen, den Urheberrechtsinhaber, die zusätzlichen Ordner, in denen nach Effekt-Plugins gesucht wird, mit der Schaltfläche <b>Plugins erneut scannen</b>, "
          "und die <b>Sprache</b> der Oberfläche. Hier findest du auch den Musikimport."),
    ("h2", "Mastering und Effekte"),
    ("p", "Es gibt drei Stellen: den Tab <b>Mastering</b> jedes Albums, die Schaltfläche <b>Mastern</b> auf der Seite jedes Songs und die Schaltfläche <b>Mastern</b> auf der Seite jedes Mixtapes."),
    ("p", "In jedem Album misst der Tab <b>Mastering</b> die Lautheit (LUFS), gleicht die Songs an (jeden einzeln oder relativ zum Album), wendet einen Spitzen-Limiter an, schneidet, blendet ein/aus und setzt Stille, "
          "schreibt Tags (ID3), fügt das Cover ein und exportiert ein ZIP, oder speichert die Master in der Bibliothek (<i>master/NN - Titel (máster).wav</i>; es überschreibt nie und fragt nach Bestätigung). "
          "Die Berechnung erfolgt in deinem Browser."),
    ("p", "Im Mastering gibt es ein Panel <b>Effekte</b>: eine Kette aus Effekten (eingebaute und deine VST3-Plugins), die vor dem Limiter angewendet wird, für alle Spuren gleich oder pro Spur verschieden. In einem Mixtape werden die Master in <i>MIXTAPES/_masters</i> gespeichert (nie in den Ordnern deiner Songs), und du kannst sie in diesem Mixtape verwenden oder zu den Originalversionen zurückkehren. "
          "Das Ergebnis lässt sich als neue Version speichern, ohne etwas zu überschreiben. Die Effekte nutzen die Bibliothek <b>pedalboard</b>, die <b>nicht enthalten ist</b> (Abschnitt 5)."),

    ("h1", "5. Optionale Programme: ffmpeg und pedalboard"),
    ("p", "Sie sind wegen ihrer Lizenzen nicht enthalten. Ohne sie funktioniert alles außer den MP3-Mixtapes (ffmpeg) und dem Effekt-Panel (pedalboard)."),
    ("h2", "ffmpeg (Mixtapes)"),
    ("li", ["<b>Windows:</b> Gib in PowerShell " + C % "winget install Gyan.FFmpeg" + " ein, oder lade ffmpeg von ffmpeg.org herunter und lege <b>ffmpeg.exe neben GestorMusica.exe</b>.",
            "<b>Mac:</b> Installiere Homebrew (brew.sh) und gib " + C % "brew install ffmpeg" + " ein; oder lege die Datei <b>ffmpeg</b> in den Ordner neben GestorMusica.app.",
            "Starte den Manager nach der Installation neu."]),
    ("h2", "pedalboard (Effekte)"),
    ("p", "pedalboard (Lizenz GPL-3.0) braucht ein normales Python auf dem Computer (3.9 bis 3.12, von python.org). Installiere es, öffne ein Terminal und gib " + C % "python -m pip install pedalboard" +
          " ein (auf dem Mac " + C % "python3 -m pip install pedalboard" + "). Danach nutze im Panel <b>Effekte</b> des Masterings «Plugin-Unterstützung installieren» oder gib bei Bedarf den Pfad dieses Pythons an (unter Windows meist "
          "<i>C:\\Users\\dein-benutzer\\AppData\\Local\\Programs\\Python\\Python312\\python.exe</i>; auf dem Mac <i>/usr/local/bin/python3</i> oder <i>/opt/homebrew/bin/python3</i>). "
          "Die automatische Installation installiert in dieses Python, nicht in die ausführbare Datei."),

    ("h1", "6. Sicherungen und Rückgängig"),
    ("li", ["Sichere <b>zwei Dinge</b>: deinen Bibliotheksordner und den Ordner <b>datos</b> zusammen mit <i>config.json</i> (sie liegen neben der ausführbaren Datei).",
            "Um das Programm auf einen anderen Computer zu übertragen: Kopiere den Programmordner mit <i>datos</i> und <i>config.json</i> und verweise in den Einstellungen auf die neue Bibliothek.",
            "Der Manager <b>löscht nie</b> deine Dateien. Wenn er etwas verschiebt (zusammenführen, eine Version verschieben, importieren), trägt er es in <i>datos/diario_movimientos.jsonl</i> ein, und es lässt sich rückgängig machen. "
            "Der Bereich Importieren hat sein eigenes Rückgängig. Für das allgemeine Protokoll öffne ein Terminal im Programmordner und gib ein:"]),
    ("cod", "Windows:  GestorMusica.exe --run-script deshacer.py            (nur Simulation)\n          GestorMusica.exe --run-script deshacer.py --apply    (macht rückgängig)\n"
            "Mac:      GestorMusica.app/Contents/MacOS/GestorMusica --run-script deshacer.py --apply"),
    ("li", ["Beim Aktualisieren auf eine neue Version ersetze den Ordner der ausführbaren Datei, behalte aber <i>datos</i> und <i>config.json</i>."]),

    ("h1", "7. Datenschutz und Sicherheit"),
    ("li", ["Der Server antwortet nur deinem eigenen Computer (127.0.0.1) und weist Anfragen ab, die nicht von seiner eigenen Seite kommen.",
            "Es gibt keine Konten, Statistiken oder Telemetrie. Deine Musik, Songtexte und Daten verlassen deinen Computer nie.",
            "Das Einzige, was das Internet nutzen kann, und nur auf deinen Wunsch: der optionale Spotify-Konnektor (öffentlicher Katalog) und die Installation von pedalboard mit pip.",
            "Das Token in <i>datos/agente.json</i> dient nur dazu, eine veröffentlichte Webseite mit deinem Programm zu koppeln; nutzt du das nicht, ignoriere es und gib es nicht weiter."]),

    ("h1", "8. Fehlerbehebung"),
    ("tabla", [["Problem", "Was tun"],
               ["Windows sagt «durch Windows geschützt»", "Weitere Informationen > Trotzdem ausführen (Abschnitt 2)."],
               ["Mac: «kann nicht geöffnet werden» oder «beschädigt»", "Rechtsklick > Öffnen; falls es bleibt, der xattr-Befehl aus Abschnitt 2."],
               ["Der Browser öffnet sich nicht", "Öffne die im Textfenster angezeigte Adresse von Hand (normalerweise http://127.0.0.1:8765/)."],
               ["«Port belegt»", "Der Manager probiert die nächsten Ports; nutze die angezeigte Adresse. Schließe alte Kopien."],
               ["Bibliothek leer oder veraltet", "Drücke Aktualisieren; prüfe den Ordner in den Einstellungen."],
               ["Ein Song erscheint nicht", "Prüfe, dass sein Ordner nicht mit _ oder . beginnt und dass er Audio oder Songtext hat."],
               ["Mixtapes: «Ich finde ffmpeg nicht»", "Installiere ffmpeg (Abschnitt 5) und starte den Manager neu."],
               ["Effekte: pedalboard nicht installiert", "Installiere ein Python und pedalboard und nutze «Plugin-Unterstützung installieren» im Effekt-Panel (Abschnitt 5)."],
               ["Mac: speichert keine Daten oder fragt nach Berechtigungen", "Verschiebe den Ordner nach Dokumente (nicht Programme) und erlaube den Ordnerzugriff, wenn macOS fragt."],
               ["Etwas Seltsames nach dem Aktualisieren", "Schließe das Programm, lösche datos/thumbs und öffne es erneut (es wird neu erzeugt). Lösche nicht den Rest von datos."],
               ["Ich will bei null anfangen", "Schließe das Programm und benenne den Ordner datos um; deine Musik bleibt unberührt."]]),
]
