#!/usr/bin/env python3
"""Moves whole folders (file by file, journaled and undoable) from one place to another in your library.

  python mover_carpetas.py "source=target" ["source2=target2" ...] [--apply]

Paths are relative to the library. If the target file already exists " (2)" is appended: it never overwrites or deletes.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

ROOT = C.root()
JOURNAL = C.DATOS / "diario_movimientos.jsonl"


def free(path):
    stem, ext = os.path.splitext(path)
    n, cand = 2, path
    while os.path.exists(C.lp(cand)):
        cand = f"{stem} ({n}){ext}"
        n += 1
    return cand


def main():
    apply = "--apply" in sys.argv
    pairs = [a.split("=", 1) for a in sys.argv[1:] if "=" in a]
    moves = []
    for s, d in pairs:
        src, dst = ROOT / s, ROOT / d
        if os.path.isfile(C.lp(src)):  # loose file: the target is the final path of the file
            moves.append((src, Path(free(str(dst)))))
            continue
        if not os.path.isdir(C.lp(src)):
            print("NO EXISTE:", s)
            continue
        for dp, _, fns in os.walk(C.lp(src)):
            dp = dp.replace("\\\\?\\", "")
            for f in fns:
                a = Path(dp) / f
                moves.append((a, Path(free(str(dst / a.relative_to(src))))))
    print(f"{len(moves)} archivos")
    if not apply:
        for a, b in moves[:6]:
            print("  ", a.relative_to(ROOT), "=>", b.relative_to(ROOT))
        print("SIMULACIÓN (añade --apply)")
        return
    C.DATOS.mkdir(parents=True, exist_ok=True)
    n = sum(1 for _ in open(JOURNAL, encoding="utf-8")) if JOURNAL.exists() else 0
    dirs = set()
    with open(JOURNAL, "a", encoding="utf-8") as j:
        for a, b in moves:
            os.makedirs(C.lp(b.parent), exist_ok=True)
            os.rename(C.lp(a), C.lp(b))
            dirs.add(a.parent)
            n += 1
            j.write(json.dumps({"id": n, "t": time.strftime("%Y-%m-%d %H:%M:%S"), "op": "move", "src": C.posix(a.relative_to(ROOT)),
                                "dst": C.posix(b.relative_to(ROOT)), "song": "(movido desde el gestor)"}, ensure_ascii=False) + "\n")
    for d in sorted(dirs, key=lambda p: -len(str(p))):
        cur = d
        while cur != ROOT:
            try:
                os.rmdir(C.lp(cur))
            except OSError:
                break
            cur = cur.parent
    print("Hecho.")


if __name__ == "__main__":
    main()
