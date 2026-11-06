# «estado» module (status)

## What it does
«Estado» section of the menu with 4 tabs:
1. **Resumen** (Summary): counters, breakdown by status (SVG donut), process lyrics→version→stems→master→cover→published, activity per month (version dates), «Lo que falta» (what is missing: lists that open the song with `GM.ui.go('song',id)`).
2. **Álbumes y canciones** (Albums and songs): progress per album/single/pre-release/project, bars per step, dots per song, plays if there are reports.
3. **Informes de plataformas** (Platform reports): CSV/TSV importer (4-step wizard), profiles, matching by normalized title (no accents/case/suffixes such as Remastered, Radio Edit, feat.) and ISRC, screen to resolve unmatched rows / review «by similarity», views per month, platform, country, song, album and trend (last 3 months vs the 3 before).
4. **Conexiones** (Connections): honest summary per platform + optional Spotify connector (public catalog).

## Files
`csv.js` (reader), `modulo.js` (panel), `informes.js`, `importar.js`, `conexiones.js`, `servidor.py`. Data in `ctx.datos`: `informes/<id>.json`, `perfiles.json`, `alias.json`, `spotify.json`, `spotify_catalogo.json`. Only the chosen tab goes into `GM.state('estado')`.

## Decisions / limits
- Rows are aggregated per month (the day is not stored). The «wide» format (dates as columns) and .xlsx are not supported (save as CSV).
- «Master» = a file in a master folder, a registration deposit, or a final ★ version in unreleased songs. Published songs without an identified master are listed separately.
- Revenue in several currencies: the currency is chosen in the filter; no conversion.
- Spotify: not tested with real keys; Spotify requires Premium for the app owner and limits storing content (only the minimum is stored).
- Pure browser mode: the server routes have no `GM.handle` version (a local agent is needed).

## Tested (port 8803, invented library of 11 songs, 1 album, 1 single, 1 pre-release, 1 project, 1 sketch)
Panel and Albums correct; light and dark; 3 invented CSVs (ANSI `;` with preamble/Total/decimal comma; UTF-8 with BOM, ISRC, country, currency; UTF-16 TSV with comma thousands and no platform) imported with autodetection, profile saved and recognized on re-import, duplicate warning, resolution of unmatched rows (ignore and assign by ISRC), performance views; Spotify connector with fake keys (controlled error). The only console 404s came from other modules (importar, vst).
Clicking a link in «Lo que falta» opens the song page (confirmed).
**Not tested**: Spotify with real keys, mobile width, large reports.

## Requests to the core
- `GM.thumbUrl(portada)` so `/thumb?f=` is not used directly.
