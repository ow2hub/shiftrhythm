#!/usr/bin/env python3
"""1つの回が終わったら、データを退避して次の回を始める.

analysis/ は1回ぶんの作業場所しか持っていないので、次のジャンルを始める前に
今回のデータを archive/<名前>/ へ移す。移すだけなので、あとから見返せる。

    python3 new_round.py --archive ep2     # 第2回のデータを退避して、空にする
    python3 new_round.py --list            # 退避済みのものを一覧する

退避したあとは、いつもどおり STEP 1 から:
    cp books.sample.csv books.csv
"""

import argparse
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVE = BASE / "archive"

# 回ごとに作られるもの(退避の対象)
FILES = ["books.csv", "canonical.json", "claims.txt", "report.md",
         "video_numbers.py", "tocs.md", "compare_report.md"]
DIRS = ["responses", "prompts_out", "extracted",
        "compare_out", "responses_compare"]
KEEP_IN_BOOKS = {"_template.md"}


def do_list():
    if not ARCHIVE.exists() or not any(ARCHIVE.iterdir()):
        print("退避済みのデータはまだありません。")
        return
    for d in sorted(p for p in ARCHIVE.iterdir() if p.is_dir()):
        books = len(list((d / "books").glob("*.md"))) if (d / "books").exists() else 0
        has = "report.md あり" if (d / "report.md").exists() else "集計前"
        print(f"  {d.name}  書籍{books}冊 / {has}")


def do_archive(name):
    dest = ARCHIVE / name
    if dest.exists():
        sys.exit(f"archive/{name}/ はすでにあります。別の名前にしてください。")

    moved = []
    dest.mkdir(parents=True)
    for f in FILES:
        src = BASE / f
        if src.exists():
            shutil.move(str(src), dest / f)
            moved.append(f)
    for d in DIRS:
        src = BASE / d
        if src.exists() and any(src.iterdir()):
            shutil.move(str(src), dest / d)
            moved.append(d + "/")
        elif src.exists():
            src.rmdir()
    # books/ は雛形だけ残す
    books = BASE / "books"
    if books.exists():
        keep = dest / "books"
        keep.mkdir(exist_ok=True)
        n = 0
        for md in sorted(books.glob("*.md")):
            if md.name in KEEP_IN_BOOKS:
                continue
            shutil.move(str(md), keep / md.name)
            n += 1
        if n:
            moved.append(f"books/({n}冊)")
        else:
            shutil.rmtree(keep)

    if not moved:
        dest.rmdir()
        sys.exit("退避するものがありませんでした。すでに空のようです。")

    print(f"archive/{name}/ に退避しました:")
    for m in moved:
        print(f"  {m}")
    print("\n次の回を始めます:")
    print("  cp books.sample.csv books.csv")
    print("  open -e books.csv          # 15冊を書く")
    print("  python3 check_books.py --init")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", metavar="名前",
                    help="今の作業データを archive/<名前>/ へ移す(例: ep2)")
    ap.add_argument("--list", action="store_true", help="退避済みのものを一覧する")
    args = ap.parse_args()

    if args.list:
        do_list()
    elif args.archive:
        do_archive(args.archive)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
