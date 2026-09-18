#!/usr/bin/env python3
"""Passo 2: deixa o homem mais alto que a mulher, sem mexer em nada mais.

Ideia: escalar o homem em torno do ponto dos pes dele. Ancorar nos pes faz
com que ele cresca so para cima - os sapatos continuam pisando exatamente no
mesmo ponto do chao, entao o piso, a sombra e o enquadramento nao mudam.

Ordem de composicao em cada frame:

    1. tapa o "fantasma" (pedacos do homem original que a versao maior nao
       cobre) com inpaint
    2. desenha o homem escalado
    3. devolve a mulher por cima, recortada do frame original - ela continua
       na frente dele, como no video de origem
    4. devolve a legenda queimada por cima de tudo

Frames sem deteccao (o card final do logo, e uns poucos em que o detector
perde uma das pessoas) saem identicos ao original.
"""
from __future__ import annotations

import argparse
import json
import os

import cv2
import numpy as np

WORK = "/tmp/work"
SCALE = 1.09          # o quanto o homem cresce
EDGE_ERODE = 2        # encolhe a matte para nao arrastar fundo na borda
EDGE_FEATHER = 1.6


def load_mask(path: str) -> np.ndarray | None:
    m = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return None if m is None else m.astype(np.float32) / 255.0


def tighten(mask: np.ndarray) -> np.ndarray:
    """Matte um pouco menor que a mascara crua, com borda suave."""
    core = (mask > 0.5).astype(np.uint8)
    if EDGE_ERODE:
        core = cv2.erode(core, np.ones((EDGE_ERODE * 2 + 1,) * 2, np.uint8))
    return cv2.GaussianBlur(core.astype(np.float32), (0, 0), EDGE_FEATHER)


def subtitle_mask(frame: np.ndarray) -> np.ndarray:
    """Acha a legenda queimada: texto branco com contorno escuro, embaixo.

    Filtra por tamanho de componente para nao confundir letra com mesa
    branca, tenis ou reflexo do piso.
    """
    h, w = frame.shape[:2]
    y0, y1 = int(h * 0.60), int(h * 0.92)
    band = frame[y0:y1]

    core = np.all(band > 218, axis=2).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    keep = np.zeros_like(core)
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        # glifos de legenda: baixos, estreitos e com area modesta
        if 5 <= ch <= 46 and 2 <= cw <= 120 and 12 <= area <= 2600:
            keep[lab == i] = 1
    if not keep.any():
        return np.zeros((h, w), np.float32)

    # pega tambem o contorno escuro que cerca as letras
    grown = cv2.dilate(keep, np.ones((7, 7), np.uint8))
    dark = np.all(band < 110, axis=2).astype(np.uint8)
    text = np.clip(keep + (grown & dark), 0, 1).astype(np.uint8)
    text = cv2.morphologyEx(text, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    out = np.zeros((h, w), np.float32)
    out[y0:y1] = cv2.GaussianBlur(text.astype(np.float32), (0, 0), 0.8)
    return out


def foot_anchor(mask: np.ndarray, hint_y: float) -> tuple[float, float]:
    """Ponto de apoio do homem: base da propria mascara, nao os landmarks.

    Os landmarks dos pes viram chute quando ele esta cortado na borda de
    baixo - num frame o pe dele foi parar do lado da mulher, e a escala
    empurrava o corpo inteiro para o lado.
    """
    h, w = mask.shape
    solid = mask > 0.4
    rows = np.where(solid.any(axis=1))[0]
    if not len(rows):
        return w / 2.0, float(h)
    bottom = float(rows[-1])
    band = mask[int(max(0, bottom - 45)):int(bottom) + 1]
    total = band.sum()
    # centro de massa, nao ponto medio dos extremos: um fiapo de mascara
    # solto na borda puxava a ancora para o lado da mulher
    ax = float((band.sum(axis=0) * np.arange(w)).sum() / total) if total > 1 else w / 2.0
    # se ele encosta na borda de baixo, os pes estao fora do quadro: o
    # landmark ainda serve para dizer o quanto
    ay = max(bottom, hint_y) if bottom >= h - 4 else bottom
    return ax, float(ay)


def same_scene(i: int, src: int, mask: np.ndarray, tol: float = 16.0) -> bool:
    """So empresta a mascara de um vizinho se a cena ainda for a mesma.

    Sem isso a mascara do ultimo frame com gente vazava no card final do
    logo e deformava a marca - justamente o que nao pode mudar.
    """
    a = cv2.imread(os.path.join(WORK, f"src_{i:04d}.png"))
    b = cv2.imread(os.path.join(WORK, f"src_{src:04d}.png"))
    sel = mask > 0.4
    if sel.sum() < 200:
        return False
    return float(cv2.absdiff(a, b).mean(axis=2)[sel].mean()) < tol


def nearest_ok(records, i: int) -> int | None:
    """Frame valido mais proximo - cobre os poucos em que o detector falhou."""
    for d in range(1, 4):
        for j in (i - d, i + d):
            if 0 <= j < len(records) and records[j]["ok"]:
                return j
    return None


def shot_cuts(n: int, thresh: float = 26.0) -> list[int]:
    """Frames onde a cena corta - a suavizacao nao pode atravessar um corte."""
    cuts, prev = [], None
    for i in range(n):
        small = cv2.resize(cv2.imread(os.path.join(WORK, f"src_{i:04d}.png")),
                           (96, 128))
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None and np.abs(g - prev).mean() > thresh:
            cuts.append(i)
        prev = g
    return cuts


def smooth_anchors(anchors, cuts, win: int = 7):
    """Media movel da ancora dentro de cada plano.

    Sem isso a ancora tremia alguns pixels por frame e o homem parecia
    pulsar de tamanho.
    """
    n = len(anchors)
    bounds = [0] + cuts + [n]
    out = list(anchors)
    for a, b in zip(bounds, bounds[1:]):
        seg = [(i, anchors[i]) for i in range(a, b) if anchors[i] is not None]
        if len(seg) < 2:
            continue
        idx = np.array([i for i, _ in seg])
        xs = np.array([p[0] for _, p in seg], dtype=np.float32)
        ys = np.array([p[1] for _, p in seg], dtype=np.float32)
        k = min(win, len(seg) if len(seg) % 2 else len(seg) - 1)
        if k >= 3:
            pad = k // 2
            for arr in (xs, ys):
                padded = np.pad(arr, pad, mode="edge")
                arr[:] = np.convolve(padded, np.ones(k) / k, mode="valid")
        for j, i in enumerate(idx):
            out[i] = (float(xs[j]), float(ys[j]))
    return out


def process(frame: np.ndarray, man_mask: np.ndarray, woman_mask: np.ndarray,
            anchor: tuple[float, float], scale: float) -> np.ndarray:
    h, w = frame.shape[:2]
    ax, ay = anchor

    alpha_m = tighten(man_mask)
    alpha_w = tighten(woman_mask)

    # tira a legenda ANTES de escalar: senao ela cresce junto com o homem e
    # aparece uma segunda copia, deslocada, por cima da legenda de verdade
    st = subtitle_mask(frame)
    clean = frame
    if st.max() > 0:
        clean = cv2.inpaint(frame, cv2.dilate((st > 0.25).astype(np.uint8),
                                              np.ones((3, 3), np.uint8)),
                            5, cv2.INPAINT_TELEA)

    M = np.float32([[scale, 0, ax * (1 - scale)],
                    [0, scale, ay * (1 - scale)]])
    big = cv2.warpAffine(clean, M, (w, h), flags=cv2.INTER_LANCZOS4,
                         borderMode=cv2.BORDER_REPLICATE)
    big_a = cv2.warpAffine(alpha_m, M, (w, h), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # 1. fantasma: onde estava o homem antigo e o novo nao chega.
    # o buraco e preenchido com o fundo do proprio quadro escalado (`big`
    # nessas posicoes ja e fundo, nao o homem) - textura de verdade, em vez
    # do borrao que o inpaint deixava em cima do braco esticado dele.
    ghost = ((alpha_m > 0.35) & (big_a < 0.35)).astype(np.uint8)
    base = clean
    if ghost.sum() > 30:
        soft = cv2.GaussianBlur(ghost.astype(np.float32), (0, 0), 2.0)[:, :, None]
        base = (clean.astype(np.float32) * (1 - soft)
                + big.astype(np.float32) * soft)
        # onde o fundo escalado traria uma copia deslocada da mulher, o
        # inpaint classico e menos pior que duplicar ela
        dup = ((cv2.warpAffine(alpha_w, M, (w, h), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0) > 0.3)
               & (ghost > 0)).astype(np.uint8)
        if dup.sum() > 30:
            patched = cv2.inpaint(clean, cv2.dilate(dup, np.ones((5, 5), np.uint8)),
                                  6, cv2.INPAINT_TELEA).astype(np.float32)
            d = cv2.GaussianBlur(dup.astype(np.float32), (0, 0), 2.0)[:, :, None]
            base = base * (1 - d) + patched * d
        base = np.clip(base, 0, 255).astype(np.uint8)

    # 2. homem escalado
    a = big_a[:, :, None]
    out = base.astype(np.float32) * (1 - a) + big.astype(np.float32) * a

    # 3. a mulher volta na frente, recortada do frame original
    aw = alpha_w[:, :, None]
    out = out * (1 - aw) + clean.astype(np.float32) * aw

    # 4. legenda queimada de volta, na posicao original
    s3 = st[:, :, None]
    out = out * (1 - s3) + frame.astype(np.float32) * s3

    return np.clip(out, 0, 255).astype(np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=SCALE)
    ap.add_argument("--only", help="faixa de frames para teste, ex 95-130")
    ap.add_argument("--outdir", default=os.path.join(WORK, "edit"))
    args = ap.parse_args()

    records = json.load(open(os.path.join(WORK, "measure.json")))
    os.makedirs(args.outdir, exist_ok=True)

    lo, hi = 0, len(records) - 1
    if args.only:
        lo, hi = (int(v) for v in args.only.split("-"))

    n = len(records)
    source = [i if records[i]["ok"] else nearest_ok(records, i) for i in range(n)]
    raw = []
    for i in range(n):
        src = source[i]
        mm = None if src is None else load_mask(f"{WORK}/mask_man_{src:04d}.png")
        if mm is not None and src != i and not same_scene(i, src, mm):
            src = source[i] = None
        raw.append(None if src is None
                   else foot_anchor(mm, records[src]["man"]["foot_y"]))
    print("  detectando cortes de cena...", flush=True)
    cuts = shot_cuts(n)
    print(f"  {len(cuts)} corte(s): {cuts}", flush=True)
    anchors = smooth_anchors(raw, cuts)

    touched = 0
    for i in range(lo, hi + 1):
        frame = cv2.imread(os.path.join(WORK, f"src_{i:04d}.png"))
        src = source[i]

        if src is None:
            out = frame                      # card final do logo: sem pessoas
        else:
            mm = load_mask(f"{WORK}/mask_man_{src:04d}.png")
            mw = load_mask(f"{WORK}/mask_woman_{src:04d}.png")
            out = process(frame, mm, mw, anchors[i], args.scale)
            touched += 1

        cv2.imwrite(os.path.join(args.outdir, f"f_{i:04d}.png"), out)
        if i % 40 == 0:
            print(f"  {i}/{hi}", flush=True)

    print(f"pronto: {hi - lo + 1} frames, {touched} com o homem escalado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
