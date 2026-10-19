#!/usr/bin/env python3
"""Genera hardware/cad/preview.html: anteprima 3D dell'assemblaggio (STL incorporati, three.js da CDN)."""
import base64, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
rep = json.load(open(os.path.join(HERE, "report.json")))
g = rep["ottica"]["centro_fantasma"]
P = rep["parametri"]

LAYERS = [  # file, etichetta, colore, opacità, esplosione (mm di spostamento su Z), visibile
    ("01_corpo", "Corpo", "#2b2f3a", 1.0, 0, True),
    ("02_anello_diffusore", "Anello diffusore", "#d9e6ff", 0.55, 14, True),
    ("03_piano_superiore", "Piano superiore", "#3a3f4d", 1.0, 34, True),
    ("04_telaio_display", "Telaio display", "#59607a", 1.0, 16, True),
    ("05_fermo_display", "Fermo display", "#7a82a0", 1.0, 8, True),
    ("06_fermo_altoparlante", "Fermo altoparlante", "#7a82a0", 1.0, 6, True),
    ("c_display", "Display (componente)", "#2e7dff", 0.9, 16, True),
    ("c_barra_mic", "Barra microfoni (comp.)", "#3ddc97", 0.9, 34, True),
    ("c_altoparlante", "Altoparlante (comp.)", "#e0a030", 0.9, 0, True),
    ("c_pi5", "Raspberry Pi 5 (comp.)", "#c64b4b", 0.9, 0, True),
    ("c_flex", "Scheda Flex (comp.)", "#8a5cff", 0.9, 0, True),
    ("c_strip_led", "Strip LED (comp.)", "#ffd447", 0.6, 14, True),
    ("disco", "Disco semiriflettente", "#9fd8ff", 0.45, 60, True),
    ("sfera", "Sfera", "#bfe3ff", 0.18, 90, True),
]
data = {}
for f, *_ in LAYERS:
    data[f] = base64.b64encode(open(os.path.join(HERE, "assembly", f + ".stl"), "rb").read()).decode()

html = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aria · anteprima 3D</title>
<style>
:root{--bg:#0b0d13;--panel:#12151e;--line:#222736;--txt:#d9deee;--mut:#8089a6;--acc:#6ea8ff}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.45 system-ui,-apple-system,sans-serif;overflow:hidden}
#c{position:fixed;inset:0;width:100%;height:100%}
#ui{position:fixed;left:8px;top:8px;width:230px;opacity:.94;font-size:12px;max-height:calc(100vh - 24px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
h1{font-size:15px;margin:0 0 6px} p{margin:4px 0;color:var(--mut);font-size:12.5px}
label{display:flex;gap:8px;align-items:center;margin:2px 0;font-size:13px;cursor:pointer}
.sw{width:12px;height:12px;border-radius:3px;border:1px solid #fff3}
button{background:#171a26;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:5px 9px;font:inherit;cursor:pointer;margin:2px 2px 2px 0}
button:hover{border-color:var(--acc)} input[type=range]{width:100%;accent-color:var(--acc)}
hr{border:0;border-top:1px solid var(--line);margin:8px 0}
</style></head><body>
<canvas id="c"></canvas>
<div id="ui"><h1>Aria · assemblaggio</h1>
<p>Trascina per ruotare, rotella per lo zoom, tasto destro per spostare.</p>
<div id="layers"></div><hr>
<label>Esploso <input type="range" id="ex" min="0" max="1" step="0.01" value="0"></label>
<label><input type="checkbox" id="ghost" checked> mostra il "fantasma" (linea riflessa)</label>
<div><button data-v="front">Fronte</button><button data-v="side">Lato</button><button data-v="top">Alto</button><button data-v="iso">3/4</button></div>
<p>Fronte = verso di te (−Y). Alto totale con sfera: <b>__H__ mm</b>. Il fantasma appare in magenta dietro il disco.</p></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://unpkg.com/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const LAYERS = __LAYERS__, DATA = __DATA__, GHOST = __GHOST__;
function parseSTL(b64){
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0)), dv = new DataView(bin.buffer);
  const n = dv.getUint32(80, true), pos = new Float32Array(n*9), nor = new Float32Array(n*9);
  for (let i = 0, o = 84; i < n; i++, o += 50) {
    const nx = dv.getFloat32(o,true), ny = dv.getFloat32(o+4,true), nz = dv.getFloat32(o+8,true);
    for (let v = 0; v < 3; v++) for (let k = 0; k < 3; k++) { pos[i*9+v*3+k] = dv.getFloat32(o+12+v*12+k*4, true); nor[i*9+v*3+k] = [nx,ny,nz][k]; }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos,3)); g.setAttribute('normal', new THREE.BufferAttribute(nor,3));
  return g;
}
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({canvas, antialias:true}); renderer.setPixelRatio(devicePixelRatio);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0b0d13);
scene.add(new THREE.AmbientLight(0xffffff, .7));
const d1 = new THREE.DirectionalLight(0xffffff, .8); d1.position.set(-200,-300,400); scene.add(d1);
const d2 = new THREE.DirectionalLight(0x88aaff, .5); d2.position.set(300,200,100); scene.add(d2);
const cam = new THREE.PerspectiveCamera(35, 1, 1, 3000); cam.up.set(0,0,1);
const ctl = new THREE.OrbitControls(cam, canvas); ctl.target.set(0, 0, 140);
const grid = new THREE.GridHelper(500, 20, 0x2a3040, 0x1b2030); grid.rotation.x = Math.PI/2; grid.position.z = -6; scene.add(grid);

const meshes = {}, list = document.getElementById('layers');
LAYERS.forEach(([f, label, color, op, lift, vis]) => {
  const m = new THREE.Mesh(parseSTL(DATA[f]), new THREE.MeshStandardMaterial({color, transparent: op < 1, opacity: op, roughness: .55, metalness: .1, side: THREE.DoubleSide, depthWrite: op >= .9}));
  m.userData.lift = lift; m.visible = vis; scene.add(m); meshes[f] = m;
  const l = document.createElement('label'); l.innerHTML = `<input type="checkbox" ${vis ? 'checked' : ''}><span class="sw" style="background:${color}"></span>${label}`;
  l.firstChild.onchange = e => m.visible = e.target.checked; list.appendChild(l);
});
// fantasma: disco verticale che guarda il fronte (-Y)
const gh = new THREE.Mesh(new THREE.CircleGeometry(35, 64), new THREE.MeshBasicMaterial({color: 0xff3ea5, transparent: true, opacity: .5, side: THREE.DoubleSide}));
gh.rotation.x = Math.PI/2; gh.position.set(GHOST[0], GHOST[1], GHOST[2]); scene.add(gh);
const ln = new THREE.Mesh(new THREE.BoxGeometry(60, .8, 1.6), new THREE.MeshBasicMaterial({color: 0xffffff})); ln.position.set(GHOST[0], GHOST[1]-.5, GHOST[2]); scene.add(ln);
document.getElementById('ghost').onchange = e => { gh.visible = ln.visible = e.target.checked; };

const ex = document.getElementById('ex');
function applyExplode(){ const t = +ex.value; Object.values(meshes).forEach(m => m.position.z = m.userData.lift * t * 2.2); gh.position.z = GHOST[2] + 60*t*2.2; ln.position.z = gh.position.z; }
ex.oninput = applyExplode;
const V = {front:[0,-520,210], side:[520,0,210], top:[0,-1,620], iso:[300,-420,330]};
function view(k){ const p = V[k].map(x => x * Math.max(1, 1/cam.aspect*0.9)); cam.position.set(...p); ctl.target.set(0,0,k==='top'?0:140); ctl.update(); }
document.querySelectorAll('[data-v]').forEach(b => b.onclick = () => view(b.dataset.v));
function resize(){ renderer.setSize(innerWidth, innerHeight, false); cam.aspect = innerWidth/innerHeight; cam.updateProjectionMatrix(); }
addEventListener('resize', resize); resize(); view('iso');
(function loop(){ ctl.update(); renderer.render(scene, cam); requestAnimationFrame(loop); })();
</script></body></html>"""
html = (html.replace("__LAYERS__", json.dumps(LAYERS)).replace("__DATA__", json.dumps(data))
            .replace("__GHOST__", json.dumps(g)).replace("__H__", str(rep["ottica"]["altezza_totale_mm"])))
open(os.path.join(HERE, "preview.html"), "w").write(html)
print("preview.html", round(len(html) / 1e6, 2), "MB")
