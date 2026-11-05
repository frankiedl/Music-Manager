# Módulo «estado»

## Qué hace
Sección «Estado» del menú con 4 pestañas:
1. **Resumen**: contadores, reparto por estado (donut SVG), proceso letra→versión→stems→máster→portada→publicada, actividad por mes (fechas de versiones), «Lo que falta» (listas que abren la canción con `GM.ui.go('song',id)`).
2. **Álbumes y canciones**: avance por álbum/single/pre/proyecto, barras por paso, puntos por canción, reproducciones si hay informes.
3. **Informes de plataformas**: importador CSV/TSV (asistente de 4 pasos), perfiles, casado por título normalizado (sin tildes/mayúsculas/sufijos tipo Remastered, Radio Edit, feat.) e ISRC, pantalla de resolver no casados / revisar «por parecido», vistas por mes, plataforma, país, canción, álbum y tendencia (últimos 3 meses vs 3 anteriores).
4. **Conexiones**: resumen honesto por plataforma + conector opcional de Spotify (catálogo público).

## Archivos
`csv.js` (lectura), `modulo.js` (panel), `informes.js`, `importar.js`, `conexiones.js`, `servidor.py`. Datos en `ctx.datos`: `informes/<id>.json`, `perfiles.json`, `alias.json`, `spotify.json`, `spotify_catalogo.json`. Solo la pestaña elegida va a `GM.state('estado')`.

## Decisiones / límites
- Filas se agregan por mes (no se guarda el día). No admite formato «ancho» (fechas como columnas) ni .xlsx (guardar como CSV).
- «Máster» = archivo en carpeta master, depósito, o versión final ★ en no publicadas. Publicada sin máster identificado se lista aparte.
- Ingresos en varias monedas: se elige moneda en el filtro; no se convierten.
- Spotify: no probado con claves reales; Spotify exige Premium al propietario y limita guardar contenido (se guarda solo lo mínimo).
- Modo navegador puro: las rutas del servidor no tienen versión `GM.handle` (necesitaría agente local).

## Probado (puerto 8803, biblioteca inventada de 11 canciones, 1 álbum, 1 single, 1 pre, 1 proyecto, 1 boceto)
Panel y Álbumes correctos; claro y oscuro; 3 CSV inventados (ANSI `;` con preámbulo/Total/coma decimal; UTF-8 con BOM, ISRC, país, moneda; TSV UTF-16 con miles en coma y sin plataforma) importados con autodetección, perfil guardado y reconocido al reimportar, aviso de duplicado, resolución de no casados (ignorar y asignar por ISRC), vistas de rendimiento; conector Spotify con claves falsas (error controlado). Las únicas 404 de consola son de módulos ajenos (importar, vst).
Clic en un enlace de «Lo que falta» abre la ficha de la canción (confirmado).
**No probado**: Spotify con claves reales, ancho móvil, informes grandes.

## Peticiones al núcleo
- `GM.thumbUrl(portada)` para no usar `/thumb?f=` directo.
