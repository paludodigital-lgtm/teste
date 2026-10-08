"""Tutorial "Como gravar para a agência" — lavanderia SuperLav.

Monta um vídeo vertical 1080x1920 a partir dos takes brutos do cliente,
cortando os melhores trechos e colocando textos na tela por cima.

    python3 src/render_tutorial.py --takes /caminho/dos/takes --out out/tutorial-gravacao.mp4

Os takes ficam fora do repositório (são ~750 MB). Cada cena abaixo aponta
para o arquivo IMG_xxxx.MP4 original e o trecho (início, fim) em segundos.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30

TEAL = (38, 190, 170)
PURPLE = (108, 92, 220)
RED = (232, 64, 64)
WHITE = (255, 255, 255)
INK = (16, 20, 28)

FONT_DIR = "/usr/share/fonts/opentype/inter"

# kind: "ok" = jeito certo, "bad" = erro, None = neutro
# audio: "voz" mantém a fala alta; "amb" deixa o som ambiente baixinho
SECTIONS = [
    {
        "card": None,
        "scenes": [
            dict(take="0850", t=(0.0, 3.6), kind=None, audio="amb", intro=True),
        ],
    },
    {
        "card": ("PASSO 1", "Celular em pé"),
        "scenes": [
            dict(take="0838", t=(1.4, 5.4), kind="ok", audio="amb",
                 cap="Grave sempre na VERTICAL"),
            dict(take="0836", t=(0.4, 3.6), kind="bad", audio="amb",
                 cap="Deitado não serve para Reels e Stories"),
        ],
    },
    {
        "card": ("PASSO 2", "Mostre onde fica"),
        "scenes": [
            dict(take="0773", t=(0.0, 4.6), kind="ok", audio="amb",
                 cap="Comece pela fachada, de longe"),
            dict(take="0759", t=(0.3, 3.8), kind="ok", audio="amb",
                 cap="Mostre o cliente chegando"),
        ],
    },
    {
        "card": ("PASSO 3", "Grave o passo a passo"),
        "scenes": [
            dict(take="0775", t=(0.6, 3.8), kind="ok", audio="amb",
                 cap="1. Colocando a roupa"),
            dict(take="0776", t=(0.9, 3.0), kind="ok", audio="amb",
                 cap="2. Fechando a porta"),
            dict(take="0779", t=(0.6, 3.2), kind="ok", audio="amb",
                 cap="3. Pagando no totem"),
            dict(take="0873", t=(0.0, 2.2), kind="ok", audio="amb",
                 cap="4. Apertando INICIAR"),
            dict(take="0780", t=(0.0, 2.8), kind="ok", audio="amb",
                 cap="5. Máquina funcionando"),
        ],
    },
    {
        "card": ("PASSO 4", "Chegue perto"),
        "scenes": [
            dict(take="0814", t=(3.0, 6.4), kind="ok", audio="amb",
                 cap="Detalhes: painel, número, botão"),
            dict(take="0841", t=(0.0, 2.8), kind="ok", audio="amb",
                 cap="A roupa girando prende o olhar"),
        ],
    },
    {
        "card": ("PASSO 5", "Mostre o ambiente"),
        "scenes": [
            dict(take="0830", t=(1.2, 5.6), kind="ok", audio="amb",
                 cap="Movimento LENTO e contínuo"),
            dict(take="0856", t=(0.0, 3.4), kind="ok", audio="amb",
                 cap="Com alguém usando o espaço"),
        ],
    },
    {
        "card": ("PASSO 6", "Fale para a câmera"),
        "scenes": [
            dict(take="0851", t=(0.0, 2.4), kind="ok", audio="voz",
                 cap="Olhe para a lente e fale com energia"),
            dict(take="0795", t=(0.0, 2.9), kind="ok", audio="voz",
                 cap="Fale perto do celular, sem barulho"),
        ],
    },
    {
        "card": ("CUIDADO", "Evite estes erros"),
        "scenes": [
            dict(take="0799", t=(0.0, 2.0), kind="bad", audio="amb",
                 cap="Câmera filmando o chão"),
            dict(take="0825", t=(0.0, 2.2), kind="bad", audio="amb",
                 cap="Dedo na lente ou sem foco"),
            dict(take="0823", t=(0.3, 2.8), kind="bad", audio="amb",
                 cap="Gravou sem querer, andando"),
            dict(take="0795", t=(2.9, 4.5), kind="bad", audio="amb",
                 cap="Baixou o celular antes de parar"),
        ],
    },
]

CHECKLIST = [
    "Celular em pé (vertical)",
    "Limpe a lente antes",
    "Cada take com 5 a 10 segundos",
    "Segure 3 segundos parado no início e no fim",
    "Movimentos lentos",
    "Grave a mesma cena mais de uma vez",
    "Envie pelo Drive ou como DOCUMENTO no WhatsApp",
]

CARD_DUR = 1.5
CHECK_DUR = 8.0
OUTRO_DUR = 3.2


# --------------------------------------------------------------------- texto

def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    for name in (f"Inter-{weight}.otf", f"InterDisplay-{weight}.otf", "Inter-Bold.otf"):
        p = os.path.join(FONT_DIR, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)


def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=f) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_mark(draw, cx, cy, r, kind):
    color = TEAL if kind == "ok" else RED
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    lw = max(6, r // 5)
    if kind == "ok":
        pts = [(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.35), (cx + r * 0.48, cy - r * 0.32)]
        draw.line(pts, fill=WHITE, width=lw, joint="curve")
    else:
        d = r * 0.38
        draw.line((cx - d, cy - d, cx + d, cy + d), fill=WHITE, width=lw)
        draw.line((cx - d, cy + d, cx + d, cy - d), fill=WHITE, width=lw)


def scene_overlay(section_label, caption, kind):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # escurece topo e base para o texto sempre ler, em qualquer take
    grad = Image.new("L", (1, H))
    for y in range(H):
        top = max(0.0, 1 - y / 420) * 150
        bot = max(0.0, (y - (H - 760)) / 760) * 190
        grad.putpixel((0, y), int(max(top, bot)))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shade.putalpha(grad.resize((W, H)))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)

    if section_label:
        f = font(40, "Bold")
        tw = d.textlength(section_label, font=f)
        x, y = 64, 120
        pill = RED if section_label == "CUIDADO" else PURPLE
        d.rounded_rectangle((x, y, x + tw + 56, y + 76), radius=38, fill=pill + (235,))
        d.text((x + 28, y + 38), section_label, font=f, fill=WHITE, anchor="lm")

    if caption:
        f = font(66, "ExtraBold")
        lines = wrap(d, caption, f, W - 2 * 64 - (150 if kind else 0))
        lh = 82
        block_h = lh * len(lines)
        base_y = H - 300 - block_h
        x0 = 64
        if kind:
            draw_mark(d, x0 + 52, base_y + block_h / 2, 52, kind)
            x0 += 140
        for i, line in enumerate(lines):
            d.text((x0, base_y + i * lh), line, font=f, fill=WHITE,
                   stroke_width=2, stroke_fill=(0, 0, 0, 120))
        if kind:
            tag = "ASSIM SIM" if kind == "ok" else "ASSIM NÃO"
            ft = font(34, "Bold")
            tw = d.textlength(tag, font=ft)
            d.rounded_rectangle((x0, base_y - 70, x0 + tw + 36, base_y - 18), radius=26,
                                fill=(TEAL if kind == "ok" else RED) + (245,))
            d.text((x0 + 18, base_y - 44), tag, font=ft, fill=WHITE, anchor="lm")
    return img


def intro_overlay():
    img = scene_overlay(None, None, None)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((64, H - 700, 64 + 330, H - 630), radius=35, fill=TEAL + (240,))
    d.text((64 + 165, H - 665), "TUTORIAL", font=font(40, "Bold"), fill=WHITE, anchor="mm")
    f = font(96, "Black")
    for i, line in enumerate(["Como gravar", "vídeos para", "a agência"]):
        d.text((64, H - 590 + i * 108), line, font=f, fill=WHITE)
    d.text((64, H - 250), "Lavanderia  •  6 passos + erros comuns", font=font(40, "SemiBold"),
           fill=(230, 230, 235))
    return img


def card_overlay(bg_frame: Image.Image, label, title):
    bg = bg_frame.convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), INK), 0.55)
    d = ImageDraw.Draw(bg)
    accent = RED if label == "CUIDADO" else TEAL
    f1, f2 = font(64, "Bold"), font(110, "Black")
    d.text((W / 2, H / 2 - 120), label, font=f1, fill=accent, anchor="mm")
    lines = wrap(d, title, f2, W - 160)
    for i, line in enumerate(lines):
        d.text((W / 2, H / 2 + 10 + i * 124), line, font=f2, fill=WHITE, anchor="mm")
    d.rounded_rectangle((W / 2 - 60, H / 2 - 66, W / 2 + 60, H / 2 - 58), radius=4, fill=accent)
    return bg


def checklist_frame(bg_frame):
    bg = bg_frame.convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(30))
    bg = Image.blend(bg, Image.new("RGB", (W, H), INK), 0.7)
    d = ImageDraw.Draw(bg)
    d.text((80, 230), "ANTES DE GRAVAR", font=font(44, "Bold"), fill=TEAL)
    d.text((80, 290), "Checklist", font=font(120, "Black"), fill=WHITE)
    f = font(50, "SemiBold")
    y = 520
    for item in CHECKLIST:
        lines = wrap(d, item, f, W - 80 - 230)
        draw_mark(d, 124, y + 32, 34, "ok")
        for j, line in enumerate(lines):
            d.text((190, y + j * 62), line, font=f, fill=WHITE)
        y += 62 * len(lines) + 58
    return bg


def outro_frame(bg_frame):
    bg = bg_frame.convert("RGB").resize((W, H))
    bg = Image.blend(bg, Image.new("RGB", (W, H), INK), 0.55)
    d = ImageDraw.Draw(bg)
    d.text((W / 2, H / 2 - 90), "Agora é com você!", font=font(92, "Black"), fill=WHITE, anchor="mm")
    d.text((W / 2, H / 2 + 20), "Grave, envie os arquivos", font=font(52, "SemiBold"),
           fill=(235, 235, 240), anchor="mm")
    d.text((W / 2, H / 2 + 90), "e a agência cuida da edição.", font=font(52, "SemiBold"),
           fill=(235, 235, 240), anchor="mm")
    d.rounded_rectangle((W / 2 - 60, H / 2 + 170, W / 2 + 60, H / 2 + 178), radius=4, fill=TEAL)
    return bg


# --------------------------------------------------------------------- vídeo

def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])


def grab_frame(path, t) -> Image.Image:
    out = tempfile.mktemp(suffix=".png")
    run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", out])
    img = Image.open(out).copy()
    os.remove(out)
    return img


VCODEC = ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS)]
ACODEC = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


def measure_volume(src, t0, dur):
    r = subprocess.run(["ffmpeg", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", src, "-vn",
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    vals = {}
    for line in r.stderr.splitlines():
        for key in ("mean_volume", "max_volume"):
            if key in line:
                vals[key] = float(line.split(":")[-1].split()[0])
    return vals.get("mean_volume", -91.0), vals.get("max_volume", -91.0)


def render_scene(src, t0, t1, overlay_png, audio_mode, out):
    dur = t1 - t0
    # voz: fala na frente; amb: som ambiente baixinho por baixo da trilha
    # alguns takes vêm com a faixa de áudio vazia: apad garante silêncio no lugar
    # (loudnorm devolve NaN em silêncio digital, então o ganho é calculado aqui)
    target = -20.0 if audio_mode == "voz" else -36.0
    mean, peak = measure_volume(src, t0, dur)
    gain = 0.0 if mean < -80 else min(target - mean, -1.5 - peak)
    a = f"aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{dur:.3f},volume={gain:.1f}dB"
    a += f",afade=t=in:d=0.08,afade=t=out:st={max(0, dur - 0.12):.3f}:d=0.12"
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"setsar=1,fps={FPS}[v];"
          f"[1:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1[o];"
          f"[v][o]overlay=0:0:shortest=1[vo]")
    run(["ffmpeg", "-y", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", src,
         "-loop", "1", "-t", f"{dur:.3f}", "-i", overlay_png,
         "-filter_complex", vf + f";[0:a]{a}[ao]", "-map", "[vo]", "-map", "[ao]",
         *VCODEC, *ACODEC, "-t", f"{dur:.3f}", out])


def render_still(png, dur, out, zoom=True):
    frames = int(round(dur * FPS))
    vf = (f"scale={W*2}:{H*2},zoompan=z='1+0.04*on/{frames}':x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
          f"fade=t=in:st=0:d=0.2") if zoom else f"fade=t=in:st=0:d=0.2"
    run(["ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", png,
         "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", vf, "-map", "0:v", "-map", "1:a", *VCODEC, *ACODEC, "-t", f"{dur:.3f}", out])


# --------------------------------------------------------------------- trilha

def music_bed(total: float, path: str, sr: int = 48000):
    """Trilha leve gerada aqui mesmo (sem direitos autorais): pad + pluck, 96 bpm."""
    n = int(total * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    beat = 60 / 96
    bar = beat * 4
    chords = [(60, 64, 67, 71), (57, 60, 64, 67), (53, 57, 60, 64), (55, 59, 62, 65)]
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    nbars = int(math.ceil(total / bar))
    for b in range(nbars):
        ch = chords[b % 4]
        s, e = int(b * bar * sr), min(n, int((b + 1) * bar * sr))
        tt = t[s:e] - b * bar
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.4)
        for m in ch:
            f = hz(m)
            out[s:e] += 0.05 * env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt))
        out[s:e] += 0.07 * env * np.sin(2 * np.pi * hz(ch[0] - 24) * tt)
        arp = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[3] + 12, ch[2] + 12, ch[1] + 12, ch[3] + 12, ch[2] + 12]
        for k, m in enumerate(arp):
            ps = int((b * bar + k * beat / 2) * sr)
            pe = min(n, ps + int(0.5 * sr))
            if ps >= n:
                break
            pt = np.arange(pe - ps) / sr
            out[ps:pe] += 0.06 * np.exp(-pt * 7) * np.sin(2 * np.pi * hz(m) * pt)
    fade = int(1.5 * sr)
    out[-fade:] *= np.linspace(1, 0, fade)
    out[:int(0.5 * sr)] *= np.linspace(0, 1, int(0.5 * sr))
    out = out / (np.abs(out).max() + 1e-9) * 0.5
    pcm = (np.stack([out, out], 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--takes", required=True)
    ap.add_argument("--out", default="out/tutorial-gravacao.mp4")
    ap.add_argument("--keep", action="store_true", help="mantém a pasta temporária")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="tut_", dir=os.environ.get("TUT_TMP"))
    parts, voice_spans, clock = [], [], 0.0
    take = lambda n: os.path.join(args.takes, f"IMG_{n}.MP4")

    for si, sec in enumerate(SECTIONS):
        first = sec["scenes"][0]
        if sec["card"]:
            png = os.path.join(tmp, f"card{si}.png")
            card_overlay(grab_frame(take(first["take"]), first["t"][0] + 0.5), *sec["card"]).save(png)
            out = os.path.join(tmp, f"{len(parts):03d}.mp4")
            render_still(png, CARD_DUR, out)
            parts.append(out)
            clock += CARD_DUR
        for sc in sec["scenes"]:
            png = os.path.join(tmp, f"ov{len(parts)}.png")
            if sc.get("intro"):
                intro_overlay().save(png)
            else:
                label = sec["card"][0] if sec["card"] else None
                if label and label.startswith("PASSO"):
                    label = f"{label}  •  {sec['card'][1].upper()}"
                scene_overlay(label, sc.get("cap"), sc["kind"]).save(png)
            out = os.path.join(tmp, f"{len(parts):03d}.mp4")
            render_scene(take(sc["take"]), *sc["t"], png, sc["audio"], out)
            parts.append(out)
            dur = sc["t"][1] - sc["t"][0]
            if sc["audio"] == "voz":
                voice_spans.append((clock, clock + dur))
            clock += dur

    png = os.path.join(tmp, "check.png")
    checklist_frame(grab_frame(take("0840"), 1.0)).save(png)
    out = os.path.join(tmp, f"{len(parts):03d}.mp4")
    render_still(png, CHECK_DUR, out, zoom=False)
    parts.append(out)
    clock += CHECK_DUR

    png = os.path.join(tmp, "outro.png")
    outro_frame(grab_frame(take("0850"), 3.0)).save(png)
    out = os.path.join(tmp, f"{len(parts):03d}.mp4")
    render_still(png, OUTRO_DUR, out)
    parts.append(out)
    clock += OUTRO_DUR

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{p}'\n" for p in parts)
    joined = os.path.join(tmp, "joined.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    bed = os.path.join(tmp, "bed.wav")
    music_bed(clock, bed)
    # abaixa a trilha enquanto alguém fala
    duck = "+".join(f"between(t,{a - 0.2:.2f},{b + 0.2:.2f})" for a, b in voice_spans) or "0"
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    run(["ffmpeg", "-y", "-i", joined, "-i", bed, "-filter_complex",
         f"[1:a]volume='if({duck},0.12,0.45)':eval=frame[m];"
         f"[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-15:TP=-1.5[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", *ACODEC, "-movflags", "+faststart", args.out])
    print(f"{args.out}  {clock:.1f}s")
    if not args.keep:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
