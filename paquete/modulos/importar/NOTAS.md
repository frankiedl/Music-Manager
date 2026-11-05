# Módulo «Importar» — NOTAS

**Estado: escrito pero SIN PROBAR de extremo a extremo.** Se acabó el límite de uso antes de abrir el navegador. Solo se comprobó que `servidor.py` compila y que `limpiar_titulo`/`es_generico` dan resultados razonables con ejemplos.

## Qué hace
Asistente de 4 pasos (Elegir carpeta → Buscar → Revisar → Copiar). Lee el origen en solo lectura y COPIA a `ctx.root/unreleased/<Título>/…`. Nunca mueve ni borra el origen y nunca sobrescribe (añade « (2)»).

Rutas (`servidor.py`): `GET carpetas?ruta=`, `POST escanear`, `GET estado?job=`, `GET propuesta?job=`, `POST presupuesto`, `POST copiar`, `POST cancelar?job=`, `GET diario`, `POST deshacer`, `GET info`.

## Destinos
`versiones/` · `master/` · `stems/` · `versiones/directos/` · `versiones/bocetos/` (dentro de versiones para que el gestor los reconozca) · `otros/tomas/` · `sesiones/<DAW>/…` · `docs/` · `midi/` · `arte/` · `video/` · `letra.txt` (la primera letra .txt/.md; las demás van a docs). Audio en formatos que el gestor no lee (ogg, opus…) va a `otros/audio/`. Los bocetos se marcan con `GM.ui.setDraft` al pulsar «Actualizar la biblioteca».

## Heurísticas (y límites)
- Título: se quitan sufijos (mix, master, final, v2, demo, bounce, 24bit, fechas, «(2)»…). Un número final suelto NO se quita («Canción 2» ≠ «Canción 1»). Fusión por parecido ≥ 88 % solo si los dígitos coinciden.
- Categoría audio: master > stem > directo > duración ≥ 15 min (directo) > toma > boceto > mix/final > < 30 s (boceto) > .m4a/.amr (boceto) > versión. Duración exacta solo en WAV; en mp3/m4a es estimada (≈) por bytes/segundo.
- Proyectos DAW: por extensión; `.logicx/.logic/.band` son paquetes. Una carpeta es «proyecto» si tiene un único nombre de sesión y (subcarpetas típicas Samples/Backup/Freeze… o nombre «… Project» o ≤ 8 subcarpetas, esto último no en la raíz). Si no, cada sesión es «suelta» (solo su archivo). Dentro de un proyecto solo se listan Bounces/Exports/Stems/etc.; lo demás es «interno» (se cuenta, no se lista).
- Duplicados: mismo nombre y tamaño (>100 KB, audio) → sin marcar; sin hash, puede fallar.
- Carpetas con ≥ 60 audios < 3 MB → «¿samples?», excluidos por defecto.
- Sesión completa duplica espacio si sus bounces también se importan como versiones.
- No se siguen enlaces simbólicos ni junctions; se salta la propia biblioteca si está dentro del origen.

## Copia y verificación
Bloques de 4 MB a `nombre.importando`, `fsync`, comparación de tamaño y SHA-256 completo (origen leído en la copia, destino releído); por encima de 2 GB (`GESTOR_IMPORTAR_LIMITE_COMPLETO` para pruebas) se verifica por muestreo (4 MB inicio + 4 MB final + 32 bloques de 1 MB). Se conserva la fecha. Bloqueados: 3 intentos, luego se omiten y se cuentan. Rutas largas de Windows con prefijo `\\?\`. Diario en `ctx.datos/diario.jsonl`. «Deshacer» borra solo archivos del diario cuyo tamaño y huella coinciden y rmdir de carpetas vacías creadas por esa importación.

## Pruebas hechas (Windows, origen inventado, paquete propio)
API + navegador: explorador de carpetas con migas, escaneo (DAW: Ableton con carpeta, FL/Reaper sueltos, Logic paquete; bounces, stems, directos, notas de voz, MIDI, letras, imágenes, acentos/emoji, ruta > 260), edición en la revisión (renombrar, categoría, mover, excluir, fundir), presupuesto de espacio, copia con verificación (completa y por muestreo), origen idéntico antes/después (tamaño, fecha, md5), reconocimiento por el gestor tras «Actualizar» y bocetos marcados, deshacer (conserva un archivo modificado), cancelar a medias (sin restos `.importando`), archivo bloqueado (omitido y avisado), consola sin errores.
**No probado:** Mac/Linux, discos de cientos de GB, enlaces simbólicos (no pude crearlos), reanudar tras cierre del gestor a mitad, variante de navegador puro. El sondeo se hace desde la interfaz; si se cierra el gestor se pierde la propuesta (hay que volver a escanear).
Detalles: duplicados exactos = audio > 100 KB con mismo nombre y tamaño; los papeles sin audio se juntan en «Archivos sueltos sin canción» (sin marcar); una canción solo con sesión (p. ej. Logic) se copia pero el gestor no la lista hasta que tenga audio o letra; el presupuesto de archivos de una sesión completa cuenta carpetas, no ficheros (los bytes sí son correctos).

## Variante futura (no implementada)
Navegador puro con File System Access API (`showDirectoryPicker`): el escaneo y la copia se harían en JS con `GM.handle('importar', …)`, usando `FileSystemDirectoryHandle` para leer el origen y escribir en la biblioteca, con hash por `crypto.subtle` en bloques.

## Peticiones al núcleo
Ninguna obligatoria. Útil: que `GM.ui.reload()` devuelva cuándo termina (ya devuelve la promesa) y que `GM.ui.go('mod:importar')` sea válido (se asume).
