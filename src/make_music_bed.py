#!/usr/bin/env python3
"""Trilha instrumental sintetizada (sem direitos de terceiros) para o reel.

Violão dedilhado (Karplus-Strong), baixo, bumbo macio e chocalho a 100 BPM,
progressão Am - F - C - G, com final em acorde suspenso. Gera um WAV estéreo.

Uso: python3 src/make_music_bed.py --seconds 17.4 --bpm 100 --out out/bed.wav
"""
import argparse
import math

import numpy as np

SR = 44100


def ks_pluck(freq, dur, decay=0.996, brightness=0.5, seed=0):
    """Karplus-Strong vetorizado por período."""
    rng = np.random.default_rng(seed)
    n = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, n)
    buf -= buf.mean()
    # suaviza o ruído inicial conforme o "brilho" (0 = abafado, 1 = brilhante)
    k = int(1 + (1 - brightness) * 6)
    buf = np.convolve(buf, np.ones(k) / k, mode="same")
    periods = int(math.ceil(dur * SR / n)) + 1
    out = np.empty(periods * n)
    for p in range(periods):
        out[p * n:(p + 1) * n] = buf
        buf = decay * 0.5 * (buf + np.roll(buf, 1))
    out = out[: int(dur * SR)]
    # ataque curto para evitar clique
    a = min(64, len(out))
    out[:a] *= np.linspace(0, 1, a)
    return out


def sine_kick(dur=0.22):
    t = np.arange(int(dur * SR)) / SR
    f = 55 + 90 * np.exp(-t * 28)
    env = np.exp(-t * 18)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env


def shaker(dur=0.08, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = rng.normal(0, 1, n)
    # passa-alta simples
    y = x - np.concatenate([[0], x[:-1]]) * 0.95
    env = np.exp(-np.arange(n) / SR * 90)
    return y * env * 0.08


def note(name):
    names = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
    n, octv = name[:-1], int(name[-1])
    semis = names[n] + (octv - 4) * 12
    return 440.0 * 2 ** (semis / 12)


CHORDS = [  # (baixo, [notas do dedilhado])
    ("A2", ["A3", "E4", "A4", "C5", "E4", "A4", "C5", "E4"]),
    ("F2", ["F3", "C4", "F4", "A4", "C4", "F4", "A4", "C4"]),
    ("C3", ["C4", "G4", "C5", "E5", "G4", "C5", "E5", "G4"]),
    ("G2", ["G3", "D4", "G4", "B4", "D4", "G4", "B4", "D4"]),
]


def render(seconds, bpm, seed=7):
    beat = 60 / bpm
    eighth = beat / 2
    total = int((seconds + 2.5) * SR)
    L = np.zeros(total)
    R = np.zeros(total)

    def add(sig, t0, gain, pan=0.0):
        i = int(t0 * SR)
        if i >= total:
            return
        s = sig[: total - i] * gain
        L[i:i + len(s)] += s * (1 - pan) * 0.5 + s * 0.5
        R[i:i + len(s)] += s * (1 + pan) * 0.5 + s * 0.5

    bars = int(math.ceil(seconds / (4 * beat)))
    k = 0
    for b in range(bars):
        bass, arp = CHORDS[b % len(CHORDS)]
        t_bar = b * 4 * beat
        last_bar = t_bar + 4 * beat >= seconds
        if last_bar:
            # acorde final: notas soando juntas, longas
            for j, nm in enumerate(arp[:4]):
                add(ks_pluck(note(nm), 3.5, decay=0.9985, brightness=0.55, seed=seed + k + j), t_bar + j * 0.03, 0.22, pan=(j - 1.5) * 0.15)
            add(ks_pluck(note(bass), 3.5, decay=0.999, brightness=0.25, seed=seed + 99), t_bar, 0.32)
            add(sine_kick(0.3), t_bar, 0.5)
            break
        add(ks_pluck(note(bass), 2 * beat, decay=0.9985, brightness=0.3, seed=seed + k), t_bar, 0.34)
        add(ks_pluck(note(bass), 2 * beat, decay=0.9985, brightness=0.3, seed=seed + k + 1), t_bar + 2 * beat, 0.26)
        for j, nm in enumerate(arp):
            t = t_bar + j * eighth
            accent = 1.0 if j % 2 == 0 else 0.78
            add(ks_pluck(note(nm), 1.2, decay=0.997, brightness=0.35, seed=seed + k + j + 10), t, 0.2 * accent, pan=0.35 if j % 2 else -0.2)
        # percussão leve
        add(sine_kick(), t_bar, 0.34)
        add(sine_kick(), t_bar + 2 * beat, 0.28)
        for j in range(8):
            add(shaker(seed=seed + k + j), t_bar + j * eighth, 0.5 if j % 2 else 0.3, pan=0.4)
        k += 20

    k3 = np.ones(3) / 3
    L = np.convolve(L, k3, mode="same"); R = np.convolve(R, k3, mode="same")
    # reverb curto (IR de ruído decaindo)
    rng = np.random.default_rng(seed)
    ir = rng.normal(0, 1, int(0.35 * SR)) * np.exp(-np.arange(int(0.35 * SR)) / SR * 14)
    ir /= np.abs(ir).sum() / 6
    from numpy.fft import irfft, rfft
    def conv(x):
        n = len(x) + len(ir) - 1
        return irfft(rfft(x, n) * rfft(ir, n), n)[: len(x)]
    L = L + 0.18 * conv(L)
    R = R + 0.18 * conv(R)

    # fade final e normalização
    out = np.stack([L, R], axis=1)
    fade = int(1.2 * SR)
    end = int(seconds * SR)
    out = out[:end]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    # compressor "soft-knee" simples
    out = np.tanh(out * 1.6) / 1.6
    out /= np.abs(out).max() + 1e-9
    return (out * 0.9 * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=17.4)
    ap.add_argument("--bpm", type=int, default=100)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import wave
    pcm = render(a.seconds, a.bpm)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("OK", a.out, f"{a.seconds}s @ {a.bpm} BPM")


if __name__ == "__main__":
    main()
