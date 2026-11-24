"""脳トレショートの問題データと出題ロジック.

問題はすべてこの表から機械的に作り、正解も機械的に確かめる。
(AIに問題を考えさせると、まれに「答えが2つある」「読み方が違う」問題が混ざるため)
"""

from collections import namedtuple

Pref = namedtuple("Pref", "name suffix reading capital capital_reading")

# 名前(都道府県を除く) / 都道府県 / 読み / 県庁所在地 / 県庁所在地の読み
PREFS = [Pref(*row) for row in [
    ("北海道", "", "ほっかいどう", "札幌", "さっぽろ"),
    ("青森", "県", "あおもり", "青森", "あおもり"),
    ("岩手", "県", "いわて", "盛岡", "もりおか"),
    ("宮城", "県", "みやぎ", "仙台", "せんだい"),
    ("秋田", "県", "あきた", "秋田", "あきた"),
    ("山形", "県", "やまがた", "山形", "やまがた"),
    ("福島", "県", "ふくしま", "福島", "ふくしま"),
    ("茨城", "県", "いばらき", "水戸", "みと"),
    ("栃木", "県", "とちぎ", "宇都宮", "うつのみや"),
    ("群馬", "県", "ぐんま", "前橋", "まえばし"),
    ("埼玉", "県", "さいたま", "さいたま", "さいたま"),
    ("千葉", "県", "ちば", "千葉", "ちば"),
    ("東京", "都", "とうきょう", "東京", "とうきょう"),
    ("神奈川", "県", "かながわ", "横浜", "よこはま"),
    ("新潟", "県", "にいがた", "新潟", "にいがた"),
    ("富山", "県", "とやま", "富山", "とやま"),
    ("石川", "県", "いしかわ", "金沢", "かなざわ"),
    ("福井", "県", "ふくい", "福井", "ふくい"),
    ("山梨", "県", "やまなし", "甲府", "こうふ"),
    ("長野", "県", "ながの", "長野", "ながの"),
    ("岐阜", "県", "ぎふ", "岐阜", "ぎふ"),
    ("静岡", "県", "しずおか", "静岡", "しずおか"),
    ("愛知", "県", "あいち", "名古屋", "なごや"),
    ("三重", "県", "みえ", "津", "つ"),
    ("滋賀", "県", "しが", "大津", "おおつ"),
    ("京都", "府", "きょうと", "京都", "きょうと"),
    ("大阪", "府", "おおさか", "大阪", "おおさか"),
    ("兵庫", "県", "ひょうご", "神戸", "こうべ"),
    ("奈良", "県", "なら", "奈良", "なら"),
    ("和歌山", "県", "わかやま", "和歌山", "わかやま"),
    ("鳥取", "県", "とっとり", "鳥取", "とっとり"),
    ("島根", "県", "しまね", "松江", "まつえ"),
    ("岡山", "県", "おかやま", "岡山", "おかやま"),
    ("広島", "県", "ひろしま", "広島", "ひろしま"),
    ("山口", "県", "やまぐち", "山口", "やまぐち"),
    ("徳島", "県", "とくしま", "徳島", "とくしま"),
    ("香川", "県", "かがわ", "高松", "たかまつ"),
    ("愛媛", "県", "えひめ", "松山", "まつやま"),
    ("高知", "県", "こうち", "高知", "こうち"),
    ("福岡", "県", "ふくおか", "福岡", "ふくおか"),
    ("佐賀", "県", "さが", "佐賀", "さが"),
    ("長崎", "県", "ながさき", "長崎", "ながさき"),
    ("熊本", "県", "くまもと", "熊本", "くまもと"),
    ("大分", "県", "おおいた", "大分", "おおいた"),
    ("宮崎", "県", "みやざき", "宮崎", "みやざき"),
    ("鹿児島", "県", "かごしま", "鹿児島", "かごしま"),
    ("沖縄", "県", "おきなわ", "那覇", "なは"),
]]
assert len(PREFS) == 47
BY_NAME = {p.name: p for p in PREFS}
SUFFIX_READING = {"県": "けん", "府": "ふ", "都": "と", "": ""}

# 県庁所在地クイズのひっかけ用。同じ都道府県にある「県庁所在地ではない」有名な市。
OTHER_CITIES = {
    "北海道": ["函館", "旭川", "小樽"],
    "岩手": ["花巻", "一関", "宮古"],
    "宮城": ["石巻", "気仙沼", "名取"],
    "茨城": ["つくば", "日立", "土浦"],
    "栃木": ["日光", "足利", "小山"],
    "群馬": ["高崎", "桐生", "太田"],
    "埼玉": ["川越", "所沢", "川口"],
    "神奈川": ["川崎", "相模原", "鎌倉"],
    "石川": ["小松", "輪島", "加賀"],
    "山梨": ["富士吉田", "甲斐", "笛吹"],
    "愛知": ["豊田", "岡崎", "一宮"],
    "三重": ["四日市", "伊勢", "鈴鹿"],
    "滋賀": ["彦根", "草津", "長浜"],
    "兵庫": ["姫路", "西宮", "尼崎"],
    "島根": ["出雲", "浜田", "益田"],
    "香川": ["丸亀", "坂出", "観音寺"],
    "愛媛": ["今治", "宇和島", "新居浜"],
    "沖縄": ["沖縄", "名護", "浦添"],
}
# 県名と県庁所在地の名前が違うところだけ出す(同じだとクイズにならない。東京は除外)
CAPITAL_QUIZ = [BY_NAME[n] for n in OTHER_CITIES]

SMALL_KANA = set("ぁぃぅぇぉゃゅょっゎー")
PREF_KANJI = set("".join(p.name for p in PREFS))
# 漢字マスの「はずれ」用。県名に使われていない、なじみのある漢字
EASY_KANJI = [k for k in (
    "花空海雪星月日火水金土光風雲雨春夏冬朝夜南西町村林竹松梅桜"
    "白赤黒緑銀中上下犬猫魚貝虫羊牛豆米麦茶糸色音楽歌絵門橋池港駅"
) if k not in PREF_KANJI]


# ---------------------------------------------------------------------------
# 漢字かくれんぼ: マスの中に都道府県が n 個かくれている
# ---------------------------------------------------------------------------
def find_in_grid(grid):
    """たて(上→下)・よこ(左→右)に読める都道府県を全部探す."""
    size = len(grid)
    found = []
    lines = []
    for r in range(size):
        lines.append([(r, c) for c in range(size)])
    for c in range(size):
        lines.append([(r, c) for r in range(size)])
    for cells in lines:
        text = "".join(grid[r][c] for r, c in cells)
        for p in PREFS:
            start = text.find(p.name)
            while start != -1:
                found.append((p.name, tuple(cells[start:start + len(p.name)])))
                start = text.find(p.name, start + 1)
    return found


def make_kanji_grid(rng, n_answers=3, size=4, tricky=True, avoid=()):
    """答えがちょうど n_answers 個になるマスを作る. 返り値: (grid, [(Pref, cells), ...])."""
    two = [p for p in PREFS if len(p.name) == 2]
    for _ in range(5000):
        answers = rng.sample(two, n_answers)
        key = ",".join(sorted(p.name for p in answers))
        if key in avoid:
            continue
        chars = [ch for p in answers for ch in p.name]
        if len(set(chars)) != len(chars):      # 答えどうしで同じ漢字を使わない(紛らわしい)
            continue
        grid = [[None] * size for _ in range(size)]
        placed = []
        for p in answers:
            for _ in range(200):
                if rng.random() < 0.5:
                    r, c = rng.randrange(size), rng.randrange(size - 1)
                    cells = ((r, c), (r, c + 1))
                else:
                    r, c = rng.randrange(size - 1), rng.randrange(size)
                    cells = ((r, c), (r + 1, c))
                if all(grid[y][x] is None for y, x in cells):
                    for (y, x), ch in zip(cells, p.name):
                        grid[y][x] = ch
                    placed.append((p, cells))
                    break
            else:
                break
        if len(placed) != n_answers:
            continue
        # 残りのマス。tricky なら県名に使われる漢字も混ぜて「おしい!」を作る
        pool = list(EASY_KANJI)
        if tricky:
            pool += [k for k in PREF_KANJI if k not in chars]
        pool = [k for k in pool if k not in chars]
        rng.shuffle(pool)
        empties = [(y, x) for y in range(size) for x in range(size) if grid[y][x] is None]
        for (y, x), k in zip(empties, pool):
            grid[y][x] = k
        found = find_in_grid(grid)
        want = sorted((p.name, cells) for p, cells in placed)
        if sorted(found) == want:          # 答えはちょうどこれだけ(余計な県が出来ていない)
            return grid, placed
    raise RuntimeError("漢字マスが作れませんでした")


# ---------------------------------------------------------------------------
# ならべかえ: ひらがなを並べ替えると都道府県
# ---------------------------------------------------------------------------
READINGS = {p.reading for p in PREFS}


def anagram_candidates():
    return [p for p in PREFS
            if 3 <= len(p.reading) <= 5 and not (set(p.reading) & SMALL_KANA)]


def make_anagram(rng, pref):
    """並べ替え順 perm を返す(表示位置 i に reading[perm[i]] を置く)."""
    n = len(pref.reading)
    for _ in range(500):
        perm = list(range(n))
        rng.shuffle(perm)
        fixed = sum(1 for i, j in enumerate(perm) if i == j)
        shown = "".join(pref.reading[j] for j in perm)
        if fixed <= (n - 1) // 3 and shown != pref.reading and shown not in READINGS:
            return perm
    raise RuntimeError(f"{pref.name} の並べ替えが作れませんでした")


# ---------------------------------------------------------------------------
# 頭文字クイズ: 「お」で始まる4文字の都道府県は?(小さい「っ」「ょ」も1文字と数える)
# ---------------------------------------------------------------------------
def initial_patterns(min_answers=2, max_answers=6):
    pats = {}
    for p in PREFS:
        n = len(p.reading)
        pats.setdefault(("head", p.reading[0], n), []).append(p)
        pats.setdefault(("tail", p.reading[-1], n), []).append(p)
    out = []
    for (pos, ch, n), ps in sorted(pats.items()):
        if ch in SMALL_KANA:
            continue
        if min_answers <= len(ps) <= max_answers:
            out.append((pos, ch, n, ps))
    return out


def capital_options(rng, pref):
    """県庁所在地の3択. 返り値: (選択肢の市名リスト, 正解の位置)."""
    wrong = rng.sample(OTHER_CITIES[pref.name], 2)
    opts = [pref.capital] + wrong
    rng.shuffle(opts)
    return opts, opts.index(pref.capital)


if __name__ == "__main__":
    # 自己チェック: データの整合性と出題ロジックを確かめる
    import random
    assert all(p.name in OTHER_CITIES or p.capital == p.name or p.name == "東京" for p in PREFS)
    for p in CAPITAL_QUIZ:
        assert p.capital not in OTHER_CITIES[p.name], p
    rng = random.Random(1)
    for i in range(300):
        g, ans = make_kanji_grid(rng, tricky=bool(i % 2))
        assert len(ans) == 3
    for p in anagram_candidates():
        perm = make_anagram(rng, p)
        assert sorted(perm) == list(range(len(p.reading)))
    pats = initial_patterns()
    print("漢字マス: 300問OK / 並べ替え候補:", len(anagram_candidates()),
          "/ 県庁所在地:", len(CAPITAL_QUIZ), "/ 頭文字パターン:", len(pats))
    for pos, ch, n, ps in pats:
        print(" ", "始まる" if pos == "head" else "終わる", ch, n, "文字:", "・".join(p.reading for p in ps))
