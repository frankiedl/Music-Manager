#!/usr/bin/env python3
"""Undoes the file moves made by the manager, reading datos/diario_movimientos.jsonl backwards.

  python deshacer.py                          simulate undoing everything
  python deshacer.py --apply                  undo everything
  python deshacer.py --song "Title" --apply   undo only that song

Files go back to their original place. Then folders left empty are removed.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

ROOT = C.root()
JOURNAL = C.DATOS / "diario_movimientos.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not JOURNAL.exists():
        print("No hay diario: nada que deshacer.")
        return 0
    entries = [json.loads(l) for l in open(JOURNAL, encoding="utf-8") if l.strip()]
    undone = {e["ref"] for e in entries if e.get("op") == "undone"}
    todo = [e for e in entries if e["op"] == "move" and e["id"] not in undone
            and (not a.song or a.song.lower() == str(e.get("song", "")).lower())]
    todo.reverse()
    print(f"{len(todo)} operaciones por deshacer" + ("" if a.apply else "  (SIMULACIÓN)"))
    if not a.apply:
        for e in todo[:10]:
            print("  ", e["dst"][-70:], "=>", e["src"][-60:])
        return 0
    skipped, dirs, nid = 0, set(), len(entries)
    with open(JOURNAL, "a", encoding="utf-8") as j:
        for e in todo:
            src, dst = ROOT / e["src"], ROOT / e["dst"]
            try:
                if not dst.exists() or src.exists():
                    skipped += 1
                    print("  salto:", e["dst"], "(no está o el origen ya existe)")
                    continue
                os.makedirs(C.lp(src.parent), exist_ok=True)
                os.rename(C.lp(dst), C.lp(src))
                dirs.add(dst.parent)
            except OSError as ex:
                print("  ERROR:", e["dst"], ex)
                continue
            nid += 1
            j.write(json.dumps({"id": nid, "op": "undone", "ref": e["id"], "t": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
            j.flush()
    for _ in range(3):  # retry: a sync service may keep a folder open for a moment
        for d in sorted(dirs, key=lambda p: -len(str(p))):
            cur = d
            while cur != ROOT:
                try:
                    os.rmdir(C.lp(cur))
                except OSError:
                    break
                cur = cur.parent
        time.sleep(1)
    print(f"Deshecho. Saltadas: {skipped}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
