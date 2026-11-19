# «huella» module

Two independent things share the module:

1. **Menu section «Huella»** (`nav`): asks AudD whether a master already sounds like a known song (see the header of `modulo.js`). Needs the user's own token.
2. **Song-page section «Huella · inspección y etiquetado»** (`songSection`, order 70): local only, nothing is sent anywhere. It inspects ONE audio file and writes the
   author's own metadata on a safe copy.

## Song-page section

Rule of thumb of the whole screen: **see first → clean what is foreign by default → put your own → verify the audio did not change.**

- Header: file selector (the song's audio files), «Inspeccionar con señal» / «sin señal» / «Resetear», integrity card (`SHA-256` of the file, `sha256_audio`,
  status `OK` / `OK · Con avisos (n)` / `Atención`), technical summary and a collapsible list of warnings. A broken file is never discarded: it is reported.
- Block 1 «Inspección y señal»: one row per tag / opaque block / cover with `Conservar` (unticked by default) and, if the signal was measured, the four traits of
  `senal.rasgos` (measurement, threshold, margin, «Indicio activo»). When the margin is positive but the trait does not count, the reason is written under it.
  A fixed note says the signal data are technical hints, not legal proof or a verdict on the origin.
- Block 2 «Limpiar y etiquetar en copia segura»: main fields, full lyrics, credits (role, name, person/tool, note) and the name of the copy.
  `1. Simular plan` (`simular:true`) shows Se quita / Se conserva / Se escribe (native field of each thing) / Avisos del formato.
  `2. Aplicar en _etiquetados/` (`simular:false`) is enabled only after a simulation and is disabled again as soon as anything changes. It asks for confirmation and
  shows the strict verification (sha256 of the audio, decoded-audio MD5, read-back, no foreign tags, kept blocks), the path of the copy and the registry entries,
  or the exact reasons why nothing was delivered.

### How it talks to the server
- `POST inspeccionar {p, senal}` → inspection document (`huella.inspeccion/1`). `POST etiquetar {p, poner, creditos, conservar, nombre, simular}`.
- Right after inspecting, the UI calls `etiquetar` with `simular:true` and nothing declared, to get the **plan**: its `acciones` say, for every element,
  whether it can be kept (`conservable`) and how to tick it (`como`: etiqueta | binario | bloque | caratula). The UI builds `conservar` from that and never guesses.
- Elements that belong to one raw block (e.g. all the `bext:*` fields) share one checkbox.

### State
- `GM.state('huella').borradores[songId]` = the form (fields and credits) so nothing has to be typed again. Lyrics are stored only if they differ from the manager's.
  The selection of what to keep is NOT stored (it depends on the file).
- The lyrics and title suggested come from the manager and are filled in at paint time (the manager may load them after the page opens).

### Translations
Static texts of the block are checked by `tests/test_idiomas.py`; so is every message the server writes. Texts that are built with numbers have patterns in
`_core/idiomas/*.json` (`{a}`, `{b}`…). `<textarea>` placeholders are translated with `window.T()` because the runtime translator skips textareas.

### Testing
- `python3 -m unittest discover -s tests -v` (inspection, signal, tagging, route, dictionaries).
- Browser: start the manager, open a song, open the section. Checked with a headless browser on WAV, MP3, FLAC and M4A, an empty (damaged) WAV, a file with a signal
  hint, a phone-sized window and the four languages (`?lang=es|en|de|pt`).
- Not tested: Windows / Mac, other browsers, long files (the request waits until the analysis ends), light theme beyond the shared variables.
