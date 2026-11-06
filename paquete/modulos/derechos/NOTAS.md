# Module «derechos» (Rights)

**What it does.** Answers "is this song published, and is it registered?" in one clear place.
- **Release status** per song (Unreleased / Pre-released / Published) on the song page (section *Derechos*). Stored in the core
  state as `ST.release[songId] = 'pub'|'pre'|'un'` (`GM.release` / `GM.setRelease`). `isPub()/isPre()` in `index.html` use it and
  fall back to the folder (`published/`, `prereleased/`). Choosing the status the folder already implies stores nothing. Folders are never
  moved, so album/single grouping (`groups()`) still follows the folder.
- **Registrations**: `GM.state('derechos').reg[songId] = [{id, soc, cod, fecha (YYYY-MM-DD), est: 'pend'|'env'|'reg', au, ed (%), notas}]`.
  Add / edit / delete on the song page. User's own notes; no connection to any society.
- **Societies**: `state.socs = [{n, c}]` (absent = presets SGAE ES, SACEM FR, GEMA DE, ASCAP/BMI/SESAC US, PRS UK, SIAE IT, SADAIC AR,
  SPA PT; the first edit materializes them). «Otra…» in the form = free name (added to the list). `state.pais` only sorts that
  country's societies first. Renaming a society renames it in existing registrations; deleting it keeps registrations as they are.
- **Registration sheet**: CSV export in the browser (UTF-8 BOM; `;` except in English, where Excel expects `,`), one row per
  registration, one blank row for songs without any. Headers/values are written in the UI language and recognized on import in
  es/en/de/pt. Import (CSV or `.xlsx`): `servidor.py` (`POST leer`, stdlib `csv`/`zipfile`/`xml`) only returns the rows; matching
  (ID column, else normalized title), preview (new / changed / release status changes / unchanged + warnings for unknown songs,
  duplicate titles, unknown societies or values) and applying happen in `modulo.js`. Blank cells never overwrite; nothing is ever deleted.
  Excel serial dates and DD/MM/YYYY are converted.
- **Integration**: Pending card + song filter «Publicadas sin registro» (`pend:true`, so it also counts in «Con algo pendiente»),
  society badges on the song cards, a Home chart (registered vs missing), a menu section with summary, sheet and society editor.

**Core hooks it uses** (added to `gm.js` / `index.html` for it, generic): `songSection`, `badges`, `tasks`, `filters`,
`GM.release/setRelease/isPub/isPre`. The art view's per-item platform checkboxes were removed at the same time (they meant nothing).

**Personal build.** The personal-only script (removed from the generic package by `empaquetar.py`, like any personal file) pushes the
author's the personal SGAE field data into `DER.ext` as a read-only «SGAE · Registrado» entry (code, ISWC, deposited file), so nothing is lost and
the old «Publicadas sin SGAE» card/filter became the generic «Publicadas sin registro». `empaquetar.py` refuses a package whose
modules mention the personal field or a personal-file marker.

**Limits.** Splits are a simple author/publisher percentage pair (sum ≤ 100), not a full co-writer split sheet. Only the first sheet
of an `.xlsx` is read; `.xls` (old format) is not supported. A title shared by two songs needs the ID column.
