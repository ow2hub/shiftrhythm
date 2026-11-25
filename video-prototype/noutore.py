#!/usr/bin/env python3
"""脳トレショート自動生成 — 1問10〜13秒の縦型動画(1080x1920)をまとめて作る.

使い方(video-prototype フォルダで):
    python3 noutore.py --sample                       # 4形式 × ★★/★★★ の見本
    python3 noutore.py --count 21 --start 2026-12-01  # 1週間分(1日3本: 7時/12時/18時)

むずかしさ(--level で全部そろえることもできる):
    ★   かんたん  : 4x4に3つ / 1つの県の並べ替え / 同じ県の市から3択 / 「お□□□」
    ★★  ふつう    : 5x5に4つ / 1文字あまる並べ替え / まぎらわしい県庁所在地の3択 / 答え3〜4つ
    ★★★ むずかしい: 5x5に4つ(ななめあり) / 2つの県がまざった並べ替え / 市から県を当てる4択 / 答え4〜6つ
    省略時は 7時・12時=★★、18時=★★★

比較テスト用のオプション:
    --voice A|B      声のセット(A=いつもの2人 / B=ゆっくり落ち着いた声)
    --no-bgm         BGMなし
    --engine auto|voicevox|openjtalk

出力: build/noutore/<開始日 or sample>/
    *.mp4              ファイル名がそのままYouTubeのタイトルになる
    アップロード手順.txt  予約投稿の時刻と、概要欄に貼る文

1本の流れ(どの形式も共通):
    0秒   問題がもう出ている(タイトル画面なし) + ノアが読み上げ
    →     カウントダウン(時計の音)。途中でメイ先生のヒント
    →     「正解は…」→ 答えが1つずつ光る(ピンポン + 紙ふぶき)
    →     「何秒でわかった?」→ 最初の画面に戻ってループ
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import subprocess
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import build_video as bv
import noutore_data as nd

W, H = 1080, 1920
FPS = 30
RATE = 48000
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "noutore_state.json"

INK, PINK, YELLOW, MINT, SKY, PURPLE, WHITE = (
    bv.INK, bv.PINK, bv.YELLOW, bv.MINT, bv.SKY, bv.PURPLE, bv.WHITE)
BG = (255, 248, 232)
DOT = (255, 232, 196)
GRAY = (214, 216, 224)
GRAY_TEXT = (150, 152, 166)
RED = (234, 64, 72)
ORANGE = (255, 146, 84)
HINT_FILL = (255, 228, 120)
ANSWER_COLORS = [PINK, SKY, MINT, PURPLE, ORANGE, YELLOW]

KINDS = {
    "grid":    {"label": "漢字かくれんぼ", "color": PINK},
    "anagram": {"label": "ならべかえ",     "color": SKY},
    "capital": {"label": "県庁所在地",     "color": MINT},
    "initial": {"label": "頭文字クイズ",   "color": PURPLE},
}
# むずかしさ(★の数)ごとの考える時間(秒)と、ヒントを出すタイミング(考える時間の何割で出すか)
COUNTS = {"grid": (5, 6, 7), "anagram": (5, 6, 7), "capital": (5, 5, 6), "initial": (6, 7, 7)}
HINT_AT = (0.5, 0.65, 0.75)
# 時間帯ごとに形式を固定すると「12時はならべかえ」と習慣になる(伸びている脳トレch の型)
# (時刻, 形式, ★の数)。夕方は時間のある人が多いので難しめにする
SLOTS = [("07:00", ["grid"], 2), ("12:00", ["anagram", "initial"], 2), ("18:00", ["capital"], 3)]

# 声のセット。VOICEVOX のキャラ名とスタイル名で指定する(IDは起動中のVOICEVOXから引く)。
# 別のキャラに変えるときは、そのキャラの利用規約を確認し、概要欄のクレジットも書き換えること。
VOICE_SETS = {
    "A": {   # いつもの2人。少し抑揚を強めてテンポよく
        "noa": {"name": "春日部つむぎ", "style": "ノーマル", "id": 8,
                "speed": 1.05, "intonation": 1.25, "pitch": 0.0},
        "mei": {"name": "四国めたん", "style": "ノーマル", "id": 2,
                "speed": 1.0, "intonation": 1.15, "pitch": 0.0},
    },
    "B": {   # ゆっくり・やわらかめ(年配の人が聞き取りやすいかの比較用)
        "noa": {"name": "春日部つむぎ", "style": "ノーマル", "id": 8,
                "speed": 0.92, "intonation": 1.0, "pitch": -0.02},
        "mei": {"name": "四国めたん", "style": "あまあま", "id": 0,
                "speed": 0.9, "intonation": 0.95, "pitch": -0.03},
    },
}
CREDITS = "VOICEVOX:春日部つむぎ\nVOICEVOX:四国めたん"

VOICE_GAIN, SFX_GAIN, BGM_GAIN = 1.0, 0.42, 0.11
OJT_SPEEDUP = 1.2         # 仮の声(Open JTalk)はゆっくりなので少し速める
LOOP_FADE = 0.35          # 最後の何秒で最初の画面に戻すか(ループ再生をなめらかに)

# 画面レイアウト(Shortsの右側ボタンと下のタイトル欄にかからない範囲に収める)
HEADER_Y = 250
Q_Y = (372, 466)
BANNER_Y = 1180
RING = (540, 1322, 80)
CHAR_SIZE = 360
CHAR_POS = {"noa": (30, 1185), "mei": (610, 1185)}


# ---------------------------------------------------------------------------
# 小物
# ---------------------------------------------------------------------------
def fnt(size):
    return bv.font(bv.FONT_BOLD, size)


def clamp01(p):
    return 0.0 if p < 0 else 1.0 if p > 1 else p


def ease_out_back(p, s=1.9):
    p = clamp01(p) - 1
    return p * p * ((s + 1) * p + s) + 1


def ease_io(p):
    p = clamp01(p)
    return p * p * (3 - 2 * p)


def pop_scale(t, t0, dur=0.32):
    """t0 から dur 秒かけて 0→1(少し行き過ぎて戻る)."""
    if t < t0:
        return 0.0
    return ease_out_back((t - t0) / dur)


def with_alpha(spr, alpha):
    if alpha >= 0.999:
        return spr
    s = spr.copy()
    s.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
    return s


def paste_center(base, spr, cx, cy, scale=1.0, sx=None, alpha=1.0):
    sxv = scale if sx is None else sx
    if scale <= 0.02 or sxv <= 0.02 or alpha <= 0.01:
        return
    w, h = spr.size
    nw, nh = max(1, int(w * sxv)), max(1, int(h * scale))
    s = spr if (nw, nh) == (w, h) else spr.resize((nw, nh), Image.BILINEAR)
    s = with_alpha(s, alpha)
    base.paste(s, (int(cx - nw / 2), int(cy - nh / 2)), s)


def rich_sprite(segs, size, stroke=9):
    """色つきの1行([(文字, 色), ...])を白ふちつきで描く."""
    f = fnt(size)
    total = sum(f.getlength(s) for s, _ in segs)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (int(total + stroke * 2 + 10), asc + desc + stroke * 2 + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x, base = stroke + 5, stroke + 5 + asc
    for s, col in segs:
        d.text((x, base), s, font=f, fill=col, anchor="ls", stroke_width=stroke, stroke_fill=WHITE)
        x += f.getlength(s)
    return img


def pill_sprite(text, size, fill, fg=WHITE, pad_x=36, pad_y=18, outline=INK):
    f = fnt(size)
    tw = f.getlength(text)
    asc, desc = f.getmetrics()
    w, h = int(tw + pad_x * 2), asc + desc + pad_y * 2
    img = Image.new("RGBA", (w + 14, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([7, 12, w + 7, h + 12], radius=h // 2, fill=(0, 0, 0, 45))
    d.rounded_rectangle([4, 4, w + 4, h + 4], radius=h // 2, fill=fill, outline=outline, width=5)
    d.text((4 + w / 2, 4 + h / 2 + 1), text, font=f, fill=fg, anchor="mm")
    return img


def rich_pill(segs, size, fill=WHITE, pad_x=36, pad_y=18):
    """色分けした文字の入った白い帯."""
    f = fnt(size)
    tw = sum(f.getlength(s) for s, _ in segs)
    asc, desc = f.getmetrics()
    w, h = int(tw + pad_x * 2), asc + desc + pad_y * 2
    img = Image.new("RGBA", (w + 14, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([7, 12, w + 7, h + 12], radius=h // 2, fill=(0, 0, 0, 45))
    d.rounded_rectangle([4, 4, w + 4, h + 4], radius=h // 2, fill=fill, outline=INK, width=5)
    x = 4 + pad_x
    for s, col in segs:
        d.text((x, 4 + h / 2 + 1), s, font=f, fill=col, anchor="lm")
        x += f.getlength(s)
    return img


def tile_sprite(ch, size, fill, fg, font_ratio=0.62, sub=None):
    pad = 14
    img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.2)
    d.rounded_rectangle([pad + 5, pad + 9, pad + size + 5, pad + size + 9], radius=r, fill=(0, 0, 0, 40))
    d.rounded_rectangle([pad, pad, pad + size, pad + size], radius=r, fill=fill, outline=INK, width=6)
    if ch:
        d.text((pad + size / 2, pad + size / 2 + 2), ch, font=fnt(int(size * font_ratio)), fill=fg, anchor="mm")
    return img


def halo_sprite(size, color=YELLOW):
    pad = 40
    img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([pad - 16, pad - 16, pad + size + 16, pad + size + 16],
                        radius=int(size * 0.3), fill=color + (230,))
    return img.filter(ImageFilter.GaussianBlur(14))


def bg_pattern():
    period = 120
    img = Image.new("RGB", (W, H + period), BG)
    d = ImageDraw.Draw(img)
    for row, y in enumerate(range(0, H + period * 2, period // 2)):
        off = (row % 2) * period // 2
        for x in range(-period, W + period, period):
            d.ellipse([x + off - 10, y - 10, x + off + 10, y + 10], fill=DOT)
    return img, period


# ---------------------------------------------------------------------------
# 音
# ---------------------------------------------------------------------------
def _t(sec):
    return np.arange(int(sec * RATE)) / RATE


def sfx(name):
    if name == "tick":
        x = _t(0.07)
        return np.sin(2 * np.pi * 1900 * x) * np.exp(-x / 0.012) * 0.9
    if name == "tock":     # 残り3秒は高く・強く
        x = _t(0.09)
        return (np.sin(2 * np.pi * 2500 * x) + 0.5 * np.sin(2 * np.pi * 1250 * x)) * np.exp(-x / 0.02) * 0.8
    if name == "pinpon":   # 正解の「ピンポーン」
        a, b = _t(0.24), _t(0.6)
        s1 = (np.sin(2 * np.pi * 1318.5 * a) + 0.3 * np.sin(2 * np.pi * 2637 * a)) * bv._env(len(a), 0.004, 0.3, RATE)
        s2 = (np.sin(2 * np.pi * 1046.5 * b) + 0.3 * np.sin(2 * np.pi * 2093 * b)) * bv._env(len(b), 0.004, 0.5, RATE)
        out = np.zeros(len(a) + len(b))
        out[:len(a)] += s1
        out[len(a) - 600:len(a) - 600 + len(b)] += s2
        return out * 0.6
    if name == "chime":    # 冒頭の「ピロン」(最初の0.1秒で耳をつかむ)
        out = np.zeros(int(0.5 * RATE))
        for i, f in enumerate((1046.5, 1568.0)):
            x = _t(0.35)
            seg = np.sin(2 * np.pi * f * x) * bv._env(len(x), 0.003, 0.16, RATE)
            st = int(i * 0.08 * RATE)
            out[st:st + len(seg)] += seg[: len(out) - st]
        return out * 0.55
    if name == "sparkle":  # ヒントの「キラン」
        out = np.zeros(int(0.6 * RATE))
        for i, f in enumerate((2093.0, 2637.0, 3136.0, 4186.0)):
            x = _t(0.3)
            seg = np.sin(2 * np.pi * f * x) * bv._env(len(x), 0.002, 0.09, RATE)
            st = int(i * 0.05 * RATE)
            out[st:st + len(seg)] += seg[: len(out) - st]
        return out * 0.4
    return bv.make_sfx(name, RATE)     # ding / tada / pop / swoosh / boing


def make_bgm(total):
    """明るいマリンバ風のループ(その場で合成するので権利の確認が要らない)."""
    beat = 60 / 112
    eighth = beat / 2
    n = int(total * RATE)
    out = np.zeros(n + RATE, np.float32)
    prog = [(48, [60, 64, 67, 72]), (45, [57, 60, 64, 69]), (41, [53, 57, 60, 65]), (43, [55, 59, 62, 67])]

    def note(m, dur, decay):
        f = 440 * 2 ** ((m - 69) / 12)
        x = _t(dur)
        return ((np.sin(2 * np.pi * f * x) + 0.22 * np.sin(2 * np.pi * 4 * f * x) * np.exp(-x / 0.04))
                * np.exp(-x / decay)).astype(np.float32)

    i = 0
    while i * eighth < total:
        bass, chord = prog[(i // 8) % 4]
        pos = i % 8
        st = int(i * eighth * RATE)
        seg = note(chord[[0, 2, 1, 3, 2, 1, 3, 2][pos]], 0.45, 0.16) * 0.35
        out[st:st + len(seg)] += seg
        if pos in (0, 4):
            seg = note(bass, 0.8, 0.3) * 0.55
            out[st:st + len(seg)] += seg
        i += 1
    out = out[:n]
    return out / (np.abs(out).max() or 1.0)


def load_voice(path):
    with wave.open(str(path)) as w:
        n, rate, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype={2: np.int16, 4: np.int32}[sw]).astype(np.float32)
    data /= 32768.0 if sw == 2 else 2147483648.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if rate != RATE:
        m = int(len(data) * RATE / rate)
        data = np.interp(np.linspace(0, len(data) - 1, m), np.arange(len(data)), data).astype(np.float32)
    # 前後の無音を切る(タイミングを正確にするため)
    peak = float(np.abs(data).max() or 1.0)
    idx = np.where(np.abs(data) > peak * 0.03)[0]
    if len(idx):
        a = max(0, idx[0] - int(0.02 * RATE))
        b = min(len(data), idx[-1] + int(0.06 * RATE))
        data = data[a:b]
    return data / peak * 0.85


class Voice:
    def __init__(self, engine, vset_name, cache_dir):
        self.engine = engine
        self.vset = VOICE_SETS[vset_name]
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.ids = {k: v["id"] for k, v in self.vset.items()}
        if engine == "voicevox":
            self._resolve_ids()

    def _resolve_ids(self):
        try:
            with urllib.request.urlopen(f"{bv.VOICEVOX_URL}/speakers", timeout=5) as r:
                speakers = json.load(r)
        except OSError:
            return
        for key, v in self.vset.items():
            for sp in speakers:
                if sp.get("name") == v["name"]:
                    for st in sp.get("styles", []):
                        if st.get("name") == v["style"]:
                            self.ids[key] = st["id"]

    def say(self, key, text):
        v = self.vset[key]
        sig = json.dumps([self.engine, self.ids[key], v, text], ensure_ascii=False)
        out = self.cache / (hashlib.sha1(sig.encode()).hexdigest()[:16] + ".wav")
        if not out.exists():
            if self.engine == "voicevox":
                q = urllib.parse.urlencode({"text": text, "speaker": self.ids[key]})
                req = urllib.request.Request(f"{bv.VOICEVOX_URL}/audio_query?{q}", method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    query = json.load(r)
                query.update(speedScale=v["speed"], intonationScale=v["intonation"],
                             pitchScale=v["pitch"], prePhonemeLength=0.05,
                             postPhonemeLength=0.08, outputSamplingRate=RATE)
                req = urllib.request.Request(
                    f"{bv.VOICEVOX_URL}/synthesis?speaker={self.ids[key]}",
                    data=json.dumps(query).encode(), method="POST",
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    out.write_bytes(r.read())
            else:
                bv.tts_openjtalk(text, bv.SPEAKERS[key]["ojt"], out, speed=v["speed"] * OJT_SPEEDUP)
        return load_voice(out)


# ---------------------------------------------------------------------------
# 問題の形式ごとの盤面
#   共通: q_lines(画面の問題文) q_tts(読み上げ) ans_tts banner hint_text title key
#         n_flips(答えを光らせる回数) draw(img, t, T)
# ---------------------------------------------------------------------------
NUM_KANA = {2: "ふたつ", 3: "みっつ", 4: "よっつ", 5: "いつつ", 6: "むっつ"}


def level_setup(board, kind, level):
    board.level = level
    board.count = COUNTS[kind][level - 1]
    board.hint_at = HINT_AT[level - 1]
    board.label = KINDS[kind]["label"]


def tile_row_size(n):
    """1行に n 枚並べるときのマスの大きさとすき間."""
    if n <= 4:
        return 160, 20
    if n == 5:
        return 146, 16
    if n == 6:
        return 128, 14
    if n == 7:
        return 114, 12
    return 102, 10


class GridBoard:
    """漢字かくれんぼ. ★=4x4に3つ / ★★=5x5に4つ / ★★★=5x5に4つ(ななめあり)."""
    kind = "grid"

    def __init__(self, rng, avoid, level=2):
        level_setup(self, self.kind, level)
        size, n_ans = (4, 3) if level == 1 else (5, 4)
        self.diagonal = level == 3
        self.grid, self.answers = nd.make_kanji_grid(
            rng, n_answers=n_ans, size=size, tricky=True, avoid=avoid,
            diagonal=self.diagonal, three=level >= 2)
        self.size = size
        self.tile, self.gap = (132, 14) if size == 4 else (108, 10)
        total = self.size * self.tile + (self.size - 1) * self.gap
        self.x0, self.y0 = (W - total) // 2, 548
        self.cell_ans = {cell: i for i, (_, cells) in enumerate(self.answers) for cell in cells}
        self.is_diag = [cells[1][0] - cells[0][0] == 1 and abs(cells[1][1] - cells[0][1]) == 1
                        for _, cells in self.answers]
        self.normal, self.colored = {}, {}
        for r, row in enumerate(self.grid):
            for c, ch in enumerate(row):
                self.normal[(r, c)] = tile_sprite(ch, self.tile, WHITE, INK)
                if (r, c) in self.cell_ans:
                    col = ANSWER_COLORS[self.cell_ans[(r, c)]]
                    self.colored[(r, c)] = tile_sprite(ch, self.tile, col, WHITE)
        self.halo = halo_sprite(self.tile)
        hint_pref, hint_cells = self.answers[0]          # ★★★ では1つ目がななめの答え
        self.hint_cell = hint_cells[0]
        r0, c0 = self.hint_cell
        self.hint_tile = tile_sprite(self.grid[r0][c0], self.tile, HINT_FILL, INK)
        names = [p.name + p.suffix for p, _ in self.answers]
        self.banner_segs = []
        for i, nm in enumerate(names):
            if i:
                self.banner_segs.append(("・", INK))
            self.banner_segs.append((nm, ANSWER_COLORS[i]))
        self.key = "grid:" + ",".join(sorted(p.name for p, _ in self.answers))
        n = len(self.answers)
        if self.diagonal:
            self.q_lines = [[("都道府県が ", INK), (f"{n}つ", PINK), (" かくれてる！", INK)],
                            [("ななめ", PINK), (" もあるよ", INK)]]
            self.q_tts = f"都道府県が、{NUM_KANA[n]}、かくれてる！ ななめもあるよ！"
        else:
            self.q_lines = [[("この中に ", INK), ("都道府県", PINK), ("が", INK)],
                            [(f"{n}つ", PINK), (" かくれているよ！", INK)]]
            self.q_tts = f"この中に、都道府県が、{NUM_KANA[n]}、かくれているよ！"
        self.ans_tts = "、".join(p.reading for p, _ in self.answers) + "！"
        self.banner = "・".join(names)
        self.hint_text = f"ヒント：「{self.grid[r0][c0]}」に注目！"
        self.n_flips = n

    def title(self, k):
        n_cells, n = self.size * self.size, len(self.answers)
        if self.level == 1:
            variants = [
                f"【漢字かくれんぼ その{k}】{n_cells}文字に都道府県が{n}つ！全部わかる？ #脳トレ #クイズ",
                f"【漢字かくれんぼ その{k}】この中に都道府県が{n}つ。5秒で見つけたらすごい！ #脳トレ #クイズ",
            ]
            return variants[k % len(variants)]
        if self.level == 2:
            return f"【漢字かくれんぼ その{k}】{n_cells}文字に都道府県が{n}つ！全部わかる？ #脳トレ #クイズ"
        return f"【漢字かくれんぼ・上級 その{k}】{n_cells}文字に都道府県が{n}つ！ななめもあるよ #脳トレ #クイズ"

    def center(self, r, c):
        return (self.x0 + c * (self.tile + self.gap) + self.tile / 2,
                self.y0 + r * (self.tile + self.gap) + self.tile / 2)

    def draw(self, img, t, T):
        d = ImageDraw.Draw(img)
        flip_dur = 0.28
        # ななめの答えは、マスの下に太い線を引いてすき間から見せる
        for i, (_, cells) in enumerate(self.answers):
            if self.is_diag[i] and t >= T["flip"][i] + flip_dur:
                pts = [self.center(r, c) for r, c in cells]
                d.line(pts, fill=ANSWER_COLORS[i], width=int(self.tile * 0.6))
        for (r, c), spr in self.normal.items():
            cx, cy = self.center(r, c)
            ai = self.cell_ans.get((r, c))
            if ai is not None and t >= T["flip"][ai]:
                p = (t - T["flip"][ai]) / flip_dur
                if p < 1:
                    paste_center(img, spr if p < 0.5 else self.colored[(r, c)], cx, cy,
                                 sx=abs(math.cos(math.pi * p)))
                else:
                    bump = 1 + 0.1 * max(0.0, 1 - (p - 1) * 2.5)
                    paste_center(img, self.colored[(r, c)], cx, cy, scale=bump)
                continue
            alpha = 0.35 if (t >= T["ans0"] and ai is None) else 1.0
            if (r, c) == self.hint_cell and T["hint"] <= t < T["ans0"]:
                pulse = 0.5 + 0.5 * math.sin((t - T["hint"]) * 2 * math.pi * 1.6)
                paste_center(img, self.halo, cx, cy, alpha=0.5 + 0.5 * pulse)
                paste_center(img, self.hint_tile, cx, cy, scale=1.04 + 0.06 * pulse)
                continue
            # 最初の1秒: マスが順番にぷるんと動く(画面が止まって見えないように)
            wv = t - (0.3 + (r + c) * 0.06)
            sc = 1 + 0.08 * math.sin(math.pi * wv / 0.3) if 0 < wv < 0.3 else 1.0
            paste_center(img, spr, cx, cy, scale=sc, alpha=alpha)
        for i, (_, cells) in enumerate(self.answers):
            if self.is_diag[i] or t < T["flip"][i] + flip_dur:
                continue
            (r0, c0), (r1, c1) = cells[0], cells[-1]
            pad = 10
            x0 = self.x0 + c0 * (self.tile + self.gap) - pad
            y0 = self.y0 + r0 * (self.tile + self.gap) - pad
            x1 = self.x0 + c1 * (self.tile + self.gap) + self.tile + pad
            y1 = self.y0 + r1 * (self.tile + self.gap) + self.tile + pad
            d.rounded_rectangle([x0, y0, x1, y1], radius=int(self.tile * 0.3),
                                outline=ANSWER_COLORS[i], width=9)


class AnagramBoard:
    """ならべかえ. ★=1つの県 / ★★=1文字あまる / ★★★=2つの県がまざってる."""
    kind = "anagram"

    def __init__(self, rng, avoid, level=2):
        level_setup(self, self.kind, level)
        self.y = 760
        self.extra = None
        if level == 3:
            self._init_pair(rng, avoid)
        else:
            self._init_single(rng, avoid, extra=(level == 2))

    # 1つの県(★ / ★★)
    def _init_single(self, rng, avoid, extra):
        cands = [p for p in nd.anagram_candidates()
                 if f"anagram:{p.name}" not in avoid and (not extra or len(p.reading) >= 4)]
        cands = cands or [p for p in nd.anagram_candidates() if not extra or len(p.reading) >= 4]
        rng.shuffle(cands)
        for pref in cands:
            rd = pref.reading
            try:
                if extra:
                    letters, ex = nd.make_anagram_extra(rng, pref)
                else:
                    perm = nd.make_anagram(rng, pref)
                    letters, ex = [rd[j] for j in perm], None
            except RuntimeError:
                continue
            break
        else:
            raise RuntimeError("並べ替え問題が作れませんでした")
        self.pref = pref
        n = len(letters)
        self.tile, self.gap = tile_row_size(n)
        # 表示位置 → 正解での位置(あまりの文字は最後のマスへ)
        used = set()
        self.tiles = []        # (文字, 表示位置, 着地位置, 色)
        for pos, ch in enumerate(letters):
            if pos == ex:
                self.tiles.append((ch, pos, n - 1, "extra"))
                continue
            j = next(i for i, c in enumerate(rd) if c == ch and i not in used)
            used.add(j)
            self.tiles.append((ch, pos, j, "a"))
        self.extra = ex
        self.rows = {"a": None}
        self.x_slots = [self._slot_x(i, n) for i in range(n)]
        self.target_xy = {}
        for ch, pos, tgt, grp in self.tiles:
            self.target_xy[pos] = (self.x_slots[tgt], self.y)
        self.sprites = {}
        for ch, pos, tgt, grp in self.tiles:
            self.sprites[(pos, "n")] = tile_sprite(ch, self.tile, WHITE, INK, 0.6)
            self.sprites[(pos, "c")] = (tile_sprite(ch, self.tile, GRAY, GRAY_TEXT, 0.6) if grp == "extra"
                                        else tile_sprite(ch, self.tile, SKY, WHITE, 0.6))
            self.sprites[(pos, "h")] = tile_sprite(ch, self.tile, HINT_FILL, INK, 0.6)
        self.hint_pos = next(pos for ch, pos, tgt, grp in self.tiles if grp == "a" and tgt == 0)
        self.halo = halo_sprite(self.tile)
        self.name_spr = rich_sprite([(pref.name + pref.suffix, SKY)], 110, stroke=10)
        self.shown = "".join(letters)
        self.key = f"anagram:{pref.name}"
        if extra:
            self.q_lines = [[("ならべかえると ", INK), ("都道府県", SKY)],
                            [("1文字", PINK), (" あまるよ！", INK)]]
            self.q_tts = "ならべかえると、都道府県になるよ。いちもじ、あまるよ！"
        else:
            self.q_lines = [[("ならべかえると", INK)],
                            [("都道府県", SKY), ("になるよ！", INK)]]
            self.q_tts = "ならべかえると、都道府県になるよ！"
        self.ans_tts = rd + "！"
        self.banner = None          # 答えは盤面に大きく出す
        self.hint_text = f"ヒント：さいしょは「{rd[0]}」"
        self.n_flips = 1

    # 2つの県(★★★)
    def _init_pair(self, rng, avoid):
        pairs = nd.anagram_pairs()
        rng.shuffle(pairs)
        for p, q in pairs:
            key = "anagram2:" + ",".join(sorted((p.name, q.name)))
            if key in avoid or not nd.pair_is_unique(p, q):
                continue
            break
        else:
            raise RuntimeError("2県まざりの問題が作れませんでした")
        if rng.random() < 0.5:
            p, q = q, p
        order = nd.make_anagram_pair(rng, p, q)
        n = len(order)
        self.tile, self.gap = tile_row_size(n)
        self.x_slots = [self._slot_x(i, n) for i in range(n)]
        rows = {0: (p, self.y - 96), 1: (q, self.y + 96)}
        self.tiles, self.target_xy, self.sprites = [], {}, {}
        for pos, (ch, which, idx) in enumerate(order):
            pref, ry = rows[which]
            tx = self._slot_x(idx, len(pref.reading))
            self.tiles.append((ch, pos, idx, "a" if which == 0 else "b"))
            self.target_xy[pos] = (tx, ry)
            col = SKY if which == 0 else PINK
            self.sprites[(pos, "n")] = tile_sprite(ch, self.tile, WHITE, INK, 0.6)
            self.sprites[(pos, "c")] = tile_sprite(ch, self.tile, col, WHITE, 0.6)
            self.sprites[(pos, "h")] = tile_sprite(ch, self.tile, HINT_FILL, INK, 0.6)
        self.hint_pos = next(pos for pos, (ch, which, idx) in enumerate(order) if which == 0 and idx == 0)
        self.halo = halo_sprite(self.tile)
        self.name_spr = None
        self.pair = (p, q)
        self.shown = "".join(ch for ch, _, _ in order)
        self.key = "anagram2:" + ",".join(sorted((p.name, q.name)))
        self.q_lines = [[("都道府県が ", INK), ("2つ", PINK)],
                        [("まざってるよ！", INK)]]
        self.q_tts = "都道府県が、ふたつ、まざってるよ！"
        self.ans_tts = f"{p.reading}と、{q.reading}！"
        self.banner_segs = [(p.name + p.suffix, SKY), ("・", INK), (q.name + q.suffix, PINK)]
        self.banner = p.name + p.suffix + "・" + q.name + q.suffix
        self.hint_text = f"ヒント：1つは「{p.reading[0]}」から"
        self.n_flips = 1

    def _slot_x(self, i, n):
        total = n * self.tile + (n - 1) * self.gap
        return (W - total) / 2 + i * (self.tile + self.gap) + self.tile / 2

    def title(self, k):
        if self.level == 3:
            return f"【ならべかえ・上級】「{self.shown}」に都道府県が2つまざってる！わかる？ #脳トレ #クイズ"
        if self.level == 2:
            return f"【ならべかえ】「{self.shown}」で都道府県を作って！1文字あまるよ #脳トレ #クイズ"
        return f"【ならべかえ】「{self.shown}」はどこの都道府県？5秒でわかる？ #脳トレ #クイズ"

    def draw(self, img, t, T):
        move_t0, move_dur = T["ans0"], 0.7
        done = t >= T["flip"][0]
        n = len(self.tiles)
        for ch, pos, tgt, grp in self.tiles:
            x_from, y_from = self.x_slots[pos], self.y
            x_to, y_to = self.target_xy[pos]
            p = ease_io((t - move_t0) / move_dur) if t >= move_t0 else 0.0
            x = x_from + (x_to - x_from) * p
            y = y_from + (y_to - y_from) * p
            if x_to != x_from and y_to == y_from:
                y -= math.sin(math.pi * p) * 90 * (1 if x_to > x_from else -1)
            if pos == self.hint_pos and T["hint"] <= t < T["ans0"]:
                pulse = 0.5 + 0.5 * math.sin((t - T["hint"]) * 2 * math.pi * 1.6)
                paste_center(img, self.halo, x, y, alpha=0.5 + 0.5 * pulse)
                paste_center(img, self.sprites[(pos, "h")], x, y, scale=1.04 + 0.06 * pulse)
                continue
            wv = t - (0.3 + pos * 0.07)
            sc = 1 + 0.08 * math.sin(math.pi * wv / 0.3) if 0 < wv < 0.3 else 1.0
            if done:
                bp = (t - T["flip"][0]) / 0.3
                sc = 1 + 0.12 * max(0.0, 1 - bp) * math.sin(math.pi * clamp01(bp))
                if grp == "extra":
                    sc = 0.8
                paste_center(img, self.sprites[(pos, "c")], x, y, scale=sc)
            else:
                paste_center(img, self.sprites[(pos, "n")], x, y, scale=sc)
        if done and self.name_spr is not None:
            paste_center(img, self.name_spr, W / 2, 985, scale=pop_scale(t, T["flip"][0] + 0.05))
        if done and self.extra is not None:
            d = ImageDraw.Draw(img)
            x = self.x_slots[n - 1]
            k = pop_scale(t, T["flip"][0] + 0.1)
            if k > 0.05:
                d.text((x, self.y + self.tile * 0.62), "あまり", font=fnt(max(8, int(34 * k))),
                       fill=GRAY_TEXT, anchor="mm")


class CapitalBoard:
    """県庁所在地. ★=同じ県の市から3択 / ★★=まぎらわしい県庁所在地の3択 / ★★★=市から県を当てる4択."""
    kind = "capital"

    def __init__(self, rng, avoid, level=2):
        level_setup(self, self.kind, level)
        self.reverse = level == 3
        prefix = "capital3:" if self.reverse else "capital:"
        pool = nd.CAPITAL_QUIZ if level == 1 else [nd.BY_NAME[n] for n in nd.CAPITAL_HARD]
        cands = [p for p in pool if f"{prefix}{p.name}" not in avoid]
        self.pref = p = rng.choice(cands or pool)
        if level == 1:
            opts, self.correct = nd.capital_options(rng, p)
            labels = [f"{c}市" for c in opts]
        elif level == 2:
            opts, self.correct = nd.capital_options_hard(rng, p)
            labels = [f"{c}市" for c in opts]
        else:
            opts, self.correct = nd.city_to_pref_options(rng, p)
            labels = [f"{o.name}{o.suffix}" for o in opts]
        self.opts = opts
        wrong = [i for i in range(len(opts)) if i != self.correct]
        self.removed = rng.choice(wrong)                      # ヒントで消す選択肢
        n = len(opts)
        self.bw, self.bh = 780, (150 if n == 3 else 124)
        self.ys = [640, 822, 1004] if n == 3 else [620, 766, 912, 1058]
        letters = "ABCD"
        self.spr = {}
        for i, label in enumerate(labels):
            self.spr[(i, "normal")] = self.button(letters[i], label, WHITE, INK, MINT)
            self.spr[(i, "correct")] = self.button(letters[i], label, MINT, WHITE, WHITE, MINT)
            self.spr[(i, "wrong")] = self.button(letters[i], label, GRAY, GRAY_TEXT, GRAY_TEXT)
        office = "道庁" if p.suffix == "" else "県庁"
        office_tts = "どうちょう" if p.suffix == "" else "けんちょう"
        letter_tts = ["エー", "ビー", "シー", "ディー"][self.correct]
        self.office = office
        if self.reverse:
            self.key = f"capital3:{p.name}"
            self.q_lines = [[(f"{p.capital}市", MINT), ("は", INK)],
                            [("何県の", INK), ("県庁所在地", INK), ("？", INK)]]
            self.q_tts = f"{p.capital_reading}しは、なにけんの、けんちょうしょざいち？"
            self.ans_tts = f"{letter_tts}、{p.reading}{nd.SUFFIX_READING[p.suffix]}！"
            self.banner = f"{p.capital}市は{p.name}{p.suffix}"
        else:
            self.key = f"capital:{p.name}"
            self.q_lines = [[(f"{p.name}{p.suffix}", MINT), ("の", INK)],
                            [(f"{office}所在地", INK), ("は？", INK)]]
            self.q_tts = f"{p.reading}{nd.SUFFIX_READING[p.suffix]}の、{office_tts}しょざいちは？"
            self.ans_tts = f"{letter_tts}、{p.capital_reading}し！"
            self.banner = f"{p.capital}市（{p.capital_reading}し）"
        self.hint_text = "ヒント：1つ消すよ！"
        self.n_flips = 1

    def button(self, letter, text, fill, fg, letter_fill, letter_fg=WHITE):
        w, h = self.bw, self.bh
        img = Image.new("RGBA", (w + 16, h + 20), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([8, 14, w + 8, h + 14], radius=40, fill=(0, 0, 0, 40))
        d.rounded_rectangle([4, 4, w + 4, h + 4], radius=40, fill=fill, outline=INK, width=6)
        r = (h - 44) // 2
        cx, cy = 4 + 28 + r, 4 + h // 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=letter_fill, outline=INK, width=5)
        d.text((cx, cy + 2), letter, font=fnt(int(r * 1.15)), fill=letter_fg, anchor="mm")
        d.text((cx + r + 34, cy + 2), text, font=fnt(68 if h >= 150 else 62), fill=fg, anchor="lm")
        return img

    def title(self, k):
        p = self.pref
        if self.reverse:
            return f"【県庁所在地・上級】{p.capital}市は何県の県庁所在地？4択 #脳トレ #クイズ"
        if self.level == 2:
            return f"【{self.office}所在地】{p.name}{p.suffix}の{self.office}所在地は？まちがえやすい3択 #脳トレ #クイズ"
        return f"【{self.office}所在地】{p.name}{p.suffix}の{self.office}所在地は？パッとわかる？ #脳トレ #クイズ"

    def draw(self, img, t, T):
        d = ImageDraw.Draw(img)
        shown = t >= T["flip"][0]
        for i, y in enumerate(self.ys):
            state = "normal"
            if shown:
                state = "correct" if i == self.correct else "wrong"
            elif i == self.removed and t >= T["hint"]:
                state = "wrong"
            sc = 1.0
            if shown and i == self.correct:
                bp = (t - T["flip"][0]) / 0.35
                sc = 1 + 0.08 * math.sin(math.pi * clamp01(bp))
            wv = t - (0.3 + i * 0.1)
            if 0 < wv < 0.3:
                sc = 1 + 0.05 * math.sin(math.pi * wv / 0.3)
            paste_center(img, self.spr[(i, state)], W / 2, y, scale=sc)
            if state == "wrong" and (not shown) and i == self.removed:
                k = pop_scale(t, T["hint"])
                s = 30 * k
                cx = W / 2 + self.bw / 2 - 90
                d.line([cx - s, y - s, cx + s, y + s], fill=RED, width=12)
                d.line([cx - s, y + s, cx + s, y - s], fill=RED, width=12)
        if shown:
            k = pop_scale(t, T["flip"][0], 0.3)
            r = (self.bh * 0.6) * k
            cx, cy = W / 2 - self.bw / 2 + 4 + 28 + (self.bh - 44) // 2, self.ys[self.correct]
            if r > 2:
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RED, width=14)


class InitialBoard:
    """頭文字クイズ. ★=「お」で始まる4文字 / ★★=答え3〜4つ / ★★★=答え4〜6つ(「山」がつく など)."""
    kind = "initial"

    def __init__(self, rng, avoid, level=2):
        level_setup(self, self.kind, level)
        if level == 1:
            self._init_fixed(rng, avoid)
        else:
            lo, hi = (3, 4) if level == 2 else (4, 6)
            pats = nd.free_patterns(lo, hi)
            cands = [x for x in pats if f"initial:{x[0]}{x[1]}" not in avoid]
            self.mode, self.ch, self.answers = rng.choice(cands or pats)
            self.n = None
            self._setup_free(rng)
        self.cards = [self.card(p, ANSWER_COLORS[i % len(ANSWER_COLORS)]) for i, p in enumerate(self.answers)]
        self.count_spr = pill_sprite(f"答えは {len(self.answers)}つ！", 50, YELLOW, INK)
        self.reveal_spr = pill_sprite("正解は…", 50, YELLOW, INK)
        self.ans_tts = "、".join(p.reading for p in self.answers) + "！"
        self.banner = None
        self.n_flips = len(self.answers)

    def _init_fixed(self, rng, avoid):
        pats = nd.initial_patterns()
        cands = [x for x in pats if f"initial:{x[0]}{x[1]}{x[2]}" not in avoid]
        pos, self.ch, self.n, self.answers = rng.choice(cands or pats)
        self.mode = pos
        self.tile, self.gap = (150, 18) if self.n <= 4 else (124, 14)
        known = 0 if pos == "head" else self.n - 1
        self.boxes = [tile_sprite(self.ch, self.tile, PURPLE, WHITE, 0.6) if i == known
                      else tile_sprite("？", self.tile, WHITE, (210, 210, 222), 0.5)
                      for i in range(self.n)]
        word = "で始まる" if pos == "head" else "で終わる"
        self.key = f"initial:{pos}{self.ch}{self.n}"
        self.q_lines = [[("「", INK), (self.ch, PURPLE), (f"」{word}", INK)],
                        [(f"{self.n}文字の", INK), ("都道府県", PURPLE), ("は？", INK)]]
        num = {2: "に", 3: "さん", 4: "よん", 5: "ご", 6: "ろく"}[self.n]
        verb = "から始まる" if pos == "head" else "で終わる"
        self.q_tts = f"{self.ch}、{verb}、{num}もじの、都道府県は？"
        idx = 1 if pos == "head" else self.n - 2
        hint_chars = sorted({p.reading[idx] for p in self.answers})
        self.hint_text = f"ヒント：{'2' if pos == 'head' else str(self.n - 1)}文字目は「{'・'.join(hint_chars)}」"
        self.word = word
        self.label = "頭文字クイズ" if pos == "head" else "都道府県クイズ"

    def _setup_free(self, rng):
        mode, ch = self.mode, self.ch
        self.tile = 170
        self.boxes = [tile_sprite(ch, self.tile, PURPLE, WHITE, 0.6)]
        word = {"head_any": "で始まる", "tail_any": "で終わる", "kanji": "がつく"}[mode]
        self.word = word
        self.key = f"initial:{mode}{ch}"
        self.q_lines = [[("「", INK), (ch, PURPLE), (f"」{word}", INK)],
                        [("都道府県", PURPLE), (" ぜんぶ言える？", INK)]]
        if mode == "kanji":
            self.q_tts = f"{nd.KANJI_READ[ch]}、という漢字がつく、都道府県。ぜんぶいえるかな？"
            self.label = "漢字クイズ"
        elif mode == "head_any":
            self.q_tts = f"{ch}、からはじまる、都道府県。ぜんぶいえるかな？"
            self.label = "頭文字クイズ"
        else:
            self.q_tts = f"{ch}、でおわる、都道府県。ぜんぶいえるかな？"
            self.label = "都道府県クイズ"
        # ヒント: 思い出しにくそうな1つの出だしを見せる(「山」なら「和歌…」)
        pick = rng.choice(self.answers)
        if mode == "kanji":
            not_head = [p for p in self.answers if not p.name.startswith(ch)]
            pick = rng.choice(not_head or self.answers)
            head = pick.name[:2] if not pick.name.startswith(ch) else pick.name[:1]
        else:
            head = pick.reading[:2]
        self.hint_text = f"ヒント：「{head}…」もあるよ"

    def card(self, p, col):
        w, h = 390, 104
        img = Image.new("RGBA", (w + 14, h + 18), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([7, 13, w + 7, h + 13], radius=30, fill=(0, 0, 0, 40))
        d.rounded_rectangle([4, 4, w + 4, h + 4], radius=30, fill=WHITE, outline=col, width=8)
        name = p.name + p.suffix
        f1 = fnt(56 if len(name) <= 3 else 48)
        d.text((30, 4 + h / 2 + 2), name, font=f1, fill=INK, anchor="lm")
        d.text((w - 18, 4 + h / 2 + 4), p.reading, font=fnt(30), fill=GRAY_TEXT, anchor="rm")
        return img

    def title(self, k):
        n = len(self.answers)
        tag = "・上級" if self.level == 3 else ""
        if self.mode in ("head", "tail"):
            return (f"【{self.label}】「{self.ch}」{self.word}{self.n}文字の都道府県は？答えは{n}つ"
                    f" #脳トレ #クイズ")
        return f"【{self.label}{tag}】「{self.ch}」{self.word}都道府県、ぜんぶ言える？答えは{n}つ #脳トレ #クイズ"

    def draw(self, img, t, T):
        if self.n is not None:            # ★: 「お□□□」のマス
            total = self.n * self.tile + (self.n - 1) * self.gap
            x0 = (W - total) // 2
            for i, spr in enumerate(self.boxes):
                x = x0 + i * (self.tile + self.gap) + self.tile / 2
                wv = t - (0.3 + i * 0.08)
                sc = 1 + 0.08 * math.sin(math.pi * wv / 0.3) if 0 < wv < 0.3 else 1.0
                paste_center(img, spr, x, 636, scale=sc)
        else:                             # ★★/★★★: 大きな1文字 + 「…」
            wv = t - 0.3
            sc = 1 + 0.08 * math.sin(math.pi * wv / 0.3) if 0 < wv < 0.3 else 1.0
            paste_center(img, self.boxes[0], W / 2, 640, scale=sc)
            d = ImageDraw.Draw(img)
            if self.mode == "head_any":
                d.text((W / 2 + 120, 650), "…", font=fnt(90), fill=GRAY_TEXT, anchor="lm")
            elif self.mode == "tail_any":
                d.text((W / 2 - 120, 650), "…", font=fnt(90), fill=GRAY_TEXT, anchor="rm")
        label = self.reveal_spr if t >= T["reveal"] else self.count_spr
        paste_center(img, label, W / 2, 800)
        cols = 2
        for i, spr in enumerate(self.cards):
            k = pop_scale(t, T["flip"][i])
            if k <= 0:
                continue
            r, c = divmod(i, cols)
            last_row_single = (i == len(self.cards) - 1 and len(self.cards) % 2 == 1)
            x = W / 2 if last_row_single else W / 2 + (-1 if c == 0 else 1) * 207
            y = 905 + r * 124
            paste_center(img, spr, x, y, scale=k)


# 毎回まったく同じ言い回しにならないよう、決めゼリフは数パターンから選ぶ
REVEAL_LINES = ["正解は〜？", "答えは〜？", "それでは、正解は〜？"]
CTA_LINES = [   # (読み上げ, 画面の大きい文字, 画面の小さい文字)
    ("なんびょうで、わかった？", [("何秒で", INK), ("わかった？", PINK)], "コメントで教えてね"),
    ("ぜんぶ、わかったかな？", [("全部", INK), ("わかった？", PINK)], "答えをコメントしてね"),
    ("わかったら、すごい！", [("わかったら", INK), ("すごい！", PINK)], "何秒だったか教えてね"),
]

BOARDS = {"grid": GridBoard, "anagram": AnagramBoard, "capital": CapitalBoard, "initial": InitialBoard}


# ---------------------------------------------------------------------------
# 1本ぶんの組み立て
# ---------------------------------------------------------------------------
_char_cache = {}


def char_sprite(key, face, m, blink):
    k = (key, face, m, blink)
    if k not in _char_cache:
        s = bv.draw_character(key, m / 3.0, blink, False, face)
        _char_cache[k] = s.resize((CHAR_SIZE, CHAR_SIZE), Image.LANCZOS)
    return _char_cache[k]


def plan_timeline(board, clips, count):
    """読み上げの長さから、各イベントの時刻を決める."""
    dur = {k: len(v) / RATE for k, v in clips.items()}
    T = {"q": 0.12}
    T["count"] = max(T["q"] + dur["q"] + 0.25, 1.6)
    T["count_end"] = T["count"] + count
    T["hint"] = T["count"] + count * board.hint_at
    T["reveal"] = T["count_end"]
    T["ans0"] = T["reveal"] + dur["reveal"] + 0.08
    n = board.n_flips
    if board.kind == "anagram":
        T["flip"] = [T["ans0"] + 0.72]
    else:
        gap = min(0.5, max(0.3, dur["ans"] / max(1, n)))
        T["flip"] = [T["ans0"] + 0.05 + i * gap for i in range(n)]
    T["cta"] = max(T["ans0"] + dur["ans"], T["flip"][-1] + 0.45) + 0.3
    T["total"] = T["cta"] + dur["cta"] + 0.65
    T["dur"] = dur
    return T


def build_audio(clips, T, count, use_bgm):
    n = int(T["total"] * RATE) + 1
    voice = np.zeros(n, np.float32)
    owners = {"q": "noa", "hint": "mei", "reveal": "mei", "ans": "mei", "cta": "noa"}
    starts = {"q": T["q"], "hint": T["hint"], "reveal": T["reveal"], "ans": T["ans0"], "cta": T["cta"]}
    env = {"noa": np.zeros(int(T["total"] * FPS) + 2, np.float32),
           "mei": np.zeros(int(T["total"] * FPS) + 2, np.float32)}
    for k, clip in clips.items():
        st = int(starts[k] * RATE)
        seg = clip[: max(0, n - st)]
        voice[st:st + len(seg)] += seg * VOICE_GAIN
        # 口パク用: フレームごとの音量
        step = RATE / FPS
        f0 = int(starts[k] * FPS)
        loud = []
        for i in range(int(len(clip) / step)):
            chunk = clip[int(i * step):int((i + 1) * step)]
            loud.append(float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0)
        if loud:
            pk = max(loud) or 1.0
            for i, v in enumerate(loud):
                if f0 + i < len(env[owners[k]]):
                    env[owners[k]][f0 + i] = max(env[owners[k]][f0 + i], min(1.0, v / pk * 1.5))
    events = [(0.0, "chime")]
    for s in range(count):
        events.append((T["count"] + s, "tock" if count - s <= 3 else "tick"))
    events.append((T["hint"], "sparkle"))
    events.append((T["reveal"] - 0.02, "swoosh"))
    for i, ft in enumerate(T["flip"]):
        events.append((ft, "pinpon" if i == 0 else "ding"))
    events.append((T["flip"][-1] + 0.15, "tada"))
    events.append((T["cta"] - 0.05, "pop"))
    fx = np.zeros(n, np.float32)
    cache = {}
    for sec, name in events:
        if name not in cache:
            cache[name] = sfx(name).astype(np.float32)
        s = cache[name]
        st = int(sec * RATE)
        seg = s[: max(0, n - st)]
        fx[st:st + len(seg)] += seg * SFX_GAIN
    out = voice + fx
    if use_bgm:
        bgm = make_bgm(T["total"])[:n]
        # 声が出ている間はBGMを下げる
        active = (np.abs(voice) > 0.02).astype(np.float32)
        k = int(0.15 * RATE)
        active = np.convolve(active, np.ones(k) / k, mode="same")
        duck = 1.0 - 0.6 * np.clip(active * 3, 0, 1)
        out[:len(bgm)] += bgm * BGM_GAIN * duck[:len(bgm)]
    fade = int(0.3 * RATE)
    out[-fade:] *= np.linspace(1, 0, fade)
    out[:240] *= np.linspace(0, 1, 240)
    peak = float(np.abs(out).max() or 1.0)
    if peak > 0.98:
        out *= 0.98 / peak
    return out, env


def write_wav(path, data):
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def make_confetti(rng, t0, origin):
    parts = []
    for _ in range(80):
        a = math.radians(rng.uniform(-165, -15))
        v = rng.uniform(700, 1400)
        parts.append((origin[0], origin[1], v * math.cos(a), v * math.sin(a),
                      rng.choice(ANSWER_COLORS), rng.uniform(16, 28), rng.uniform(0, 6.3), rng.uniform(-9, 9)))
    return t0, parts


def draw_confetti(d, conf, t):
    t0, parts = conf
    dt_ = t - t0
    if dt_ < 0 or dt_ > 2.2:
        return
    for x, y, vx, vy, col, size, rot, vr in parts:
        px = x + vx * dt_
        py = y + vy * dt_ + 1500 * dt_ * dt_
        if py > H or py < -50:
            continue
        a = rot + vr * dt_
        hw, hh = size / 2, size / 4 * (0.35 + 0.65 * abs(math.cos(a * 1.3)))
        ca, sa = math.cos(a), math.sin(a)
        pts = [(px + ca * dx - sa * dy, py + sa * dx + ca * dy)
               for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        d.polygon(pts, fill=col)


class Short:
    def __init__(self, board, no, voice, use_bgm, seed):
        self.board = board
        self.no = no
        self.kind = KINDS[board.kind]
        self.count = board.count
        pick = random.Random(f"lines-{seed}")
        cta_tts, cta_big, cta_small = pick.choice(CTA_LINES)
        clips = {
            "q": voice.say("noa", board.q_tts),
            "hint": voice.say("mei", "ヒント！"),
            "reveal": voice.say("mei", pick.choice(REVEAL_LINES)),
            "ans": voice.say("mei", board.ans_tts),
            "cta": voice.say("noa", cta_tts),
        }
        self.T = plan_timeline(board, clips, self.count)
        self.audio, self.env = build_audio(clips, self.T, self.count, use_bgm)
        self.pattern, self.period = bg_pattern()
        stars = "★" * board.level + "☆" * (3 - board.level)
        self.header = pill_sprite(f"第{no}問  {board.label}  {stars}", 44, self.kind["color"])
        self.q_sprites = [rich_sprite(line, 76) for line in board.q_lines]
        self.cta_sprites = [rich_sprite(cta_big, 84), rich_sprite([(cta_small, INK)], 54)]
        self.reveal_banner = pill_sprite("正解は…", 54, YELLOW, INK)
        segs = getattr(board, "banner_segs", None)
        size = 52 if board.banner and len(board.banner) <= 12 else 44
        if segs:
            self.ans_banner = rich_pill(segs, size)
        else:
            self.ans_banner = pill_sprite(board.banner, size, WHITE, INK) if board.banner else None
        self.hint_spr = pill_sprite(board.hint_text, 42, YELLOW, INK)
        self.conf = make_confetti(random.Random(seed), self.T["flip"][-1] + 0.1, (W / 2, BANNER_Y))
        self.first = None

    # --- 部品 ---
    def draw_ring(self, d, t):
        T = self.T
        if t >= T["reveal"] + 0.25:
            return
        cx, cy, r = RING
        k = 1.0
        if t >= T["reveal"]:
            k = 1 - clamp01((t - T["reveal"]) / 0.25)
        remain = min(self.count, max(0.0, T["count_end"] - t))
        frac = remain / self.count
        col = MINT if remain > self.count / 2 else YELLOW if remain > 3 else RED
        if 0 < remain <= 3:
            k *= 1 + 0.07 * abs(math.sin(math.pi * (T["count_end"] - t)))
        rr = r * k
        if rr < 4:
            return
        d.ellipse([cx - rr - 14, cy - rr - 14, cx + rr + 14, cy + rr + 14], fill=WHITE, outline=INK, width=6)
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 0, 360, fill=(238, 232, 222), width=int(18 * k))
        if frac > 0:
            d.arc([cx - rr, cy - rr, cx + rr, cy + rr], -90, -90 + 360 * frac, fill=col, width=int(18 * k))
        num = max(1, math.ceil(remain)) if remain > 0 else 0
        d.text((cx, cy + 4), str(num), font=fnt(max(10, int(84 * k))), fill=RED if remain <= 3 else INK,
               anchor="mm")

    def draw_chars(self, img, d, t):
        T = self.T
        fi = int(t * FPS)
        for key in ("noa", "mei"):
            if key == "noa":
                face = ("normal" if t < T["count"] else "sad" if t < T["reveal"]
                        else "surprise" if t < T["cta"] else "normal")
            else:
                face = "normal" if t < T["count"] else "smug" if t < T["reveal"] else "normal"
            env = self.env[key]
            m = int(round(min(1.0, env[min(fi, len(env) - 1)]) * 3))
            blink = ((t + (1.0 if key == "noa" else 2.4)) % 3.6) < 0.12 and face != "surprise"
            spr = char_sprite(key, face, m, blink)
            x, y = CHAR_POS[key]
            bob = math.sin(2 * math.pi * (t * 0.8 + (0 if key == "noa" else 0.5))) * 6
            jump = 0.0
            if key == "noa":
                for ft in T["flip"]:
                    p = (t - ft) / 0.35
                    if 0 <= p < 1:
                        jump = max(jump, math.sin(math.pi * p) * 40)
            elif 0 <= t - T["hint"] < 0.35:
                jump = math.sin(math.pi * (t - T["hint"]) / 0.35) * 26
            img.paste(spr, (x, int(y + bob - jump)), spr)
        # 考え中: ノアの頭の上に「…」、残り少なくなると汗
        if T["count"] <= t < T["hint"]:
            bx, by = 232, 1150
            d.ellipse([bx - 82, by - 40, bx + 82, by + 40], fill=WHITE, outline=INK, width=5)
            d.ellipse([bx - 96, by + 40, bx - 70, by + 62], fill=WHITE, outline=INK, width=4)
            n_dots = int((t - T["count"]) * 2.5) % 4
            for i in range(n_dots):
                cx = bx - 40 + i * 40
                d.ellipse([cx - 10, by - 10, cx + 10, by + 10], fill=INK)
        if T["count"] + self.count * 0.55 <= t < T["reveal"]:
            sx, sy = 92, 1292 + 6 * math.sin(t * 7)
            d.polygon([(sx, sy - 30), (sx - 16, sy), (sx + 16, sy)], fill=SKY)
            d.ellipse([sx - 16, sy - 14, sx + 16, sy + 18], fill=SKY)

    def frame(self, t):
        T = self.T
        off = int((t * 16) % self.period)
        img = self.pattern.crop((0, off, W, off + H))
        d = ImageDraw.Draw(img)
        paste_center(img, self.header, W / 2, HEADER_Y)
        # 上の文字: 問題文 → 最後は「何秒でわかった?」に入れ替える
        if t < T["cta"]:
            for spr, y in zip(self.q_sprites, Q_Y):
                paste_center(img, spr, W / 2, y)
        else:
            k = pop_scale(t, T["cta"])
            paste_center(img, self.cta_sprites[0], W / 2, Q_Y[0] - 4, scale=k)
            paste_center(img, self.cta_sprites[1], W / 2, Q_Y[1] + 10, scale=k)
        self.board.draw(img, t, T)
        self.draw_ring(d, t)
        # 中段の帯: ヒント → 正解は… → 答え
        if T["hint"] <= t < T["reveal"]:
            paste_center(img, self.hint_spr, W / 2, BANNER_Y, scale=pop_scale(t, T["hint"]))
        elif self.board.kind != "initial" and T["reveal"] <= t:
            if t < T["flip"][0]:
                paste_center(img, self.reveal_banner, W / 2, BANNER_Y, scale=pop_scale(t, T["reveal"]))
            elif self.ans_banner:
                paste_center(img, self.ans_banner, W / 2, BANNER_Y, scale=pop_scale(t, T["flip"][0], 0.3))
        self.draw_chars(img, d, t)
        draw_confetti(d, self.conf, t)
        return img

    def render(self, mp4, tmp_wav):
        write_wav(tmp_wav, self.audio)
        n_frames = int(self.T["total"] * FPS)
        first = self.frame(0.0)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-i", str(tmp_wav),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(mp4)],
            stdin=subprocess.PIPE)
        for i in range(n_frames):
            t = i / FPS
            img = first if i == 0 else self.frame(t)
            left = self.T["total"] - t
            if left < LOOP_FADE:
                img = Image.blend(img, first, clamp01(1 - left / LOOP_FADE))
            enc.stdin.write(img.tobytes())
        enc.stdin.close()
        enc.wait()
        if enc.returncode != 0:
            raise SystemExit(f"ffmpeg が失敗しました: {mp4}")


# ---------------------------------------------------------------------------
# まとめて作る
# ---------------------------------------------------------------------------
DESCRIPTION = """毎日7時・12時・18時に、10秒でできる頭の体操クイズを出しています。
何秒でわかったか、コメントで教えてね！

▼施設でのご利用について
デイサービス・高齢者施設・地域のサロンなどのレクリエーションに、自由にお使いください（ご連絡は不要です）。

※このチャンネルのクイズは、楽しみながら頭を使うためのものです。医療的な効果を保証するものではありません。

{credits}

#脳トレ #都道府県クイズ #頭の体操 #クイズ"""


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"next_no": 1, "used": [], "kind_count": {}}


def safe_name(s):
    return s.replace("/", "／").replace(":", "：")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", action="store_true", help="4形式を1本ずつ作る(番号は進めない)")
    ap.add_argument("--count", type=int, default=21, help="作る本数(既定21 = 1週間分)")
    ap.add_argument("--start", default=None, help="最初の投稿日 YYYY-MM-DD(既定: 明日)")
    ap.add_argument("--only", choices=list(BOARDS), help="この形式だけ作る")
    ap.add_argument("--level", type=int, choices=[1, 2, 3],
                    help="むずかしさ(1=かんたん 2=ふつう 3=むずかしい)。省略時は時間帯ごと(7時・12時=2、18時=3)")
    ap.add_argument("--voice", choices=list(VOICE_SETS), default="A")
    ap.add_argument("--no-bgm", action="store_true")
    ap.add_argument("--engine", choices=["auto", "voicevox", "openjtalk"], default="auto")
    ap.add_argument("--out", default=str(HERE / "build" / "noutore"))
    args = ap.parse_args()

    engine = args.engine
    if engine == "auto":
        engine = "voicevox" if bv.voicevox_available() else "openjtalk"
    print(f"[voice] {engine} / セット{args.voice}" + ("" if engine == "voicevox" else
          "  ※VOICEVOXが起動していないので仮の声です。本番はVOICEVOXを起動してから実行"))
    voice = Voice(engine, args.voice, Path(args.out) / "_tts")

    state = load_state()
    used = set(state["used"])
    if args.sample:
        start = None
        kinds = [args.only] if args.only else list(BOARDS)
        levels = [args.level] if args.level else [2, 3]
        plan = [(None, k, lv) for lv in levels for k in kinds]
        out_dir = Path(args.out) / "sample"
    else:
        start = (dt.date.fromisoformat(args.start) if args.start
                 else dt.date.today() + dt.timedelta(days=1))
        plan = []
        day, slot = 0, 0
        while len(plan) < args.count:
            when, kinds, slot_level = SLOTS[slot]
            kind = args.only or kinds[day % len(kinds)]
            date = start + dt.timedelta(days=day)
            plan.append((f"{date.isoformat()} {when}", kind, args.level or slot_level))
            slot += 1
            if slot == len(SLOTS):
                slot, day = 0, day + 1
        out_dir = Path(args.out) / start.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    no = state["next_no"]
    for i, (when, kind, level) in enumerate(plan):
        seed = f"{no}-{kind}-{level}-{len(used)}"
        rng = random.Random(seed)
        board = BOARDS[kind](rng, used, level)
        kcount = state["kind_count"].get(kind, 0) + 1
        title = board.title(kcount)
        mp4 = out_dir / (safe_name(title) + ".mp4")
        short = Short(board, no, voice, not args.no_bgm, seed)
        short.render(mp4, out_dir / "_audio.wav")
        print(f"[{i + 1}/{len(plan)}] {short.T['total']:.1f}秒  {title}")
        lines.append(f"{when or '見本'}  {'★' * level}  {title}")
        if not args.sample:
            used.add(board.key)
            state["kind_count"][kind] = kcount
            no += 1
    (out_dir / "_audio.wav").unlink(missing_ok=True)

    if not args.sample:
        state["next_no"] = no
        state["used"] = sorted(used)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    guide = ["■ 予約投稿の一覧（ファイル名がそのままタイトルになります）", ""] + lines + [
        "", "■ 概要欄（最初に1回だけ、YouTube Studio の",
        "  設定 → アップロード動画のデフォルト設定 → 説明 に貼る）", "",
        DESCRIPTION.format(credits=CREDITS)]
    (out_dir / "アップロード手順.txt").write_text("\n".join(guide) + "\n", encoding="utf-8")
    print(f"[done] {out_dir}")


if __name__ == "__main__":
    main()
