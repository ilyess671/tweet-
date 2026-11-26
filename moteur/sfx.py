"""Bruitages synthétisés (aucun fichier externe, donc libres de droits) et mixage sur une liste d'événements."""
import numpy as np, wave, sys

SR = 48000
rng = np.random.default_rng(7)

def t_(d): return np.arange(int(d * SR)) / SR
def env(n, a=0.002, r=0.1):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / r)
    return e
def lowpass(x, fc):
    # one-pole low-pass, fc may be an array (sweep)
    fc = np.broadcast_to(fc, x.shape)
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc; y[i] = acc
    return y
def highpass(x, fc): return x - lowpass(x, fc)

# ---------- sons ----------
def pop(f0=900, f1=260, d=0.09, vol=0.6):
    t = t_(d); f = f1 + (f0 - f1) * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return vol * np.sin(ph) * env(len(t), 0.001, 0.03)

def bubble(vol=0.5):  # pop plus rond pour cartes / lignes
    t = t_(0.14); f = 300 + 700 * (1 - np.exp(-t / 0.03))
    ph = 2 * np.pi * np.cumsum(f) / SR
    return vol * np.sin(ph) * env(len(t), 0.003, 0.045)

def whoosh(d=0.45, vol=0.5, up=True):
    n = int(d * SR); x = rng.standard_normal(n)
    k = np.linspace(0, 1, n)
    fc = 300 + 5000 * (np.sin(np.pi * k) ** 2)
    y = lowpass(x, fc); y = highpass(y, 150)
    e = np.sin(np.pi * k) ** 2.2
    return vol * y / (np.abs(y).max() + 1e-9) * e

def clac(vol=0.9):  # arrêt sur image : clic d'obturateur + impact
    a = highpass(rng.standard_normal(int(0.03 * SR)), 2500) * env(int(0.03 * SR), 0.0005, 0.006)
    b = np.zeros(int(0.07 * SR)); b[int(0.045 * SR):] = 0  # 2e clic
    c2 = highpass(rng.standard_normal(int(0.025 * SR)), 3000) * env(int(0.025 * SR), 0.0005, 0.005)
    t = t_(0.35); thump = np.sin(2 * np.pi * (55 + 90 * np.exp(-t / 0.03)) * t) * env(len(t), 0.001, 0.09)
    out = np.zeros(int(0.4 * SR))
    out[:len(a)] += a * 0.8; out[int(0.05 * SR):int(0.05 * SR) + len(c2)] += c2 * 0.6
    out[:len(thump)] += thump * 0.9
    return vol * out / np.abs(out).max()

def tick(hi=True, vol=0.55):  # tic (aigu) / tac (grave) façon bois
    f = 2600 if hi else 1700; t = t_(0.06)
    s = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.3 * t)
    n = highpass(rng.standard_normal(len(t)), 1500) * 0.3
    return vol * (s + n) * env(len(t), 0.0005, 0.012)

def sparkle(vol=0.25):
    out = np.zeros(int(0.6 * SR))
    for k in range(7):
        f = 2400 + 400 * k * (1 + 0.1 * rng.standard_normal()); st = int(k * 0.06 * SR)
        t = t_(0.2); s = np.sin(2 * np.pi * f * t) * env(len(t), 0.001, 0.05)
        out[st:st + len(s)] += s
    return vol * out

def chime(freqs, step=0.07, vol=0.35, decay=0.35):
    out = np.zeros(int((step * len(freqs) + 1.0) * SR))
    for i, f in enumerate(freqs):
        t = t_(1.0); s = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t))
        s *= env(len(t), 0.002, decay); st = int(i * step * SR); out[st:st + len(s)] += s
    return vol * out / 1.5

def riser(d=0.35, vol=0.25):
    t = t_(d); f = 400 * np.exp(np.log(4) * t / d)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / d) ** 2
    n = lowpass(rng.standard_normal(len(t)), 4000) * (t / d) ** 2 * 0.5
    return vol * (s + n)

def click(vol=0.6):
    t = t_(0.02); return vol * highpass(rng.standard_normal(len(t)), 3000) * env(len(t), 0.0003, 0.003)

def soft_swish(vol=0.18): return whoosh(0.3, vol)

def pad(dur, vol=0.05):  # nappe très discrète en fond
    t = t_(dur); out = np.zeros(len(t))
    for f in (220, 277.2, 329.6, 440):
        out += np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * 0.2 * t))
    fade = np.minimum(1, t / 1.0) * np.minimum(1, (dur - t) / 1.0)
    return vol * out / 4 * fade

def mix(events, dur, out_path, with_pad=False):
    track = np.zeros(int(dur * SR) + SR)
    for t0, s in events:
        st = int(t0 * SR); track[st:st + len(s)] += s[:len(track) - st]
    if with_pad: track[:int(dur * SR)] += pad(dur)
    track = track[:int(dur * SR)]
    track = np.tanh(track * 1.2) / np.tanh(1.2)       # limiteur doux
    track *= 0.9 / (np.abs(track).max() + 1e-9)
    st = np.stack([track, track], 1)
    with wave.open(out_path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype('<i2').tobytes())



def vine_boom(vol=1.0):
    """« BOUM » façon mème (recréé de zéro) : coup grave qui descend, saturé, avec résonance."""
    d = 1.6; t = t_(d)
    f = 45 + 110 * np.exp(-t / 0.05)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)
    e = np.minimum(1, t / 0.004) * np.exp(-t / 0.45)
    x = np.tanh(2.5 * body * e)
    n = int(0.03 * SR)
    x[:n] += 0.8 * lowpass(rng.standard_normal(n), 2500) * env(n, 0.0005, 0.008)
    out = x.copy()
    for dl, g in [(0.043, 0.35), (0.071, 0.3), (0.097, 0.25), (0.131, 0.2), (0.173, 0.15)]:
        k = int(dl * SR); out[k:] += g * x[:-k]
    out = lowpass(out, 3000)
    return vol * out / np.abs(out).max()


SONS = {'vine_boom': vine_boom}


def charger(path):
    """Son fourni par l'utilisateur (mp3/wav) → tableau mono 48 kHz."""
    import subprocess
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype='<f4').astype(float)


def piste(events, dur, out_path):
    """Comme mix() mais sans normalisation (pour les sons de mème, gardés à leur volume)."""
    track = np.zeros(int(dur * SR) + SR)
    for t0, s in events:
        st = int(t0 * SR); track[st:st + len(s)] += s[:len(track) - st]
    track = np.clip(track[:int(dur * SR)], -1, 1)
    st = np.stack([track, track], 1)
    with wave.open(out_path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767 * 0.9).astype('<i2').tobytes())
