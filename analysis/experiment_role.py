#!/usr/bin/env python3
"""「AIに役割を与える」は本当に効くのかを、数えて確かめる(第7回).

第6回の experiment.py は「形の条件を守れたか」を測った。
役割(「あなたは◯◯です」)は形ではなく中身を変えるための技なので、
**役割を与えたら、出力がその役割らしい方向に動くか** を数える。

    python3 experiment_role.py --init     # プロンプト A(役割なし)/ B(役割あり)を作る
    python3 experiment_role.py --score    # 答えを読んで判定する

A と B の違いは、各依頼の頭に「あなたは◯◯です。」が1行あるかどうかだけ。
数えるのはすべて機械的な値(漢字の割合・行数・数字を含む行の数など)。
**3回とも予想の方向に動いたものだけを「効いた」と呼ぶ。**
"""

import argparse
import re
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "experiment_role_out"
RESP_DIR = BASE / "experiment_role_responses"
RUNS = 3

HEADER = """次の4つの依頼に、それぞれ答えてください。

- 依頼ごとに `=== t1 ===` のような見出しを付けてから答えを書くこと
- 見出しの行には、答えを書かないこと
- 答えは箇条書き(各行を「・」で始める)で書くこと
- 前置きや後書きは書かないこと

"""


# ---- 数える関数 ------------------------------------------------------------
def lines_of(text):
    return [l.strip() for l in text.strip().splitlines() if l.strip()]


def bullets(text):
    return [l for l in lines_of(text) if re.match(r"^([・\-\*•]|\d+[\.\)．、])", l)]


def kanji_ratio(text):
    """漢字 /(漢字+ひらがな+カタカナ). 低いほどやさしい文章."""
    k = len(re.findall(r"[一-鿿々]", text))
    kana = len(re.findall(r"[぀-ヿ]", text))
    return k / (k + kana) if (k + kana) else 0.0


def avg_len(text):
    bl = bullets(text) or lines_of(text)
    return statistics.mean(len(l) for l in bl) if bl else 0.0


def n_bullets(text):
    return len(bullets(text))


def n_digit_lines(text):
    return len([l for l in bullets(text) if re.search(r"[0-9０-９]", l)])


TASKS = [
    {
        "id": "t1",
        "request": "インフレとは何かを説明してください。",
        "role": "あなたは小学校の先生です。",
        "metrics": [
            ("漢字の割合", kanji_ratio, "down", "{:.0%}"),
            ("1行の平均文字数", avg_len, "down", "{:.1f}字"),
        ],
    },
    {
        "id": "t2",
        "request": "次の文章の問題点を挙げてください。\n"
                   "「弊社の新サービスは、お客様にとって非常に便利で、使いやすく、"
                   "様々な場面で活用でき、今後もさらに改善していく予定であり、ぜひご利用ください。」",
        "role": "あなたは厳しい編集者です。",
        "metrics": [("指摘の数", n_bullets, "up", "{:.0f}個")],
    },
    {
        "id": "t3",
        "request": "社内で、週1回・全員参加の朝会を新しく始めます。考えられる問題点を挙げてください。",
        "role": "あなたは慎重なリスク管理の担当者です。",
        "metrics": [("挙げた問題の数", n_bullets, "up", "{:.0f}個")],
    },
    {
        "id": "t4",
        "request": "会議を短くする方法を挙げてください。",
        "role": "あなたは会議の進行を20年やってきたプロです。",
        "metrics": [("数字が入った行の数", n_digit_lines, "up", "{:.0f}行")],
    },
]


def build(with_role):
    body = []
    for t in TASKS:
        block = [f"\n--- {t['id']} ---"]
        if with_role:
            block.append(t["role"])
        block.append(f"依頼: {t['request']}")
        body.append("\n".join(block) + "\n")
    return HEADER + "".join(body)


def do_init():
    OUT_DIR.mkdir(exist_ok=True)
    RESP_DIR.mkdir(exist_ok=True)
    for run in range(1, RUNS + 1):
        (OUT_DIR / f"A_run{run}.txt").write_text(build(False), encoding="utf-8")
        (OUT_DIR / f"B_run{run}.txt").write_text(build(True), encoding="utf-8")
    print(f"プロンプトを{RUNS * 2}個 作りました: {OUT_DIR}")
    print("  A = 役割なし / B = 役割あり(違いは「あなたは◯◯です。」の1行だけ)")
    print(f"\n次にやること({RUNS * 2}回とも「新しいチャット」で):")
    for run in range(1, RUNS + 1):
        for side in ("A", "B"):
            print(f"  touch experiment_role_responses/{side}_run{run}.txt && "
                  f"open -e experiment_role_out/{side}_run{run}.txt "
                  f"experiment_role_responses/{side}_run{run}.txt")
    print("\n  終わったら python3 experiment_role.py --score")


def split_answers(text):
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
    if not RESP_DIR.exists():
        sys.exit(f"{RESP_DIR}/ がありません。先に --init してください。")
    runs = {}
    for path in sorted(RESP_DIR.glob("*.txt")):
        m = re.match(r"^([AB])_run(\d+)\.txt$", path.name)
        if not m:
            continue
        ans = split_answers(path.read_text(encoding="utf-8", errors="replace"))
        if not ans:
            print(f"  [警告] {path.name}: === t1 === の区切りが見当たりません")
            continue
        runs.setdefault(int(m.group(2)), {})[m.group(1)] = ans
    pairs = sorted(r for r, v in runs.items() if "A" in v and "B" in v)
    if not pairs:
        sys.exit("A と B がそろった回がありません。")

    out = ["# 「AIに役割を与える」は効くのか — 実験レポート", "",
           "※experiment_role.py が自動生成しています。",
           "※判定はすべて機械的な値。AIには採点させていません。",
           f"※比べた回数: {len(pairs)}回(各回、A と B を同じ回どうしで比べる)", "",
           "## 判定ルール", "",
           f"- {len(pairs)}回とも予想の方向に動いた → **効いた**",
           "- 半分以上 → 傾向あり",
           "- それ以下 → 効いていない", "",
           "## 結果", "",
           "| 依頼 | 役割 | 数えたもの | 予想 | 役割なし(平均) | 役割あり(平均) | 予想どおりの回 | 判定 |",
           "|---|---|---|---|---|---|---|---|"]
    summary = []
    for t in TASKS:
        for name, fn, direction, fmt in t["metrics"]:
            a_vals, b_vals, hits = [], [], 0
            for r in pairs:
                a = fn(runs[r]["A"].get(t["id"], ""))
                b = fn(runs[r]["B"].get(t["id"], ""))
                a_vals.append(a)
                b_vals.append(b)
                if (direction == "up" and b > a) or (direction == "down" and b < a):
                    hits += 1
            n = len(pairs)
            verdict = "**効いた**" if hits == n else ("傾向あり" if hits * 2 >= n else "効いていない")
            arrow = "増える" if direction == "up" else "減る"
            ma, mb = statistics.mean(a_vals), statistics.mean(b_vals)
            out.append(f"| {t['id']} | {t['role']} | {name} | {arrow} | "
                       f"{fmt.format(ma)} | {fmt.format(mb)} | {hits}/{n} | {verdict} |")
            summary.append((t["id"], name, fmt.format(ma), fmt.format(mb), hits, n,
                            verdict.replace("*", "")))

    out += ["", "## 回ごとの値(確認用)", ""]
    for t in TASKS:
        for name, fn, _, fmt in t["metrics"]:
            vals = []
            for r in pairs:
                a = fn(runs[r]["A"].get(t["id"], ""))
                b = fn(runs[r]["B"].get(t["id"], ""))
                vals.append(f"run{r}: {fmt.format(a)} → {fmt.format(b)}")
            out.append(f"- {t['id']} {name}: " + " / ".join(vals))

    (BASE / "experiment_role_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    for tid, name, ma, mb, hits, n, v in summary:
        print(f"{tid} {name}: 役割なし {ma} → 役割あり {mb}  ({hits}/{n}回 予想どおり) {v}")
    print("\n出力: experiment_role_report.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="プロンプトを作る")
    ap.add_argument("--score", action="store_true", help="答えを読んで判定する")
    args = ap.parse_args()
    if args.init:
        do_init()
    elif args.score:
        do_score()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
