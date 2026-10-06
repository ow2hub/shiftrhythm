#!/usr/bin/env python3
"""books.csv から指定したidの本を外す(idは振り直さない).

集計の途中で「この本は対象外だった」と気づいたときに使う。
responses/ の答えはidで対応しているので、**idは絶対に振り直さない**。
外した本は books_dropped.csv に控えが残る。

    python3 drop_books.py b02 b05 b06 b12
    python3 aggregate.py
"""

import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
BOOKS = BASE / "books.csv"
DROPPED = BASE / "books_dropped.csv"
COLS = ["id", "title", "author", "year", "origin"]


def main():
    ids = {a.strip() for a in sys.argv[1:] if a.strip()}
    if not ids:
        sys.exit("外すidを並べてください。例:\n  python3 drop_books.py b02 b05")
    if not BOOKS.exists():
        sys.exit("books.csv がありません。")

    rows = list(csv.DictReader(BOOKS.open(encoding="utf-8-sig")))
    keep = [r for r in rows if (r.get("id") or "").strip() not in ids]
    gone = [r for r in rows if (r.get("id") or "").strip() in ids]

    missing = ids - {(r.get("id") or "").strip() for r in rows}
    if missing:
        print(f"  [注意] books.csv に無いid: {', '.join(sorted(missing))}")
    if not gone:
        print("外す本がありませんでした。books.csv は変えていません。")
        return

    def write(path, data, append=False):
        exists = path.exists()
        with path.open("a" if append else "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            if not (append and exists):
                w.writeheader()
            w.writerows(data)

    write(DROPPED, gone, append=True)
    write(BOOKS, keep)

    print(f"{len(rows)}冊 -> {len(keep)}冊(外した{len(gone)}冊は books_dropped.csv に控えました)")
    print("\n外した本:")
    for r in gone:
        print(f"  {r['id']}  {r['title']}")
    print("\n残った本:")
    for r in keep:
        print(f"  {r['id']}  {r['title']}")
    print("\n※idは振り直していません(AIの答えとの対応が壊れるため)")
    print("次: python3 aggregate.py")


if __name__ == "__main__":
    main()
