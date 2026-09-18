#!/usr/bin/env python3
"""
Lavland - anima cao do reel 9:16 a partir da arte estatica da loja.

O script trata a imagem como um mini set de cinema:

  * uma camera virtual faz zoom/pan sobre a arte (Ken Burns);
  * as duas pessoas sao recortadas numa camada propria que aproxima
    um pouco mais rapido que o fundo, criando o parallax;
  * os tambores das secadoras/lavadoras giram de verdade, com o
    reflexo do vidro mantido parado;
  * o LED do teto e os paineis das maquinas pulsam;
  * os textos entram e saem em cima de tudo.

Uso:
    python3 src/render_reel.py                # 12s, 1080x1920, 30fps
    python3 src/render_reel.py --fps 24 --duration 8
    python3 src/render_reel.py --preview      # 1 frame por segundo, rapido

Saida: out/lavland-reel.mp4 e out/lavland-poster.jpg
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "assets", "lavland-source.webp")
LOGO = os.path.join(ROOT, "assets", "logo.png")  # opcional: se existir, substitui o texto
OUT_DIR = os.path.join(ROOT, "out")

# --------------------------------------------------------------------------
# MARCA - cores e textos. E aqui que se mexe para trocar a copy do video.
# --------------------------------------------------------------------------

PURPLE_DEEP = (52, 18, 84)
PURPLE = (91, 42, 138)
PURPLE_LIT = (138, 72, 201)
AMBER = (247, 170, 32)
ORANGE = (233, 104, 20)
SKY = (124, 203, 252)
WHITE = (255, 255, 255)

COPY = {
    "badge": "24H",
    "badge_sub": "TODOS OS DIAS",
    "a_title": "LAVLAND",
    "a_sub": "LAVANDERIA EXPRESS",
    "b_title": "ABERTO 24 HORAS",
    "b_sub": "TODOS OS DIAS DO ANO",
    "c_words": ["LAVA", "SECA", "DOBRA"],
    "d_title": "BAIXE O APP LAVLAND",
    "d_sub": "AGENDE E ACOMPANHE PELO CELULAR",
}

# --------------------------------------------------------------------------
# GEOMETRIA - tudo em coordenadas da arte original (1086 x 1448)
# --------------------------------------------------------------------------

# Silhueta dos dois atendentes. Um blob unico: eles se encostam, e os vaos
# internos (entre as pernas) sao pequenos demais para o parallax denunciar.
PEOPLE_POLY = [
    (318, 340), (330, 300), (390, 283), (470, 300), (500, 345), (490, 420),
    (500, 480), (515, 510), (522, 360), (530, 318), (570, 298), (640, 298),
    (690, 330), (700, 372), (705, 440), (722, 500), (736, 532), (746, 572),
    (752, 612), (790, 620), (836, 642), (836, 702), (820, 760), (770, 776),
    (762, 792), (776, 852), (792, 952), (802, 1052), (812, 1152), (818, 1252),
    (836, 1300), (830, 1362), (760, 1372), (700, 1360), (640, 1292),
    (600, 1282), (520, 1266), (505, 1232), (470, 1290), (465, 1346),
    (400, 1374), (320, 1360), (288, 1310), (300, 1268), (295, 1250),
    (300, 1200), (330, 1190), (340, 1150), (330, 1050), (325, 950),
    (300, 870), (285, 820), (270, 780), (225, 730), (212, 690), (218, 645),
    (232, 600), (245, 555), (270, 530), (245, 520), (232, 470), (245, 420),
    (270, 380), (300, 350),
]

# (cx, cy, raio, rpm_base). rpm positivo = horario.
# secadoras giram continuo; lavadoras fazem o vai-e-vem do ciclo de lavagem.
DRYERS = [(735, 437, 34), (838, 436, 35), (957, 435, 36)]
WASHERS = [(838, 616, 35), (949, 617, 35)]

# Regioes que brilham: (x0, y0, x1, y1, limiar_de_luz, cor)
GLOW_ZONES = [
    (0, 0, 1086, 240, 205, (255, 246, 226)),    # LED do teto
    (560, 215, 1086, 330, 190, (255, 214, 132)),  # letreiro Lavland
    (690, 330, 1086, 770, 195, (255, 206, 150)),  # paineis das maquinas
]

# Janela base da camera na arte: 9:16 de altura cheia, enquadrada para
# manter as duas pessoas e as cinco maquinas dentro do corte.
CAM_W = 1448 * 9 / 16       # 814.5
CAM_CX0, CAM_CY0 = 573.0, 724.0
CAM_CX1, CAM_CY1 = 564.0, 698.0
ZOOM0, ZOOM1 = 1.0, 1.075
FG_DEPTH = 1.7              # quanto a camada das pessoas aproxima a mais


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------

def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ramp(t: float, a: float, b: float) -> float:
    """0 antes de a, 1 depois de b, suave no meio."""
    if b <= a:
        return 1.0 if t >= b else 0.0
    return smoothstep((t - a) / (b - a))


def overshoot(x: float, amount: float = 1.7) -> float:
    """Ease-out com um leve passar do ponto - da vida na entrada dos textos."""
    x = max(0.0, min(1.0, x))
    p = x - 1.0
    return p * p * ((amount + 1) * p + amount) + 1.0


def pick_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    names = (
        ["InterDisplay-ExtraBold", "Inter-ExtraBold", "InterDisplay-Bold",
         "Inter-Bold", "DejaVuSans-Bold", "LiberationSans-Bold"]
        if bold else
        ["InterDisplay-SemiBold", "Inter-SemiBold", "Inter-Medium",
         "DejaVuSans", "LiberationSans-Regular"]
    )
    roots = ["/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/inter",
             "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"]
    for name in names:
        for root in roots:
            for ext in (".otf", ".ttf"):
                path = os.path.join(root, name + ext)
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def text_width(text: str, font, tracking: float) -> float:
    if not text:
        return 0.0
    return sum(font.getlength(c) for c in text) + tracking * (len(text) - 1)


def draw_tracked(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, tracking: float = 0.0):
    """Desenha texto com espacamento entre letras (o Pillow nao tem nativo)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + tracking


def with_glow(layer: Image.Image, radius: int = 18, strength: float = 0.85) -> Image.Image:
    """Sombra escura difusa atras da arte - garante leitura sobre qualquer fundo."""
    alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    alpha = alpha.point(lambda v: int(min(255, v * strength)))
    shadow = Image.new("RGBA", layer.size, (14, 4, 30, 0))
    shadow.putalpha(alpha)
    return Image.alpha_composite(shadow, layer)


# --------------------------------------------------------------------------
# preparo (roda uma vez)
# --------------------------------------------------------------------------

def build_people_layer(src: Image.Image) -> Image.Image:
    """Arte recortada nas duas pessoas, com borda dilatada e suavizada."""
    mask = Image.new("L", src.size, 0)
    ImageDraw.Draw(mask).polygon(PEOPLE_POLY, fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(9))        # engorda ~4px
    mask = mask.filter(ImageFilter.GaussianBlur(3.5))   # borda macia
    people = src.convert("RGBA")
    people.putalpha(mask)
    return people


def build_drum_kit(src: Image.Image):
    """Para cada tambor: recorte, mascara circular e mascara do reflexo.

    O reflexo do vidro fica parado enquanto o miolo gira - sem isso o brilho
    roda junto e a maquina parece um cata-vento.
    """
    kit = []
    for cx, cy, r in DRYERS + WASHERS:
        box = (cx - r, cy - r, cx + r, cy + r)
        patch = src.crop(box).convert("RGB")
        size = 2 * r

        circle = Image.new("L", (size, size), 0)
        ImageDraw.Draw(circle).ellipse([1, 1, size - 2, size - 2], fill=255)
        circle = circle.filter(ImageFilter.GaussianBlur(1.6))

        lum = np.asarray(patch.convert("L"), dtype=np.float32)
        spec = np.clip((lum - 150.0) / 70.0, 0.0, 1.0) * 255.0
        spec_mask = Image.fromarray(spec.astype(np.uint8), "L")
        spec_mask = spec_mask.filter(ImageFilter.GaussianBlur(0.8))
        spec_mask = ImageChops.multiply(spec_mask, circle)

        kit.append({"box": box, "patch": patch, "r": r,
                    "circle": circle, "spec": spec_mask, "cache": {}})
    return kit


def build_glow_map(src: Image.Image) -> np.ndarray:
    """Mapa aditivo (float32 HxWx3) das luzes que vao pulsar."""
    lum = np.asarray(src.convert("L"), dtype=np.float32)
    h, w = lum.shape
    glow = np.zeros((h, w, 3), dtype=np.float32)
    for x0, y0, x1, y1, thr, color in GLOW_ZONES:
        band = np.zeros((h, w), dtype=np.float32)
        sub = lum[y0:y1, x0:x1]
        band[y0:y1, x0:x1] = np.clip((sub - thr) / (255.0 - thr), 0.0, 1.0)
        band = np.asarray(
            Image.fromarray((band * 255).astype(np.uint8), "L")
            .filter(ImageFilter.GaussianBlur(7)),
            dtype=np.float32,
        ) / 255.0
        glow += band[:, :, None] * np.array(color, dtype=np.float32) / 255.0
    return np.clip(glow, 0.0, 1.0)


def build_vignette(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx / (w - 1) - 0.5) * 2.0
    ny = (yy / (h - 1) - 0.5) * 2.0
    d = np.sqrt(nx ** 2 + (ny * 0.78) ** 2)
    v = 1.0 - 0.34 * np.clip((d - 0.55) / 0.85, 0.0, 1.0) ** 1.4
    return v[:, :, None].astype(np.float32)


# --------------------------------------------------------------------------
# animacao por frame
# --------------------------------------------------------------------------

def spin_drums(frame: Image.Image, kit, t: float):
    for i, drum in enumerate(kit):
        r = drum["r"]
        if i < len(DRYERS):
            # secadora: rotacao continua, cada uma num ritmo proprio
            angle = t * (52 + 9 * i) * (1 if i % 2 == 0 else -1)
        else:
            # lavadora: ciclo de lavagem - gira, para, volta
            j = i - len(DRYERS)
            angle = 150.0 * math.sin(2 * math.pi * (t / 2.7 + 0.35 * j))
        key = int(angle) % 360
        rot = drum["cache"].get(key)
        if rot is None:
            rot = drum["patch"].rotate(
                key, resample=Image.Resampling.BICUBIC, center=(r, r)
            )
            drum["cache"][key] = rot
        frame.paste(rot, drum["box"], drum["circle"])
        frame.paste(drum["patch"], drum["box"], drum["spec"])  # reflexo parado


def pulse_lights(arr: np.ndarray, glow: np.ndarray, t: float) -> np.ndarray:
    ceiling = 0.26 + 0.12 * math.sin(2 * math.pi * t / 2.3)
    flicker = 0.035 * math.sin(2 * math.pi * t / 0.37)
    return np.clip(arr + glow * (ceiling + flicker) * 255.0, 0, 255)


def camera_rect(t: float, dur: float, zoom_extra: float = 1.0, dy: float = 0.0):
    k = smoothstep(t / dur)
    z = (ZOOM0 + (ZOOM1 - ZOOM0) * k) * zoom_extra
    cx = CAM_CX0 + (CAM_CX1 - CAM_CX0) * k
    cy = CAM_CY0 + (CAM_CY1 - CAM_CY0) * k + dy
    hw = CAM_W / 2 / z
    hh = (CAM_W * 16 / 9) / 2 / z
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def render_base(src_rgb, people, kit, glow, t, dur, canvas):
    """Fundo com maquinas girando + camada das pessoas por cima (parallax)."""
    W, H = canvas

    bg_full = src_rgb.copy()
    spin_drums(bg_full, kit, t)
    arr = pulse_lights(np.asarray(bg_full, dtype=np.float32), glow, t)
    bg_full = Image.fromarray(arr.astype(np.uint8), "RGB")

    bg = bg_full.resize((W, H), Image.Resampling.LANCZOS,
                        box=camera_rect(t, dur))

    # respiracao: a camada das pessoas sobe/desce alguns pixels e "infla" 0.4%
    breath = math.sin(2 * math.pi * t / 3.4)
    sway = math.sin(2 * math.pi * t / 5.1)
    k = smoothstep(t / dur)
    fg_zoom = (1.0 + (ZOOM1 - ZOOM0) * k * (FG_DEPTH - 1.0)) * (1.0 + 0.004 * breath)
    fg = people.resize((W, H), Image.Resampling.LANCZOS,
                       box=camera_rect(t, dur, fg_zoom, dy=-2.2 * breath))
    if abs(sway) > 0.01:
        fg = ImageChops.offset(fg, int(round(2.0 * sway)), 0)

    return Image.alpha_composite(bg.convert("RGBA"), fg)


# --------------------------------------------------------------------------
# camadas de texto
# --------------------------------------------------------------------------

def card_title(text: str, sub: str, w: int) -> Image.Image:
    f_big = pick_font(112, True)
    f_sub = pick_font(38, True)
    tr_big, tr_sub = 2.0, 9.0

    layer = Image.new("RGBA", (w, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    tw = text_width(text, f_big, tr_big)
    draw_tracked(d, ((w - tw) / 2, 0), text, f_big, WHITE + (255,), tr_big)

    bar_y = 142
    d.rounded_rectangle([w / 2 - 58, bar_y, w / 2 + 58, bar_y + 7], 4,
                        fill=AMBER + (255,))

    sw = text_width(sub, f_sub, tr_sub)
    draw_tracked(d, ((w - sw) / 2, bar_y + 30), sub, f_sub, SKY + (255,), tr_sub)
    return with_glow(layer)


def card_words(words, w: int, progress: float) -> Image.Image:
    """LAVA . SECA . DOBRA - cada palavra entra na sua vez."""
    f = pick_font(78, True)
    f_dot = pick_font(78, True)
    tr = 2.5
    gap = 30.0

    widths = [text_width(x, f, tr) for x in words]
    dot_w = f_dot.getlength("·")
    total = sum(widths) + (len(words) - 1) * (2 * gap + dot_w)

    layer = Image.new("RGBA", (w, 132), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = (w - total) / 2
    for i, word in enumerate(words):
        p = ramp(progress, i * 0.16, i * 0.16 + 0.34)
        if p > 0.001:
            off = (1.0 - overshoot(p)) * 46
            a = int(255 * min(1.0, p * 1.6))
            tmp = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            draw_tracked(ImageDraw.Draw(tmp), (x, 18 + off), word, f,
                         WHITE + (a,), tr)
            layer.alpha_composite(tmp)
        x += widths[i]
        if i < len(words) - 1:
            pd = ramp(progress, i * 0.16 + 0.12, i * 0.16 + 0.3)
            d.text((x + gap, 18), "·", font=f_dot,
                   fill=AMBER + (int(255 * pd),))
            x += 2 * gap + dot_w
    return with_glow(layer)


def card_cta(text: str, sub: str, w: int, t: float) -> Image.Image:
    f = pick_font(46, True)
    f_sub = pick_font(30, True)
    tr, tr_sub = 3.0, 5.0

    tw = text_width(text, f, tr)
    pill_w = int(tw + 132)
    pill_h = 116
    layer = Image.new("RGBA", (w, pill_h + 76), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    breathe = 0.5 + 0.5 * math.sin(2 * math.pi * t / 1.25)
    x0 = (w - pill_w) / 2
    halo = int(10 + 12 * breathe)
    d.rounded_rectangle([x0 - halo, 26 - halo, x0 + pill_w + halo, 26 + pill_h + halo],
                        (pill_h + 2 * halo) / 2,
                        fill=AMBER + (int(46 + 34 * breathe),))
    d.rounded_rectangle([x0, 26, x0 + pill_w, 26 + pill_h], pill_h / 2,
                        fill=AMBER + (255,))
    draw_tracked(d, (x0 + 66, 26 + (pill_h - 52) / 2), text, f,
                 PURPLE_DEEP + (255,), tr)

    sw = text_width(sub, f_sub, tr_sub)
    draw_tracked(d, ((w - sw) / 2, 26 + pill_h + 22), sub, f_sub,
                 WHITE + (230,), tr_sub)
    return with_glow(layer, radius=22)


def card_badge() -> Image.Image:
    f = pick_font(56, True)
    f_sub = pick_font(21, True)
    sub = COPY["badge_sub"]
    tr_sub = 3.4
    w = int(max(f.getlength(COPY["badge"]), text_width(sub, f_sub, tr_sub)) + 72)
    h = 132
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 30, fill=PURPLE + (216,))
    d.rounded_rectangle([0, 0, w - 1, h - 1], 30, outline=AMBER + (190,), width=3)
    tw = f.getlength(COPY["badge"])
    d.text(((w - tw) / 2, 20), COPY["badge"], font=f, fill=WHITE + (255,))
    sw = text_width(sub, f_sub, tr_sub)
    draw_tracked(d, ((w - sw) / 2, 86), sub, f_sub, AMBER + (255,), tr_sub)
    return with_glow(layer, radius=14, strength=0.7)


def build_scrim(w: int, h: int) -> Image.Image:
    """Degrade roxo no topo e no pe do quadro - da contraste pro texto."""
    scrim = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(scrim)
    for y in range(int(h * 0.52), h):
        k = max(0.0, (y - h * 0.52) / (h * 0.48))
        d.line([(0, y), (w, y)], fill=PURPLE_DEEP + (int(206 * k ** 1.8),))
    for y in range(0, int(h * 0.20)):
        k = max(0.0, 1.0 - y / (h * 0.20))
        d.line([(0, y), (w, y)], fill=PURPLE_DEEP + (int(150 * k ** 1.7),))
    return scrim


def light_sweep(w: int, h: int, p: float) -> Image.Image:
    """Faixa de luz diagonal cruzando o quadro nas viradas de texto."""
    band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(band)
    x = -w * 0.7 + p * (w * 2.2)
    for i in range(-110, 111):
        a = int(70 * math.cos(i / 110 * math.pi / 2) ** 2)
        d.line([(x + i, -60), (x + i - h * 0.32, h + 60)],
               fill=(255, 255, 255, a), width=3)
    return band


# --------------------------------------------------------------------------
# linha do tempo
# --------------------------------------------------------------------------

def overlay_frame(t: float, dur: float, cards, canvas) -> Image.Image:
    W, H = canvas
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # escala os tempos do roteiro (escrito para 12s) para a duracao pedida
    s = dur / 12.0
    def T(v):
        return v * s

    # selo 24h fixo no topo esquerdo
    a = ramp(t, T(0.5), T(1.1)) * (1.0 - ramp(t, dur - T(0.45), dur))
    if a > 0.004:
        badge = cards["badge"]
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tmp.paste(badge, (64, 92 + int((1 - overshoot(min(1, a))) * -34)))
        layer.alpha_composite(Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 0)), tmp, a))

    base_y = int(H * 0.705)

    def place(card, t_in, t_out, y=base_y, rise=64):
        a_in = ramp(t, T(t_in), T(t_in + 0.55))
        a_out = 1.0 - ramp(t, T(t_out), T(t_out + 0.38))
        alpha = a_in * a_out
        if alpha <= 0.004:
            return
        dy = int((1 - overshoot(a_in)) * rise + (1 - a_out) * -26)
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tmp.paste(card, ((W - card.width) // 2, y + dy))
        layer.alpha_composite(
            Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 0)), tmp, alpha))

    place(cards["a"], 0.45, 3.15)
    place(cards["b"], 3.70, 6.40)

    prog = (t / s - 6.95) / 1.5
    if -0.2 < prog < 6:
        place(card_words(COPY["c_words"], W, max(0.0, min(1.0, prog))),
              6.95, 9.05, y=base_y + 34)

    place(card_cta(COPY["d_title"], COPY["d_sub"], W, t), 9.60, 99.0,
          y=base_y - 10)

    # varridas de luz nas trocas de mensagem
    for mark in (3.45, 6.75, 9.45):
        p = (t - T(mark)) / T(0.62)
        if 0.0 <= p <= 1.0:
            layer.alpha_composite(light_sweep(W, H, p))

    return layer


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--preview", action="store_true",
                    help="renderiza 1 frame por segundo em PNG, sem video")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "lavland-reel.mp4"))
    args = ap.parse_args()

    if not os.path.exists(SOURCE):
        print(f"arte nao encontrada: {SOURCE}", file=sys.stderr)
        return 1

    W = args.width
    H = W * 16 // 9
    canvas = (W, H)
    dur = args.duration

    print(f"preparando camadas  ({W}x{H}, {dur}s @ {args.fps}fps)")
    src = Image.open(SOURCE).convert("RGB")
    people = build_people_layer(src)
    kit = build_drum_kit(src)
    glow = build_glow_map(src)
    vignette = build_vignette(W, H)
    scrim = build_scrim(W, H)
    cards = {
        "badge": card_badge(),
        "a": card_title(COPY["a_title"], COPY["a_sub"], W),
        "b": card_title(COPY["b_title"], COPY["b_sub"], W),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="lavland-frames-")
    total = 1 + int(dur) if args.preview else int(round(dur * args.fps))
    poster_at = int(total * 0.80)

    try:
        for i in range(total):
            t = i * (1.0 if args.preview else 1.0 / args.fps)
            frame = render_base(src, people, kit, glow, t, dur, canvas)
            frame = Image.alpha_composite(frame, scrim)
            frame = Image.alpha_composite(frame, overlay_frame(t, dur, cards, canvas))

            arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
            arr *= vignette                                   # vinheta
            arr = np.clip((arr - 128.0) * 1.055 + 128.0, 0, 255)  # contraste
            fade = ramp(t, 0.0, 0.42) * (1.0 - ramp(t, dur - 0.34, dur))
            arr *= fade
            out = Image.fromarray(arr.astype(np.uint8), "RGB")

            if i == poster_at:
                out.save(os.path.join(OUT_DIR, "lavland-poster.jpg"), quality=92)
            out.save(os.path.join(tmpdir, f"f{i:05d}.png"))

            if i % 30 == 0 or i == total - 1:
                print(f"  frame {i + 1}/{total}")

        if args.preview:
            dest = os.path.join(OUT_DIR, "preview")
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(tmpdir, dest)
            print(f"preview em {dest}")
            return 0

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(args.fps), "-i", os.path.join(tmpdir, "f%05d.png"),
            "-c:v", "libx264", "-profile:v", "high", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-r", str(args.fps), args.out,
        ]
        subprocess.run(cmd, check=True)
        size = os.path.getsize(args.out) / 1e6
        print(f"pronto: {args.out}  ({size:.1f} MB)")
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
