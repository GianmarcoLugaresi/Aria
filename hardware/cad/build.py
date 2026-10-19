#!/usr/bin/env python3
"""
Aria · generatore parametrico dei pezzi stampati in 3D.

    python hardware/cad/build.py   # genera stl/ + assembly/ + report.json + preview.html

Tutte le quote in mm. Modifica i parametri qui sotto (soprattutto dopo aver misurato i pezzi
veri con un calibro) e rilancia: i pezzi vengono rigenerati e i controlli di interferenza
rifatti. Riferimento: asse Z = asse della sfera, Z=0 = fondo del cuore, FRONTE = -Y (verso di te).

Come funziona l'ottica (riflesso "fantasma"): lo schermo guarda in su sotto il piano superiore;
un disco semiriflettente a 45°, dentro la sfera, ne riflette l'immagine verso di te: la linea
appare sospesa dietro il disco, la sfera resta trasparente.
"""
import json, math, os, sys
import numpy as np
import trimesh
from manifold3d import Manifold, OpType

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------- PARAMETRI
P = dict(
    # corpo
    ped_d=210.0,        # diametro del corpo (richiede un piano di stampa >= 215 mm)
    wall=2.4, floor=3.0,
    cup_h=90.0,         # altezza del "bicchiere"
    band_h=12.0,        # anello diffusore della luce (traslucido)
    plate_t=4.0,        # piano superiore
    # sfera (globo con collo): MISURA la tua!
    sphere_d=160.0,     # diametro esterno (150-200 mm vanno bene)
    neck_id=100.0,      # diametro INTERNO dell'apertura (collo)
    neck_wall=3.0,      # spessore vetro/acrilico
    neck_h=12.0,        # lunghezza del tratto cilindrico del collo
    sphere_wall=3.0,
    lip_clear=0.7,      # gioco radiale tra lip centratore e collo
    lip_h=8.0,
    # disco semiriflettente
    disc_d=110.0, disc_t=2.0, disc_slot=2.5,
    disc_cy=5.0,        # spostamento del centro del disco verso il retro (+Y)
    disc_low=2.5,       # quota del punto più basso del disco sopra il piano superiore
    # display Waveshare 3.4" HDMI tondo (modulo quadrato)
    disp_w=115.0, disp_t=17.0, disp_clear=0.4, active_d=87.6, win_d=90.0,
    # barra microfoni reSpeaker Flex Linear (110 x ~20 mm: MISURA)
    mic_len=110.0, mic_w=20.0, mic_t=3.0, mic_pitch=33.0, mic_y=-72.0,
    # altoparlante full-range da 3" (MISURA)
    spk_frame_d=87.0, spk_depth=38.0, spk_cut_d=66.0, spk_x=-48.0, spk_y=0.0,
    # Raspberry Pi 5
    pi_x=50.0, pi_y=6.0, pi_standoff=6.0,
    # scheda principale Flex 86 x 35 (zona frontale)
    flex_w=86.0, flex_d=35.0,
)
for k, v in (kv.split("=") for kv in sys.argv[1:] if "=" in kv):     # override da riga di comando
    P[k] = type(P[k])(v)

R_IN = P["ped_d"] / 2 - P["wall"]
Z_BAND = P["cup_h"]
Z_PLATE = Z_BAND + P["band_h"]            # sotto del piano
Z_DECK = Z_PLATE + P["plate_t"]           # sopra del piano (qui appoggia la sfera)
LIP_R = P["neck_id"] / 2 - P["lip_clear"]
WIN_R = P["win_d"] / 2
TILT = 45.0
FLANGE_T = 3.0
SPK_PAD_TOP = 4.6
FLEX_Y = -72.5
SEG = 160

# ----------------------------------------------------------------------------- UTILITY
def cyl(r, h, z0=0.0, x=0.0, y=0.0, seg=SEG):
    return Manifold.cylinder(h, r, r, seg).translate((x, y, z0))

def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))

def ring(r_out, r_in, z0, z1, seg=SEG):
    return cyl(r_out, z1 - z0, z0, seg=seg) - cyl(r_in, z1 - z0 + 2, z0 - 1, seg=seg)

def union(parts):
    return Manifold.batch_boolean(parts, OpType.Add)

def to_trimesh(m):
    me = m.to_mesh()
    return trimesh.Trimesh(vertices=np.array(me.vert_properties)[:, :3], faces=np.array(me.tri_verts), process=False)

def vol(m):
    return 0.0 if m.is_empty() else m.volume()

def bbox(m):
    b = m.bounding_box()
    return [round(b[3] - b[0], 1), round(b[4] - b[1], 1), round(b[5] - b[2], 1)]

# frame locale del disco: u = asse X, v = su lungo il disco (alto-fronte), w = normale (basso-fronte)
DISC_C = (0.0, P["disc_cy"], 0.0)   # z calcolato sotto
disc_r = P["disc_d"] / 2
_s45 = math.sin(math.radians(TILT))
DISC_C = (0.0, P["disc_cy"], Z_DECK + P["disc_low"] + disc_r * _s45)

def to_world_disc(m):
    return m.rotate((135.0, 0, 0)).translate(DISC_C)

def local_box(u0, u1, v0, v1, w0, w1):
    return to_world_disc(box(u0, u1, v0, v1, w0, w1))

# ----------------------------------------------------------------------------- PEZZI
def make_cup():
    w, fl = P["wall"], P["floor"]
    body = cyl(P["ped_d"] / 2, P["cup_h"]) - cyl(R_IN, P["cup_h"] - fl + 1, fl)
    # altoparlante: finestra + griglia + sede flangia
    sx, sy = P["spk_x"], P["spk_y"]
    win = cyl(P["spk_cut_d"] / 2, fl + 2, -1, sx, sy)
    spokes = union([box(-1.0, 1.0, -P["spk_cut_d"] / 2, P["spk_cut_d"] / 2, 0, fl).rotate((0, 0, a)).translate((sx, sy, 0))
                    for a in (0, 60, 120)])
    inner_ring = ring(P["spk_cut_d"] / 4 + 1.0, P["spk_cut_d"] / 4 - 1.0, 0, fl, 96).translate((sx, sy, 0))
    body = body - win + (spokes ^ cyl(P["spk_cut_d"] / 2 + 0.2, fl, 0, sx, sy)) + inner_ring
    # sede della flangia (incavo 1.5 mm) e 3 colonnine per l'anello di fissaggio
    body = body - cyl(P["spk_frame_d"] / 2 + 0.3, 1.6, fl - 1.5, sx, sy)
    bosses = []
    for a in (90, 210, 330):                       # piazzole per le viti del fermo altoparlante (viti M3 dal basso)
        bx = sx + 50 * math.cos(math.radians(a)); by = sy + 50 * math.sin(math.radians(a))
        bosses.append(cyl(5.2, SPK_PAD_TOP - fl + 0.1, fl - 0.1, bx, by, 48))
    body_holes = [cyl(1.7, SPK_PAD_TOP + 2, -1, sx + 50 * math.cos(math.radians(a)), sy + 50 * math.sin(math.radians(a)), 24)
                  + cyl(3.1, 3.2, -1, sx + 50 * math.cos(math.radians(a)), sy + 50 * math.sin(math.radians(a)), 24) for a in (90, 210, 330)]
    # colonnine del Raspberry Pi 5 (fori 58 x 49, M2.5)
    for dx in (-24.5, 24.5):
        for dy in (-29.0, 29.0):
            bx, by = P["pi_x"] + dx, P["pi_y"] + dy
            bosses.append(cyl(3.2, P["pi_standoff"], fl - 0.1, bx, by, 32) - cyl(1.1, P["pi_standoff"] + 1, fl + 0.5, bx, by, 24))
    # 4 piedini di appoggio per la scheda Flex (nastro biadesivo)
    fy = FLEX_Y
    for fx in (-35, 35):
        for dyy in (-9, 9):
            bosses.append(box(fx - 4, fx + 4, fy + dyy - 4, fy + dyy + 4, fl - 0.1, fl + 4))
    # 6 colonne per le viti del piano (M3, inserti a caldo dall'alto): base larga + stelo sottile nella fascia LED
    cols = []
    for k in range(6):
        a = math.radians(30 + 60 * k)
        cr, cr2 = R_IN - 4.4, R_IN - 6.3
        cols.append(cyl(4.6, Z_BAND - fl + 0.1, fl - 0.1, cr * math.cos(a), cr * math.sin(a), 48))
        cols.append(cyl(3.6, Z_PLATE - Z_BAND + 0.1, Z_BAND - 0.1, cr2 * math.cos(a), cr2 * math.sin(a), 40)
                    - cyl(2.0, 9.0, Z_PLATE - 9, cr2 * math.cos(a), cr2 * math.sin(a), 24))
    body = union([body] + bosses + cols) - union(body_holes)
    # tacca per il cavo di alimentazione (dietro, in basso) e feritoie di areazione
    body = body - box(-9, 9, R_IN - 1, P["ped_d"] / 2 + 1, -1, 12)
    slots = []
    for k in range(34):
        ang = 20 + k * (320 / 33)
        if 60 < ang < 120:     # niente feritoie sopra la tacca del cavo
            continue
        slots.append(box(-1.2, 1.2, R_IN - 1, P["ped_d"] / 2 + 1, 64, 82).rotate((0, 0, ang - 90)))
    body = body - union(slots)
    return body

def make_band():
    return ring(P["ped_d"] / 2, P["ped_d"] / 2 - 1.2, Z_BAND, Z_PLATE)

def make_top_plate():
    pt = P["plate_t"]
    plate = cyl(P["ped_d"] / 2, pt, Z_PLATE)
    lip = ring(LIP_R, WIN_R, Z_DECK - 0.01, Z_DECK + P["lip_h"])
    parts = [plate, lip]
    # --- supporti laterali del disco: puntone inclinato + forcella con fessura
    slot_cuts = []
    for sgn in (+1, -1):
        fork = local_box(sgn * 50.0 if sgn > 0 else -60.0, 60.0 if sgn > 0 else -50.0, -9, 9, -6, 6)
        foot_x = sgn * 44.8
        top = to_world_disc(Manifold.cube((0.01, 0.01, 0.01)).translate((sgn * 53.5, -3.0, 3.6)))
        tb = top.bounding_box()
        top_pt = ((tb[0] + tb[3]) / 2, (tb[1] + tb[4]) / 2, (tb[2] + tb[5]) / 2)
        strut = Manifold.batch_hull([
            box(foot_x - 1.8, foot_x + 1.8, P["disc_cy"] - 2.2, P["disc_cy"] + 2.2, Z_DECK + P["lip_h"] - 1.0, Z_DECK + P["lip_h"] + 0.5),
            box(top_pt[0] - 1.8, top_pt[0] + 1.8, top_pt[1] - 2.2, top_pt[1] + 2.2, top_pt[2] - 1.0, top_pt[2] + 1.0),
        ])
        parts += [fork, strut]
        slot_cuts.append(local_box(sgn * 48.0 if sgn > 0 else -57.0, 57.0 if sgn > 0 else -48.0, -14, 14, -P["disc_slot"] / 2, P["disc_slot"] / 2))
    # --- tacca posteriore: sostiene il punto più basso del disco
    tab = local_box(-6, 6, -63, -50, -6, 6) ^ cyl(LIP_R, 60, Z_PLATE)
    parts.append(tab)
    slot_cuts.append(local_box(-7, 7, -(disc_r + 1.5), -30, -P["disc_slot"] / 2, P["disc_slot"] / 2))
    top = union(parts)
    top = top - union(slot_cuts)
    top = top - to_world_disc(cyl(disc_r + 0.6, P["disc_slot"] + 0.4, -(P["disc_slot"] + 0.4) / 2))   # scanalatura dove il disco attraversa il lip
    top = top - cyl(WIN_R, pt + 40, Z_PLATE - 5)                 # finestra sullo schermo
    # fori microfoni (4 x Ø2) sopra la barra
    for i in range(4):
        mx = (i - 1.5) * P["mic_pitch"]
        top = top - cyl(1.0, pt + 2, Z_PLATE - 1, mx, P["mic_y"], 24)
    # viti piano -> cuore (6, M3 svasate) e piano -> telaio (4)
    for k in range(6):
        a = math.radians(30 + 60 * k); cr = R_IN - 4.4
        cx, cy = cr * math.cos(a), cr * math.sin(a)
        top = top - cyl(1.7, pt + 2, Z_PLATE - 1, cx, cy, 24) - Manifold.cylinder(1.6, 1.7, 3.3, 24).translate((cx, cy, Z_DECK - 1.6))
    for (fx, fy) in FRAME_SCREWS:
        top = top - cyl(1.7, pt + 2, Z_PLATE - 1, fx, fy, 24) - Manifold.cylinder(1.6, 1.7, 3.3, 24).translate((fx, fy, Z_DECK - 1.6))
    return top

FRAME_SCREWS = [(70.0, 45.0), (-70.0, 45.0), (85.0, -15.0), (-85.0, -15.0)]

def make_frame():
    """Telaio sotto il piano: tasca per il display + sede della barra microfoni."""
    dw = P["disp_w"] + 2 * P["disp_clear"]
    ow = dw + 2 * 4.0
    h = P["disp_t"]
    z0 = Z_PLATE - h
    walls = box(-ow / 2, ow / 2, -ow / 2, ow / 2, z0, Z_PLATE) - box(-dw / 2, dw / 2, -dw / 2, dw / 2, z0 - 1, Z_PLATE + 1)
    # fori per i fermi del display (M2.5 autofilettanti dal basso, al centro dei 4 lati)
    for (px, py) in ((ow / 2 - 2, 0), (-ow / 2 + 2, 0), (0, ow / 2 - 2), (0, -ow / 2 + 2)):
        walls = walls - cyl(1.1, 9, z0 - 1, px, py, 24)
    # passaggio cavi dietro
    walls = walls - box(-22, 22, ow / 2 - 5, ow / 2 + 1, z0 - 1, z0 + 11)
    parts = [walls]
    # bracci con colonnine per le viti dal piano
    for (fx, fy) in FRAME_SCREWS:
        edge_x = math.copysign(ow / 2 - 1, fx)
        arm = Manifold.batch_hull([box(min(edge_x, edge_x + 2 * math.copysign(1, fx)) - 0.1, max(edge_x, edge_x + 2 * math.copysign(1, fx)) + 0.1,
                                       fy - 5, fy + 5, Z_PLATE - 3, Z_PLATE),
                                   cyl(5.0, 3.0, Z_PLATE - 3, fx, fy, 40)])
        boss = cyl(5.0, 8.0, Z_PLATE - 8, fx, fy, 40) - cyl(2.1, 9, Z_PLATE - 9, fx, fy, 24)
        parts += [arm, boss]
    # sede barra microfoni (cassetto basso 4.5 mm sotto il piano, fronte del display)
    mw = P["mic_len"] + 1.0
    t = 1.2
    y_rear = -ow / 2 + 0.5
    y_front = P["mic_y"] - P["mic_w"] / 2 - 0.3
    pocket_z0 = Z_PLATE - (P["mic_t"] + 1.5)
    bracket = box(-mw / 2 - t, mw / 2 + t, y_front - t, y_rear, pocket_z0, Z_PLATE) \
              - box(-mw / 2, mw / 2, y_front, y_rear + 1.0, pocket_z0 - 1, Z_PLATE + 1)
    parts.append(bracket ^ cyl(R_IN - 0.6, 40, Z_PLATE - 20))
    return union(parts)

def make_display_retainer():
    dw = P["disp_w"] + 2 * P["disp_clear"]; ow = dw + 8.0
    z0 = Z_PLATE - P["disp_t"] - 2.5
    r = box(-ow / 2, ow / 2, -ow / 2, ow / 2, z0, z0 + 2.5) - box(-48, 48, -48, 48, z0 - 1, z0 + 4)
    for (px, py) in ((ow / 2 - 2, 0), (-ow / 2 + 2, 0), (0, ow / 2 - 2), (0, -ow / 2 + 2)):
        r = r - cyl(1.4, 4, z0 - 1, px, py, 24)
    return r

def make_speaker_retainer():
    sx, sy = P["spk_x"], P["spk_y"]
    z0 = SPK_PAD_TOP                                 # sopra la flangia (che sta in un incavo di 1.5 mm)
    r = ring(P["spk_frame_d"] / 2 + 3.0, P["spk_frame_d"] / 2 - 4.0, z0, z0 + 2.5, 96)
    ears = []
    for a in (90, 210, 330):
        ex = 50 * math.cos(math.radians(a)); ey = 50 * math.sin(math.radians(a))
        ears.append(cyl(5.8, 4.0, z0, ex, ey, 48))
        ears.append(box(-3.0, 3.0, 36, 50, z0, z0 + 2.5).rotate((0, 0, a - 90)))
    r = union([r] + ears)
    for a in (90, 210, 330):
        ex = 50 * math.cos(math.radians(a)); ey = 50 * math.sin(math.radians(a))
        nut = Manifold.cylinder(2.6, 3.3, 3.3, 6).translate((ex, ey, z0 + 1.5))           # dado M3 (esagono 5.7 mm)
        r = r - cyl(1.7, 6, z0 - 1, ex, ey, 24) - nut
    return r.translate((sx, sy, 0))

# ---- componenti "finti" (solo per verificare gli ingombri, non si stampano)
def comp_display():
    w = P["disp_w"]
    return box(-w / 2, w / 2, -w / 2, w / 2, Z_PLATE - P["disp_t"], Z_PLATE)

def comp_mic_bar():
    mw = P["mic_len"]
    return box(-mw / 2, mw / 2, P["mic_y"] - P["mic_w"] / 2, P["mic_y"] + P["mic_w"] / 2, Z_PLATE - P["mic_t"], Z_PLATE)

def comp_speaker():
    sx, sy = P["spk_x"], P["spk_y"]
    flange = cyl(P["spk_frame_d"] / 2, FLANGE_T, P["floor"] - 1.5, sx, sy)
    body = cyl(P["spk_frame_d"] * 0.38, P["spk_depth"] - FLANGE_T, P["floor"] - 1.5 + FLANGE_T, sx, sy)
    return flange + body

def comp_pi():
    # Pi 5 con il lato lungo sull'asse Y; i fori sono a 10 mm dal centro scheda
    return box(P["pi_x"] - 28, P["pi_x"] + 28, P["pi_y"] - 52.5, P["pi_y"] + 32.5, P["floor"] + P["pi_standoff"], P["floor"] + P["pi_standoff"] + 27)

def comp_flex():
    fy = FLEX_Y
    return box(-P["flex_w"] / 2, P["flex_w"] / 2, fy - P["flex_d"] / 2, fy + P["flex_d"] / 2, P["floor"] + 4, P["floor"] + 4 + 10)

def comp_led_strip():
    return ring(P["ped_d"] / 2 - 1.2, P["ped_d"] / 2 - 3.4, Z_BAND + 1, Z_PLATE - 1)

def sphere_shell():
    R = P["sphere_d"] / 2
    z_neck_top = Z_DECK + P["neck_h"]
    r_o_neck = P["neck_id"] / 2 + P["neck_wall"]
    zc = z_neck_top + math.sqrt((R - P["sphere_wall"]) ** 2 - (P["neck_id"] / 2) ** 2)   # il raccordo interno parte dal foro del collo
    outer = Manifold.sphere(R, 128).translate((0, 0, zc))
    inner = Manifold.sphere(R - P["sphere_wall"], 128).translate((0, 0, zc))
    cut_below = box(-R - 1, R + 1, -R - 1, R + 1, zc - R - 1, z_neck_top)
    shell = (outer - inner) - cut_below
    neck = ring(r_o_neck, P["neck_id"] / 2, Z_DECK + 0.02, z_neck_top + 0.5)
    return shell + neck, zc

def disc_model():
    return to_world_disc(cyl(disc_r, P["disc_t"], -P["disc_t"] / 2))

# ---- provini di calibrazione (stampali PRIMA)
def coupon_neck():
    base = cyl(P["neck_id"] / 2 + 14, 3.0, 0)
    lip = ring(LIP_R, WIN_R, 2.99, 3.0 + P["lip_h"])
    return base - cyl(WIN_R, 6, -1) + lip

def coupon_display():
    dw = P["disp_w"] + 2 * P["disp_clear"]; ow = dw + 8.0
    return box(-ow / 2, ow / 2, -ow / 2, ow / 2, 0, 8) - box(-dw / 2, dw / 2, -dw / 2, dw / 2, 2.0, 9) - box(-48, 48, -48, 48, -1, 3)

def coupon_speaker():
    base = cyl(P["spk_frame_d"] / 2 + 12, P["floor"], 0)
    base = base - cyl(P["spk_cut_d"] / 2, 6, -1) - cyl(P["spk_frame_d"] / 2 + 0.3, 1.6, P["floor"] - 1.5)
    return base

def coupon_disc_slot():
    blk = box(0, 18, 0, 22, 0, 12)
    sl = box(2, 15, -1, 23, 5, 5 + P["disc_slot"])
    return blk - sl

def coupon_mic():
    mw = P["mic_len"] + 1.0
    plate = box(-mw / 2 - 4, mw / 2 + 4, 0, P["mic_w"] + 9, 0, 3.0)
    pocket = box(-mw / 2, mw / 2, 4, 4 + P["mic_w"] + 0.5, 1.5, 4)
    for i in range(4):
        plate = plate - cyl(1.0, 5, -1, (i - 1.5) * P["mic_pitch"], 4 + (P["mic_w"] + 0.5) / 2, 24)
    return plate - pocket

# ----------------------------------------------------------------------------- ASSEMBLAGGIO
def flipped_for_print(m):
    """Capovolge (sopra <-> sotto) e porta z minimo a 0."""
    r = m.rotate((180, 0, 0))
    b = r.bounding_box()
    return r.translate((0, 0, -b[2]))

def on_bed(m):
    b = m.bounding_box()
    return m.translate((-0.0, -0.0, -b[2]))

def main():
    os.makedirs(os.path.join(HERE, "stl"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "assembly"), exist_ok=True)

    parts = {
        "01_corpo": (make_cup(), "stl/01_corpo.stl", "su"),
        "02_anello_diffusore": (make_band(), "stl/02_anello_diffusore.stl", "su"),
        "03_piano_superiore": (make_top_plate(), "stl/03_piano_superiore.stl", "su"),
        "04_telaio_display": (make_frame(), "stl/04_telaio_display.stl", "capovolto"),
        "05_fermo_display": (make_display_retainer(), "stl/05_fermo_display.stl", "su"),
        "06_fermo_altoparlante": (make_speaker_retainer(), "stl/06_fermo_altoparlante.stl", "su"),
    }
    coupons = {
        "T1_prova_collo_sfera": coupon_neck(),
        "T2_prova_tasca_display": coupon_display(),
        "T3_prova_altoparlante": coupon_speaker(),
        "T4_prova_fessura_disco": coupon_disc_slot(),
        "T5_prova_barra_microfoni": coupon_mic(),
    }

    report = {"parametri": P, "pezzi": {}, "interferenze": {}, "note": []}
    asm = {}
    for name, (m, path, orient) in parts.items():
        asm[name] = m
        pm = flipped_for_print(m) if orient == "capovolto" else on_bed(m)
        to_trimesh(pm).export(os.path.join(HERE, path))
        report["pezzi"][name] = dict(volume_cm3=round(vol(m) / 1000, 1), ingombro_stampa=bbox(pm), orientamento=orient,
                                     manifold=str(m.status()).endswith("NO_ERROR") or str(m.status()).endswith("NoError"))
    for name, m in coupons.items():
        pm = on_bed(m)
        to_trimesh(pm).export(os.path.join(HERE, "stl", name + ".stl"))
        report["pezzi"][name] = dict(volume_cm3=round(vol(m) / 1000, 1), ingombro_stampa=bbox(pm), orientamento="su")

    # --- esporta assemblaggio (per l'anteprima)
    sph, zc = sphere_shell()
    extras = {"sfera": sph, "disco": disc_model(), "c_display": comp_display(), "c_barra_mic": comp_mic_bar(),
              "c_altoparlante": comp_speaker(), "c_pi5": comp_pi(), "c_flex": comp_flex(), "c_strip_led": comp_led_strip()}
    for k, m in {**{n: v[0] for n, v in parts.items()}, **extras}.items():
        to_trimesh(m).export(os.path.join(HERE, "assembly", k + ".stl"))

    # --- controlli di interferenza (volume sovrapposto: deve essere ~0)
    def inter(a, b):
        return round(vol(a ^ b), 3)
    cup, band, top, frame, ret, spk_ret = (parts[n][0] for n in ("01_corpo", "02_anello_diffusore", "03_piano_superiore", "04_telaio_display", "05_fermo_display", "06_fermo_altoparlante"))
    printed = {"corpo": cup, "diffusore": band, "piano": top, "telaio": frame, "fermo_display": ret, "fermo_altoparlante": spk_ret}
    solid = {"disco": extras["disco"], "sfera": sph}
    comps = {k[2:]: v for k, v in extras.items() if k.startswith("c_")}
    bad = []
    for pn, pm in printed.items():
        for sn, sm in {**solid, **comps}.items():
            v = inter(pm, sm)
            report["interferenze"][f"{pn} x {sn}"] = v
            if v > 0.5:
                bad.append((pn, sn, v))
    # tra pezzi stampati (devono solo toccarsi, non compenetrarsi)
    names = list(printed)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            v = inter(printed[names[i]], printed[names[j]])
            report["interferenze"][f"{names[i]} x {names[j]}"] = v
            if v > 0.5:
                bad.append((names[i], names[j], v))
    for i, a in enumerate(comps):
        for b in list(comps)[i + 1:]:
            v = inter(comps[a], comps[b])
            report["interferenze"][f"{a} x {b}"] = v
            if v > 0.5:
                bad.append((a, b, v))
    report["problemi"] = [f"{a} x {b}: {v} mm3" for a, b, v in bad]

    # --- geometria ottica (fantasma)
    s = _s45
    Q = (0.0, DISC_C[1] + disc_r * s, DISC_C[2] - disc_r * s)             # punto più basso del disco
    ghost_y = Q[1] + Q[2] - Z_PLATE + 0.0
    report["ottica"] = dict(
        z_piano=Z_DECK, centro_disco=[round(c, 1) for c in DISC_C], centro_sfera_z=round(zc, 1),
        altezza_totale_mm=round(zc + P["sphere_d"] / 2 + 6, 1),
        fantasma_piano_y=round(Q[1] + (Z_PLATE - Q[2]) , 1),
        nota="il fantasma è un disco verticale dietro il disco semiriflettente; il bordo del display lato fronte diventa il bordo alto")
    # quota del centro del fantasma: riflesso del centro dello schermo (0, 0, Z_PLATE) sul piano del disco
    n = np.array([0.0, s, s]); Qv = np.array(Q); Pc = np.array([0.0, 0.0, Z_PLATE])
    G = Pc - 2 * np.dot(Pc - Qv, n) * n
    report["ottica"]["centro_fantasma"] = [round(float(g), 1) for g in G]
    # visibilita' diretta dello schermo: elevazione minima da cui lo si vede sopra il lip
    for r_px, label in ((35.0, "pixel_luminosi"), (P["active_d"] / 2, "bordo_vetro_attivo")):
        elev = math.degrees(math.atan2(Z_DECK + P["lip_h"] - Z_PLATE, LIP_R - r_px))
        report["ottica"][f"schermo_non_visibile_sotto_deg_{label}"] = round(elev, 1)

    tot_vol = sum(v["volume_cm3"] for k, v in report["pezzi"].items() if k[0].isdigit())
    report["filamento_stimato_g"] = round(tot_vol * 1.27 * 0.85)       # PETG: pareti da 2.4 mm quasi piene (stima)
    json.dump(report, open(os.path.join(HERE, "report.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("pezzi", "problemi", "ottica", "filamento_stimato_g")}, indent=2, ensure_ascii=False))
    print("\nInterferenze rilevate:" if bad else "\nNessuna interferenza sopra 0.5 mm3.")
    for a, b, v in bad:
        print(f"  {a} x {b}: {v} mm3")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
