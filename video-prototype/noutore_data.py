"""脳トレショートの問題データと出題ロジック.

問題はすべてこの表から機械的に作り、正解も機械的に確かめる。
(AIに問題を考えさせると、まれに「答えが2つある」「読み方が違う」問題が混ざるため)
"""

from collections import Counter, namedtuple

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
DIRS_STRAIGHT = ((0, 1), (1, 0))          # よこ(左→右) / たて(上→下)
DIRS_DIAG = ((1, 1), (1, -1))              # ななめ(右下へ) / ななめ(左下へ)
ALL_DIRS = DIRS_STRAIGHT + DIRS_DIAG


def grid_lines(size, dirs=ALL_DIRS):
    lines = []
    for dr, dc in dirs:
        for r in range(size):
            for c in range(size):
                if 0 <= r - dr < size and 0 <= c - dc < size:
                    continue                       # 線の途中のマスは始点にしない
                cells, y, x = [], r, c
                while 0 <= y < size and 0 <= x < size:
                    cells.append((y, x))
                    y, x = y + dr, x + dc
                if len(cells) >= 2:
                    lines.append(cells)
    return lines


def find_in_grid(grid, dirs=ALL_DIRS):
    """たて・よこ・ななめに読める都道府県を全部探す(上から下・左から右に読む)."""
    size = len(grid)
    found = []
    for cells in grid_lines(size, dirs):
        text = "".join(grid[r][c] for r, c in cells)
        for p in PREFS:
            start = text.find(p.name)
            while start != -1:
                found.append((p.name, tuple(cells[start:start + len(p.name)])))
                start = text.find(p.name, start + 1)
    return found


def make_kanji_grid(rng, n_answers=3, size=4, tricky=True, avoid=(), diagonal=False, three=False):
    """答えがちょうど n_answers 個になるマスを作る. 返り値: (grid, [(Pref, cells), ...]).

    diagonal=True なら、答えのうち1つ以上をななめに置く(ルールに「ななめ」を書く)。
    どのレベルでも、たて・よこ・ななめの全方向で「余計な県」が出来ていないか確かめる。
    """
    two = [p for p in PREFS if len(p.name) == 2]
    threes = [p for p in PREFS if len(p.name) == 3]
    dirs = ALL_DIRS if diagonal else DIRS_STRAIGHT
    for _ in range(30000):
        k3 = 1 if (three and rng.random() < 0.5) else 0
        answers = rng.sample(threes, k3) + rng.sample(two, n_answers - k3)
        key = ",".join(sorted(p.name for p in answers))
        if key in avoid:
            continue
        chars = [ch for p in answers for ch in p.name]
        if len(set(chars)) != len(chars):      # 答えどうしで同じ漢字を使わない(紛らわしい)
            continue
        grid = [[None] * size for _ in range(size)]
        placed = []
        for idx, p in enumerate(answers):
            for _ in range(300):
                dr, dc = rng.choice(DIRS_DIAG if (diagonal and idx == 0) else dirs)
                r, c = rng.randrange(size), rng.randrange(size)
                cells = tuple((r + i * dr, c + i * dc) for i in range(len(p.name)))
                if all(0 <= y < size and 0 <= x < size and grid[y][x] is None for y, x in cells):
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
            pool += [k for k in sorted(PREF_KANJI) if k not in chars]   # sorted: 毎回同じ問題を再現できるように
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


KANA_POOL = list("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわ"
                 "がぎぐげござじずぜぞだでどばびぶべぼ")


def _fits(word, cnt):
    """word の文字が cnt(手持ちの文字)で全部作れるか."""
    return all(cnt[ch] >= n for ch, n in Counter(word).items())


def make_anagram_extra(rng, pref):
    """1文字あまる並べ替え. 返り値: (表示順の文字リスト, あまる文字の位置)."""
    rd = pref.reading
    for _ in range(2000):
        extra = rng.choice([k for k in KANA_POOL if k not in rd])
        tiles = list(rd) + [extra]
        cnt = Counter(tiles)
        # 「1文字あまる」ので、同じ文字数のほかの県が作れたら答えが2つになる
        if any(len(p.reading) == len(rd) and _fits(p.reading, cnt) for p in PREFS if p is not pref):
            continue
        rng.shuffle(tiles)
        shown = "".join(tiles)
        if any(p.reading in shown for p in PREFS):
            continue                       # 並べ替えずに読めてしまう
        return tiles, tiles.index(extra)
    raise RuntimeError(f"{pref.name} の1文字あまり問題が作れませんでした")


def anagram_pairs(min_len=6, max_len=8):
    simple = [p for p in PREFS if not (set(p.reading) & SMALL_KANA)]
    out = []
    for i, p in enumerate(simple):
        for q in simple[i + 1:]:
            if min_len <= len(p.reading) + len(q.reading) <= max_len:
                out.append((p, q))
    return out


def pair_is_unique(p, q):
    """この文字の組で作れる「2つの県」の組み合わせが1通りだけか."""
    target = Counter(p.reading + q.reading)
    hits = 0
    for i, a in enumerate(PREFS):
        for b in PREFS[i + 1:]:
            if len(a.reading) + len(b.reading) == sum(target.values()) and \
                    Counter(a.reading + b.reading) == target:
                hits += 1
    return hits == 1


def make_anagram_pair(rng, p, q):
    """2つの県がまざった並べ替え. 返り値: 表示順の (文字, 0=p/1=q, 何文字目) のリスト."""
    tiles = [(ch, 0, i) for i, ch in enumerate(p.reading)] + [(ch, 1, i) for i, ch in enumerate(q.reading)]
    for _ in range(2000):
        rng.shuffle(tiles)
        shown = "".join(t[0] for t in tiles)
        if not any(x.reading in shown for x in PREFS):
            return list(tiles)
    raise RuntimeError(f"{p.name}+{q.name} の並べ替えが作れませんでした")


# ---------------------------------------------------------------------------
# 県庁所在地(中級: まちがえやすい市どうしの3択 / 上級: 市から県を当てる4択)
# ---------------------------------------------------------------------------
CAPITAL_HARD = ["岩手", "宮城", "茨城", "栃木", "群馬", "石川", "山梨", "三重", "滋賀",
                "兵庫", "島根", "香川", "愛媛"]
# ひっかけに使う「ほかの県の県庁所在地」(名前が県名と違って、まぎらわしいもの)
CONFUSE_CAPITALS = {
    "岩手": ["仙台", "水戸", "前橋"],
    "宮城": ["盛岡", "水戸", "宇都宮"],
    "茨城": ["宇都宮", "前橋", "盛岡"],
    "栃木": ["前橋", "水戸", "甲府"],
    "群馬": ["宇都宮", "水戸", "甲府"],
    "石川": ["甲府", "大津", "松江"],
    "山梨": ["前橋", "金沢", "宇都宮"],
    "三重": ["大津", "神戸", "松江"],
    "滋賀": ["津", "神戸", "金沢"],
    "兵庫": ["大津", "津", "松江"],
    "島根": ["松山", "高松", "大津"],
    "香川": ["松山", "松江", "津"],
    "愛媛": ["高松", "松江", "前橋"],
}
# 市から県を当てるときの選択肢(となり・近くの県)
NEIGHBORS = {
    "岩手": ["宮城", "秋田", "青森"],
    "宮城": ["岩手", "山形", "福島"],
    "茨城": ["栃木", "群馬", "千葉"],
    "栃木": ["茨城", "群馬", "埼玉"],
    "群馬": ["栃木", "茨城", "埼玉"],
    "石川": ["富山", "福井", "岐阜"],
    "山梨": ["長野", "静岡", "埼玉"],
    "三重": ["滋賀", "奈良", "和歌山"],
    "滋賀": ["三重", "京都", "福井"],
    "兵庫": ["大阪", "京都", "岡山"],
    "島根": ["鳥取", "山口", "広島"],
    "香川": ["愛媛", "徳島", "高知"],
    "愛媛": ["香川", "高知", "徳島"],
}
BY_CAPITAL = {p.capital: p for p in PREFS}


def capital_options_hard(rng, pref):
    """まちがえやすい3択. 返り値: (市名リスト, 正解の位置)."""
    opts = [pref.capital] + rng.sample(CONFUSE_CAPITALS[pref.name], 2)
    rng.shuffle(opts)
    return opts, opts.index(pref.capital)


def city_to_pref_options(rng, pref):
    """市 → 県の4択. 返り値: (Prefリスト, 正解の位置)."""
    opts = [pref] + [BY_NAME[n] for n in NEIGHBORS[pref.name]]
    rng.shuffle(opts)
    return opts, opts.index(pref)


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


KANJI_READ = {"山": "やま", "島": "しま", "川": "かわ", "福": "ふく", "岡": "おか"}


def free_patterns(min_answers, max_answers):
    """文字数を決めない出題. ("head_any"|"tail_any"|"kanji", 文字, [Pref...]) のリスト.

    head_any: 「と」で始まる都道府県 / tail_any: 「た」で終わる / kanji: 「山」がつく
    """
    pats = {}
    for p in PREFS:
        pats.setdefault(("head_any", p.reading[0]), []).append(p)
        pats.setdefault(("tail_any", p.reading[-1]), []).append(p)
    for k in KANJI_READ:
        pats[("kanji", k)] = [p for p in PREFS if k in p.name]
    out = []
    for (kind, ch), ps in sorted(pats.items()):
        if ch in SMALL_KANA:
            continue
        if min_answers <= len(ps) <= max_answers:
            out.append((kind, ch, ps))
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
    for i in range(200):
        g, ans = make_kanji_grid(rng, n_answers=4, size=5, diagonal=True, three=True)
        assert len(ans) == 4 and any(abs(c[1][1] - c[0][1]) == 1 and c[1][0] - c[0][0] == 1
                                     for _, c in ans), "ななめの答えがない"
        assert sorted(find_in_grid(g)) == sorted((p.name, c) for p, c in ans)
    for p in anagram_candidates():
        if 4 <= len(p.reading):
            tiles, ex = make_anagram_extra(rng, p)
            assert sorted(tiles[:ex] + tiles[ex + 1:]) == sorted(p.reading)
    pairs = [pq for pq in anagram_pairs() if pair_is_unique(*pq)]
    for p, q in pairs[:40]:
        make_anagram_pair(rng, p, q)
    for n, wrong in CONFUSE_CAPITALS.items():
        assert all(w in BY_CAPITAL and BY_CAPITAL[w].name != n for w in wrong), n
    for n, nb in NEIGHBORS.items():
        assert n not in nb and all(x in BY_NAME for x in nb), n
    print("上級マス(5x5・ななめ): 200問OK / 1文字あまり: OK / 2県まざり(答えが1通り):",
          len(pairs), "組 / まぎらわしい県庁所在地:", len(CAPITAL_HARD))
    for kind, ch, ps in free_patterns(3, 6):
        print("  ", kind, ch, len(ps), "つ:", "・".join(p.name for p in ps))
    pats = initial_patterns()
    print("漢字マス: 300問OK / 並べ替え候補:", len(anagram_candidates()),
          "/ 県庁所在地:", len(CAPITAL_QUIZ), "/ 頭文字パターン:", len(pats))
    for pos, ch, n, ps in pats:
        print(" ", "始まる" if pos == "head" else "終わる", ch, n, "文字:", "・".join(p.reading for p in ps))
