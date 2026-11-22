# Synthetic ambient bed + a few designed accents for the Blindgrasp pitch (all generated here, no samples).
# usage: .venv-free: python3 audio/music.py  -> public/music.wav
import json, sys
import numpy as np
sys.path.insert(0, "audio")
from dsp import SR, hz, lp, hp, curve, fade, put, noise, reverb, write, cue, words

W = words(); END = W[-1]["e"] + 3.0
N = int(END * SR); t = np.arange(N) / SR
bed = np.zeros((N, 2))

def voice(freq, dur, seed, bright=1800):
    n = int(dur * SR); tt = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * freq * k * tt * (1 + 0.0015 * np.sin(2 * np.pi * (0.13 + 0.03 * k) * tt + seed + k))) / k ** 1.6 for k in range(1, 6))
    x = lp(x, bright)
    env = np.minimum(1, tt / 2.5) * np.minimum(1, (dur - tt) / 2.5)
    return x * env

# Chords (Dm9 - Bbmaj7 - Fmaj7 - C6), 9.6 s each, overlapping.
CH = [["D3", "A3", "C4", "E4", "F4"], ["Bb2", "F3", "A3", "D4"], ["F2", "C3", "A3", "E4"], ["C3", "G3", "A3", "E4"]]
L = 9.6
for i in range(int(END // L) + 1):
    for j, nme in enumerate(CH[i % 4]):
        v = voice(hz(nme), L + 3, seed=i * 7 + j) * 0.16
        pan = (j / max(1, len(CH[i % 4]) - 1)) * 1.2 - 0.6
        put(bed, np.column_stack([v * (1 - pan) / 2 ** 0.5, v * (1 + pan) / 2 ** 0.5]), i * L, 1.0)
# soft pulse: a muted pluck on the chord root every half bar after the hook
def pluck(freq, seed):
    n = int(1.2 * SR); tt = np.arange(n) / SR
    return lp(np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 5) + 0.3 * np.sin(4 * np.pi * freq * tt) * np.exp(-tt * 8), 2500)
start = cue("This is Blindgrasp", 0)
k = 0
for s in np.arange(start, END - 4, 0.833):
    root = CH[int(s // L) % 4][-2 if k % 2 else -1]
    put(bed, np.column_stack([pluck(hz(root) * 2, k)] * 2), s, 0.05 * (0.7 + 0.3 * (k % 4 == 0)))
    k += 1
bed = reverb(bed, decay=4.5, wet=0.45, bright=4000)[:N]

# Level automation: quiet under speech, small swells on the title and end card, fade out.
duck = np.ones(N)
env = np.array(json.load(open("src/vo_env.json")))
vo = np.interp(t, np.arange(len(env)) / 30, env)
vo = np.convolve(vo, np.ones(int(0.4 * SR)) / int(0.4 * SR), mode="same")
duck = 1 - 0.45 * np.clip(vo * 2.5, 0, 1)
shape = curve(t, [(0, 0), (1.5, 0.75), (start - 0.3, 0.85), (start + 0.6, 1.25), (start + 3, 0.9), (cue("A robot that learns") - 0.5, 0.95),
                  (cue("A robot that learns") + 1, 1.25), (END - 2.5, 1.1), (END, 0)])
bed *= (duck * shape)[:, None]

# Accents: a soft low hit + shimmer on "By touch", the title and the end card.
def accent(seed):
    n = int(3 * SR); tt = np.arange(n) / SR
    low = np.sin(2 * np.pi * 55 * tt * (1 - 0.15 * tt / 3)) * np.exp(-tt * 2.2)
    sh = hp(noise(n, seed), 6000) * np.exp(-tt * 3) * 0.08
    return np.column_stack([low * 0.5 + sh, low * 0.5 + sh[::-1]])
for at in (cue("By touch"), start, cue("A robot that learns")):
    put(bed, reverb(accent(int(at)), decay=2.5, wet=0.4), at, 0.55)
# Touch ticks in the hook: one soft tick per reveal (8 reveals, 3 frames apart, starting 3 frames after "By touch").
for i in range(8):
    n = int(0.25 * SR); tt = np.arange(n) / SR
    tick = np.sin(2 * np.pi * 1400 * tt) * np.exp(-tt * 40)
    put(bed, np.column_stack([tick, tick]), cue("By touch") + (3 + i * 3) / 30, 0.08)

write("public/music.wav", fade(bed[:N], 0.01, 2.0), peak=-6)
print("music.wav", round(END, 2), "s")
