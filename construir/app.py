"""Punto de entrada del ejecutable (PyInstaller). Arranca el gestor, o ejecuta un script del gestor si se le pide:
   GestorMusica --run-script build_data.py [args]   (así el gestor lanza sus propios scripts sin necesitar Python instalado)."""
import builtins
import os
import runpy
import sys

if sys.stdin is None:  # app sin consola (Mac .app): las preguntas por terminal se saltan y todo se cambia luego en Ajustes
    def _no_input(*_a, **_k):
        raise EOFError
    builtins.input = _no_input
for _s in ("stdout", "stderr"):
    st = getattr(sys, _s)
    if st is not None:
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    else:
        setattr(sys, _s, open(os.devnull, "w", encoding="utf-8"))

RES = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
GESTOR = os.path.join(RES, "gestor")
sys.path.insert(0, GESTOR)

if len(sys.argv) > 2 and sys.argv[1] == "--run-script":
    nombre = os.path.basename(sys.argv[2])
    sys.argv = [nombre, *sys.argv[3:]]
    runpy.run_path(os.path.join(GESTOR, nombre), run_name="__main__")
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".py") and os.path.isfile(sys.argv[1]):  # actuar como "python script.py" (p. ej. el trabajador de Efectos)
    sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name="__main__")
    sys.exit(0)

import gestor  # noqa: E402  (en gestor/, empaquetado como datos)

sys.exit(gestor.main())
