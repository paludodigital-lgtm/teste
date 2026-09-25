#!/usr/bin/env python3
"""Bodega do Gringo — V2 do reel do rodízio, no formato dos reels de rodízio.

Diferenças da V1 (render_bodega_promo.py):
  * Takes estabilizados (vidstab, 2 passadas) antes de qualquer corte.
  * Gancho em slow-motion (0.75x com interpolação de movimento) no fio de queijo.
  * Plano aberto acelerado (1.25x) para tirar tempo morto.
  * Carimbos "1ª RODADA / 2ª RODADA / 3ª RODADA" acima dos títulos.
  * Transições zoom-in (xfade) entre pratos, corte seco no gancho.
  * Cartão final mais curto. Total ~21 s.

Uso:
  python3 src/render_bodega_promo_v2.py --clips DIR --logo assets/bodega-logo-white.png \
      --fonts assets/fonts --out out/bodega-rodizio-v2.mp4
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import render_bodega_promo as v1  # noqa: E402

W, H, FPS = v1.W, v1.H, v1.FPS
XF = 0.22  # duração da transição

SHOTS = [
    dict(src="IMG_1972", start=4.5, dur=2.6, speed=0.75, zoom=(1.15, 1.26), focus_y=0.38,
         title="TEM RODÍZIO DE MASSA\nNA RODA DE QUEIJO", sub="em Caxias do Sul", hook=True),
    dict(src="IMG_1972", start=8.0, dur=2.4, zoom=(1.10, 1.18), focus_y=0.40,
         stamp="1ª RODADA", title="MASSA NA RODA DE QUEIJO", sub="finalizada na sua frente"),
    dict(src="IMG_1976", start=7.8, dur=2.2, zoom=(1.00, 1.08), focus_y=0.50,
         stamp="2ª RODADA", title="RISOTO CREMOSO", sub="feito na hora"),
    dict(src="IMG_1980", start=0.2, dur=2.4, zoom=(1.00, 1.10), focus_y=0.50,
         stamp="3ª RODADA", title="CARNE COM MOLHO DA CASA", sub="suculenta, no ponto"),
    dict(src="IMG_1972", start=1.0, dur=3.2, speed=1.25, zoom=(1.02, 1.10), focus_y=0.40,
         title="E NÃO PARA POR AÍ", sub="o Gringo serve na sua mesa"),
    dict(src="IMG_1976", start=4.4, dur=2.4, zoom=(1.00, 1.08), focus_y=0.45,
         title="SABOR DA SERRA GAÚCHA", sub="receitas da colônia italiana"),
    dict(src="IMG_1976", start=0.0, dur=2.4, zoom=(1.06, 1.00), focus_y=0.55,
         title="RESERVE SUA MESA", sub="quarta a domingo · somente com reserva", cta=True),
]
END_DUR = 4.0


def stabilize(src, tmp):
    """vidstab em 2 passadas; cache por nome do arquivo."""
    name = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(tmp, f"stab_{name}.mp4")
    if os.path.exists(out):
        return out
    trf = os.path.join(tmp, f"{name}.trf")
    v1.run(["ffmpeg", "-y", "-v", "error", "-i", src,
            "-vf", f"vidstabdetect=shakiness=6:accuracy=12:result={trf}", "-f", "null", "-"])
    v1.run(["ffmpeg", "-y", "-v", "error", "-i", src,
            "-vf", f"vidstabtransform=input={trf}:smoothing=20:zoom=4:optzoom=1:interpol=bicubic",
            "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-c:a", "copy", out])
    return out


def render_shot(i, shot, clips, fonts_dir, tmp):
    src = clips[shot["src"]]
    speed = shot.get("speed", 1.0)
    out_dur = shot["dur"] / speed
    txt = os.path.join(tmp, f"txt{i}.png")
    v1.render_text_layer(shot, fonts_dir, txt)
    out = os.path.join(tmp, f"seg{i}.mp4")
    n = int(out_dur * FPS)
    z0, z1 = shot["zoom"]
    fy = shot["focus_y"]
    if speed < 1.0:
        # slow-motion com interpolação de movimento (fio de queijo fica sedoso)
        tempo = f"setpts={1/speed:.4f}*PTS,minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
    elif speed > 1.0:
        tempo = f"setpts={1/speed:.4f}*PTS,fps={FPS},"
    else:
        tempo = f"fps={FPS},"
    vf = (
        f"{tempo}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"zoompan=z='{z0}+({z1}-{z0})*on/{n}':x='iw/2-(iw/zoom/2)':"
        f"y='min(max(ih*{fy}-(ih/zoom/2),0),ih-ih/zoom)':d=1:s={W}x{H}:fps={FPS},"
        f"eq=contrast=1.07:brightness=0.005:saturation=1.22:gamma=0.98,"
        f"unsharp=5:5:0.55:5:5:0.0,vignette=angle=PI/5.2,setsar=1"
    )
    t_in = 0.10 if shot.get("hook") else 0.22
    fade_out_st = max(0.0, out_dur - 0.30)
    fc = (
        f"[0:v]{vf}[base];"
        f"[1:v]format=rgba,fade=in:st={t_in}:d=0.28:alpha=1,fade=out:st={fade_out_st}:d=0.28:alpha=1[txt];"
        f"[base][txt]overlay=0:0:format=auto,format=yuv420p[v];"
        f"[0:a]atempo={speed},aresample=48000[a]"
    )
    v1.run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", str(shot["start"]), "-t", str(shot["dur"]), "-i", src,
        "-loop", "1", "-t", str(out_dur), "-i", txt,
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{out_dur:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out,
    ])
    return out, out_dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--logo", required=True)
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tmp", default=None, help="pasta de trabalho (mantém cache da estabilização)")
    args = ap.parse_args()

    tmp = args.tmp or tempfile.mkdtemp(prefix="bodega_v2_")
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

    segs = []
    for i, s in enumerate(SHOTS):
        segs.append(render_shot(i, s, clips, args.fonts, tmp))
    v1.END_DUR = END_DUR
    end = os.path.join(tmp, "end.mp4")
    v1.render_end_card(args.logo, args.fonts, end, tmp)
    segs.append((end, END_DUR))

    # Encadeia com xfade (zoom-in entre pratos, fade para o cartão final) e acrossfade no áudio.
    n = len(segs)
    inputs = []
    for p, _ in segs:
        inputs += ["-i", p]
    fc = ""
    for i in range(n):
        fc += f"[{i}:v]setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}];[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}];"
    prev_v, prev_a = "[v0]", "[a0]"
    offset = segs[0][1]
    for i in range(1, n):
        trans = "fade" if i == n - 1 else "zoomin"
        ov = f"[vx{i}]" if i < n - 1 else "[vout]"
        oa = f"[ax{i}]" if i < n - 1 else "[amix]"
        fc += f"{prev_v}[v{i}]xfade=transition={trans}:duration={XF}:offset={offset - XF:.3f}{ov};"
        fc += f"{prev_a}[a{i}]acrossfade=d={XF}:c1=tri:c2=tri{oa};"
        prev_v, prev_a = ov, oa
        offset += segs[i][1] - XF
    fc += "[amix]highpass=f=90,lowpass=f=12000,loudnorm=I=-18:TP=-1.5:LRA=9,volume=0.9[aout]"
    v1.run([
        "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", args.out,
    ])
    v1.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.2", "-i", args.out, "-frames:v", "1", "-q:v", "2",
            os.path.splitext(args.out)[0] + "-capa.jpg"])
    print("OK:", args.out, f"({offset:.1f}s)")


if __name__ == "__main__":
    main()
