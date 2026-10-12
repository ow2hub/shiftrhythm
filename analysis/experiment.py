#!/usr/bin/env python3
"""「出力の見本を示す」は本当に効くのかを、数えて確かめる.

6つの依頼を、見本なし(A)と見本あり(B)の2通りで出す。
出力が指定どおりかは **Pythonが機械的に判定する**(AIに採点させない)。

    python3 experiment.py --init     # プロンプトA/Bを作る
    python3 experiment.py --score    # 答えを読んで採点する

採点基準は1依頼につき4条件、6依頼で24条件。すべて文字数・行数・前方一致など、
人によって judgement が変わらないものだけにしてある。
"""

import argparse
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "experiment_out"
RESP_DIR = BASE / "experiment_responses"
RUNS = 2

HEADER_A = """次の6つの依頼に、それぞれ答えてください。

- 依頼ごとに `=== t1 ===` のような見出しを付けてから答えを書くこと
- 見出しの行には、答えを書かないこと
- 前置きや後書きは書かないこと

"""

HEADER_B = """次の6つの依頼に、それぞれ答えてください。
**各依頼には「出力の見本」が付いています。その形式に合わせて答えてください。**

- 依頼ごとに `=== t1 ===` のような見出しを付けてから答えを書くこと
- 見出しの行には、答えを書かないこと
- 前置きや後書きは書かないこと

"""

# C: 条件を言葉で書かず、見本だけを渡す。A(言葉だけ)と比べるための条件群。
HEADER_C = """次の6つの依頼に、それぞれ答えてください。
**各依頼には「出力の見本」が付いています。その形式に合わせて答えてください。**

- 依頼ごとに `=== t1 ===` のような見出しを付けてから答えを書くこと
- 見出しの行には、答えを書かないこと
- 前置きや後書きは書かないこと

"""


def lines_of(text):
    return [l.strip() for l in text.strip().splitlines() if l.strip()]


TASKS = [
    {
        "id": "t1",
        "request": "社内の定例会議(新商品の発売日を11月20日に決定、販促費は前年比120%、"
                   "担当は営業部)の議事録を、要点だけにまとめてください。",
        "conds": "・【要点】で始める\n・そのあと箇条書きを3行ちょうど\n"
                 "・箇条書きは1行40字以内\n・数字を1つ以上入れる",
        "example": "【要点】\n・発売日を12月3日に確定\n・広告費は前年の90%に圧縮\n・進行は企画部が担当",
        "checks": [
            ("【要点】で始まる", lambda t: t.strip().startswith("【要点】")),
            ("箇条書きが3行", lambda t: len([l for l in lines_of(t) if l.startswith("・")]) == 3),
            ("各行40字以内", lambda t: all(len(l) <= 40 for l in lines_of(t) if l.startswith("・"))),
            ("数字を含む", lambda t: bool(re.search(r"[0-9０-９]", t))),
        ],
    },
    {
        "id": "t2",
        "request": "取引先から「納期を1週間早められないか」と相談されました。"
                   "社内で検討してから回答する旨の返信メール本文を書いてください。",
        "conds": "・「お世話になっております。」で始める\n・全体150字以内\n"
                 "・空行を1つ以上入れる\n・「?」を使わない",
        "example": "お世話になっております。\n\nご相談の件、社内で確認のうえ、"
                   "明日中にご回答いたします。\nお待たせして恐縮ですが、よろしくお願いいたします。",
        "checks": [
            ("お世話になっておりますで始まる",
             lambda t: t.strip().startswith("お世話になっております")),
            ("150字以内", lambda t: len(t.strip().replace("\n", "")) <= 150),
            ("空行がある", lambda t: "\n\n" in t.strip()),
            ("?を使っていない", lambda t: "?" not in t and "？" not in t),
        ],
    },
    {
        "id": "t3",
        "request": "ノートパソコン用のスタンドを、通販サイトの商品説明として紹介してください。",
        "conds": "・1行目に商品名だけを書く\n・2行目以降に特徴を2行ちょうど\n"
                 "・特徴の行は「◎」で始める\n・全体120字以内",
        "example": "折りたたみノートPCスタンド\n◎6段階の高さ調整で姿勢をラクに\n◎厚さ1cm、カバンに入る軽さ",
        "checks": [
            ("1行目に◎が無い", lambda t: bool(lines_of(t)) and not lines_of(t)[0].startswith("◎")),
            ("◎の行が2行", lambda t: len([l for l in lines_of(t) if l.startswith("◎")]) == 2),
            ("全体3行", lambda t: len(lines_of(t)) == 3),
            ("120字以内", lambda t: len(t.strip().replace("\n", "")) <= 120),
        ],
    },
    {
        "id": "t4",
        "request": "新人向けに「報告・連絡・相談」の違いを説明してください。",
        "conds": "・3つの見出しを「■」で始める\n・各見出しの下に説明を1行\n"
                 "・説明は1行50字以内\n・全体で6行ちょうど",
        "example": "■報告\n終わった仕事の結果を伝えること\n■連絡\n決まった事実を関係者に知らせること\n"
                   "■相談\n判断に迷ったとき、先に意見をもらうこと",
        "checks": [
            ("■の行が3行", lambda t: len([l for l in lines_of(t) if l.startswith("■")]) == 3),
            ("全体6行", lambda t: len(lines_of(t)) == 6),
            ("説明が50字以内",
             lambda t: all(len(l) <= 50 for l in lines_of(t) if not l.startswith("■"))),
            ("■で始まる", lambda t: bool(lines_of(t)) and lines_of(t)[0].startswith("■")),
        ],
    },
    {
        "id": "t5",
        "request": "社内アンケート(回答数240件、満足と答えた人が62%、"
                   "最も多かった要望はリモート勤務の拡大)の結果を共有する文を書いてください。",
        "conds": "・1行目を「調査結果」とだけ書く\n・2行目以降は「-」で始まる3行\n"
                 "・各行に数字を1つ以上入れる\n・全体4行ちょうど",
        "example": "調査結果\n- 回答数は180件(回答率45%)\n- 満足と答えた人は71%\n- 要望の1位は会議時間の短縮(38件)",
        "checks": [
            ("1行目が調査結果", lambda t: bool(lines_of(t)) and lines_of(t)[0] == "調査結果"),
            ("-の行が3行", lambda t: len([l for l in lines_of(t) if l.startswith("-")]) == 3),
            ("各行に数字",
             lambda t: all(re.search(r"[0-9０-９]", l) for l in lines_of(t) if l.startswith("-"))),
            ("全体4行", lambda t: len(lines_of(t)) == 4),
        ],
    },
    {
        "id": "t6",
        "request": "「会議が長い」という社内の悩みに対して、改善案を出してください。",
        "conds": "・「案1:」「案2:」「案3:」の3行\n・各行60字以内\n"
                 "・各案に「分」という字を入れる\n・前置きを書かない",
        "example": "案1: 開始5分で目的を全員に共有してから進める\n"
                   "案2: 議題ごとに10分の持ち時間を決めて区切る\n"
                   "案3: 決定事項の確認に最後の5分を必ず残す",
        "checks": [
            ("案1案2案3がある",
             lambda t: all(f"案{i}:" in t or f"案{i}：" in t for i in (1, 2, 3))),
            ("全体3行", lambda t: len(lines_of(t)) == 3),
            ("各行60字以内", lambda t: all(len(l) <= 60 for l in lines_of(t))),
            ("分を含む", lambda t: all("分" in l for l in lines_of(t))),
        ],
    },
]


def build(side):
    """A=条件だけ / B=条件+見本 / C=見本だけ."""
    body = []
    for t in TASKS:
        block = [f"\n--- {t['id']} ---", f"依頼: {t['request']}"]
        if side in ("A", "B"):
            block.append(f"条件:\n{t['conds']}")
        if side in ("B", "C"):
            block.append(f"出力の見本:\n{t['example']}")
        body.append("\n".join(block) + "\n")
    head = {"A": HEADER_A, "B": HEADER_B, "C": HEADER_C}[side]
    return head + "".join(body)


SIDES = ("A", "B", "C")


def do_init(only=None):
    OUT_DIR.mkdir(exist_ok=True)
    RESP_DIR.mkdir(exist_ok=True)
    sides = SIDES if not only else [s for s in SIDES if s in only]
    for run in range(1, RUNS + 1):
        for side in sides:
            (OUT_DIR / f"{side}_run{run}.txt").write_text(build(side), encoding="utf-8")
    print(f"プロンプトを{RUNS * len(sides)}個 作りました: {OUT_DIR}")
    print("  A = 条件だけ / B = 条件+見本 / C = 見本だけ(依頼はすべて同じ)")
    print(f"\n次にやること({RUNS * len(sides)}回とも「新しいチャット」で):")
    for run in range(1, RUNS + 1):
        for side in sides:
            print(f"  touch experiment_responses/{side}_run{run}.txt && "
                  f"open -e experiment_out/{side}_run{run}.txt "
                  f"experiment_responses/{side}_run{run}.txt")
    print("\n  終わったら python3 experiment.py --score")


def split_answers(text):
    """=== t1 === 区切りで答えを切り出す."""
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^\s*=+\s*(t\d)\s*=+\s*$", line)
        if m:
            if cur:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        elif cur:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf)
    return out


def do_score():
    if not RESP_DIR.exists() or not any(RESP_DIR.glob("*.txt")):
        sys.exit(f"{RESP_DIR}/ に答えがありません。")

    by_side = {s: [] for s in SIDES}
    for path in sorted(RESP_DIR.glob("*.txt")):
        side = path.name[0].upper()
        if side not in by_side:
            continue
        answers = split_answers(path.read_text(encoding="utf-8", errors="replace"))
        if not answers:
            print(f"  [警告] {path.name}: === t1 === の区切りが見当たりません")
            continue
        by_side[side].append((path.name, answers))

    if not by_side["A"] or not by_side["B"]:
        sys.exit("AとBの両方が必要です。")

    present = [s for s in SIDES if by_side[s]]
    rows, totals = [], {s: [0, 0] for s in present}
    per_task = {t["id"]: {s: [0, 0] for s in present} for t in TASKS}
    for side in present:
        runs = by_side[side]
        for fname, answers in runs:
            for t in TASKS:
                ans = answers.get(t["id"], "")
                for name, fn in t["checks"]:
                    try:
                        ok = bool(ans.strip()) and bool(fn(ans))
                    except Exception:
                        ok = False
                    totals[side][0] += int(ok)
                    totals[side][1] += 1
                    per_task[t["id"]][side][0] += int(ok)
                    per_task[t["id"]][side][1] += 1
                    rows.append((side, fname, t["id"], name, ok))

    def pct(p):
        return f"{p[0]}/{p[1]} = {p[0] / p[1] * 100:.0f}%" if p[1] else "-"

    LABEL = {"A": "条件だけ(A)", "B": "条件+見本(B)", "C": "見本だけ(C)"}
    out = ["# 「出力の見本を示す」は効くのか — 実験レポート", "",
           "※experiment.py が自動生成しています。",
           "※採点はすべて機械判定(文字数・行数・前方一致)。AIには採点させていません。", "",
           "## 結果", ""]
    for s_ in present:
        out.append(f"- {LABEL[s_]}: **{pct(totals[s_])}**")
    out.append("")
    base = totals[present[0]]
    for s_ in present[1:]:
        d = (totals[s_][0] / totals[s_][1] - base[0] / base[1]) * 100
        out.append(f"- {LABEL[present[0]]} との差({LABEL[s_]}): **{d:+.0f}ポイント**")
    out += ["", "## 依頼ごと", "",
            "| 依頼 | " + " | ".join(LABEL[s_] for s_ in present) + " |",
            "|---" * (len(present) + 1) + "|"]
    for t in TASKS:
        p = per_task[t["id"]]
        out.append(f"| {t['id']} | " + " | ".join(pct(p[s_]) for s_ in present) + " |")

    out += ["", "## 外れた条件(どこで落ちたか)", ""]
    for side, fname, tid, name, ok in rows:
        if not ok:
            out.append(f"- [{side}] {tid} / {name}({fname})")

    (BASE / "experiment_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    for s_ in present:
        print(f"{LABEL[s_]}: {pct(totals[s_])}")
    print("\n出力: experiment_report.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="プロンプトを作る(A/B/C)")
    ap.add_argument("--only", default=None,
                    help="作る条件群を絞る(例: --only C)")
    ap.add_argument("--score", action="store_true", help="答えを読んで採点する")
    args = ap.parse_args()
    if args.init:
        do_init(args.only)
    elif args.score:
        do_score()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
