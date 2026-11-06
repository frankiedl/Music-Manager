# «Importar» module (import) — NOTES

**Status: originally written without an end-to-end test** (the usage limit ran out before the browser was opened); a later test round is described under «Tests done» below.

## What it does
4-step wizard (Choose folder → Scan → Review → Copy). It reads the source read-only and COPIES into `ctx.root/unreleased/<Title>/…`. It never moves or deletes the source and never overwrites (appends « (2)»).

Routes (`servidor.py`): `GET carpetas?ruta=`, `POST escanear`, `GET estado?job=`, `GET propuesta?job=`, `POST presupuesto`, `POST copiar`, `POST cancelar?job=`, `GET diario`, `POST deshacer`, `GET info`.

## Targets
`versiones/` · `master/` · `stems/` · `versiones/directos/` · `versiones/bocetos/` (inside versiones so the manager recognizes them) · `otros/tomas/` · `sesiones/<DAW>/…` · `docs/` · `midi/` · `arte/` · `video/` · `letra.txt` (the first .txt/.md lyrics file; the others go to docs). Audio in formats the manager does not read (ogg, opus…) goes to `otros/audio/`. Sketches are marked with `GM.ui.setDraft` when «Actualizar la biblioteca» (refresh the library) is pressed.

## Heuristics (and limits)
- Title: suffixes are removed (mix, master, final, v2, demo, bounce, 24bit, dates, «(2)»…). A lone trailing number is NOT removed («Canción 2» ≠ «Canción 1»). Merge by similarity ≥ 88 % only if the digits match.
- Audio category: master > stem > live > duration ≥ 15 min (live) > take > sketch > mix/final > < 30 s (sketch) > .m4a/.amr (sketch) > version. Exact duration only for WAV; for mp3/m4a it is estimated (≈) from bytes/second.
- DAW projects: by extension; `.logicx/.logic/.band` are packages. A folder is a «project» if it has a single session name and (typical subfolders Samples/Backup/Freeze… or a «… Project» name or ≤ 8 subfolders, the latter not at the root). Otherwise each session is «loose» (only its file). Inside a project only Bounces/Exports/Stems/etc. are listed; the rest is «internal» (counted, not listed).
- Duplicates: same name and size (>100 KB, audio) → unchecked; no hash, so it may be wrong.
- Folders with ≥ 60 audio files < 3 MB → «samples?», excluded by default.
- A full session doubles the space if its bounces are also imported as versions.
- Symlinks and junctions are not followed; the library itself is skipped if it is inside the source.

## Copy and verification
4 MB blocks to `name.importando`, `fsync`, size comparison and full SHA-256 (source read during the copy, target re-read); above 2 GB (`GESTOR_IMPORTAR_LIMITE_COMPLETO` for tests) verification is by sampling (4 MB start + 4 MB end + 32 blocks of 1 MB). The date is preserved. Locked files: 3 attempts, then skipped and counted. Windows long paths with the `\\?\` prefix. Journal in `ctx.datos/diario.jsonl`. «Deshacer» (undo) deletes only journal files whose size and fingerprint match, and rmdirs empty folders created by that import.

## Tests done (Windows, invented source, own package)
API + browser: folder browser with breadcrumbs, scan (DAW: Ableton with folder, loose FL/Reaper, Logic package; bounces, stems, live takes, voice memos, MIDI, lyrics, images, accents/emoji, path > 260), editing in the review (rename, category, move, exclude, merge), space budget, copy with verification (full and by sampling), source identical before/after (size, date, md5), recognition by the manager after «Actualizar» and sketches marked, undo (keeps a modified file), cancel halfway (no `.importando` leftovers), locked file (skipped and reported), console without errors.
**Not tested:** Mac/Linux, disks of hundreds of GB, symlinks (could not create them), resuming after the manager is closed halfway, pure browser variant. Polling is done from the UI; if the manager is closed the proposal is lost (scan again).
Details: exact duplicates = audio > 100 KB with the same name and size; papers without audio are grouped in «Archivos sueltos sin canción» (loose files without a song, unchecked); a song with only a session (e.g. Logic) is copied but the manager does not list it until it has audio or lyrics; the file budget of a full session counts folders, not files (the bytes are correct).

## Future variant (not implemented)
Pure browser with the File System Access API (`showDirectoryPicker`): scan and copy would be done in JS with `GM.handle('importar', …)`, using `FileSystemDirectoryHandle` to read the source and write into the library, hashing with `crypto.subtle` in blocks.

## Requests to the core
None required. Useful: `GM.ui.reload()` reporting when it finishes (it already returns the promise) and `GM.ui.go('mod:importar')` being valid (assumed).
