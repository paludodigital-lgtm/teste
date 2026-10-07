"""Reel vertical da Seld Lavanderia Express Uruguaiana.

Pipeline:
  1. ffmpeg corta os melhores takes, estabiliza (vidstab), tira ruído,
     corrige cor e faz upscale 464x832 -> 1080x1920.
  2. Python compõe transições, textos animados e o cartão final com a logo.
  3. Trilha sintetizada (120 BPM) com os cortes caindo no tempo da batida.

Uso:
  python3 src/render_seld.py --src-a VIDEO_A.mp4 --src-b VIDEO_B.mp4 --logo logo.png
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
NAVY = (40, 70, 96)
RED = (233, 51, 55)
WHITE = (255, 255, 255)
FONT_BLACK = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
FONT_XBOLD = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
FONT_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"

# (fonte, início, fim, velocidade, ajuste de cor, título, subtítulo)
# Velocidade < 1 = câmera lenta (a fonte é 60fps, então fica fluido).
# Durações fecham em múltiplos de 0,5s = 1 batida a 120 BPM.
SHOTS = [
    ("b", 15.00, 16.50, 0.75, "cool", "CHEGA DE\nVARAL!", None),
    ("b", 9.60, 12.10, 1.00, "cool", "LAVA E SECA", "no mesmo lugar"),
    ("a", 14.40, 15.90, 0.75, "warm", "VOCÊ ESCOLHE", "a temperatura ideal"),
    ("a", 16.30, 17.20, 0.60, "warm", "SIMPLES", "e rapidinho"),
    ("a", 0.00, 2.00, 1.00, "warm", "ROUPA SEQUINHA", "e cheirosa"),
]
END = ("b", 0.00, 2.00, 0.50)  # fundo do cartão final (4s)

GRADE = {
    # fonte A puxa pro amarelo (luz quente): esfria um pouco
    "warm": "colorbalance=rs=-0.04:bs=0.06:rm=-0.03:bm=0.04,eq=contrast=1.08:saturation=1.18:gamma=1.02",
    "cool": "colorbalance=rs=0.01:bs=0.02,eq=contrast=1.08:saturation=1.22:gamma=1.03",
}


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def prep_clip(src, t0, t1, speed, grade, out, tmp):
    trf = os.path.join(tmp, os.path.basename(out) + ".trf")
    trim = f"trim={t0}:{t1},setpts=(PTS-STARTPTS)/{speed}"
    run(["ffmpeg", "-y", "-i", src, "-vf", f"{trim},vidstabdetect=shakiness=6:accuracy=15:result={trf}",
         "-f", "null", "-"])
    vf = ",".join([
        trim,
        f"vidstabtransform=input={trf}:smoothing=18:zoom=4:optzoom=0:interpol=bicubic",
        "hqdn3d=2.5:2:4:3",
        "fps=30",
        GRADE[grade],
        "scale=1080:1937:flags=lanczos",
        "crop=1080:1920",
        "cas=0.55",
        "format=yuv420p",
    ])
    run(["ffmpeg", "-y", "-i", src, "-vf", vf, "-an", "-c:v", "libx264", "-crf", "14",
         "-preset", "fast", out])


def read_frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    frames = []
    while True:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        frames.append(np.frombuffer(buf, np.uint8).reshape(H, W, 3))
    p.wait()
    return frames


# ---------- gráficos ----------

def ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    t = min(max(t, 0), 1)
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out(t):
    t = min(max(t, 0), 1)
    return 1 - (1 - t) ** 3


def text_card(title, subtitle):
    """Bloco de texto no estilo da logo: título branco em faixa vermelha,
    subtítulo azul-marinho em pílula branca."""
    ft = ImageFont.truetype(FONT_BLACK, 118)
    fs = ImageFont.truetype(FONT_XBOLD, 62)
    lines = title.split("\n")
    pad_x, pad_y, gap = 46, 22, 14
    sizes = [ft.getbbox(l) for l in lines]
    lw = [b[2] - b[0] for b in sizes]
    lh = 118
    title_h = len(lines) * (lh + 2 * pad_y) + (len(lines) - 1) * gap
    sub_w = sub_h = 0
    if subtitle:
        sb = fs.getbbox(subtitle)
        sub_w, sub_h = sb[2] - sb[0] + 2 * 40, 62 + 2 * 22
    cw = max(max(lw) + 2 * pad_x, sub_w) + 40
    ch = title_h + (sub_h + 18 if subtitle else 0) + 40
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(img), ImageDraw.Draw(shadow)
    y = 20
    for l, b, w in zip(lines, sizes, lw):
        bw = w + 2 * pad_x
        x = (cw - bw) // 2
        box = (x, y, x + bw, y + lh + 2 * pad_y)
        ds.rounded_rectangle((box[0], box[1] + 8, box[2], box[3] + 8), 26, fill=(0, 0, 0, 110))
        d.rounded_rectangle(box, 26, fill=RED + (255,))
        d.text((x + pad_x - b[0], y + pad_y - b[1] + (lh - (b[3] - b[1])) // 2), l, font=ft, fill=WHITE)
        y += lh + 2 * pad_y + gap
    if subtitle:
        y += 18 - gap
        x = (cw - sub_w) // 2
        box = (x, y, x + sub_w, y + sub_h)
        ds.rounded_rectangle((box[0], box[1] + 6, box[2], box[3] + 6), sub_h // 2, fill=(0, 0, 0, 100))
        d.rounded_rectangle(box, sub_h // 2, fill=WHITE + (255,), outline=NAVY + (255,), width=5)
        sb = fs.getbbox(subtitle)
        d.text((x + 40 - sb[0], y + (sub_h - (sb[3] - sb[1])) // 2 - sb[1]), subtitle, font=fs, fill=NAVY)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    card = Image.alpha_composite(shadow, img)
    if card.width > 1000:  # títulos longos: reduz para caber com margem
        card = card.resize((1000, round(card.height * 1000 / card.width)), Image.LANCZOS)
    return card


def load_logo(path, size):
    im = Image.open(path).convert("RGBA")
    # recorta só o círculo (fundo da arte é branco)
    cx, cy, r = 81.5, 72.5, 64.5
    big = im.resize((im.width * 8, im.height * 8), Image.LANCZOS)
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).ellipse(((cx - r) * 8, (cy - r) * 8, (cx + r) * 8, (cy + r) * 8), fill=255)
    big.putalpha(mask)
    big = big.crop((int((cx - r) * 8), int((cy - r) * 8), int((cx + r) * 8), int((cy + r) * 8)))
    logo = big.resize((size, size), Image.LANCZOS)
    logo = logo.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
    # anel branco + sombra para destacar sobre o vídeo
    pad = 40
    out = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((pad - 4, pad + 10, pad + size + 4, pad + size + 18), fill=(0, 0, 0, 140))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(out).ellipse((pad - 10, pad - 10, pad + size + 10, pad + size + 10), fill=WHITE + (255,))
    out.alpha_composite(logo, (pad, pad))
    return out


def paste_scaled(base, layer, cx, cy, scale, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    lw, lh = max(1, int(layer.width * scale)), max(1, int(layer.height * scale))
    l = layer.resize((lw, lh), Image.BICUBIC)
    if alpha < 1:
        a = l.getchannel("A").point(lambda v: int(v * alpha))
        l.putalpha(a)
    base.alpha_composite(l, (int(cx - lw / 2), int(cy - lh / 2)))


def brand_bar(base, progress):
    """Barrinha de progresso na base, nas cores da marca."""
    d = ImageDraw.Draw(base)
    d.rectangle((0, H - 14, W, H), fill=NAVY + (200,))
    d.rectangle((0, H - 14, int(W * progress), H), fill=RED + (255,))


def small_tag(text):
    f = ImageFont.truetype(FONT_BOLD, 40)
    b = f.getbbox(text)
    w, h = b[2] - b[0] + 56, 76
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=NAVY + (235,))
    d.text((28 - b[0], (h - (b[3] - b[1])) // 2 - b[1]), text, font=f, fill=WHITE)
    return im


# ---------- trilha ----------

def make_music(path, dur, cuts):
    sr = 44100
    n = int(sr * dur)
    t = np.arange(n) / sr
    out = np.zeros(n)
    beat = 0.5
    rng = np.random.default_rng(7)

    def add(sig, at):
        i = int(at * sr)
        j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[: j - i]

    # kick
    kl = int(0.35 * sr)
    kt = np.arange(kl) / sr
    kick = np.sin(2 * np.pi * (50 + 110 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
    # hat
    hl = int(0.05 * sr)
    hat = rng.standard_normal(hl) * np.exp(-np.arange(hl) / sr * 90)
    hat = np.diff(np.concatenate([[0], hat]))
    # clap
    cl = int(0.18 * sr)
    clap = rng.standard_normal(cl) * np.exp(-np.arange(cl) / sr * 22)
    clap = np.convolve(clap, np.ones(6) / 6, "same")

    # progressão alegre: C - G - Am - F
    chords = [[261.63, 329.63, 392.0], [246.94, 293.66, 392.0], [220.0, 261.63, 329.63], [220.0, 261.63, 349.23]]
    bass = [65.41, 98.0, 110.0, 87.31]
    bar = 4 * beat
    intro = beat * 2  # gancho começa só com os acordes, batida entra no 1º corte... depois de 1s
    nb = int(dur / beat)
    for k in range(nb):
        at = k * beat
        if at >= intro:
            add(kick * 0.9, at)
            if k % 2 == 1:
                add(clap * 0.35, at)
        add(hat * 0.18, at + beat / 2)
        if at >= intro:
            add(hat * 0.10, at)
    for b in range(int(math.ceil(dur / bar))):
        c = chords[b % 4]
        at = b * bar
        L = int(bar * sr)
        tt = np.arange(L) / sr
        # pad + stabs em semicolcheia sincopada
        pad = sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt) for f in c)
        pad *= 0.045 * (1 - np.exp(-tt * 6))
        add(pad, at)
        for off in (0.0, 0.75, 1.5, 2.0, 2.75, 3.5):
            sl = int(0.18 * sr)
            st = np.arange(sl) / sr
            stab = sum(np.sign(np.sin(2 * np.pi * f * 2 * st)) * 0.25 + np.sin(2 * np.pi * f * 2 * st) for f in c)
            add(stab * np.exp(-st * 18) * 0.05, at + off * beat)
        bl = int(beat * sr * 0.9)
        bt = np.arange(bl) / sr
        for q in range(4):
            if at + q * beat >= intro:
                add(np.sin(2 * np.pi * bass[b % 4] * bt) * np.exp(-bt * 3) * 0.35, at + q * beat + beat / 2)
    # whoosh nos cortes
    wl = int(0.35 * sr)
    wn = rng.standard_normal(wl)
    env = np.sin(np.linspace(0, np.pi, wl)) ** 2
    wn = np.convolve(wn, np.ones(30) / 30, "same") * env
    for c in cuts:
        add(wn * 0.6, max(0, c - 0.2))
    # final: fade out
    fade = np.ones(n)
    fl = int(0.8 * sr)
    fade[-fl:] = np.linspace(1, 0, fl)
    out *= fade
    out /= np.max(np.abs(out)) + 1e-9
    out = np.tanh(out * 1.4) * 0.85
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-a", required=True)
    ap.add_argument("--src-b", required=True)
    ap.add_argument("--logo", required=True)
    ap.add_argument("--out", default="out/seld-uruguaiana-reel.mp4")
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    srcs = {"a": args.src_a, "b": args.src_b}
    tmp = args.work or tempfile.mkdtemp()
    os.makedirs(tmp, exist_ok=True)

    clips = []
    for i, (s, t0, t1, sp, g, *_ ) in enumerate(SHOTS):
        out = os.path.join(tmp, f"shot{i}.mp4")
        if not os.path.exists(out):
            print(f"preparando take {i}...", file=sys.stderr)
            prep_clip(srcs[s], t0, t1, sp, g, out, tmp)
        clips.append(read_frames(out))
    end_path = os.path.join(tmp, "end.mp4")
    if not os.path.exists(end_path):
        prep_clip(srcs[END[0]], END[1], END[2], END[3], "cool", end_path, tmp)
    end_frames = read_frames(end_path)

    durs = [round((t1 - t0) / sp * FPS) for _, t0, t1, sp, *_ in SHOTS]
    end_len = round((END[2] - END[1]) / END[3] * FPS)
    total = sum(durs) + end_len
    cuts = np.cumsum(durs) / FPS

    cards = [text_card(s[5], s[6]) for s in SHOTS]
    logo = load_logo(args.logo, 520)
    tag = small_tag("SELD EXPRESS  •  URUGUAIANA")
    f_cta = ImageFont.truetype(FONT_BLACK, 84)
    f_sub = ImageFont.truetype(FONT_XBOLD, 54)

    wav = os.path.join(tmp, "music.wav")
    make_music(wav, total / FPS, list(cuts))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out,
    ], stdin=subprocess.PIPE)

    gidx = 0
    for ci, frames in enumerate(clips):
        n = durs[ci]
        for k in range(n):
            fr = frames[min(k, len(frames) - 1)]
            # punch-in suave contínuo + "zoom de impacto" no início de cada corte
            z = 1.0 + 0.04 * k / n + (0.10 * (1 - ease_out(k / 6)) if ci > 0 else 0)
            img = Image.fromarray(fr)
            if z > 1.001:
                cw, ch = W / z, H / z
                img = img.crop(((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)).resize((W, H), Image.BICUBIC)
            img = img.convert("RGBA")
            # flash branco rápido no corte
            if ci > 0 and k < 3:
                img = Image.blend(img, Image.new("RGBA", (W, H), WHITE + (255,)), 0.45 * (1 - k / 3))
            # texto
            t = k / FPS
            sc = ease_out_back((t - 0.08) / 0.35)
            alpha = 1.0 if k < n - 4 else max(0, (n - k) / 4)
            cy = 560 if ci == 0 else 1380
            paste_scaled(img, cards[ci], W / 2, cy, sc, alpha)
            # selo da marca no canto
            paste_scaled(img, logo, W - 120, 150, 0.36)
            brand_bar(img, gidx / total)
            enc.stdin.write(img.convert("RGB").tobytes())
            gidx += 1

    # cartão final
    for k in range(end_len):
        fr = end_frames[min(k, len(end_frames) - 1)]
        img = Image.fromarray(fr).filter(ImageFilter.GaussianBlur(14)).convert("RGBA")
        tint = Image.new("RGBA", (W, H), NAVY + (int(185 * ease_out(k / 10)),))
        img = Image.alpha_composite(img, tint)
        if k < 3:
            img = Image.blend(img, Image.new("RGBA", (W, H), WHITE + (255,)), 0.5 * (1 - k / 3))
        t = k / FPS
        paste_scaled(img, logo, W / 2, 640, ease_out_back((t - 0.05) / 0.45))
        d = ImageDraw.Draw(img)
        a1 = ease_out((t - 0.45) / 0.3)
        if a1 > 0:
            line = "LAVE E SEQUE"
            b = f_cta.getbbox(line)
            y = 1090 + 40 * (1 - a1)
            d.text(((W - (b[2] - b[0])) / 2 - b[0], y), line, font=f_cta, fill=WHITE + (int(255 * a1),))
            line2 = "SEM COMPLICAÇÃO"
            b = f_cta.getbbox(line2)
            d.text(((W - (b[2] - b[0])) / 2 - b[0], y + 104), line2, font=f_cta, fill=WHITE + (int(255 * a1),))
        a2 = ease_out_back((t - 0.8) / 0.4)
        if a2 > 0:
            cta = Image.new("RGBA", (760, 128), (0, 0, 0, 0))
            dc = ImageDraw.Draw(cta)
            dc.rounded_rectangle((0, 0, 759, 127), 64, fill=RED + (255,))
            txt = "VEM PRA SELD!"
            b = f_cta.getbbox(txt)
            dc.text(((760 - (b[2] - b[0])) / 2 - b[0], (128 - (b[3] - b[1])) / 2 - b[1]), txt, font=f_cta, fill=WHITE)
            pulse = 1 + 0.03 * math.sin(max(0, t - 1.2) * 2 * math.pi * 2) if t > 1.2 else 1
            paste_scaled(img, cta, W / 2, 1430, a2 * pulse)
        a3 = ease_out((t - 1.1) / 0.3)
        if a3 > 0:
            paste_scaled(img, tag, W / 2, 1600, 1.0, a3)
        brand_bar(img, gidx / total)
        enc.stdin.write(img.convert("RGB").tobytes())
        gidx += 1

    enc.stdin.close()
    enc.wait()
    print(args.out)


if __name__ == "__main__":
    main()
