"""Ajuste do vídeo de dicas gravado pela agência (WhatsApp, 3 min, 576x1024).

Mantém o áudio original, tira silêncios e respiros, encurta as demonstrações
sem fala, sobe para 1080x1920 e coloca o título de cada dica na tela.

    python3 src/edit_dicas.py --src video.mp4 --out out/dicas-gravacao.mp4

Os tempos abaixo são do vídeo original (em segundos), tirados da transcrição.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile

from PIL import ImageDraw

from render_tutorial import (H, TEAL, W, WHITE, font, run, scene_overlay)

FPS = 30

# Trechos que ficam, na ordem (início, fim). Fala com uma folguinha nas
# pontas; demonstrações sem fala encurtadas para o melhor pedaço.
KEEP = [
    (0.95, 14.75),     # abertura
    (15.15, 33.65),    # fachada
    (33.85, 44.05),
    (44.30, 49.45),    # vertical e horizontal
    (49.70, 57.55),
    (57.75, 59.95),
    (61.50, 67.60),    # entorno
    (67.95, 86.60),
    (88.00, 95.00),    # demo: filmando ao redor
    (100.45, 113.30),  # localização ("Outro ponto importante...")
    (115.00, 137.85),
    (138.40, 144.40),  # demo: filmando o posto (vertical)
    (149.80, 153.80),  # demo: foto na horizontal
    (156.30, 164.70),  # estacionamento
    (164.70, 180.10),
]

# Seções: (início, fim, rótulo do topo)
SECTIONS = [
    (0.0, 15.0, None),
    (15.0, 44.5, "DICA 1  •  FACHADA"),
    (44.5, 61.0, "DICA 2  •  VERTICAL E HORIZONTAL"),
    (61.0, 100.0, "DICA 3  •  GRAVE O ENTORNO"),
    (100.0, 156.0, "DICA 4  •  AJUDE A LOCALIZAR"),
    (156.0, 181.0, "DICA 5  •  ESTACIONAMENTO"),
]

# Frases na base da tela: (início, fim, texto, marca)
CALLOUTS = [
    (15.3, 30.0, "Pegue a lavanderia inteira", "ok"),
    (30.0, 44.5, "Foto mais aberta: a gente corta na edição", "ok"),
    (44.3, 49.7, "Envie nas duas posições", None),
    (49.7, 57.6, "Vertical: Reels e Stories", "ok"),
    (57.6, 61.0, "Horizontal: feed", "ok"),
    (61.5, 68.0, "Mostre o que tem ao redor", None),
    (68.0, 86.6, "Mercado, avenida, pontos conhecidos", "ok"),
    (88.0, 95.0, "Gire devagar mostrando a região", "ok"),
    (100.4, 113.3, "Afaste-se: vá até a esquina", "ok"),
    (115.0, 137.9, "Mostre o posto, a galeria ou o shopping", "ok"),
    (138.4, 144.4, "Vertical para vídeo", "ok"),
    (149.8, 153.8, "Horizontal para foto", "ok"),
    (156.3, 164.7, "Tem vagas? Mostre!", "ok"),
    (164.7, 180.1, "Placas e vagas ajudam o cliente", "ok"),
]


def intro_overlay():
    img = scene_overlay(None, None, None)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((64, H - 640, 64 + 300, H - 570), radius=35, fill=TEAL + (240,))
    d.text((64 + 150, H - 605), "DICAS", font=font(40, "Bold"), fill=WHITE, anchor="mm")
    f = font(84, "Black")
    for i, line in enumerate(["Como enviar fotos", "e vídeos para", "a agência"]):
        d.text((64, H - 530 + i * 96), line, font=f, fill=WHITE)
    return img


def label_at(t):
    for a, b, lab in SECTIONS:
        if a <= t < b:
            return lab
    return None


def callout_at(t):
    for a, b, txt, kind in CALLOUTS:
        if a <= t < b:
            return txt, kind
    return None, None


def pieces():
    """Divide cada trecho nos pontos onde o texto da tela muda."""
    cuts = sorted({x for a, b, *_ in CALLOUTS for x in (a, b)} | {a for a, _, _ in SECTIONS})
    for a, b in KEEP:
        pts = [a] + [c for c in cuts if a < c < b] + [b]
        for s, e in zip(pts, pts[1:]):
            if e - s > 0.05:
                yield s, e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="out/dicas-gravacao.mp4")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="dicas_", dir=os.environ.get("TUT_TMP"))
    overlays, parts = {}, []
    for i, (s, e) in enumerate(pieces()):
        mid = (s + e) / 2
        key = ("intro",) if mid < 15.0 else (label_at(mid), *callout_at(mid))
        if key not in overlays:
            png = os.path.join(tmp, f"ov{len(overlays)}.png")
            (intro_overlay() if key == ("intro",) else scene_overlay(*key)).save(png)
            overlays[key] = png
        png = overlays[key]
        # o texto só "entra" com fade quando muda; dentro do mesmo texto fica fixo
        prev = parts[-1][1] if parts else None
        fade = "fade=t=in:st=0:d=0.25:alpha=1," if prev != png else ""
        dur = e - s
        out = os.path.join(tmp, f"{i:03d}.mp4")
        vf = (f"[0:v]scale={W}:{H}:flags=lanczos,unsharp=5:5:0.6,"
              f"eq=contrast=1.04:saturation=1.08,setsar=1,fps={FPS}[v];"
              f"[1:v]format=rgba,{fade}null[o];[v][o]overlay=0:0:shortest=1[vo];"
              f"[0:a]aresample=48000,afade=t=in:d=0.02,"
              f"afade=t=out:st={max(0, dur - 0.03):.3f}:d=0.03[ao]")
        run(["ffmpeg", "-y", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}", "-i", args.src,
             "-loop", "1", "-t", f"{dur:.3f}", "-i", png, "-filter_complex", vf,
             "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "pcm_s16le", "-t", f"{dur:.3f}", out])
        parts.append((out, png))

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{p}'\n" for p, _ in parts)
    joined = os.path.join(tmp, "joined.mov")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    # áudio original, só com o volume nivelado para redes sociais
    total = sum(e - s for s, e in pieces())
    run(["ffmpeg", "-y", "-i", joined,
         "-vf", f"fade=t=out:st={total - 0.6:.3f}:d=0.6",
         "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={total - 0.6:.3f}:d=0.6",
         "-c:v", "libx264", "-preset", "slow", "-crf", "25", "-maxrate", "3M",
         "-bufsize", "6M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", args.out])
    shutil.rmtree(tmp)
    print(args.out, sum(e - s for s, e in KEEP))


if __name__ == "__main__":
    main()
