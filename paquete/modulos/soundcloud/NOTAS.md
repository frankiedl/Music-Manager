# Module «soundcloud» — upload an album or a song to the user's own SoundCloud account

**What it does.** Menu section *SoundCloud* (connect / disconnect / upload history), album tab *☁ SoundCloud* and song action
*Subir a SoundCloud* (wide dialog). Flow: preview table → confirm dialog («nothing has been uploaded yet») → tracks uploaded one at
a time with a progress bar → optional album set in album order → links. Nothing is ever uploaded without the confirm step.

**Connection (each user brings their own app).** 3 steps on screen: create an app at `soundcloud.com/you/apps` (Artist Pro),
register the Redirect URI `http://127.0.0.1:8765/soundcloud/callback`, paste Client ID + Client Secret → «Conectar» opens the
authorize page in a new tab. OAuth 2.1 code + PKCE (S256) in `servidor.py`: `POST conectar` builds the URL (random `state`; the
verifier stays in memory, 15 min), `GET /soundcloud/callback` (a **public route**, see below) exchanges the code at
`secure.soundcloud.com/oauth/token` (form-encoded, `client_secret` included: SoundCloud treats clients as confidential) and shows a
small translated page («Conectado…, puedes cerrar esta pestaña»). The UI polls `estado` every 2 s until connected.
The redirect URI sent is the one of the **actual** port; if it is not 8765 the UI warns (section + album tab) and shows the address
that would have to be registered too.

**Secrets.** `datos/modulos/soundcloud/cuenta.json` only (atomic write, 0600 on Mac/Linux): never in `estado.json`, never in the
package (`datos/` is never packaged), never printed, never returned to the UI (`estado` gives the Client ID and a masked secret
`••••••••abcd`). Error bodies are scrubbed of the secret/tokens before reaching the UI. «Desconectar» = `POST /disconnect`
(best effort) + delete tokens (credentials kept); «Borrar credenciales» deletes the file.

**Tokens.** Access token ~1 h. Refreshed proactively (2 min margin, 10 min before an upload) and on any 401 (one retry). Refresh
tokens are single-use: the new one is always persisted; refreshes are serialized with a lock. A refused refresh (400/401/403)
drops the tokens → «vuelve a conectar».

**Upload.** Source per song: a file in its `master/` folder (the final one if it is there, else lossless and newest), else
`GM.finalPath || GM.bestVersion`; a per-row select lets the user pick another version. `POST subir` starts a thread and returns a
job id (`GET progreso`); the multipart body is built by hand and **streamed from disk** in 1 MB chunks (`http.client`), so 4 GB
files never go into memory. Fields: `track[title]`, `asset_data`, `sharing` (private by default), `license` (default
all-rights-reserved), `genre`, `tag_list` (space-separated, multiword quoted), `description` (+ lyrics if ticked; never for
sketches), `label_name`, `release_date`, `isrc` (if the Rights module has a registration whose society is «ISRC»),
`artwork_data` (group cover, JPG/PNG/GIF ≤ 8 MB). If an upload with artwork fails with 400/403/413/415/422 it is retried once
without artwork and the user is told (artwork is PRO only). Uploads are sequential (≈100 req/min limit). A 429 on an upload is
reported with its Retry-After; small JSON requests wait once if Retry-After ≤ 30 s.

**Set.** After all selected tracks are uploaded (it waits while any failed): `POST /playlists` (multipart with
`playlist[artwork_data]` and `playlist[tracks][][urn]` when there is a cover, falling back to JSON without artwork), set_type album
or playlist; then `GET /playlists/{urn}?show_tracks=true` and, if the order differs, `PUT` with the right `tracks` and read again
(result: ok / corregido / distinto / no_verificado, shown to the user). An existing set for the same album is updated with `PUT`
(or a new one is created, user's choice).

**Duplicates.** `datos/modulos/soundcloud/subidas.json` = `{songs: {songId: {urn, url, titulo, archivo, sharing, t}}, sets: {groupKey: …}}`;
each operation is also appended to `datos/diario_movimientos.jsonl` (`op: "soundcloud"`, ignored by `deshacer.py`, which only replays
`move`). An uploaded song shows «Ya subida» with: don't upload again (default; still part of the set) / update its data
(`PUT /tracks/{urn}`, audio unchanged) / upload again (duplicate). Songs uploaded get a «☁ SoundCloud» badge.

**Publications (Nov 2026).** Through `GM.pub` (the «publicaciones» module; everything works without it): each upload/update
upserts the song's entry `{plat:'SoundCloud', tipo:'pre', fecha, url: permalink_url, urn, priv: public|private, auto:'sc'}`
(matched by urn); a set is stored at album level (`albumUpsert`, `auto:'sc-set'`). A PUBLIC upload of a song that is still
«Sin publicar» offers the phase «Adelanto» at the end (same dialog as the phase bar: change only the state, or also move the
folder to `prereleased/`); private uploads change no phase. Uploads recorded before are mirrored into publications when the
SoundCloud section or the song page opens. When `GM.pub` exists the «☁ SoundCloud» badge is not drawn (the publications chip replaces it).
`GM.on('movidas')`: per-album preferences and the set record (`POST claves`) follow an album folder that moved.

**Numbers.** «↻ Actualizar números de SoundCloud» (menu section) → `POST numeros {items:[{id, urn}]}` → job (`GET progreso`):
`GET /tracks/{urn}` one after another in a server thread; fields `playback_count`, `likes_count`|`favoritings_count`,
`comment_count`|`comments_count`, `reposts_count`|`repost_count` (missing → left out, never 0). A 429 waits its Retry-After once
(≤ 60 s) and retries; a second 429 (or no session / network) stops the job with the translated message. Stored in
`datos/modulos/soundcloud/numeros.json` `{songId: {urn, hist:[{f, plays, likes, comments, reposts}]}}`, at most one row per day
(the same day is replaced), and mirrored into the publication entry (`GM.pub.numeros`). Opening a song page (`GM.on('cancion')`)
reads that song once a day when connected and online (`si_no_hoy`: the server skips songs already read today), never blocking the UI.
Tested against the fake server (`GET /tracks/{urn}` added, with forced 429 + Retry-After and missing fields); **not** against the real SoundCloud.

**Errors.** 401/403/404/413/422/429/5xx/network → translated message (server `aviso()` strings, X-Lang) + short API detail. A
failed track does not stop the others; the result lists OK/failed and «Reintentar las que fallaron» re-sends only those.

**Core hooks added for it (generic).** `PUBLIC_ROUTES` in a module's `servidor.py` → `/<id>/<route>` served by
`modulos_core.Registro.publica()` **before** the manager's access check (an OAuth redirect from another site has no Origin/token);
only the Host header is checked there, the route validates itself (single-use `state`). `gestor.py` (personal and
`distribucion/plantilla/gestor/gestor.py`) call it at the top of `do_GET`. `GM.tags(song)` in `gm.js`.

**Tests.** `GESTOR_SOUNDCLOUD_AUTH` / `GESTOR_SOUNDCLOUD_API` env vars point the module to a fake server (the UI then shows «modo de
prueba»). Tested end to end (es + en, Playwright) against a local fake SoundCloud: connect, refresh, preview, 3-song album with cover,
set order fix, duplicates, forced 422/429 + retry, artwork refused, disconnect, no secret in any browser response.
**Not tested against the real SoundCloud** (field-level behaviour of `/tracks` and `/playlists`, order after transcoding,
artwork on sets).

**Limits.** No resumable upload (a dropped connection restarts that track). The job state lives in memory (restarting the manager
mid-upload loses the progress, not the record of finished ones). Lyrics/description capped at 4000 characters. A dialog upload is
lost if the user navigates away from the album tab while uploading (the server finishes the current track and records it).
