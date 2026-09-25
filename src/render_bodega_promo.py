#!/usr/bin/env python3
"""Bodega do Gringo — vídeo promocional do rodízio (Reels/TikTok 1080x1920).

Pipeline 100% ffmpeg + Pillow:
  1. Cada trecho é cortado, enquadrado (cover 9:16), recebe Ken Burns via zoompan,
     correção de cor (contraste/saturação/nitidez/vinheta) e um layer de texto
     renderizado com Pillow (PNG RGBA) com fade in/out.
  2. Cartão final: fundo escuro com padrão xadrez vermelho (identidade do restaurante),
     logo com pop-in suave, chamada para reserva.
  3. Tudo concatenado; áudio ambiente dos clipes com crossfade e normalização.

Uso:
  python3 src/render_bodega_promo.py --clips DIR --logo assets/bodega-logo.png \
      --fonts assets/fonts --out out/bodega-rodizio.mp4
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
RED = (179, 33, 43)
CREAM = (247, 240, 228)
INK = (24, 20, 18)


# ----------------------------------------------------------------------------
# Roteiro (tempos em segundos no arquivo de origem)
# ----------------------------------------------------------------------------
# focus_y: onde está a ação no quadro (0 = topo, 1 = base) para o zoom mirar.
SHOTS = [
    dict(src="IMG_1972", start=4.3, dur=3.0, zoom=(1.18, 1.30), focus_y=0.38,
         title="A MASSA SAI DE DENTRO\nDA RODA DE QUEIJO", sub="rodízio da Bodega do Gringo", hook=True),
    dict(src="IMG_1980", start=0.0, dur=3.0, zoom=(1.00, 1.10), focus_y=0.50,
         title="CARNES SUCULENTAS", sub="com molho da casa"),
    dict(src="IMG_1976", start=7.6, dur=2.6, zoom=(1.00, 1.08), focus_y=0.50,
         title="RISOTO CREMOSO", sub="feito na hora"),
    dict(src="IMG_1972", start=0.8, dur=3.4, zoom=(1.02, 1.10), focus_y=0.40,
         title="SEQUÊNCIA DE MASSAS", sub="servida na sua mesa"),
    dict(src="IMG_1976", start=4.4, dur=2.8, zoom=(1.00, 1.08), focus_y=0.45,
         title="SABOR DA SERRA GAÚCHA", sub="receitas da colônia italiana"),
    dict(src="IMG_1972", start=8.0, dur=3.0, zoom=(1.08, 1.16), focus_y=0.42,
         title="É SÓ CHEGAR COM FOME", sub="a gente cuida do resto"),
    dict(src="IMG_1976", start=0.0, dur=2.6, zoom=(1.06, 1.00), focus_y=0.55,
         title="RESERVE SUA MESA", sub="quarta a domingo · somente com reserva", cta=True),
]
END_DUR = 5.0
END_TEXT = ["BODEGA DO GRINGO", "Caxias do Sul · RS"]
END_CTA = "Reservas pelo link na bio"


def run(cmd, **kw):
    print(" ".join(str(c) for c in cmd)[:400], file=sys.stderr)
    subprocess.run(cmd, check=True, **kw)


def font(fonts_dir, name, size):
    return ImageFont.truetype(os.path.join(fonts_dir, name), size)


def draw_text_with_shadow(draw, xy, text, fnt, fill, anchor="mm", shadow=(0, 0, 0, 170), blur_layer=None):
    x, y = xy
    if blur_layer is not None:
        sd = ImageDraw.Draw(blur_layer)
        sd.text((x + 4, y + 6), text, font=fnt, fill=shadow, anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def render_text_layer(shot, fonts_dir, path):
    """PNG 1080x1920 RGBA com título + subtítulo no estilo da marca."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    title_lines = shot["title"].split("\n")
    size = 128 if len(title_lines) > 1 else 150
    big = font(fonts_dir, "BebasNeue.ttf", size)
    # encolhe até caber na área segura (margem de 70px de cada lado)
    while size > 80 and max(d.textlength(l, font=big) for l in title_lines) > W - 140:
        size -= 4
        big = font(fonts_dir, "BebasNeue.ttf", size)
    small = font(fonts_dir, "Montserrat-SemiBold.ttf", 40)

    # Área segura para Reels: evita os 300px de baixo e 250px do topo.
    if shot.get("hook"):
        base_y = 330
    else:
        base_y = 1290
    line_h = big.size * 0.95
    y = base_y
    for line in title_lines:
        draw_text_with_shadow(d, (W / 2, y), line, big, (255, 255, 255, 255), blur_layer=shadow)
        y += line_h

    # Subtítulo em "pill" vermelha (cor do xadrez da casa)
    sub = shot["sub"]
    tw = d.textlength(sub, font=small)
    pw, ph = tw + 64, 74
    px, py = (W - pw) / 2, y + 6
    if shot.get("cta"):
        # CTA: pill mais alta e destacada
        ph = 84
        small = font(fonts_dir, "Montserrat-ExtraBold.ttf", 38)
        tw = d.textlength(sub, font=small)
        pw = tw + 80
        px = (W - pw) / 2
    ImageDraw.Draw(shadow).rounded_rectangle((px + 3, py + 6, px + pw + 3, py + ph + 6), ph / 2, fill=(0, 0, 0, 140))
    d.rounded_rectangle((px, py, px + pw, py + ph), ph / 2, fill=RED + (255,))
    d.text((W / 2, py + ph / 2 + 1), sub, font=small, fill=CREAM + (255,), anchor="mm")

    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    out = Image.alpha_composite(shadow, img)
    out.save(path)


def gingham(w, h, cell=48, alpha=38):
    """Padrão xadrez vermelho translúcido (toalha da Bodega)."""
    tile = Image.new("RGBA", (cell * 2, cell * 2), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.rectangle((0, 0, cell, cell), fill=RED + (alpha,))
    td.rectangle((cell, cell, cell * 2, cell * 2), fill=RED + (alpha,))
    td.rectangle((cell, 0, cell * 2, cell), fill=RED + (alpha // 2,))
    td.rectangle((0, cell, cell, cell * 2), fill=RED + (alpha // 2,))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for yy in range(0, h, cell * 2):
        for xx in range(0, w, cell * 2):
            layer.paste(tile, (xx, yy))
    return layer


def ease_out_back(t, s=1.4):
    t -= 1
    return 1 + t * t * ((s + 1) * t + s)


def render_end_card(logo_path, fonts_dir, out_mp4, tmp):
    """Cartão final animado: frames RGB por stdin -> ffmpeg (com áudio silencioso)."""
    n = int(END_DUR * FPS)
    bg = Image.new("RGBA", (W, H), INK + (255,))
    # vinheta quente + xadrez sutil
    g = gingham(W, H)
    bg = Image.alpha_composite(bg, g)
    vign = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vign)
    vd.ellipse((-200, -100, W + 200, H + 100), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(260))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dark.putalpha(Image.eval(vign, lambda v: 255 - v))
    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    bg = Image.alpha_composite(bg, dark.filter(ImageFilter.GaussianBlur(1)))

    logo = Image.open(logo_path).convert("RGBA")
    LOGO_SIZE = 720
    title_f = font(fonts_dir, "BebasNeue.ttf", 118)
    sub_f = font(fonts_dir, "Montserrat-SemiBold.ttf", 42)
    cta_f = font(fonts_dir, "Montserrat-ExtraBold.ttf", 38)

    ff = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(END_DUR), "-shortest",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", out_mp4,
    ]
    p = subprocess.Popen(ff, stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        frame = bg.copy()
        # logo pop-in (0.0 -> 0.7s), depois respira levemente
        k = min(1.0, t / 0.7)
        s = ease_out_back(k) if k < 1 else 1 + 0.012 * math.sin((t - 0.7) * 1.6)
        size = max(2, int(LOGO_SIZE * s))
        lg = logo.resize((size, size), Image.LANCZOS)
        a = lg.split()[3].point(lambda v: int(v * min(1.0, t / 0.35)))
        lg.putalpha(a)
        frame.alpha_composite(lg, (int(W / 2 - size / 2), int(760 - size / 2)))

        d = ImageDraw.Draw(frame)
        # textos entram em sequência
        def fade(start, dur=0.4):
            return max(0.0, min(1.0, (t - start) / dur))
        a1 = fade(0.55)
        if a1 > 0:
            dy = int((1 - a1) * 30)
            d.text((W / 2, 1230 + dy), END_TEXT[0], font=title_f, fill=(255, 255, 255, int(255 * a1)), anchor="mm")
        a2 = fade(0.75)
        if a2 > 0:
            dy = int((1 - a2) * 30)
            d.text((W / 2, 1325 + dy), END_TEXT[1], font=sub_f, fill=CREAM + (int(230 * a2),), anchor="mm")
        a3 = fade(1.05)
        if a3 > 0:
            tw = d.textlength(END_CTA, font=cta_f)
            pw, ph = tw + 90, 88
            px, py = (W - pw) / 2, 1440 + int((1 - a3) * 30)
            d.rounded_rectangle((px, py, px + pw, py + ph), ph / 2, fill=RED + (int(255 * a3),))
            d.text((W / 2, py + ph / 2 + 1), END_CTA, font=cta_f, fill=CREAM + (int(255 * a3),), anchor="mm")
        a4 = fade(1.35)
        if a4 > 0:
            d.text((W / 2, 1585), "quarta a domingo  ·  somente com reserva", font=font(fonts_dir, "Montserrat-SemiBold.ttf", 30),
                   fill=(200, 190, 178, int(220 * a4)), anchor="mm")
        # fade final para preto
        if t > END_DUR - 0.6:
            fo = (t - (END_DUR - 0.6)) / 0.6
            frame = Image.alpha_composite(frame, Image.new("RGBA", (W, H), (0, 0, 0, int(255 * fo))))
        p.stdin.write(frame.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg falhou no cartão final")


def render_shot(i, shot, clips, fonts_dir, tmp):
    src = clips[shot["src"]]
    txt = os.path.join(tmp, f"txt{i}.png")
    render_text_layer(shot, fonts_dir, txt)
    out = os.path.join(tmp, f"seg{i}.mp4")
    dur = shot["dur"]
    n = int(dur * FPS)
    z0, z1 = shot["zoom"]
    fy = shot["focus_y"]
    # Ken Burns: zoompan em cada frame (d=1). Enquadramento cover 9:16 antes.
    zexpr = f"{z0}+({z1}-{z0})*on/{n}"
    vf = (
        f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='min(max(ih*{fy}-(ih/zoom/2),0),ih-ih/zoom)':"
        f"d=1:s={W}x{H}:fps={FPS},"
        # correção de cor: mais contraste, saturação e nitidez; vinheta suave
        f"eq=contrast=1.07:brightness=0.005:saturation=1.22:gamma=0.98,"
        f"unsharp=5:5:0.55:5:5:0.0,vignette=angle=PI/5.2,"
        f"setsar=1"
    )
    # Texto: fade in aos 0.25s e fade out 0.3s antes do fim
    fade_out_st = max(0.0, dur - 0.35)
    t_in = 0.12 if shot.get("hook") else 0.25
    fc = (
        f"[0:v]{vf}[base];"
        f"[1:v]format=rgba,fade=in:st={t_in}:d=0.3:alpha=1,fade=out:st={fade_out_st}:d=0.3:alpha=1[txt];"
        f"[base][txt]overlay=0:0:format=auto,format=yuv420p[v];"
        f"[0:a]aresample=48000,volume=1.0[a]"
    )
    run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", str(shot["start"]), "-t", str(dur), "-i", src,
        "-loop", "1", "-t", str(dur), "-i", txt,
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-t", str(dur),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out,
    ])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True, help="pasta com IMG_1972.MP4 etc. (nome pode ter prefixo)")
    ap.add_argument("--logo", required=True)
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    clips = {}
    for f in os.listdir(args.clips):
        for key in {s["src"] for s in SHOTS}:
            if key in f and f.lower().endswith(".mp4"):
                clips[key] = os.path.join(args.clips, f)
    missing = {s["src"] for s in SHOTS} - set(clips)
    if missing:
        raise SystemExit(f"clipes faltando: {missing}")

    tmp = tempfile.mkdtemp(prefix="bodega_")
    segs = [render_shot(i, s, clips, args.fonts, tmp) for i, s in enumerate(SHOTS)]
    end = os.path.join(tmp, "end.mp4")
    render_end_card(args.logo, args.fonts, end, tmp)
    segs.append(end)

    # Concatenação: cortes secos entre pratos (ritmo de reel) e fade para o cartão final.
    inputs = []
    for s in segs:
        inputs += ["-i", s]
    n = len(segs)
    parts = []
    for i in range(n):
        v = f"[{i}:v]"
        if i == n - 1:
            v_f = f"[{i}:v]fade=in:st=0:d=0.35[v{i}];"
        elif i == 0:
            v_f = f"[{i}:v]fade=in:st=0:d=0.15[v{i}];"
        else:
            v_f = f"[{i}:v]copy[v{i}];"
        parts.append(v_f)
    # áudio: leve crossfade entre segmentos usando acrossfade encadeado
    afilters = "".join(parts)
    vcat = "".join(f"[v{i}]" for i in range(n))
    afilters += "".join(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}];" for i in range(n))
    prev = "[a0]"
    for i in range(1, n):
        outl = f"[ax{i}]" if i < n - 1 else "[amix]"
        afilters += f"{prev}[a{i}]acrossfade=d=0.12:c1=tri:c2=tri{outl};"
        prev = outl
    afilters += f"{vcat}concat=n={n}:v=1:a=0[vcat];"
    # ambiente do restaurante: passa-alta leve pra tirar ronco, normaliza e deixa mais baixo
    afilters += "[amix]highpass=f=90,lowpass=f=12000,loudnorm=I=-18:TP=-1.5:LRA=9,volume=0.9[aout]"
    total = sum(s["dur"] for s in SHOTS) + END_DUR
    run([
        "ffmpeg", "-y", "-v", "error", *inputs,
        "-filter_complex", afilters, "-map", "[vcat]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.2f}", args.out,
    ])
    # capa (thumbnail) = frame do gancho
    run(["ffmpeg", "-y", "-v", "error", "-ss", "0.9", "-i", args.out, "-frames:v", "1", "-q:v", "2",
         os.path.splitext(args.out)[0] + "-capa.jpg"])
    print("OK:", args.out, f"({total:.1f}s)")


if __name__ == "__main__":
    main()
