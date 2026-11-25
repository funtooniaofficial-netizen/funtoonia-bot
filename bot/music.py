"""Composes a short ORIGINAL, copyright-free music bed for every reel.

feelgood -> lofi: warm electric-piano chords, soft kick/snare/hats, vinyl crackle
funny    -> bouncy: plucked (ukulele-like) melody, staccato bass, claps, whistle-ish lead
news     -> upbeat: bright pad, 8th-note pulse, light drums
Every call picks a random key, tempo, chord progression and melody.
"""
import random
import wave

import numpy as np

SR = 44100


def _midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _env(n, a=0.01, d=0.2, s=0.6, r=0.3, length=None):
    length = length or n
    t = np.arange(n) / SR
    e = np.ones(n) * s
    ai, di = int(a * SR), int(d * SR)
    e[:ai] = np.linspace(0, 1, max(ai, 1))[:min(ai, n)]
    if ai < n:
        seg = e[ai:ai + di]
        e[ai:ai + di] = np.linspace(1, s, max(di, 1))[:len(seg)]
    ri = int(r * SR)
    if ri and n > ri:
        e[-ri:] *= np.linspace(1, 0, ri)
    return e


def _epiano(freq, dur, vel=0.3):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t)
            * np.exp(-t * 3) + 0.15 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t * 5))
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return vel * tone * trem * _env(n, 0.005, 0.6, 0.35, 0.4)


def _pluck(freq, dur, vel=0.4, bright=0.996):
    """Karplus-Strong plucked string (ukulele / guitar-like)."""
    n = int(dur * SR)
    p = max(2, int(SR / freq))
    buf = np.random.uniform(-1, 1, p)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = bright * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return vel * out * _env(n, 0.001, 0.05, 1.0, 0.05)


def _pad(freq, dur, vel=0.12):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = sum(np.sin(2 * np.pi * freq * (1 + d) * t) for d in (-0.004, 0, 0.004)) / 3
    return vel * tone * _env(n, 0.4, 0.5, 0.8, 0.6)


def _kick(vel=0.9):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 110 * np.exp(-t * 18) + 45
    return vel * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _snare(vel=0.35):
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    noise = np.random.uniform(-1, 1, n)
    noise = np.convolve(noise, np.ones(3) / 3, "same")
    return vel * (noise * np.exp(-t * 18) + 0.4 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25))


def _hat(vel=0.12):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    noise = np.random.uniform(-1, 1, n)
    noise = noise - np.convolve(noise, np.ones(8) / 8, "same")  # high-pass
    return vel * noise * np.exp(-t * 60)


def _clap(vel=0.3):
    n = int(0.2 * SR)
    t = np.arange(n) / SR
    noise = np.random.uniform(-1, 1, n)
    env = np.exp(-t * 30) + 0.6 * np.exp(-((t - 0.012) * 300) ** 2) + 0.5 * np.exp(-((t - 0.024) * 300) ** 2)
    return vel * noise * env


def _add(buf, sig, at):
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[:j - i]


PROGS = {  # scale degrees (semitones from root) for 4-chord loops
    "feelgood": [[0, 4, 7, 11], [9, 12, 16, 19], [5, 9, 12, 16], [7, 11, 14, 17]],
    "feelgood2": [[2, 5, 9, 12], [7, 11, 14, 17], [0, 4, 7, 11], [9, 12, 16, 19]],
    "funny": [[0, 4, 7], [5, 9, 12], [7, 11, 14], [0, 4, 7]],
    "funny2": [[0, 4, 7], [9, 12, 16], [5, 9, 12], [7, 11, 14]],
    "news": [[0, 4, 7], [7, 11, 14], [9, 12, 16], [5, 9, 12]],
}
MAJOR = [0, 2, 4, 5, 7, 9, 11, 12, 14, 16]


def compose(mode: str, seconds: float, out_wav: str, weather: str = "none") -> str:
    rnd = random.Random()
    n = int(seconds * SR)
    mix = np.zeros(n)
    root = 48 + rnd.choice([0, 2, 3, 5, 7, 8, 10])  # random key

    if mode == "funny":
        bpm = rnd.randint(118, 132)
        prog = PROGS[rnd.choice(["funny", "funny2"])]
    elif mode == "news":
        bpm = rnd.randint(108, 120)
        prog = PROGS["news"]
    else:
        bpm = rnd.randint(70, 84)
        prog = PROGS[rnd.choice(["feelgood", "feelgood2"])]
    beat = 60 / bpm
    bar = 4 * beat

    t, ci = 0.0, 0
    while t < seconds:
        chord = prog[ci % len(prog)]
        if mode == "feelgood":
            for k, s in enumerate(chord):  # gently strummed e-piano
                _add(mix, _epiano(_midi(root + 12 + s), bar + 0.4, 0.16), t + k * 0.03)
            _add(mix, _epiano(_midi(root + chord[0] - 12), bar, 0.22), t)
            for b in range(4):  # lazy lofi drums with swing
                bt = t + b * beat
                if b in (0, 2):
                    _add(mix, _kick(0.55), bt)
                if b in (1, 3):
                    _add(mix, _snare(0.18), bt)
                for h in (0, 0.58):
                    _add(mix, _hat(0.05), bt + h * beat)
            if rnd.random() < 0.7:  # little melody notes
                for k in range(rnd.randint(2, 4)):
                    note = root + 24 + rnd.choice(MAJOR[:8])
                    _add(mix, _epiano(_midi(note), beat * 1.5, 0.07),
                         t + rnd.choice([0.5, 1, 1.5, 2, 2.5, 3]) * beat)
        elif mode == "funny":
            for b in range(8):  # bouncy 8th-note ukulele strum
                bt = t + b * beat / 2
                for k, s in enumerate(chord):
                    _add(mix, _pluck(_midi(root + 12 + s), beat / 2 + 0.1, 0.09), bt + k * 0.008)
            for b in range(4):  # staccato "oom-pah" bass + claps
                bt = t + b * beat
                _add(mix, _pluck(_midi(root - 12 + (chord[0] if b % 2 == 0 else chord[-1])),
                                 beat * 0.4, 0.35, 0.99), bt)
                if b in (1, 3):
                    _add(mix, _clap(0.22), bt)
                if b == 0:
                    _add(mix, _kick(0.4), bt)
            for k in range(rnd.randint(3, 6)):  # playful hopping lead
                note = root + 24 + chord[rnd.randrange(len(chord))] + rnd.choice([0, 12])
                _add(mix, _pluck(_midi(note), beat * 0.5, 0.14, 0.997),
                     t + rnd.choice([0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]) * beat)
        else:  # news
            for s in chord:
                _add(mix, _pad(_midi(root + 12 + s), bar + 0.3, 0.07), t)
            for b in range(8):
                bt = t + b * beat / 2
                _add(mix, _pluck(_midi(root + chord[0]), beat / 2, 0.12, 0.99), bt)
                _add(mix, _hat(0.06), bt)
            for b in range(4):
                bt = t + b * beat
                _add(mix, _kick(0.6) if b % 2 == 0 else _snare(0.2), bt)
        t += bar
        ci += 1

    if mode == "feelgood":  # vinyl crackle for warmth
        crackle = np.zeros(n)
        idx = np.random.randint(0, n, int(seconds * 25))
        crackle[idx] = np.random.uniform(-0.08, 0.08, len(idx))
        mix += crackle + np.random.normal(0, 0.003, n)
    if weather == "rain":  # soft rain bed under the music
        noise = np.random.normal(0, 1, n)
        rain = np.convolve(noise, np.ones(30) / 30, "same")
        mix += 0.06 * rain / (np.abs(rain).max() + 1e-9)

    # simple room reverb (feedback delays) + normalise + fades
    for d, g in ((0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2)):
        k = int(d * SR)
        mix[k:] += g * mix[:-k] * (0.6 if mode == "feelgood" else 0.3)
    mix /= (np.abs(mix).max() + 1e-9)
    mix *= 0.85
    f_in, f_out = int(0.8 * SR), int(1.5 * SR)
    mix[:f_in] *= np.linspace(0, 1, f_in)
    mix[-f_out:] *= np.linspace(1, 0, f_out)

    stereo = np.stack([mix, np.roll(mix, 220)], axis=1)  # slight stereo width
    data = (stereo * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return out_wav
