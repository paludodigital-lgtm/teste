#!/usr/bin/env python3
"""Passo 1: detecta as duas pessoas em cada frame e guarda mascara + medidas.

Duas armadilhas do MediaPipe neste video, as duas tratadas aqui:

  1. com num_poses=2 ele as vezes devolve a MESMA pessoa duas vezes, quando
     os dois estao encostados. Nesse caso caimos no plano B: detecta um,
     apaga ele do quadro, detecta de novo.
  2. a mascara de segmentacao de uma pessoa invade a outra - a do homem
     chegava a cobrir as pernas da mulher. Por isso cada pixel e atribuido a
     quem tem o esqueleto mais perto, e as duas mascaras saem exclusivas.

Saida:
    /tmp/work/mask_man_XXXX.png    mascara do homem (uint8 0-255)
    /tmp/work/mask_woman_XXXX.png  mascara da mulher
    /tmp/work/measure.json         topo da cabeca, pes e caixa de cada um
"""
import json
import os

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

WORK = "/tmp/work"
MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "models", "pose_landmarker_heavy.task")

FACE = list(range(11))
SHOULDERS = (11, 12)
FEET = (27, 28, 29, 30, 31, 32)
TOES = (29, 30, 31, 32)

SKELETON = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
]


def skeleton_image(pl, w: int, h: int) -> np.ndarray:
    """Bonequinho de palito da pessoa, para decidir de quem e cada pixel."""
    img = np.zeros((h, w), np.uint8)
    px = [(int(p.x * w), int(p.y * h)) for p in pl]
    for a, b in SKELETON:
        cv2.line(img, px[a], px[b], 255, 9)
    # cabeca: os landmarks do rosto nao alcancam bone nem cabelo
    sw = max(18.0, abs(pl[11].x - pl[12].x) * w)
    cv2.circle(img, px[0], int(sw * 0.62), 255, -1)
    return img


def split_masks(m_a, pl_a, m_b, pl_b, w, h):
    """Deixa as duas mascaras exclusivas.

    Duas regras: o pixel fica com o esqueleto mais perto, E precisa estar
    perto do proprio dono. So a comparacao relativa nao bastava - sobrava uma
    faixa da mulher dentro da mascara do homem, longe dos dois esqueletos.
    """
    da = cv2.distanceTransform(255 - skeleton_image(pl_a, w, h), cv2.DIST_L2, 3)
    db = cv2.distanceTransform(255 - skeleton_image(pl_b, w, h), cv2.DIST_L2, 3)
    lim_a = max(70.0, abs(pl_a[11].x - pl_a[12].x) * w * 1.15)
    lim_b = max(70.0, abs(pl_b[11].x - pl_b[12].x) * w * 1.15)
    own_a = ((da <= db) & (da < lim_a)).astype(np.float32)
    own_b = ((db < da) & (db < lim_b)).astype(np.float32)
    return m_a * own_a, m_b * own_b


def head_top(mask: np.ndarray, nose_x: float, shoulder_w: float) -> float:
    """Linha mais alta da mascara na coluna da cabeca (ignora braco erguido)."""
    h, w = mask.shape
    half = max(12.0, shoulder_w * 0.75)
    band = mask[:, int(max(0, nose_x - half)):int(min(w, nose_x + half + 1))]
    rows = np.where(band.max(axis=1) > 0.4)[0]
    return float(rows[0]) if len(rows) else float("nan")


def describe(pl, mask, w, h):
    sw = abs(pl[SHOULDERS[0]].x - pl[SHOULDERS[1]].x) * w
    return {
        "nose_x": pl[0].x * w,
        "nose_y": pl[0].y * h,
        "shoulder_w": sw,
        "head_top": head_top(mask, pl[0].x * w, sw),
        "face_top": min(pl[k].y for k in FACE) * h,
        "foot_y": max(pl[k].y for k in FEET) * h,
        "foot_x": float(np.mean([pl[k].x for k in TOES])) * w,
        "cover": float(mask.mean()),
    }


def main() -> int:
    frames = sorted(f for f in os.listdir(WORK) if f.startswith("src_"))

    def make(n):
        return vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=mpp.BaseOptions(model_asset_path=MODEL),
                running_mode=vision.RunningMode.IMAGE, num_poses=n,
                output_segmentation_masks=True,
                min_pose_detection_confidence=0.2,
                min_pose_presence_confidence=0.2))

    lm2, lm1 = make(2), make(1)

    def run(lmk, bgr):
        r = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        # numpy_view() aponta para memoria do MediaPipe, liberada quando `r`
        # sai de escopo - sem a copia o processo morre com segfault
        return [(pl, np.array(m.numpy_view()[:, :, 0], copy=True))
                for pl, m in zip(r.pose_landmarks or [],
                                 r.segmentation_masks or [])]

    out, bad, fallback = [], 0, 0
    for i, name in enumerate(frames):
        img = cv2.imread(os.path.join(WORK, name))
        h, w = img.shape[:2]
        rec = {"frame": i, "ok": False}

        pair = None
        found = run(lm2, img)
        if len(found) == 2 and abs(found[0][0][0].x - found[1][0][0].x) * w > 0.04 * w:
            pair = found
        else:
            # plano B: apaga quem foi achado e procura o outro no que sobrou
            one = run(lm1, img)
            if one:
                pl1, m1 = one[0]
                hole = cv2.dilate((m1 > 0.4).astype(np.uint8), np.ones((9, 9), np.uint8))
                two = run(lm1, cv2.inpaint(img, hole, 7, cv2.INPAINT_TELEA))
                if two and abs(pl1[0].x - two[0][0][0].x) * w > 0.04 * w:
                    pair = [(pl1, m1), two[0]]
                    fallback += 1

        if pair:
            # o homem esta sempre a direita da mulher neste video
            (plm, mm), (plw, mw) = sorted(pair, key=lambda t: -t[0][0].x)
            mm, mw = split_masks(mm, plm, mw, plw, w, h)
            rec["ok"] = True
            rec["man"] = describe(plm, mm, w, h)
            rec["woman"] = describe(plw, mw, w, h)
            cv2.imwrite(f"{WORK}/mask_man_{i:04d}.png",
                        (np.clip(mm, 0, 1) * 255).astype(np.uint8))
            cv2.imwrite(f"{WORK}/mask_woman_{i:04d}.png",
                        (np.clip(mw, 0, 1) * 255).astype(np.uint8))
        else:
            bad += 1
        out.append(rec)
        if i % 40 == 0:
            print(f"  {i}/{len(frames)}  (sem deteccao: {bad}, plano B: {fallback})",
                  flush=True)

    with open(os.path.join(WORK, "measure.json"), "w") as fh:
        json.dump(out, fh)
    print(f"pronto: {len(out)} frames | {bad} sem deteccao "
          f"(inclui o card final do logo, sem pessoas) | {fallback} pelo plano B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
