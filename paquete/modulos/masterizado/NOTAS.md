# Módulo «masterizado» — pestaña Masterización en cada álbum

## Qué hace
Pestaña «🎚 Masterización» (`albumTab`). Pistas = `GM.order(g)`; fuente de cada una = `GM.finalPath(s)||GM.bestVersion(s)`,
salvo los «… (máster).wav» que genera este mismo módulo (se saltan para no remasterizar un máster). Mide LUFS (BS.1770, verificado
con ffmpeg ebur128: coincide a 0,1 LU), iguala (modo «cada canción» o «álbum/relativo»), limitador de picos con 0,3 dB de margen extra,
recorte, fundidos, silencios, etiquetas ID3v2.3 + RIFF INFO, carátula (`g.cover`, PNG/JPEG; otros formatos o >3,5 MB se pasan a JPEG),
forma de onda, escucha con/sin normalización. Exporta: (a) ZIP propio sin compresión (sin librerías, sin CDN), (b) «Guardar másters en la
biblioteca» → `POST guardar_master` → `<canción>/master/NN - Título (máster).wav`, nunca sobrescribe («… (2)»), con confirmación.
Selector de estado del álbum (Borrador · Mezcla · Masterización · Listo para distribuir); emite `GM.emit('masterizado:estado',{album,estado})`.

## Datos
`GM.state('masterizado')[g.key] = {estado,modo,lufs,techo,bits,dither,artista,anio,genero,idioma,portada,fuera:[ids],pistas:{[idCancion]:{name,artist,trimStart,trimEnd,fadeIn,fadeOut,padStart,padEnd,previewNorm,meta:[{key,value}]}}}`. Nunca audio.
Las pistas añadidas a mano (WAV arrastrados) NO se recuerdan al recargar.

## Decisiones
- WAV: se lee nativo (frecuencia/bits originales). No-WAV (MP3, FLAC…): `decodeAudioData` a 44,1 kHz float; se exporta a los bits elegidos a 44,1 kHz.
- Memoria: el audio solo está en memoria mientras se usa (carga bajo demanda, se suelta tras medir/exportar); se guardan picos de onda. Se cede el hilo por pista/canal.
- Nombres: ZIP `NN - Título.wav`; biblioteca `NN - Título (máster).wav`.
- Limitador sobre pico de muestras (no true-peak real).

## Efectos (implementado, usa el módulo `vst`)
- Panel «Efectos · antes del limitador» (plegado). Edita la cadena con `GM.mods.vst.montarCadena` (VST3 + internos, presets). Cadena general + «cadena propia» por pista. Se guarda en `ajustes.fx = {on, cadena, porPista:{idPista:cadena}}`.
- **Dónde actúa**: «Aplicar efectos» procesa cada pista en el servidor al CARGARLA (`traerFx` → `GM.mods.vst.procesar`, WAV de 24 bits; si pasa de 0 dB el servidor baja el volumen y al decodificar se devuelve con `bajado_db`). Por tanto medición LUFS, ganancia, limitador, escucha y exportación ya trabajan con el audio con efectos. Los originales no se tocan.
- Caché en memoria por pista+cadena (`FXCACHE` → id del trabajo en el servidor; si ya no está se reprocesa). Solo se reprocesan las pistas cuya cadena cambió. «Quitar efectos» vuelve al audio original.
- Sin `vst` o sin pedalboard: el panel lo explica (con el botón de instalar de vst) y la masterización sigue igual, sin efectos.
- Límites: no es tiempo real (ida y vuelta al servidor); el audio con efectos se descarga entero (24 bits) en cada carga.

## Masterizar una sola canción
`songAction` «🎚 Masterizar» (ficha y menú de la canción): abre la misma interfaz en una ventana con un grupo ficticio de 1 pista; ajustes en `GM.state('masterizado')['cancion:'+id]`; «Guardar máster» escribe en su carpeta `master/`.

## Mixtapes
`mixtapeAction` «🎚 Masterizar» (página del mixtape): misma interfaz en una ventana, pistas = `mixtape.items` en su orden (`it.p` si existe, si no `GM.finalPath||GM.bestVersion`). ↑/↓ reordenan y se reflejan en `mixtape.items` (`GM.mixSave()`). Ajustes en `GM.state('masterizado')['mix:'+id]` (incluye `mixMasters` = ruta guardada por item y `origMix` = `it.p` original).
- «Guardar máster» escribe en `MIXTAPES/_masters/<id>/NN - título.wav` (`POST guardar_master?mix=`), sin sobrescribir; NUNCA en `master/` de las canciones.
- «Usar en este mixtape» pone `it.p` = esos WAV (guarda el `it.p` anterior en `origMix`) y llama a `GM.mixSave()`; «Volver a las versiones originales» lo restaura. Si `it.p` apunta a un máster de este módulo, no se vuelve a masterizar: se parte del original.
- Probado: reordenar, guardar 3 WAV, usar/volver, y que `/api/mix_convertir` convierte a MP3 un `it.p` de `_masters` (sin cambios en el núcleo). No probado: regeneración automática de MP3 en la interfaz del mixtape tras «Usar» (`GM.mixSave()` + cola del núcleo), ni audio real.

## Pendiente / no probado
- Probado en navegador (puerto 8801): pestaña, carga en orden, LUFS, normalización (pista y álbum), limitador, ZIP (CRC, etiquetas, carátula verificados con Python/ffmpeg), guardar en master/ (sin sobrescribir, tras recargar aparecen), persistencia, MP3, quitar/restaurar, WAV a mano, reproducción, oscuro.
- Tema claro: probado visualmente OK. NO probado: canciones de 40–60 MB reales, otros navegadores, Mac/Linux, modo navegador puro (`GM.handle`, no implementado), ZIP > 4 GB.
- Sin imprimir captura del `Space`/atajos de teclado (no hay).

## Peticiones al núcleo
- `GM.cfg`/artista para rellenar «Artista del álbum» automáticamente.
- Que el gestor no elija como «final» los másters recién guardados si no se desea (hoy `autoFinal` prefiere `/master/`).
- Pruebas de audio: la reproducción se verificó por estado; no repetir con sonido (silenciar AudioContext en los arneses).

## Portada y copyright en mixtapes
Mixtape: la carátula de la cabecera y la incrustada en los WAV es `GM.mixCover(mix,1200)` (casete); `album` = nombre del mixtape y `copyright` = `GM.mixCopy(mix)` (ID3 `TCOP` + RIFF `ICOP`). Canción suelta / álbum: portada de siempre. Probado leyendo los WAV exportados (APIC JPEG 1200×771, TALB, TCOP/ICOP).

## Textos nuevos (para traducir)
La interfaz usa una palabra de contexto `X` (álbum / mixtape / canción) en pocas plantillas:
- `Masterización {del álbum|del mixtape|de la canción} «{título}»` · `Estado {…}` (oculto en mixtape y canción) · `Artista {…}`
- Panel: `Álbum` | `Mixtape` | `Canción` · `Se sube todo {el álbum|el mixtape} lo mismo, …` (el modo «relativo» se oculta en canción suelta)
- Botón: `Guardar másters del álbum` | `Guardar másters del mixtape` | `Guardar máster`
- Destino en la ayuda: `la carpeta master de cada canción` | `la carpeta MIXTAPES/_masters de este mixtape` | `la carpeta master de la canción`
- Vacío: `Este álbum no tiene canciones todavía. Añade canciones al álbum o arrastra aquí archivos WAV.` | igual con «mixtape» | `Esta canción no tiene audio todavía. Arrastra aquí un archivo WAV.`
- Sin portada: `Sin carátula elegida. Ponla con «Cambiar portada» y se incrustará aquí.`
- Solo mixtape: `Subir en el mixtape`, `Bajar en el mixtape`, `Guardar másters del mixtape` (diálogo), `Usar en este mixtape`, `Volver a las versiones originales`, `Másters del mixtape guardados (n).`

## FX1…FX5 por pista y escucha en directo
- La cadena general pasa a ser **5 huecos** (`S.fx.cadena`, máx. 5, iguales para el álbum/mixtape/canción). Cada pista guarda `S.fx.porPista[id] = {m:[1,1,0,1,1], off:0}` (máscara de los 5 huecos y «todo apagado»); si es todo unos se borra. Las antiguas «cadenas propias» por pista se descartan al abrir. Todo dentro de `GM.state('masterizado')`.
- Interfaz: en cada pista, botones **FX1…FXn** y **∅**; arriba, interruptor global **Con efectos / Original** (ambos saltan los efectos también al exportar). Al añadir el primer hueco se pasa a «Con efectos».
- Con **motor** (`sounddevice` instalado y huecos definidos): al pulsar ▶ suena el motor del agente (navegador en silencio, medidor L/R en la barra), los botones/interruptor se oyen al instante, y el orden/recortes/fundidos/«Oír igualada» se envían al motor. Sin motor: A/B por render (se reprocesa la canción actual ~700 ms después del cambio). Las demás pistas se invalidan (`fxRevisar`) y se reprocesan al exportar/medir, por eso exportar siempre refleja las máscaras actuales.
- Exportar: igual que antes (efectos en servidor por pista con la cadena filtrada por su máscara → ganancia → limitador en el navegador). Mismo grafo que el motor (ver NOTAS de `vst`).
- Probado en navegador con salida nula: ▶ con motor (posición avanza 1,02 s/s, medidor, navegador en silencio), FX2 off → máscara [1,0,1], ∅ → `apagado`, Original/Con efectos → `efectos` false/true, pausa, cierre del modal cierra el motor; mixtape de 3 pistas: botones en cada fila, paso automático a la pista siguiente, «Oír con volumen igualado» manda `gain_db` al motor.
- No probado: exportar un álbum entero con máscaras distintas (la lógica es la misma, verificada pieza a pieza), plugins de terceros, sonido real.
- Para probar con la salida nula: `localStorage.gm_sink='nulo'` y recargar.

### Textos nuevos (para traducir)
«Efectos · FX1…FX5, antes del limitador», «Con efectos», «Original», «Instalar motor en directo», «Escucha en directo», «Todos los efectos apagados en esta pista», «Máximo N efectos (FX1…FXN)», «Cerrar editor», «Cerrando…», y los textos explicativos del panel de efectos y del instalador de «sounddevice».

## ⚠ Efectos DESACTIVADOS (decisión del usuario, no reaccionaban)
`const FX_ACTIVO=false` al principio de `modulo.js`: el panel «Efectos», FX1…FX5, «Con efectos/Original», el motor en directo y el medidor quedan ocultos/inertes; la exportación y la escucha usan solo la normalización (LUFS objetivo + limitador). El módulo `vst` tiene `"distribuir": false` y ya no sale en Ajustes. Todo el código se conserva para retomarlo (poner `FX_ACTIVO=true` y `distribuir:true`).
Núcleo a revisar: ver el informe (empaquetar debe respetar `distribuir:false`; `ajustes/servidor.py` aún guarda `vst_carpetas`, inofensivo).

## Etiquetas de los másters (WAV)
Los másters se codifican desde el audio decodificado, así que **no arrastran ningún metadato ni portada del original**; se escriben solo los del gestor: título, artista, artista del álbum, álbum (en mixtape = nombre del mixtape), pista n/total, año, género, idioma, compositor (por defecto el artista; se puede cambiar en «Etiquetas» de la pista), copyright «© año titular» (titular de Ajustes; en mixtapes, `GM.mixCopy`), comentario/ISRC/editorial… (campos propios de la pista), **letra (USLT, `GM.lyrics`)** y portada (APIC). Verificado con ffprobe. Limitación WAV: RIFF INFO no tiene letra, solo va en el chunk ID3 (lo lee ffmpeg/ffprobe, no todos los reproductores). MP3/FLAC con letra los generan el mixtape ZIP y `mix_convertir` del núcleo (no tocados aquí).
