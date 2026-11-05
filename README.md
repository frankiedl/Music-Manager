# Gestor de música (ejecutables)

© Frankie De Leonardis. Se puede usar (también para trabajo comercial) pero no vender el programa ni sus partes: ver `LICENSE` y `AVISOS.md`.

Gestor local de música para Windows 10/11 y Mac. Este repositorio **solo construye** los ejecutables en la nube (GitHub Actions); no contiene datos de nadie.

1. Pestaña **Actions** > **Construir** > **Run workflow**.
2. Cuando termine (unos 5-10 min), entra en la ejecución y descarga los zips de **Artifacts** (Windows, Mac-Intel, Mac-AppleSilicon).
3. Cada zip trae el ejecutable, su carpeta de soporte y `Manual.pdf`.

Pasos detallados para personas no técnicas: `CONSTRUIR.md` (en la carpeta `distribucion` del proyecto original).
Estructura: `paquete/` (gestor genérico), `construir/` (PyInstaller), `manual/` (genera el PDF), `.github/workflows/construir.yml`.
Para reconstruir en local: `pip install pyinstaller pillow reportlab` y `python construir/construir.py --paquete paquete --salida salida`.
