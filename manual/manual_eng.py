# -*- coding: utf-8 -*-
"""Manual in English (Manual_ENG.pdf). Same structure as the Spanish content in hacer_manual.py; button names match the English interface."""
C = "<font name='Courier'>%s</font>"
TEXTOS = dict(titulo="Music Manager", subtitulo="User guide", version="Version {v} - for Windows 10, Windows 11 and Mac",
              lema="Your music, organized, on your own computer.<br/>No accounts, no internet, no need to install Python.",
              pie="Music Manager - User guide", pagina="Page {n}")

CONTENIDO = [
    ("h1", "1. What it is"),
    ("p", "The <b>Music Manager</b> is a program to organize your own music on your computer: songs, lyrics, versions, masters, stems, covers and videos. "
          "You listen to it in the browser, mark sketches, merge duplicates, prepare albums and MP3 mixtapes with their lyrics, and you can normalize their loudness."),
    ("p", "Everything happens <b>on your computer</b>: the program only answers your own machine (address 127.0.0.1), it has no accounts, sends no statistics and your music "
          "is not copied anywhere; it is read from your folder. <b>You do not need to install Python</b> or anything else."),
    ("p", "The folder you receive contains only this: the executable (" + C % "GestorMusica.exe" + " on Windows, " + C % "GestorMusica.app" + " on Mac), "
          "a support folder (" + C % "_internal" + " on Windows; do not touch it), an empty " + C % "datos" + " folder and this manual."),

    ("h1", "2. Installation and first start"),
    ("h2", "Windows 10 and Windows 11"),
    ("li", ["Unzip the file into a folder of your own, for example <i>Documents\\GestorMusica</i>. Do not run it from inside the zip and avoid protected folders such as <i>Program Files</i>.",
            "Double-click <b>GestorMusica.exe</b>. A small text window opens (it is the engine of the program: <b>close it to quit</b>) and after a few seconds your browser opens with the manager.",
            "<b>Windows warning (SmartScreen):</b> because the program is not signed, you may see \"Windows protected your PC\". Click <b>More info</b> and then <b>Run anyway</b>.",
            "If the zip comes from the internet, before unzipping you can right-click the zip, choose <i>Properties</i> and tick <b>Unblock</b>.",
            "If your antivirus blocks it by mistake (it sometimes happens with unsigned programs), add the folder as an exception.",
            "The Windows firewall may ask whether to allow access: the program only uses your own computer; you can cancel and it works the same."]),
    ("h2", "Mac (Intel and Apple Silicon)"),
    ("li", ["There are two versions: <b>apple-silicon</b> (M1, M2, M3, M4… Macs) and <b>intel</b>. If you do not know which you have: Apple menu > <i>About This Mac</i>; if it says Apple M…, use apple-silicon.",
            "Unzip (double-click) and move the folder to, for example, <i>Documents</i>. Your data is saved <b>next to the .app</b>, so do not leave it inside Applications "
            "(if it cannot be written there, <i>~/Library/Application Support/GestorMusica</i> is used).",
            "<b>Gatekeeper warning:</b> the application is not signed by Apple. The first time, <b>right-click (or Control-click) GestorMusica.app > Open > Open</b>. "
            "This is needed only once. If macOS says it is \"damaged\", open Terminal and type (change the path to yours):"]),
    ("cod", "xattr -dr com.apple.quarantine /path/to/GestorMusica.app"),
    ("li", ["When it opens you will not see a window of its own: the browser opens with the manager. To quit, right-click the Dock icon > <i>Quit</i>."]),
    ("h2", "The first time"),
    ("p", "A box appears to <b>choose your music library folder</b> (it can be a new, empty folder). On Windows the program also asks your artist name and the copyright holder (for mixtapes); "
          "on Mac you can set them later in <b>Settings</b>. Everything is saved in " + C % "config.json" + ", next to the executable. Then the browser opens at " + C % "http://127.0.0.1:8765/" +
          ". If that port is busy, the next ones are tried and the text window shows the right address."),

    ("h1", "3. The library and its structure"),
    ("p", "The manager understands this structure and creates it by itself inside your folder:"),
    ("cod", "your-library/\n  unreleased/            unpublished songs\n     My song/\n     My project/         folder with several songs = project or album in preparation\n"
            "        01 Song A/\n  prereleased/           pre-releases\n  published/\n     Singles/My single/\n     Albumes/My album/01 Song A/\n"
            "  ARTE/                  covers, images and videos\n  MIXTAPES/              generated mixtapes"),
    ("p", "Inside each song folder:"),
    ("cod", "letra.txt      the lyrics (the first line may be the title)\nloose audio    .wav .mp3 .m4a .flac .aif\nversiones/     versions and mixes\nmaster/        the master\n"
           "stems/         separate tracks\nsesiones/ docs/ midi/ otros/"),
    ("li", ["Folders whose name starts with <b>_</b> or <b>.</b> are ignored.",
            "The title comes from the folder name (a leading number such as \"01 \" is removed).",
            "You do not need to create it by hand: use <b>+ Add songs</b> or the <b>Import</b> section and the manager sorts each file.",
            "If you move a folder by hand, press <b>Refresh</b>: the song is recognized by its lyrics and its audio and keeps its stars, notes and marks.",
            "Your work in the manager (stars, notes, names, sketches…) lives in the <b>datos</b> folder, next to the executable; <b>not</b> inside your library."]),

    ("h1", "4. The sections"),
    ("h2", "Albums"),
    ("p", "Albums, singles, pre-releases and projects, with their progress. <b>+ New album</b> creates one: add songs by dragging them from the list on the left, reorder them by dragging them between each other "
          "and remove them with the X (the song is not deleted or moved from its folder). \"Change cover\" uploads an image or picks an existing one; \"Crop\" prepares 1:1, 4:3, 3:4, 16:9 and 9:16 without touching the original."),
    ("h2", "Songs"),
    ("p", "All the songs, with search and filters (press a filter again to remove it, or <b>Clear filters</b>). On each one: play versions, stars, notes, rename "
          "(it only changes the name in the manager, not your folders) and <b>merge duplicates</b> (select several with Ctrl/Shift, right-click > Merge). "
          "Keyboard: up/down arrows change song; the space bar plays or pauses."),
    ("h2", "Lyrics"),
    ("p", "Read and search inside the lyrics, also by theme."),
    ("h2", "Sketches"),
    ("p", "Mark lyrics that are not meant to be shared (drag them onto the <i>Sketches</i> button). They do not go into mixtapes."),
    ("h2", "Mixtape"),
    ("p", "It needs <b>ffmpeg</b> (section 5). Create as many mixtapes as you like with a name, quality (128, 192 or 320 kbps) and copyright notice. Drag songs onto the mixtape or use \"Add to a mixtape…\": "
          "its MP3 version is created in <i>MIXTAPES/_versiones</i> (your original music is not touched). It carries a cassette cover with the title and the © with your name and year. "
          "<b>Send</b> creates a ZIP containing: an HTML file (<i>Open.html</i>) that the recipient opens with a double click, with no installation and no internet connection, showing the cover, the track list, a player and the lyrics of the playing track; the <i>Songs</i> folder with the MP3s (<i>NN - Title.mp3</i>); the <i>Lyrics</i> folder with one .txt per song; <i>COPYRIGHT.txt</i> and <i>Portada.jpg</i>. The lyrics are also stored inside each MP3's tag (unsynchronised lyrics). The names of the HTML and the folders follow the language chosen in Settings. The <b>Everything in one HTML</b> box puts the audio inside the HTML itself (a single file), only for small mixtapes: above about 25 MB the manager warns you and recommends the normal ZIP."),
    ("h2", "Pending"),
    ("p", "What is missing per song or album: no lyrics, no master, no cover, etc."),
    ("h2", "Art and video"),
    ("p", "Covers, images and clips of each song or album. Thumbnails are saved in <i>datos/thumbs</i>."),
    ("h2", "Status (inside Home)"),
    ("p", "Below the Home information you will see \"Status of your music\": the progress of your music: lyrics, version, stems, master, cover and published; what is missing; and, if you import them from a CSV, platform reports (by month, platform, country, song). "
          "Reports are read on your computer. \"Connections\" includes an optional Spotify connector that only queries the public catalog if you turn it on."),
    ("h2", "Import (inside Settings)"),
    ("p", "It opens in Settings (the ⚙ wheel), under \"My music\", with \"Import music from other folders…\". It is a 4-step assistant (Choose folder > Search > Review > Copy) to organize sketches, versions, stems, live recordings and DAW projects from any folder. "
          "It <b>copies</b> to <i>unreleased/&lt;Title&gt;</i>; it never moves or deletes the source and never overwrites (it adds \" (2)\"). It detects duplicates and groups by similar title. "
          "Every copy is recorded in a journal and can be undone."),
    ("h2", "Settings (the ⚙ wheel next to \"My music\")"),
    ("p", "At the top left, next to \"My music\". Here you change the library folder (everything is read again at once), your artist name, the copyright holder and the interface <b>Language</b>. You will also find the music import here."),
    ("h2", "Mastering"),
    ("p", "There are three places: the <b>Mastering</b> tab of each album, the <b>Master</b> button on each song's page and the <b>Master</b> button on each mixtape's page."),
    ("p", "In each album, the <b>Mastering</b> tab measures the loudness (LUFS), evens out the songs (each one, or relative to the album), applies a peak limiter, trims, fades and silences, "
          "writes tags (ID3), adds the cover art and exports a ZIP, or saves the masters in the library (<i>master/NN - Title (master).wav</i>; it never overwrites and asks for confirmation). "
          "The calculation is done in your browser."),
    ("p", "In a mixtape, masters are saved in <i>MIXTAPES/_masters</i> (never in your song folders) and you can use them in that mixtape or go back to the original versions. "
          "The result can be saved as a new version, without overwriting anything."),

    ("h1", "5. Optional program: ffmpeg"),
    ("p", "It is not bundled because of its license. Without it everything works except MP3 mixtapes."),
    ("h2", "ffmpeg (mixtapes)"),
    ("li", ["<b>Windows:</b> in PowerShell type " + C % "winget install Gyan.FFmpeg" + ", or download ffmpeg from ffmpeg.org and leave <b>ffmpeg.exe next to GestorMusica.exe</b>.",
            "<b>Mac:</b> install Homebrew (brew.sh) and type " + C % "brew install ffmpeg" + "; or leave the <b>ffmpeg</b> file in the folder next to GestorMusica.app.",
            "Restart the manager after installing it."]),

    ("h1", "6. Backups and undo"),
    ("li", ["Back up <b>two things</b>: your library folder, and the <b>datos</b> folder together with <i>config.json</i> (they are next to the executable).",
            "To move the program to another computer: copy the program folder with <i>datos</i> and <i>config.json</i>, and in Settings point to the new library.",
            "The manager <b>never deletes</b> your files. When it moves something (merge, move a version, import) it notes it in <i>datos/diario_movimientos.jsonl</i>, and it can be undone. "
            "The Import section has its own undo. For the general journal, open a terminal in the program folder and type:"]),
    ("cod", "Windows:  GestorMusica.exe --run-script deshacer.py            (simulation only)\n          GestorMusica.exe --run-script deshacer.py --apply    (undoes)\n"
            "Mac:      GestorMusica.app/Contents/MacOS/GestorMusica --run-script deshacer.py --apply"),
    ("li", ["When updating to a new version, replace the executable folder but keep <i>datos</i> and <i>config.json</i>."]),

    ("h1", "7. Privacy and security"),
    ("li", ["The server only answers your own computer (127.0.0.1) and rejects requests that do not come from its own page.",
            "There are no accounts, statistics or telemetry. Your music, lyrics and data never leave your computer.",
            "The only things that may use the internet, and only if you ask: the optional Spotify connector (public catalog).",
            "The token in <i>datos/agente.json</i> is only for pairing a published web page with your program; if you do not use that, ignore it and do not share it."]),

    ("h1", "8. Troubleshooting"),
    ("tabla", [["Problem", "What to do"],
               ["Windows says \"protected your PC\"", "More info > Run anyway (section 2)."],
               ["Mac: \"cannot be opened\" or \"damaged\"", "Right-click > Open; if it persists, the xattr command in section 2."],
               ["The browser does not open", "Open by hand the address shown in the text window (normally http://127.0.0.1:8765/)."],
               ["\"Port busy\"", "The manager tries the next ports; use the address it shows. Close old copies."],
               ["Library empty or out of date", "Press Refresh; check the folder in Settings."],
               ["A song does not appear", "Check that its folder does not start with _ or . and that it has audio or lyrics."],
               ["Mixtapes: \"I can't find ffmpeg\"", "Install ffmpeg (section 5) and restart the manager."],
               ["Mac: it does not save data or asks for permissions", "Move the folder to Documents (not Applications) and grant folder access if macOS asks."],
               ["Something odd after updating", "Close the program, delete datos/thumbs and open it again (it is regenerated). Do not delete the rest of datos."],
               ["I want to start from scratch", "Close the program and rename the datos folder; your music is not touched."]]),
]
