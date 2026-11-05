# Music Manager

A local music-library manager for composers and producers (Windows 10/11 and Mac). Organize songs, lyrics, albums and mixtapes, normalize audio, and export clean files with your own metadata (title, artist, composer, copyright, lyrics, cover). Everything runs on your own computer: your music never leaves it.

(c) Frankie De Leonardis. You may use it, including for commercial work, but you may not sell the program or any part of it. See `LICENSE` and `AVISOS.md` (third-party notices).

Languages: English, Spanish, German, Portuguese.

## Get the apps

This repository builds the executables in the cloud (GitHub Actions); it contains nobody's data.

1. Open the **Actions** tab > **Construir** > **Run workflow**.
2. When it finishes (about 5-10 min), open the run and download the zips under **Artifacts** (Windows, Mac-Intel, Mac-AppleSilicon).
3. Each zip contains the app, its support folder and the PDF manual.

## Structure

`paquete/` (generic manager), `construir/` (PyInstaller build), `manual/` (PDF manual generator), `.github/workflows/construir.yml`.

Build locally: `pip install pyinstaller pillow reportlab` then `python construir/construir.py --paquete paquete --salida salida`.
