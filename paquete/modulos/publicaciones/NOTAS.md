# Module «publicaciones» — the phase of a song and where it is published

**Two different things, on purpose.** *Phase* (this module) = where the song is in its life: **Sin publicar** (only you have it),
**Adelanto** (pre-release: shared before the official release, e.g. SoundCloud) or **Publicada** (official release through a
distributor: DistroKid, Ditto, TuneCore…). *Registrations* (module «derechos») = protection of the work (collecting society, Safe
Creative). The UI says so in one line in both places.

**Phase bar** (`songTop`, full width at the top of every song page): three big buttons + «↺ Según la carpeta» + a line saying
whether the phase comes from the folder or was chosen by the user. Stored in the core state `ST.release[id]` via `GM.setRelease`
only when it differs from the folder (`GM.isPub/isPre/release` unchanged, so every other module keeps working). Choosing a phase
that differs from the folder simulates the move (`GM.moverCanciones(items, {simular:true})`) and shows one dialog with
from → to for every song: «Cancelar» / «Solo cambiar el estado» / «Sí, mover la carpeta». Conflicts (destination exists, the
folder holds other songs, no folder) are listed in red and that song cannot be moved. When the folder already matches, the
override is cleared. With an override, the bar offers «Mover la carpeta a …» later.

**Folder moves** (core: `POST /api/mover_cancion` in both `gestor/gestor.py` and `distribucion/plantilla/gestor/gestor.py`):
`published/Singles/<name>`; album-level publish of a project `unreleased/<P>/<song>` → `published/Álbumes/<P>/<NN name>`
(NN = album order; the project's album artwork `ARTE/Proyectos/<P>/…` goes to `ARTE/Álbumes/<P>/…`); `prereleased/<name>`
(flat); `unreleased/<name>`, or `unreleased/<album>/<folder>` out of a published album. `<name>` = folder name without its track
number. Albums are never invented (a single song never creates an album folder). Never overwrites: an existing destination
refuses that song. Files move one by one, each with a journal line (`op: move`, `song`, plus `sid`, `dir`), the song's own
`ARTE/` folder moves too, empty folders are removed (never the phase roots), a locked file rolls that song back (journaled as
`undone`). Then the data is rebuilt like «Actualizar». Undo: `deshacer.py --song "<title>" --apply`.

**Identity.** The song keeps its id: `build_data.py` (generic) maps the journal's live `dir` → `sid` before any other matching
(and reserves those ids); `build_gestor_data.py` (personal) points catalogue songs to the new folder and keeps `N…` ids of songs
found on disk; lyrics paths follow the journal. Everything keyed by id (stars, notes, tags, rights, publications, SoundCloud
uploads) is untouched. Paths saved in the state (final version, lanes, chosen covers, album order, mixtape items, artwork roles)
are remapped by the UI (`remapPaths`) from the `pares` the server returns; `GM.emit('movidas', pairs)` lets modules follow
(this module's album entries, SoundCloud's per-album preferences and set record).

**Publications** (`GM.state('publicaciones')` → `estado.json` `mod.publicaciones`): `pubs[songId] = [{id, plat, tipo: 'pre'|'lan',
fecha, url, upc, isrc, cod, notas, priv?, urn?, auto?, alb?, num: [{f, plays, likes, comments, reposts}]}]` (numbers: one row per
day, history shown under «Historial»), `albs[groupKey] = [entry + songs]`, `plats` (absent = presets SoundCloud, Spotify, Apple
Music, YouTube Music, Bandcamp, DistroKid, Ditto, TuneCore, CD Baby, Amuse, Otra; add/rename/delete/restore in the menu section;
renaming renames existing entries). Section «Publicado en» (`songSection`, `order: 5`, above Rights): add / edit / delete. A new
«Lanzamiento» offers phase Publicada, a new «Adelanto» on an unreleased song offers Adelanto (same dialog). Album tab
«🚀 Publicación»: «Marcar este álbum como publicado…» asks platform/type/date/URL/UPC once, stores it at album level and on each
song (matched by album + platform + type, editable per song), then one phase dialog for all its songs (one journal batch).
Badges: platform chips on song cards. Pending card / filter «Publicaciones sin fecha o enlace» (own entries only).

**API for other modules** (`GM.pub`, null without this module): `list(id)`, `upsert(id, entry, match?)` (default match: urn, or
`auto` + platform), `albumUpsert(key, entry)`, `numeros(id, urn, row)`, `fase(ids, f, {preguntar, titulo, quieto})`, `faseDe(s)`.
Read-only entries from other files: `PUB.ext.push(song => [...])` (the personal build adds the author's distributor/SoundCloud
history this way, from a personal-only file that `empaquetar.py` drops from the generic package, like any personal file).

**Tests** (Playwright, scratch package + invented library + fake SoundCloud, es and en): phase without/with move, move later,
conflicts, audio-only song, undo with `deshacer.py`, identity (stars/notes/tags/rights/final/cover), publication CRUD + numbers
history, presets, album publish (one dialog, numbered folders, album artwork, new album key), SoundCloud automation, module absent.

**Limits.** An undo done with `deshacer.py` (outside the UI) does not remap the paths saved in the state (final version, chosen
cover…): the song keeps its id and data, but those choices may need to be made again. A folder that contains other songs, or a
song without its own folder, is never moved. Moving a whole published album back to «Sin publicar» moves each song into
`unreleased/<album>/` (a project), its album artwork stays in `ARTE/Álbumes/`.
