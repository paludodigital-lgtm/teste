#!/usr/bin/env python3
"""Bodega do Gringo — V3 (corte profissional) do reel do rodízio.

Princípios desta versão:
  * Imagem: origem 720p tratada com estabilização, upscale Lanczos, zoom mínimo
    (nunca mais que 5%), nitidez moderada, grão fino e grade de cor por ambiente
    (salão quente/lâmpada x mesa externa fria) para um look único de "trattoria".
  * Ritmo: cortes secos alinhados à batida (100 BPM = 0,6 s), sem transições de efeito.
    Gancho em slow-motion 0,6x com interpolação de movimento.
  * Tipografia: poucas palavras, caixa alta com tracking, entrada deslizando de baixo
    com easing, sem carimbos nem pílulas. Zona segura de Reels respeitada.
  * Áudio: trilha instrumental própria (src/make_music_bed.py) + ambiente do salão
    bem baixo por baixo, normalizado.
  * Encerramento: dip to black e cartão limpo com a logo.

Uso:
  python3 src/render_bodega_promo_v3.py --clips DIR --logo assets/bodega-logo-white.png \
      --fonts assets/fonts --out out/bodega-rodizio-v3.mp4 [--tmp DIR]
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import render_bodega_promo as v1  # noqa: E402  (run, stabilize helpers)
from render_bodega_promo_v2 import stabilize  # noqa: E402

W, H, FPS = 1080, 1920, 30
BPM = 100
BEAT = 60 / BPM
CREAM = (246, 238, 226)
INK = (16, 12, 10)

# Grades por ambiente. "salao" = clipe interno com lâmpada quente; "mesa" = pratos na mesa externa.
GRADE = {
    "salao": ("colortemperature=temperature=5200:mix=0.7,"
              "curves=master='0/0.02 0.25/0.24 0.6/0.65 1/0.97',"
              "colorbalance=rs=0.03:gs=-0.02:bs=-0.02,eq=saturation=1.12:contrast=1.03"),
    "mesa": ("colortemperature=temperature=7200:mix=0.6,"
             "curves=master='0/0.02 0.25/0.23 0.6/0.64 1/0.97',"
             "colorbalance=rs=0.04:bs=-0.03:rh=0.01:bh=-0.02,eq=saturation=1.10:contrast=1.04"),
}
ENV = {"IMG_1972": "salao", "IMG_1976": "mesa", "IMG_1980": "mesa"}

# Roteiro na grade de batidas (durações em batidas). Fonte 720p: zoom máx. 1.05.
SHOTS = [
    dict(src="IMG_1972", start=4.6, beats=5, speed=0.6, push=(1.00, 1.04), focus_y=0.40,
         text=["RODÍZIO NA", "RODA DE QUEIJO"], kicker="BODEGA DO GRINGO · CAXIAS DO SUL", top=True),
    dict(src="IMG_1980", start=0.3, beats=3, push=(1.00, 1.05), focus_y=0.50),
    dict(src="IMG_1976", start=5.8, beats=3, push=(1.04, 1.00), focus_y=0.50),
    dict(src="IMG_1972", start=1.2, beats=4, speed=1.25, push=(1.00, 1.04), focus_y=0.40,
         text=["MASSAS · RISOTOS · CARNES"], kicker="SERVIDOS À MESA PELO GRINGO"),
    dict(src="IMG_1976", start=4.4, beats=2, push=(1.00, 1.03), focus_y=0.45),
    dict(src="IMG_1972", start=9.0, beats=3, push=(1.02, 1.05), focus_y=0.42,
         text=["SABOR DA SERRA GAÚCHA"], kicker="RECEITAS DA COLÔNIA ITALIANA"),
    dict(src="IMG_1976", start=0.0, beats=3, push=(1.05, 1.00), focus_y=0.55,
         text=["RESERVE SUA MESA"], kicker="QUARTA A DOMINGO · SOMENTE COM RESERVA", cta=True),
]
END_BEATS = 6


def font(fonts_dir, name, size):
    return ImageFont.truetype(os.path.join(fonts_dir, name), size)


def draw_tracked(draw, cx, y, text, fnt, fill, tracking, anchor_mid=True, shadow_draw=None):
    """Texto com espaçamento entre letras, centralizado em cx."""
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        if shadow_draw is not None:
            shadow_draw.text((x + 2, y + 4), ch, font=fnt, fill=(0, 0, 0, 150), anchor="ls")
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
        x += w + tracking
    return total


def render_text_layer(shot, fonts_dir, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, sd = ImageDraw.Draw(img), ImageDraw.Draw(sh)
    lines = shot["text"]
    big = font(fonts_dir, "Oswald-Bold.ttf", 76 if len(lines) > 1 else 68)
    small = font(fonts_dir, "Montserrat-SemiBold.ttf", 26)
    # bloco: kicker pequeno + regra fina + título; topo (gancho) ou terço inferior
    y = 360 if shot.get("top") else 1400
    if shot.get("kicker") and not shot.get("cta"):
        draw_tracked(d, W / 2, y, shot["kicker"], small, CREAM + (235,), 4, shadow_draw=sd)
        y += 26
        d.rectangle((W / 2 - 28, y, W / 2 + 28, y + 2), fill=CREAM + (220,))
        y += 74
    else:
        y += 20
    for ln in lines:
        draw_tracked(d, W / 2, y, ln, big, (255, 255, 255, 255), 3, shadow_draw=sd)
        y += big.size * 1.12
    if shot.get("cta"):
        y += 4
        d.rectangle((W / 2 - 28, y - 30, W / 2 + 28, y - 28), fill=CREAM + (220,))
        draw_tracked(d, W / 2, y + 10, shot["kicker"], small, CREAM + (235,), 4, shadow_draw=sd)
    sh = sh.filter(ImageFilter.GaussianBlur(8))
    Image.alpha_composite(sh, img).save(path)


def ease_out(t):
    return 1 - (1 - t) ** 3


def render_end_card(logo_path, fonts_dir, out_mp4, dur):
    n = int(dur * FPS)
    base = Image.new("RGBA", (W, H), INK + (255,))
    # leve luz quente no centro
    import numpy as np
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / 620) ** 2 + ((yy - 860) / 760) ** 2)
    glow = Image.fromarray((70 * np.clip(1 - r, 0, 1) ** 2).astype("uint8"), "L")
    warm = Image.new("RGBA", (W, H), (120, 60, 30, 255))
    warm.putalpha(glow)
    base = Image.alpha_composite(base, warm)
    logo = Image.open(logo_path).convert("RGBA")
    SIZE = 560
    tf = font(fonts_dir, "Oswald-Bold.ttf", 64)
    sf = font(fonts_dir, "Montserrat-SemiBold.ttf", 26)
    ff = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
          "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", out_mp4]
    p = subprocess.Popen(ff, stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        fr = base.copy()
        k = ease_out(min(1, t / 0.6))
        s = int(SIZE * (0.92 + 0.08 * k))
        lg = logo.resize((s, s), Image.LANCZOS)
        a = lg.split()[3].point(lambda v: int(v * min(1, t / 0.4)))
        lg.putalpha(a)
        fr.alpha_composite(lg, (int(W / 2 - s / 2), int(800 - s / 2)))
        d = ImageDraw.Draw(fr)
        for j, (txt, fnt, y0, tr) in enumerate([("BODEGA DO GRINGO", tf, 1200, 6), ("CAXIAS DO SUL · RS", sf, 1262, 4),
                                                ("RESERVAS PELO LINK NA BIO", sf, 1400, 4)]):
            st = 0.35 + j * 0.15
            kk = ease_out(max(0, min(1, (t - st) / 0.5)))
            if kk <= 0:
                continue
            col = ((255, 255, 255) if j == 0 else CREAM) + (int(255 * kk),)
            draw_tracked(d, W / 2, y0 + int((1 - kk) * 24), txt, fnt, col, tr)
            if j == 1:
                d.rectangle((W / 2 - 28, 1326, W / 2 + 28, 1328), fill=CREAM + (int(200 * kk),))
        if t > dur - 0.5:
            fo = (t - (dur - 0.5)) / 0.5
            fr = Image.alpha_composite(fr, Image.new("RGBA", (W, H), (0, 0, 0, int(255 * fo))))
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg falhou no cartão final")


def render_shot(i, shot, clips, fonts_dir, tmp):
    src = clips[shot["src"]]
    speed = shot.get("speed", 1.0)
    out_dur = shot["beats"] * BEAT
    src_dur = out_dur * speed
    n = int(out_dur * FPS)
    z0, z1 = shot["push"]
    fy = shot["focus_y"]
    if speed < 1:
        tempo = f"setpts={1/speed:.4f}*PTS,minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
    elif speed > 1:
        tempo = f"setpts={1/speed:.4f}*PTS,fps={FPS},"
    else:
        tempo = f"fps={FPS},"
    vf = (
        f"{tempo}scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
        f"zoompan=z='{z0}+({z1}-{z0})*on/{n}':x='iw/2-(iw/zoom/2)':"
        f"y='min(max(ih*{fy}-(ih/zoom/2),0),ih-ih/zoom)':d=1:s={W}x{H}:fps={FPS},"
        f"{GRADE[ENV[shot['src']]]},unsharp=5:5:0.4:3:3:0.0,noise=alls=6:allf=t+u,"
        f"vignette=angle=PI/7.5,setsar=1"
    )
    out = os.path.join(tmp, f"seg{i}.mp4")
    inputs = ["-ss", str(shot["start"]), "-t", f"{src_dur + 0.2:.3f}", "-i", src]
    if shot.get("text"):
        txt = os.path.join(tmp, f"txt{i}.png")
        render_text_layer(shot, fonts_dir, txt)
        inputs += ["-loop", "1", "-t", f"{out_dur:.3f}", "-i", txt]
        t_in = 0.05 if shot.get("top") else 0.15
        fo = max(0.0, out_dur - 0.25)
        # entrada: desliza 36px de baixo para cima com easing cúbico + fade
        fc = (f"[0:v]{vf}[base];"
              f"[1:v]format=rgba,fade=in:st={t_in}:d=0.3:alpha=1,fade=out:st={fo}:d=0.25:alpha=1[txt];"
              f"[base][txt]overlay=x=0:y='36*pow(1-min(max(t-{t_in},0)/0.5,1),3)':format=auto,format=yuv420p[v];")
    else:
        fc = f"[0:v]{vf},format=yuv420p[v];"
    fc += f"[0:a]atempo={speed},aresample=48000[a]"
    v1.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-t", f"{out_dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out])
    return out, out_dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--logo", required=True)
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tmp", default=None)
    args = ap.parse_args()
    tmp = args.tmp or tempfile.mkdtemp(prefix="bodega_v3_")
    os.makedirs(tmp, exist_ok=True)

    raw = {}
    for f in os.listdir(args.clips):
        for key in {s["src"] for s in SHOTS}:
            if key in f and f.lower().endswith(".mp4"):
                raw[key] = os.path.join(args.clips, f)
    missing = {s["src"] for s in SHOTS} - set(raw)
    if missing:
        raise SystemExit(f"clipes faltando: {missing}")
    clips = {k: stabilize(p, tmp) for k, p in raw.items()}

    segs = [render_shot(i, s, clips, args.fonts, tmp) for i, s in enumerate(SHOTS)]
    end_dur = END_BEATS * BEAT
    end = os.path.join(tmp, "end.mp4")
    render_end_card(args.logo, args.fonts, end, end_dur)
    total = sum(d for _, d in segs) + end_dur

    # trilha
    bed = os.path.join(tmp, "bed.wav")
    v1.run([sys.executable, os.path.join(os.path.dirname(__file__), "make_music_bed.py"),
            "--seconds", f"{total:.2f}", "--bpm", str(BPM), "--out", bed])

    n = len(segs)
    inputs = []
    for p, _ in segs:
        inputs += ["-i", p]
    inputs += ["-i", end, "-i", bed]
    fc = ""
    for i in range(n):
        fc += f"[{i}:v]setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}];"
        fc += f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}];"
    # último take faz dip to black antes do cartão
    last = n - 1
    fc = fc.replace(f"[v{last}];", f",fade=out:st={segs[last][1]-0.3:.3f}:d=0.3[v{last}];")
    fc += f"[{n}:v]setpts=PTS-STARTPTS,fps={FPS},format=yuv420p,fade=in:st=0:d=0.3[vend];"
    fc += "".join(f"[v{i}]" for i in range(n)) + f"[vend]concat=n={n+1}:v=1:a=0[vout];"
    fc += "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,apad,atrim=0:{total:.3f}[amb];"
    # ambiente bem baixo e filtrado; trilha em primeiro plano
    fc += "[amb]highpass=f=200,lowpass=f=6000,volume=0.16[amb2];"
    fc += f"[{n+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.95[mus];"
    fc += "[mus][amb2]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.0:LRA=8[aout]"
    v1.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}", args.out])
    v1.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.4", "-i", args.out, "-frames:v", "1", "-q:v", "2",
            os.path.splitext(args.out)[0] + "-capa.jpg"])
    print("OK:", args.out, f"({total:.1f}s)")


if __name__ == "__main__":
    main()
