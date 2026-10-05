#!/usr/bin/env python3
"""仮動画ビルダー v2 — 漫画風ポップアニメ + キャラ掛け合い + VOICEVOX対応.

「本のデータ研究所」第1回:
  『時間術の本15冊の「Amazon紹介文」を分析したら、共通点がゼロだった』

  数値は実データ(analysis/ で集計した結果)。集計手順は analysis/START_HERE.md、
  復元用の抽出結果と名寄せ表は analysis/recovered/ にある。

特徴:
  - 2キャラの掛け合い台本(吹き出し=字幕を兼ねる漫画レイアウト)
  - 口パク(音声の音量に同期) / まばたき / 体の上下ゆれ / 吹き出しポップイン
  - 横棒グラフ・大数字のカウントアップ・集中線などのポップ演出
  - 音声は VOICEVOX(推奨) → 無ければ Open JTalk にフォールバック
  - フレームは ffmpeg に直接パイプするので中間PNGを吐かない

音声エンジン:
  VOICEVOX を使う場合は先にエンジンを起動しておく(Macならアプリを起動するだけ)。
      既定の接続先: http://127.0.0.1:50021
  起動していれば自動検出して VOICEVOX を使う。検出できなければ Open JTalk。

  ※VOICEVOXは無料・商用利用可だが、キャラクターごとに利用規約があり
    クレジット表記(例: VOICEVOX:ずんだもん)が必要。概要欄に必ず記載すること。
  ※本スクリプトが描画するキャラ絵はオリジナルの簡易イラストであり、
    VOICEVOXキャラクターの立ち絵ではない(立ち絵は別途ライセンスが必要)。

使い方:
    python3 build_video.py <出力ディレクトリ> [--engine voicevox|openjtalk|auto]
"""

import argparse
import importlib.util
import json
import math
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------------------
W, H = 1280, 720
SHORT_W, SHORT_H = 1080, 1920      # Shorts(縦型)の書き出しサイズ
FPS = 15
CHANNEL = "本のデータ研究所"
WATERMARK = ""          # 仮ビルド中の注記。公開版は空にしておく



def _pick_font(candidates):
    """環境にある日本語フォントを順に探す(macOS / Linux 両対応)."""
    for path in candidates:
        if Path(path).exists():
            return path
    raise SystemExit(
        "日本語フォントが見つかりません。build_video.py の FONT_BOLD / FONT_REG に\n"
        "手元のフォントのパスを指定してください。候補として探した場所:\n  "
        + "\n  ".join(candidates))


FONT_BOLD = _pick_font([
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",          # Linux
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",                 # macOS
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/NotoSansCJKjp-Bold.otf",
])
FONT_REG = _pick_font([
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/NotoSansCJKjp-Regular.otf",
])
VOICEVOX_URL = "http://127.0.0.1:50021"
OJT_DIC = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
OJT_VOICE = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"

# ポップな配色
CREAM = (255, 249, 235)
INK = (38, 42, 66)
PINK = (255, 108, 145)
YELLOW = (255, 201, 71)
MINT = (86, 208, 184)
SKY = (108, 178, 255)
PURPLE = (154, 124, 235)
WHITE = (255, 255, 255)

# 話者定義: VOICEVOXのspeaker IDと、Open JTalkフォールバック時の声色パラメータ
# VOICEVOX speaker id 例: 2=四国めたん(ノーマル) 3=ずんだもん(ノーマル)
#                        8=春日部つむぎ 11=玄野武宏 13=青山龍星 14=冥鳴ひまり
SPEAKERS = {
    "noa": {    # 後輩・生徒・ツッコミ役
        "name": "ノア",
        "voicevox": 8,          # 春日部つむぎ
        "ojt": {"fm": 5.0, "rate": 1.05},
        "body": (128, 214, 238), "hair": (86, 196, 172), "side": "left",
        "style": "twin",        # ツインテール + 前髪ぱっつん
    },
    "mei": {    # 先輩・解説役
        "name": "メイ先生",
        "voicevox": 2,          # 四国めたん
        "ojt": {"fm": -1.0, "rate": 1.0},
        "body": PINK, "hair": (206, 78, 118), "side": "right",
        "style": "long",        # ロングヘア + メガネ
    },
}

LINE_PAUSE = 0.40       # セリフ間の空白(秒)
SCENE_PAUSE = 0.9       # シーンの切れ目はさらに長く取る

# Shortsは本編と同じテンポだと遅い。冒頭1秒で判断されるので詰める。
SHORT_SPEED = 1.12      # 読み上げ速度(本編は1.0)
SHORT_LINE_PAUSE = 0.18
SHORT_SCENE_PAUSE = 0.35
SPEED = 1.0             # tts_voicevox が参照する。ショート生成中だけ上書きする

# ---------------------------------------------------------------------------
# 台本
#   visual: bullets / stat / bars   impact=True で集中線
#   lines : sp(話者) text(吹き出し表示) tts(読み上げ用/省略時はtext)
# ---------------------------------------------------------------------------
# 台本はエピソードごとのファイル(ep1.py / ep2.py)に置いてある。
# SCENES / SHORTS / THUMB / NUMBER は load_episode() が読み込んで差し込む。
SCENES, SHORTS, THUMB, NUMBER = [], [], {}, "01"


def load_episode(n):
    """epN.py から台本を読み込んでモジュール変数に流し込む."""
    global SCENES, SHORTS, THUMB, NUMBER
    path = Path(__file__).resolve().parent / f"ep{n}.py"
    if not path.exists():
        raise SystemExit(f"{path.name} がありません。--episode の指定を確認してください。")
    spec = importlib.util.spec_from_file_location(f"ep{n}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    SCENES, SHORTS = mod.SCENES, mod.SHORTS
    THUMB, NUMBER = mod.THUMB, mod.NUMBER
    return mod


# ---------------------------------------------------------------------------
# 音声合成
# ---------------------------------------------------------------------------
def voicevox_available(base=VOICEVOX_URL):
    try:
        with urllib.request.urlopen(f"{base}/version", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def tts_voicevox(text, speaker_id, out_wav, base=VOICEVOX_URL):
    q = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    req = urllib.request.Request(f"{base}/audio_query?{q}", method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        query = json.load(r)
    query["speedScale"] = SPEED  # 本編は1.0。ショートは SHORT_SPEED に差し替わる
    query["prePhonemeLength"] = 0.05
    query["postPhonemeLength"] = 0.1
    body = json.dumps(query).encode()
    req = urllib.request.Request(
        f"{base}/synthesis?speaker={speaker_id}", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out_wav.write_bytes(r.read())


def tts_openjtalk(text, cfg, out_wav):
    txt = out_wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    subprocess.run(
        ["open_jtalk", "-x", OJT_DIC, "-m", OJT_VOICE,
         "-fm", str(cfg["fm"]), "-r", str(cfg["rate"]), "-s", "48000",
         "-ow", str(out_wav), str(txt)],
        check=True, capture_output=True)


def read_wav(path):
    with wave.open(str(path)) as w:
        n, rate, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, rate


def mouth_envelope(samples, rate, duration, fps):
    """フレームごとの口の開き具合(0..1)を音量から作る."""
    n_frames = max(1, int(duration * fps))
    env = np.zeros(n_frames, dtype=np.float32)
    step = rate / fps
    for i in range(n_frames):
        a, b = int(i * step), int((i + 1) * step)
        chunk = samples[a:b]
        if len(chunk):
            env[i] = np.sqrt(np.mean(chunk ** 2))
    peak = env.max() if env.max() > 0 else 1.0
    return np.clip(env / peak * 1.6, 0, 1)


# ---------------------------------------------------------------------------
# 描画ヘルパ
# ---------------------------------------------------------------------------
_font_cache = {}


def font(path, size):
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=fnt) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def outlined_text(d, xy, text, fnt, fill, outline=WHITE, width=4, anchor=None):
    x, y = xy
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy <= width * width:
                d.text((x + dx, y + dy), text, font=fnt, fill=outline, anchor=anchor)
    d.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def draw_character(key, mouth, blink, dim):
    """2頭身のオリジナル簡易キャラを RGBA で返す(VOICEVOXの立ち絵ではない)."""
    cw, ch = 300, 300
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    spec = SPEAKERS[key]
    body = spec["body"]
    hair = spec["hair"]
    if dim:  # 聞き手はトーンを落として、話者を目立たせる
        body = tuple(int(c * 0.45 + 252 * 0.55) for c in body)
        hair = tuple(int(c * 0.45 + 252 * 0.55) for c in hair)
    cx = cw // 2
    style = spec.get("style", "twin")
    skin = (255, 240, 228)
    # 後ろ髪(頭より先に描く)
    if style == "twin":     # ツインテール
        for sx in (cx - 124, cx + 68):
            d.rounded_rectangle([sx, 92, sx + 56, 256], radius=28, fill=hair, outline=INK, width=6)
    else:                   # ロングヘア
        d.rounded_rectangle([cx - 106, 90, cx + 106, 246], radius=76, fill=hair, outline=INK, width=6)
    # 体
    d.rounded_rectangle([cx - 74, 186, cx + 74, 300], radius=48, fill=body, outline=INK, width=6)
    # 腕
    d.rounded_rectangle([cx - 104, 208, cx - 62, 276], radius=21, fill=body, outline=INK, width=6)
    d.rounded_rectangle([cx + 62, 208, cx + 104, 276], radius=21, fill=body, outline=INK, width=6)
    # 襟もと(ノアはリボン、メイは襟)
    if style == "twin":
        d.polygon([(cx - 30, 196), (cx, 210), (cx - 30, 224)], fill=YELLOW, outline=INK)
        d.polygon([(cx + 30, 196), (cx, 210), (cx + 30, 224)], fill=YELLOW, outline=INK)
        d.ellipse([cx - 11, 199, cx + 11, 221], fill=YELLOW, outline=INK, width=4)
    else:
        d.polygon([(cx - 44, 190), (cx, 232), (cx + 44, 190)], fill=WHITE, outline=INK)
    # 頭
    d.ellipse([cx - 84, 40, cx + 84, 208], fill=skin, outline=INK, width=6)
    # 前髪(chordは弦の部分にも輪郭線を引いてしまうので、髪色で塗り消す)
    d.chord([cx - 84, 40, cx + 84, 208], 180, 360, fill=hair, outline=INK, width=6)
    d.line([(cx - 80, 124), (cx + 80, 124)], fill=hair, width=10)
    if style == "twin":     # ぱっつん
        d.rectangle([cx - 78, 106, cx + 78, 124], fill=hair)
    else:                   # 斜め分け
        d.ellipse([cx - 90, 62, cx - 10, 132], fill=hair, outline=INK, width=6)
    # 目
    for ex in (cx - 36, cx + 36):
        if blink:
            d.arc([ex - 18, 122, ex + 18, 152], 200, 340, fill=INK, width=6)
        else:
            d.ellipse([ex - 18, 112, ex + 18, 152], fill=INK)
            d.ellipse([ex - 8, 120, ex + 4, 134], fill=WHITE)
            d.ellipse([ex + 2, 138, ex + 9, 145], fill=(255, 255, 255, 200))
    # メガネ(先生役)
    if style == "long":
        for ex in (cx - 36, cx + 36):
            d.ellipse([ex - 26, 110, ex + 26, 156], outline=INK, width=5)
        d.line([cx - 10, 132, cx + 10, 132], fill=INK, width=5)
    # 頬
    d.ellipse([cx - 74, 150, cx - 46, 170], fill=(255, 168, 180))
    d.ellipse([cx + 46, 150, cx + 74, 170], fill=(255, 168, 180))
    # 口(mouth: 0=閉じ 〜 1=大きく開く)
    if mouth < 0.18:
        d.arc([cx - 16, 166, cx + 16, 186], 20, 160, fill=INK, width=5)
    else:
        oh = int(8 + mouth * 26)
        d.ellipse([cx - 16, 168, cx + 16, 168 + oh], fill=(150, 66, 84), outline=INK, width=4)
    return img


def build_char_cache():
    cache = {}
    for key in SPEAKERS:
        for dim in (False, True):
            for blink in (False, True):
                for m in range(4):   # 口の開き 4段階
                    cache[(key, dim, blink, m)] = draw_character(key, m / 3.0, blink, dim)
    return cache


def draw_burst(d, cx, cy, n=26, r0=170, r1=900, color=(255, 236, 190)):
    """集中線."""
    for i in range(n):
        a = 2 * math.pi * i / n
        wdt = 0.055
        pts = [
            (cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
            (cx + r1 * math.cos(a - wdt), cy + r1 * math.sin(a - wdt)),
            (cx + r1 * math.cos(a + wdt), cy + r1 * math.sin(a + wdt)),
        ]
        d.polygon(pts, fill=color)


def scene_background(scene):
    """シーンの静止部分(背景・帯・カード枠)を1枚作る."""
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    # 背景のドット模様
    for y in range(0, H, 40):
        for x in range(0, W, 40):
            d.ellipse([x, y, x + 6, y + 6], fill=(240, 232, 214))
    if scene.get("impact"):
        draw_burst(d, W // 2, 250)
    # トップ帯
    d.rounded_rectangle([-30, -40, W + 30, 86], radius=26, fill=YELLOW, outline=INK, width=6)
    vis = scene["visual"]
    outlined_text(d, (44, 18), vis["kicker"], font(FONT_BOLD, 38), INK, WHITE, 3)
    chip = scene.get("chip", "")
    if chip:
        f = font(FONT_BOLD, 28)
        tw = d.textlength(chip, font=f)
        d.rounded_rectangle([W - 44 - tw - 40, 12, W - 44, 68], radius=16, fill=PINK, outline=INK, width=5)
        d.text((W - 44 - tw - 20, 24), chip, font=f, fill=WHITE)
    # メインカード
    d.rounded_rectangle([56, 108, W - 56, 372], radius=30, fill=WHITE, outline=INK, width=6)
    footer = f"{CHANNEL} / {WATERMARK}" if WATERMARK else CHANNEL
    d.text((640, 382), footer, font=font(FONT_REG, 17),
           fill=(170, 160, 145), anchor="ma")
    # 種類別の静止部分
    if vis["type"] == "bullets":
        # カード内(132..352)に必ず収まるよう、はみ出す場合だけ自動で縮める
        top, bottom = 132, 352
        tlines = vis["title"].split("\n")
        ts, tlh, ilh = 46, 56, 48
        need = len(tlines) * tlh + 12 + len(vis["items"]) * ilh
        if need > bottom - top:
            k = (bottom - top) / need
            ts, tlh, ilh = int(ts * k), int(tlh * k), int(ilh * k)
        y = top
        for tl in tlines:
            d.text((92, y), tl, font=font(FONT_BOLD, ts), fill=INK)
            y += tlh
        y += 12
        isize = min(32, ilh - 14)
        for i, it in enumerate(vis["items"]):
            col = [PINK, SKY, PURPLE][i % 3]
            d.rounded_rectangle([92, y + 4, 124, y + 4 + isize], radius=10, fill=col)
            d.text((142, y), it, font=font(FONT_REG, isize), fill=INK)
            y += ilh
    elif vis["type"] == "stat":
        d.text((640, 140), vis["label"], font=font(FONT_BOLD, 32), fill=(120, 118, 130), anchor="ma")
    elif vis["type"] == "bars":
        d.text((92, 128), vis["title"], font=font(FONT_BOLD, 40), fill=INK)
    elif vis["type"] == "rank":
        # 順位バッジ
        d.rounded_rectangle([92, 138, 252, 298], radius=34, fill=YELLOW, outline=INK, width=6)
        rtxt, rf, uf = str(vis["rank"]), font(FONT_BOLD, 92), font(FONT_BOLD, 34)
        rw = d.textlength(rtxt, font=rf)
        uw = d.textlength("位", font=uf)
        x = 172 - (rw + uw + 6) / 2
        outlined_text(d, (x, 152), rtxt, rf, PINK, INK, 5)
        d.text((x + rw + 6, 216), "位", font=uf, fill=INK)
        # 主張(長ければ字を縮めて2行に収める)
        size = 54
        while True:
            f = font(FONT_BOLD, size)
            lines = wrap(d, vis["claim"], f, 760)
            if len(lines) <= 2 or size <= 30:
                break
            size -= 4
        lines = lines[:2]
        y = 150 if len(lines) > 1 else 178
        for ln in lines:
            d.text((288, y), ln, font=f, fill=INK)
            y += size + 12
    return img


def draw_visual_anim(img, scene, t):
    """カード内のアニメーション部分(カウントアップ/バー伸長)を重ねる."""
    vis = scene["visual"]
    d = ImageDraw.Draw(img)
    p = min(1.0, t / 0.9)
    p = 1 - (1 - p) ** 3          # ease-out
    if vis["type"] == "stat":
        try:
            target = int(vis["num"])
            shown = str(int(round(target * p)))
        except ValueError:
            shown = vis["num"]
        f = font(FONT_BOLD, 150)
        uf = font(FONT_BOLD, 60)
        tw = d.textlength(shown, font=f)
        uw = d.textlength(vis["unit"], font=uf)
        x = 640 - (tw + uw + 14) / 2
        outlined_text(d, (x, 186), shown, f, PINK, INK, 5)
        outlined_text(d, (x + tw + 14, 268), vis["unit"], uf, INK, WHITE, 3)
    elif vis["type"] == "bars":
        # 本数に応じて行間を詰め、カード内(186..352)に必ず収める
        items = vis["items"]
        y0, y1 = 186, 352
        lh = min(56, (y1 - y0) // max(1, len(items)))
        barh = lh - 14
        fsize = min(30, barh - 4)
        y = y0
        for i, (label, val, total) in enumerate(items):
            col = [PINK, SKY, PURPLE][i % 3]
            d.text((92, y + (barh - fsize) // 2), label, font=font(FONT_REG, fsize), fill=INK)
            bx0, bx1 = 460, 1080
            d.rounded_rectangle([bx0, y, bx1, y + barh], radius=barh // 2, fill=(238, 234, 226))
            wpx = int((bx1 - bx0) * (val / total) * p)
            if wpx > barh:
                d.rounded_rectangle([bx0, y, bx0 + wpx, y + barh], radius=barh // 2, fill=col,
                                    outline=INK, width=4)
            d.text((1100, y + (barh - fsize) // 2), f"{int(round(val * p))}/{total}",
                   font=font(FONT_BOLD, fsize), fill=INK)
            y += lh
    elif vis["type"] == "rank":
        total = vis["total"]
        bx0, bx1, by, barh = 288, 1050, 306, 36
        d.rounded_rectangle([bx0, by, bx1, by + barh], radius=barh // 2, fill=(238, 234, 226))
        wpx = int((bx1 - bx0) * (vis["val"] / total) * p)
        if wpx > barh:
            d.rounded_rectangle([bx0, by, bx0 + wpx, by + barh], radius=barh // 2,
                                fill=SKY, outline=INK, width=4)
        d.text((1070, by + 1), f"{int(round(vis['val'] * p))}/{total}",
               font=font(FONT_BOLD, 30), fill=INK)


BUBBLE_W, BUBBLE_M = 720, 140    # 吹き出し本体の幅 / しっぽ用の左右マージン
BUBBLE_BOTTOM = 612              # 吹き出し本体の下端の画面Y
BUBBLE_TOP_PAD = 22              # 名前タグが本体上端からはみ出す分の余白
BUBBLE_LEFT = {"left": 258, "right": 262}   # 話者別の本体左端X(顔を隠さない位置)
CHAR_X = {"left": -40, "right": 980}        # キャラ立ち位置(300pxスプライトの左上X)
CHAR_Y = 428


def render_bubble(text, speaker):
    """吹き出し(=字幕)を返す。(RGBA画像, 本体の高さ) — 本体左上は (BUBBLE_M, 0)."""
    bw, m, pad = BUBBLE_W, BUBBLE_M, 34
    f = font(FONT_BOLD, 34)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap(tmp, text, f, bw - pad * 2)
    bh = pad * 2 + 46 * len(lines)
    top = BUBBLE_TOP_PAD          # 名前タグが本体からはみ出す分(切れないように確保)
    img = Image.new("RGBA", (bw + m * 2, top + bh + 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    left = SPEAKERS[speaker]["side"] == "left"
    # しっぽ(先に描いて本体で根元を隠す)
    by = top + bh
    if left:
        tail = [(m + 30, by - 20), (m + 110, by - 20), (m - 74, by + 48)]
    else:
        tail = [(m + bw - 110, by - 20), (m + bw - 30, by - 20), (m + bw + 74, by + 48)]
    d.polygon(tail, fill=WHITE)
    d.line([tail[0], tail[2]], fill=INK, width=6)
    d.line([tail[1], tail[2]], fill=INK, width=6)
    # 本体
    d.rounded_rectangle([m, top, m + bw, by], radius=28, fill=WHITE, outline=INK, width=6)
    y = top + pad - 6
    for ln in lines:
        d.text((m + pad, y), ln, font=f, fill=INK)
        y += 46
    # 名前タグ(本体の上端にまたがる)
    nf = font(FONT_BOLD, 24)
    name = SPEAKERS[speaker]["name"]
    nw = d.textlength(name, font=nf)
    nx = m + 40 if left else m + bw - nw - 40
    tag = tuple(int(c * 0.62) for c in SPEAKERS[speaker]["body"])   # 白文字が読める濃さに
    d.rounded_rectangle([nx - 16, top - 20, nx + nw + 16, top + 20], radius=15,
                        fill=tag, outline=INK, width=4)
    d.text((nx, top - 16), name, font=nf, fill=WHITE)
    return img, bh


# ---------------------------------------------------------------------------
# 音声・フレームの生成(本編とShortsで共用)
# ---------------------------------------------------------------------------
def synthesize(scenes, audio_dir, engine, narration, quiet=False,
               line_pause=None, scene_pause=None):
    """台本を読み上げてwavにまとめ、(タイムライン, チャプター, 合計秒)を返す."""
    timeline, chapters, all_audio = [], [], []
    elapsed, rate = 0.0, None
    for si, scene in enumerate(scenes):
        if "chapter" in scene:
            chapters.append((elapsed, scene["chapter"]))
        for li, line in enumerate(scene["lines"]):
            wav = audio_dir / f"l{len(timeline):03d}.wav"
            spec = SPEAKERS[line["sp"]]
            text = line.get("tts", line["text"])
            if engine == "voicevox":
                tts_voicevox(text, spec["voicevox"], wav)
            else:
                tts_openjtalk(text, spec["ojt"], wav)
            samples, rate = read_wav(wav)
            lp = LINE_PAUSE if line_pause is None else line_pause
            sp_ = SCENE_PAUSE if scene_pause is None else scene_pause
            pause = sp_ if li == len(scene["lines"]) - 1 else lp
            dur = len(samples) / rate + pause
            timeline.append({"scene": si, "line": line, "dur": dur,
                             "env": mouth_envelope(samples, rate, dur, FPS)})
            elapsed += dur
            all_audio.append(samples)
            all_audio.append(np.zeros(int(pause * rate), dtype=np.float32))
        if not quiet:
            print(f"  tts scene {si + 1}/{len(scenes)}")

    merged = np.concatenate(all_audio)
    peak = np.abs(merged).max() or 1.0
    merged = (merged / peak * 0.89 * 32767).astype(np.int16)
    with wave.open(str(narration), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(merged.tobytes())
    return timeline, chapters, elapsed


def compose_frame(scene, item, fi, t, scene_t, chars, bg_cache, bubble, bub_h):
    """横型(1280x720)のフレームを1枚組み立てる."""
    speaker = item["line"]["sp"]
    frame = bg_cache.copy()
    draw_visual_anim(frame, scene, scene_t + t)
    # キャラ(話者は揺れ+口パク、聞き手はトーンダウン)
    for key in SPEAKERS:
        talking = key == speaker
        m = int(round(item["env"][min(fi, len(item["env"]) - 1)] * 3)) if talking else 0
        blink = (int((scene_t + t) * 1000) % 3400) < 130
        bob = int(math.sin((scene_t + t) * 7.5) * 5) if talking else 0
        sprite = chars[(key, not talking, blink, m)]
        frame.paste(sprite, (CHAR_X[SPEAKERS[key]["side"]], CHAR_Y + bob), sprite)
    # 吹き出し(登場時にポップイン)
    pop = min(1.0, t / 0.16)
    scale = 0.86 + 0.18 * pop - 0.04 * max(0.0, math.sin(pop * math.pi))
    bx = BUBBLE_LEFT[SPEAKERS[speaker]["side"]] - BUBBLE_M
    by = BUBBLE_BOTTOM - bub_h - BUBBLE_TOP_PAD
    if scale < 0.999:
        b = bubble.resize((int(bubble.width * scale), int(bubble.height * scale)),
                          Image.BILINEAR)
        # 本体の下端を固定したまま縮小(ポップイン時の位置ブレ防止)
        bx += int((bubble.width - b.width) * 0.5)
        by += int(bub_h - bub_h * scale)
    else:
        b = bubble
    frame.paste(b, (bx, by), b)
    return frame


def open_encoder(size, narration, mp4):
    w, h = size
    return subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
         "-i", str(narration),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-shortest", str(mp4)],
        stdin=subprocess.PIPE)


# ---------------------------------------------------------------------------
# 本体
# ---------------------------------------------------------------------------
def render_video(scenes, timeline, chars, narration, mp4, vertical=None, opening=None):
    """タイムラインどおりに動画を書き出す。vertical を渡すと縦型で包む."""
    size = (SHORT_W, SHORT_H) if vertical else (W, H)
    proc = open_encoder(size, narration, mp4)
    pop = pop_in_frames(opening) if opening is not None else []
    bg_cache, cur_scene, scene_t = None, -1, 0.0
    for item in timeline:
        scene = scenes[item["scene"]]
        hero = bool(vertical and scene.get("_opening"))
        if item["scene"] != cur_scene:
            cur_scene = item["scene"]
            bg_cache = None if hero else scene_background(scene)
            scene_t = 0.0
        n_frames = max(1, int(round(item["dur"] * FPS)))
        if hero:
            # 最初の数フレームだけ拡大して出す(静止画の出だしは動きが無いと切られる)
            for fi in range(n_frames):
                proc.stdin.write((pop[fi] if fi < len(pop) else opening).tobytes())
            scene_t += item["dur"]
            continue
        bubble, bub_h = render_bubble(item["line"]["text"], item["line"]["sp"])
        for fi in range(n_frames):
            frame = compose_frame(scene, item, fi, fi / FPS, scene_t,
                                  chars, bg_cache, bubble, bub_h)
            if vertical:
                frame = wrap_vertical(frame, vertical)
            proc.stdin.write(frame.tobytes())
        scene_t += item["dur"]
    proc.stdin.close()
    proc.wait()


def shorts_backdrop(short):
    """Shortsの固定部分(上のフック文と下のCTA)を1枚作る."""
    img = Image.new("RGB", (SHORT_W, SHORT_H), CREAM)
    d = ImageDraw.Draw(img)
    for y in range(0, SHORT_H, 44):
        for x in range(0, SHORT_W, 44):
            d.ellipse([x, y, x + 7, y + 7], fill=(240, 232, 214))
    # 上: フック(1行ずつ収まるところまで縮める)
    d.rounded_rectangle([44, 96, SHORT_W - 44, 470], radius=40, fill=YELLOW,
                        outline=INK, width=8)
    hook = short["hook"].split("\n")
    size = 84
    while size > 40 and any(d.textlength(l, font=font(FONT_BOLD, size)) > SHORT_W - 160
                            for l in hook):
        size -= 4
    f = font(FONT_BOLD, size)
    y = 283 - (len(hook) * (size + 18) - 18) // 2
    for ln in hook:
        outlined_text(d, (SHORT_W // 2, y), ln, f, INK, WHITE, 5, anchor="ma")
        y += size + 18
    # 下: CTA
    # 下端はShortsのUI(タイトル・ボタン)に隠れるので、1500より下には置かない
    d.rounded_rectangle([44, 1288, SHORT_W - 44, 1468], radius=40, fill=PINK,
                        outline=INK, width=8)
    d.text((SHORT_W // 2, 1338), short["cta"], font=font(FONT_BOLD, 62),
           fill=WHITE, anchor="ma")
    d.text((SHORT_W // 2, 1496), CHANNEL, font=font(FONT_BOLD, 42),
           fill=(150, 142, 128), anchor="ma")
    return img


def shorts_opening_card(short):
    """ショートの冒頭に出す、画面いっぱいの大文字カード.

    ショートは最初の1秒で判断されるので、ここでは本編の画面を出さない。
    結論だけを、読める最大の字で置く。
    """
    img = Image.new("RGB", (SHORT_W, SHORT_H), CREAM)
    d = ImageDraw.Draw(img)
    for y in range(0, SHORT_H, 44):
        for x in range(0, SHORT_W, 44):
            d.ellipse([x, y, x + 7, y + 7], fill=(240, 232, 214))
    draw_burst(d, SHORT_W // 2, 820, n=34, r0=240, r1=1500, color=(255, 232, 178))

    lines = short["hook"].split("\n")
    size = 150
    while size > 56 and any(d.textlength(l, font=font(FONT_BOLD, size)) > SHORT_W - 110
                            for l in lines):
        size -= 4
    f = font(FONT_BOLD, size)
    lh = size + 34
    y = 820 - (len(lines) * lh - 34) // 2
    for i, ln in enumerate(lines):
        # 落ちは最後の行に置く約束なので、そこだけ色を変えて目を留める
        col = PINK if i == len(lines) - 1 and len(lines) > 1 else INK
        outlined_text(d, (SHORT_W // 2, y), ln, f, col, WHITE, 9, anchor="ma")
        y += lh

    # 下にキャラを置いて、チャンネルの顔を一瞬で見せる
    for key, x in (("noa", 110), ("mei", 600)):
        sp = draw_character(key, 0.7, False, False).resize((370, 370), Image.LANCZOS)
        img.paste(sp, (x, 1360), sp)
    d.text((SHORT_W // 2, 1760), CHANNEL, font=font(FONT_BOLD, 44),
           fill=(150, 142, 128), anchor="ma")
    return img


def pop_in_frames(card, n=5):
    """冒頭カードが出るときの、ひと呼吸ぶんの拡大アニメ."""
    out = []
    for i in range(n):
        k = 1.10 - 0.10 * ((i + 1) / n)          # 1.10倍から等倍へ
        w, h = int(SHORT_W * k), int(SHORT_H * k)
        big = card.resize((w, h), Image.BILINEAR)
        x, y = (w - SHORT_W) // 2, (h - SHORT_H) // 2
        out.append(big.crop((x, y, x + SHORT_W, y + SHORT_H)))
    return out


def wrap_vertical(frame, backdrop):
    """横型フレームを縮小して、Shortsの背景の真ん中に貼る."""
    img = backdrop.copy()
    fh = round(SHORT_W * H / W)
    img.paste(frame.resize((SHORT_W, fh), Image.BILINEAR), (0, 556))
    return img


def build_shorts(out, engine, chars):
    """本編から切り出した縦型ショートを書き出す.

    冒頭は本編のセリフを使わず、`opening` に書いた1行の断定から始める。
    ショートは最初の1秒で判断されるので、前置きから入ると全部スワイプされる。
    """
    global SPEED
    SPEED = SHORT_SPEED
    try:
        for si, short in enumerate(SHORTS, 1):
            scenes = []
            if short.get("opening"):
                scenes.append({"visual": {"type": "bullets", "kicker": "", "title": "",
                                          "items": []},
                               "lines": short["opening"], "_opening": True})
            scenes += [SCENES[i] for i in short["scenes"]]

            audio_dir = out / f"audio_short{si}"
            audio_dir.mkdir(parents=True, exist_ok=True)
            narration = out / f"short{si}.wav"
            timeline, _, total = synthesize(
                scenes, audio_dir, engine, narration, quiet=True,
                line_pause=SHORT_LINE_PAUSE, scene_pause=SHORT_SCENE_PAUSE)
            mp4 = out / f"short{si}.mp4"
            render_video(scenes, timeline, chars, narration, mp4,
                         vertical=shorts_backdrop(short),
                         opening=shorts_opening_card(short))
            head = sum(t["dur"] for t in timeline if scenes[t["scene"]].get("_opening"))
            print(f"[short {si}] {total:.0f}秒(冒頭カード {head:.1f}秒) / "
                  f"{short['title']} -> {mp4}")
            if not short.get("opening"):
                print("    ※openingが無いので本編のセリフから始まります。冒頭で切られます。")
            if total > 175:
                print("    ※3分を超えるとShortsになりません。シーンを減らしてください。")
    finally:
        SPEED = 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default="build")
    ap.add_argument("--engine", choices=["auto", "voicevox", "openjtalk"], default="auto")
    ap.add_argument("--shorts", action="store_true",
                    help="本編を作らず、縦型ショート3本だけを書き出す")
    ap.add_argument("--episode", type=int, default=2,
                    help="どの回を作るか(台本は ep1.py / ep2.py にある)")
    args = ap.parse_args()

    load_episode(args.episode)
    print(f"[episode] #{NUMBER}  {len(SCENES)}シーン / "
          f"{sum(len(sc['lines']) for sc in SCENES)}行")

    out = Path(args.outdir)
    audio_dir = out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    engine = args.engine
    if engine == "auto":
        engine = "voicevox" if voicevox_available() else "openjtalk"
    print(f"[engine] {engine}")
    if engine == "openjtalk":
        print("  ※VOICEVOXエンジン未検出のためOpen JTalkで仮生成します。")
        print("    Mac側でVOICEVOXアプリを起動してから実行すると、ずんだもん等の声になります。")

    chars = build_char_cache()

    if args.shorts:
        build_shorts(out, engine, chars)
        return

    narration = out / "narration.wav"
    timeline, chapters, total = synthesize(SCENES, audio_dir, engine, narration)
    print(f"[audio] {total/60:.2f} min / {len(timeline)} lines")

    # チャプターは音声の長さで決まるので、この時点で確定できる
    if chapters:
        lines_out = [f"{int(t) // 60:02d}:{int(t) % 60:02d} {name}" for t, name in chapters]
        (out / "chapters.txt").write_text("\n".join(lines_out) + "\n", encoding="utf-8")
        print(f"[chapters] {len(chapters)}章 -> {out / 'chapters.txt'}")
        for l in lines_out:
            print(f"    {l}")

    mp4 = out / "sample_video.mp4"
    render_video(SCENES, timeline, chars, narration, mp4)
    render_thumbnail(out / "thumbnail.png")
    print(f"[done] {total/60:.2f} min -> {mp4}")


def render_thumbnail(path):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    draw_burst(d, 700, 300, n=30, r0=120, r1=1100, color=(255, 226, 168))
    d.rounded_rectangle([-20, -20, W + 20, H + 20], radius=10, outline=INK, width=14)
    top, mid, bottom = THUMB["big"]
    outlined_text(d, (58, 40), THUMB["kicker"], font(FONT_BOLD, 46), PINK, WHITE, 6)
    outlined_text(d, (58, 122), top, font(FONT_BOLD, 92), INK, WHITE, 8)
    outlined_text(d, (58, 232), mid, font(FONT_BOLD, 160), PINK, WHITE, 10)
    outlined_text(d, (58, 412), bottom, font(FONT_BOLD, 92), INK, WHITE, 8)
    band = font(FONT_BOLD, 54)
    bw = d.textlength(THUMB["band"], font=band)
    d.rounded_rectangle([52, 540, 108 + bw, 646], radius=24, fill=SKY, outline=INK, width=7)
    outlined_text(d, (80, 558), THUMB["band"], band, WHITE, INK, 4)
    # スプライトは左右に余白を含むので、右端で切れないよう内側に寄せる
    for key, x in (("noa", 770), ("mei", 975)):
        sp = draw_character(key, 0.7, False, False)
        sp = sp.resize((330, 330), Image.LANCZOS)
        img.paste(sp, (x, 380), sp)
    d.text((W - 40, 30), f"{CHANNEL} #{NUMBER}", font=font(FONT_BOLD, 30), fill=INK, anchor="ra")
    img.save(path)


if __name__ == "__main__":
    main()
