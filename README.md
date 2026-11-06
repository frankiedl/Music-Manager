# Music Manager

A local music-library manager for composers and producers (Windows 10/11 and Mac). Organize songs, lyrics, albums and mixtapes, normalize audio, and export clean files with your own metadata (title, artist, composer, copyright, lyrics, cover). Everything runs on your own computer: your music never leaves it.

(c) Frankie De Leonardis. You may use it, including for commercial work, but you may not sell the program or any part of it. See `LICENSE` and `AVISOS.md` (third-party notices).

Languages: English, Spanish, German, Portuguese.

## Screenshots

All screenshots use invented demo data.

![Home](docs/screenshots/01-home.png)
*Home: a summary of your catalog.*

![Album](docs/screenshots/02-album.png)
*An album page with its songs and cover.*

![Song](docs/screenshots/03-song.png)
*A song page: cover, versions, themes and lyrics.*

![Album mastering](docs/screenshots/04-album-mastering.png)
*Loudness measurement and normalization for an album.*

![Mixtape](docs/screenshots/05-mixtape.png)
*A mixtape with its cassette cover, ready to export as a ZIP of tagged MP3s with lyrics.*

![Settings](docs/screenshots/06-settings.png)
*Settings: library folder, artist name and language.*

## Get the apps

This repository builds the executables in the cloud (GitHub Actions); it contains nobody's data.

1. Open the **Actions** tab > **Construir** > **Run workflow**.
2. When it finishes (about 5-10 min), open the run and download the zips under **Artifacts** (Windows, Mac-Intel, Mac-AppleSilicon).
3. Each zip contains the app, its support folder and the PDF manual.

## Structure

`paquete/` (generic manager), `construir/` (PyInstaller build), `manual/` (PDF manual generator), `.github/workflows/construir.yml`.

For developers: see [ARCHITECTURE.md](ARCHITECTURE.md) (folders, data files, request flow, modules, translations, build). Code identifiers and folder names are in Spanish; comments and developer docs are in English.

Build locally: `pip install pyinstaller pillow reportlab` then `python construir/construir.py --paquete paquete --salida salida`.
