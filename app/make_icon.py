"""Icone di Aria a partire dal logo disegnato dall'utente: Resources/brand/icon_1024.png (bianco su nero, 1024x1024).

Produce:
  Resources/AppIcon.icns       icona dell'app: il logo dentro la sagoma standard macOS (corpo 824 px su 1024, angoli continui, ombra)
  Resources/MenuIcon.png       logo per la barra dei menu: nero con trasparenza (36x36 = 18 pt @2x), colorabile da AppKit
  Resources/MenuIconMuted.png  lo stesso con una barra diagonale (microfono silenziato)
  build/AppIcon_1024.png       anteprima dell'icona dell'app
  build/menubar_preview.png    anteprima della barra dei menu chiara e scura

Nessuna dipendenza grafica: numpy + sips/iconutil di macOS. Non modifica mai il file sorgente.
"""
import os
import struct
import subprocess
import tempfile
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "Resources", "brand", "icon_1024.png")
N = 1024
BODY = 824                                      # corpo dell'icona nel quadrato 1024 (griglia standard macOS)
MENU_PX = 36                                    # 18 pt @2x
MENU_GLYPH = 31                                 # altezza del logo dentro 36 px: aria intorno, come i simboli di sistema


def png(path, rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def load_gray(path):
    """Legge un'immagine qualsiasi come luminanza 0..1 (la converte in BMP con sips: nessun decoder PNG da scrivere)."""
    with tempfile.TemporaryDirectory() as t:
        bmp = os.path.join(t, "x.bmp")
        subprocess.run(["sips", "-s", "format", "bmp", path, "--out", bmp], check=True, stdout=subprocess.DEVNULL)
        d = open(bmp, "rb").read()
    off, w, h, bpp = struct.unpack_from("<I", d, 10)[0], struct.unpack_from("<i", d, 18)[0], struct.unpack_from("<i", d, 22)[0], struct.unpack_from("<H", d, 28)[0]
    assert bpp in (24, 32), f"BMP a {bpp} bit non gestito"
    row = ((bpp * w + 31) // 32) * 4
    a = np.frombuffer(d, np.uint8, count=row * abs(h), offset=off).reshape(abs(h), row)[:, : w * bpp // 8].reshape(abs(h), w, bpp // 8)
    if h > 0:
        a = a[::-1]                                                     # BMP e' scritto dal basso
    return a[..., :3].astype(np.float32).mean(axis=2) / 255.0


def area_weights(n_in, n_out):
    """Matrice del filtro 'media sull'area' (rimpicciolire senza aliasing)."""
    w = np.zeros((n_out, n_in), np.float32)
    s = n_in / n_out
    for i in range(n_out):
        lo, hi = i * s, (i + 1) * s
        for j in range(int(lo), min(n_in, int(np.ceil(hi)))):
            w[i, j] = max(0.0, min(j + 1, hi) - max(j, lo))
        w[i] /= w[i].sum()
    return w


def resize(a, h, w):
    return area_weights(a.shape[0], h) @ a @ area_weights(a.shape[1], w).T


def blur(a, sigma):
    r = int(sigma * 3)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for axis in (0, 1):
        a = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), axis, a)
    return a


def glyph_mask(gray):
    """Luminanza -> opacita' del logo: pulisce il rumore di compressione del nero e del bianco."""
    return np.clip((gray - 0.10) / 0.80, 0.0, 1.0)


def squircle(n, body):
    """Copertura (0..1) della forma 'continua' di macOS (superellisse n=5) con bordo antialias."""
    c = (n - 1) / 2.0
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    a, p = body / 2.0, 5.0
    u, v = np.abs(x - c) / a + 1e-6, np.abs(y - c) / a + 1e-6
    f = u ** p + v ** p - 1.0
    gx, gy = p * u ** (p - 1) / a, p * v ** (p - 1) / a
    dist = f / np.sqrt(gx ** 2 + gy ** 2)                               # distanza in pixel dal bordo (negativa dentro)
    return np.clip(0.5 - dist, 0.0, 1.0), np.clip(-dist, 0.0, None)


def app_icon(mask):
    cov, depth = squircle(N, BODY)
    art = np.zeros((N, N), np.float32)
    o = (N - BODY) // 2
    art[o:o + BODY, o:o + BODY] = resize(mask, BODY, BODY)             # tutto il disegno dell'utente nel corpo dell'icona
    rim = np.clip(1.8 - depth, 0.0, 1.0) * 0.16 * cov                   # filo di luce sul bordo: separa il nero dagli sfondi scuri
    col = np.clip(art + rim * (1 - art), 0, 1)
    shadow = np.roll(blur(cov, 16.0), 12, axis=0) * 0.38
    alpha = cov + shadow * (1 - cov)
    g = np.where(alpha > 1e-4, col * cov / np.maximum(alpha, 1e-4), 0)         # colore non premoltiplicato (grigio: il disegno e' bianco su nero)
    rgba = np.dstack([g, g, g, alpha])
    return np.ascontiguousarray(np.clip(rgba * 255 + 0.5, 0, 255).astype(np.uint8))


def menu_icons(mask):
    ys, xs = np.where(mask > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    pad = 3
    crop = mask[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    ss = 4
    S = MENU_PX * ss
    gh = MENU_GLYPH * ss
    gw = int(round(gh * (x1 - x0 + 2 * pad) / (y1 - y0 + 2 * pad)))
    g = resize(crop, gh, gw)
    canvas = np.zeros((S, S), np.float32)
    oy, ox = (S - gh) // 2, (S - gw) // 2
    canvas[oy:oy + gh, ox:ox + gw] = g
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    cx = cy = (S - 1) / 2.0
    d = np.abs((xx - cx) - (yy - cy)) / np.sqrt(2.0)                    # distanza dalla diagonale alto-sinistra -> basso-destra
    along = np.abs(xx - cx) <= S * 0.43
    slash = np.clip(1.5 * ss - d + 0.5, 0, 1) * along
    muted = np.maximum(canvas * np.clip(d - 2.9 * ss + 0.5, 0, 1), slash)
    out = []
    for a in (canvas, muted):
        a = resize(a, MENU_PX, MENU_PX)
        rgba = np.zeros((MENU_PX, MENU_PX, 4), np.uint8)
        rgba[..., 3] = np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)
        out.append(rgba)
    return out


def menubar_preview(idle, muted, path):
    """Barre dei menu finte (chiara sopra, scura sotto), ingrandite 6x, per controllare a occhio la leggibilita'."""
    rows = []
    for bg, fg in ((235, 20), (30, 240)):
        tiles = []
        for ic in (idle, muted):
            t = np.full((MENU_PX + 8, MENU_PX + 8, 3), bg, np.float32)
            al = ic[..., 3:4].astype(np.float32) / 255
            t[4:4 + MENU_PX, 4:4 + MENU_PX] = (1 - al) * bg + al * fg
            tiles.append(t)
        rows.append(np.concatenate(tiles, axis=1))
    img = np.repeat(np.repeat(np.concatenate(rows, axis=0).astype(np.uint8), 6, axis=0), 6, axis=1)
    png(path, np.dstack([img, np.full(img.shape[:2], 255, np.uint8)]))


def main():
    mask = glyph_mask(load_gray(SRC))
    assert mask.shape == (N, N), f"il logo deve essere {N}x{N}, e' {mask.shape}"
    res, build = os.path.join(HERE, "Resources"), os.path.join(HERE, "build")
    os.makedirs(build, exist_ok=True)

    base = os.path.join(build, "AppIcon_1024.png")
    png(base, app_icon(mask))
    iconset = os.path.join(build, "AppIcon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for s in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = s * scale
            name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
            subprocess.run(["sips", "-z", str(px), str(px), base, "--out", os.path.join(iconset, name)],
                           check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(res, "AppIcon.icns")], check=True)

    idle, muted = menu_icons(mask)
    png(os.path.join(res, "MenuIcon.png"), idle)
    png(os.path.join(res, "MenuIconMuted.png"), muted)
    menubar_preview(idle, muted, os.path.join(build, "menubar_preview.png"))
    print("icone create in", res)


if __name__ == "__main__":
    main()
