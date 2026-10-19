/* neural.js · Aria come un cervello, nello stile del suo logo.

   Una nuvola di sfere piene (non una sfera perfetta) che fluttua piano e gira su se stessa. Come nel logo:
   le sfere sono piatte e bianche, e quando si collegano lo fanno con "colli" organici che si allargano verso le sfere e si fondono con loro
   (effetto metaball: tutto viene disegnato in bianco su un canvas, poi un filtro SVG sfoca e riaffila il contorno).
     idle       respira: le sfere si muovono appena
     listening  le sfere TREMANO con la tua voce
     thinking   le sfere si GONFIANO e si accendono a ondate (le "cellule" prendono le informazioni)
     speaking   NASCONO COLLEGAMENTI tra le sfere vicine, come neuroni: il collo esce da una sfera, si allunga e si ingrossa; si scioglie nelle pause e a fine frase

   Uso:  const b = new NeuralBrain(canvas, {ghost: false});  b.setState('speaking');  b.setLevel(0.6);  b.draw(tempoInSecondi);
   ghost:true = per il display dell'oggetto fisico (la pagina deve avere lo sfondo nero; l'immagine si riflette nel disco semiriflettente).
   goo:false  = niente filtro (sfere e linee semplici). */
(function (root) {
  'use strict';
  const TAU = Math.PI * 2;
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
  const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
  function rng(seed) {                                   // generatore deterministico: la nuvola e' sempre la stessa
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  const PALETTE = {                                      // un solo accento per stato: tinge le sfere quando si accendono
    idle: [176, 190, 255], listening: [104, 224, 255], thinking: [200, 156, 255], speaking: [255, 168, 208], error: [255, 118, 96],
  };
  const SPIN = { idle: 0.15, listening: 0.11, thinking: 0.34, speaking: 0.2, error: 0.1 };   // rad/s
  const WHITE = [246, 247, 252];

  // forma "logo", in px CSS per la nuvola dell'overlay (REF_AREA = semiasse orizzontale x verticale = 179 x 78 px); tutto scala con la radice dell'area.
  // Il filtro sfoca di GOO_BLUR px e riaffila la soglia a 0,5: un collo di larghezza w compare solo quando w supera ~1,4 x GOO_BLUR.
  const NODE_R = 8.6, NECK_MIN = 3.2, NECK_MAX = 10.4, GOO_BLUR = 3.8, GOO_SLOPE = 24, REF_AREA = 179 * 78, REACH_FULL = 74, REACH_NONE = 108;   // oltre REACH_NONE px (a scala 1) il collo si spezza

  class NeuralBrain {
    constructor(canvas, opts = {}) {
      this.cv = canvas;
      this.ctx = canvas.getContext('2d');
      this.n = opts.nodes || 20;
      this.ghost = !!opts.ghost;
      this.sc = 0;
      this.goo = opts.goo !== false && this._installGoo();
      this.state = 'idle';
      this.level = 0; this.sLevel = 0;                   // livello grezzo e smussato (0..1)
      this.conn = 0; this.trem = 0; this.think = 0;      // quanto sono collegati / tremanti / accesi
      this.quiet = 0; this.yaw = 0; this.spin = SPIN.idle;
      this.accent = PALETTE.idle.slice();
      this.last = null;
      this._build(opts.seed || 11);
    }

    /* filtro "goo": sfoca il disegno e poi riaffila il canale alfa -> le sfere vicine si fondono con colli lisci e raccordi concavi */
    _installGoo() {
      const doc = root.document;
      if (!doc) return false;
      try {
        if (!doc.getElementById('aria-goo')) {
          const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
          svg.setAttribute('width', '0'); svg.setAttribute('height', '0'); svg.setAttribute('aria-hidden', 'true');
          svg.style.cssText = 'position:absolute;width:0;height:0;pointer-events:none';
          svg.innerHTML = `<defs><filter id="aria-goo" x="-4%" y="-4%" width="108%" height="108%" color-interpolation-filters="sRGB">` +
            `<feGaussianBlur id="aria-goo-blur" stdDeviation="${GOO_BLUR}"/>` +
            `<feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 ${GOO_SLOPE} ${-GOO_SLOPE / 2}"/></filter></defs>`;
          doc.body.appendChild(svg);
        }
        this.cv.style.webkitFilter = this.cv.style.filter = 'url(#aria-goo)';
        return true;
      } catch (_) { return false; }
    }

    setState(s) { if (PALETTE[s]) this.state = s; }
    setLevel(v) { this.level = clamp(+v || 0); }

    _build(seed) {
      const r = rng(seed), N = this.n, golden = Math.PI * (3 - Math.sqrt(5));
      this.nodes = [];
      for (let i = 0; i < N; i++) {
        const y = 1 - 2 * (i + 0.5) / N, rr = Math.sqrt(1 - y * y), ph = i * golden;
        let v = [Math.cos(ph) * rr, y, Math.sin(ph) * rr];
        v = v.map(c => c + (r() - 0.5) * 0.5);                            // smuove le direzioni: niente guscio regolare
        const l = Math.hypot(v[0], v[1], v[2]) || 1, rad = 0.55 + 0.45 * Math.pow(r(), 0.6);
        this.nodes.push({
          p: v.map(c => c / l * rad),
          amp: 0.022 + r() * 0.05,                                        // deriva lenta
          fr: [0.22 + r() * 0.6, 0.22 + r() * 0.6, 0.22 + r() * 0.6], ph: [r() * TAU, r() * TAU, r() * TAU],
          tf: 17 + r() * 24, tp: [r() * TAU, r() * TAU, r() * TAU],       // frequenza e fasi del tremito
          size: 0.86 + r() * 0.34, act: 0, seed: r() * TAU,
        });
      }
      // collegamenti: un ALBERO che unisce tutte le sfere (Prim sulla nuvola a riposo: i rami si diramano come nel logo, niente reticolo fitto)
      // piu' qualche anello tra vicine, cosi' la rete non e' una semplice ramificazione
      const E = [], seen = new Set(), inTree = new Array(N).fill(false), at = (i) => this.nodes[i].p;
      const link = (i, j) => {
        const key = i < j ? i + ',' + j : j + ',' + i;
        if (seen.has(key)) return false;
        seen.add(key); E.push({ a: i, b: j, len: dist(at(i), at(j)) });
        return true;
      };
      inTree[0] = true;
      for (let c = 1; c < N; c++) {
        let best = null;
        for (let i = 0; i < N; i++) if (inTree[i]) for (let j = 0; j < N; j++) if (!inTree[j]) {
          const d = dist(at(i), at(j));
          if (!best || d < best.d) best = { i, j, d };
        }
        inTree[best.j] = true; link(best.i, best.j);
      }
      const med = E.map(e => e.len).sort((x, y) => x - y)[E.length >> 1];
      for (let i = 0; i < N; i++) {
        if (r() > 0.32) continue;
        let best = null;
        for (let j = 0; j < N; j++) {
          if (j === i || seen.has(i < j ? i + ',' + j : j + ',' + i)) continue;
          const d = dist(at(i), at(j));
          if (!best || d < best.d) best = { j, d };
        }
        if (best && best.d < med * 1.25) link(i, best.j);
      }
      const maxLen = Math.max(...E.map(e => e.len));
      for (const e of E) { e.th = clamp(e.len / maxLen * 0.8 + r() * 0.24 - 0.04); e.v = 0; }   // i piu' vicini si legano per primi
      this.edges = E;
      this.signals = [];
    }

    resize() {
      const dpr = root.devicePixelRatio || 1, w = Math.max(2, this.cv.clientWidth * dpr | 0), h = Math.max(2, this.cv.clientHeight * dpr | 0);
      if (this.cv.width !== w || this.cv.height !== h) { this.cv.width = w; this.cv.height = h; }
      this.dpr = dpr;
    }

    draw(t) {
      this.resize();
      const ctx = this.ctx, W = this.cv.width, H = this.cv.height, dpr = this.dpr;
      const dt = this.last == null ? 1 / 60 : clamp(t - this.last, 0.001, 0.08);
      this.last = t;
      const st = this.state, k = (rate) => 1 - Math.exp(-dt * rate);

      // ---- dinamica (tutto smussato: nessuno scatto)
      this.sLevel += (this.level - this.sLevel) * k(this.level > this.sLevel ? 22 : 7);
      const tremT = st === 'listening' ? 0.18 + 1.1 * this.sLevel : st === 'thinking' ? 0.3 : st === 'speaking' ? 0.05 : 0.02;
      this.trem += (tremT - this.trem) * k(14);
      this.think += ((st === 'thinking' ? 1 : 0) - this.think) * k(3.2);
      let connT = 0;
      if (st === 'speaking') {                          // si legano mentre c'e' voce, si sciolgono nelle pause e a fine frase
        this.quiet = this.sLevel < 0.07 ? this.quiet + dt : 0;
        connT = this.quiet > 0.3 ? 0 : clamp(0.24 + this.sLevel * 1.2);
      } else this.quiet = 0;
      this.conn += (connT - this.conn) * k(connT > this.conn ? 7 : 2.4);
      this.spin += ((SPIN[st] || 0.15) - this.spin) * k(2);
      this.yaw += this.spin * dt;
      const pal = PALETTE[st] || PALETTE.idle;
      for (let i = 0; i < 3; i++) this.accent[i] += (pal[i] - this.accent[i]) * k(3.5);

      // ---- proiezione
      const Ry = H * 0.40, Rx = Math.min(W * 0.42, Ry * 2.0), cx = W / 2, cy = H / 2, F = 5.2;   // nuvola larga quanto serve alla schermata; prospettiva lieve
      const sc = clamp(Math.sqrt((Rx / dpr) * (Ry / dpr) / REF_AREA), 0.35, 8);  // scala rispetto all'overlay: la distanza tra le sfere resta proporzionale (il display fisico e' molto piu' grande)
      if (this.goo && Math.abs(sc - this.sc) > 0.02) {
        this.sc = sc;
        const bn = root.document.getElementById('aria-goo-blur');
        if (bn) bn.setAttribute('stdDeviation', (GOO_BLUR * sc).toFixed(2));
      }
      const cosY = Math.cos(this.yaw), sinY = Math.sin(this.yaw);
      const pitch = 0.42 + 0.12 * Math.sin(t * 0.17), cosP = Math.cos(pitch), sinP = Math.sin(pitch);
      const P = new Array(this.n);
      for (let i = 0; i < this.n; i++) {
        const n = this.nodes[i];
        let x = n.p[0] + n.amp * Math.sin(t * n.fr[0] + n.ph[0]);
        let y = n.p[1] + n.amp * Math.sin(t * n.fr[1] + n.ph[1]);
        let z = n.p[2] + n.amp * Math.sin(t * n.fr[2] + n.ph[2]);
        const ta = 0.010 + 0.075 * this.trem;                                   // ampiezza del tremito
        x += ta * Math.sin(t * n.tf + n.tp[0]); y += ta * Math.sin(t * n.tf * 1.13 + n.tp[1]); z += ta * Math.sin(t * n.tf * 0.87 + n.tp[2]);
        const x1 = x * cosY + z * sinY, z1 = -x * sinY + z * cosY;
        const y2 = y * cosP - z1 * sinP, z2 = y * sinP + z1 * cosP;
        const s = F / (F + z2), near = clamp((1 - z2) / 2);
        // accensione: ondata mentre pensa, bagliore con la voce mentre ascolta/parla
        const wave = Math.pow(0.5 + 0.5 * Math.sin(t * 3.1 - y * 5.2 + n.seed), 3);
        const voice = st === 'listening' ? this.sLevel * (0.4 + 0.6 * Math.sin(t * 8 + n.seed) ** 2)
                    : st === 'speaking' ? (0.22 + this.sLevel * 0.55) * (0.5 + 0.5 * Math.sin(t * 2.4 + n.seed * 1.7)) : 0;
        n.act = clamp(this.think * wave + voice);
        P[i] = { x: cx + x1 * Rx * s, y: cy + y2 * Ry * s, z: z2, s, near, act: n.act, size: n.size,
                 pulse: 1 + n.act * 0.5 + this.trem * 0.1 * Math.sin(t * n.tf + n.seed) };
      }

      // ---- colori: bianco del logo; piu' scure quelle lontane; tinte dell'accento quando si accendono
      const acc = this.accent, css = (c) => `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
      const mix = (a, b, f) => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
      for (let i = 0; i < this.n; i++) {
        const p = P[i], dark = 0.86 + 0.14 * p.near;                            // 0,86 (lontana) .. 1 (vicina): quasi piatto, bianco come il logo (la profondita' la danno le dimensioni)
        const base = [WHITE[0] * dark, WHITE[1] * dark, WHITE[2] * dark * (0.97 + 0.03 * dark)];
        p.col = css(mix(base, acc, (st === 'idle' ? 0.06 : 0.09) + 0.32 * p.act));
        p.rgb = base;
      }

      // ---- disegno: tutto opaco; il filtro del canvas fa il resto
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      ctx.lineCap = 'round';
      const gain = (this.ghost ? 1.12 : 1) * sc;
      let live = 0;
      for (const e of this.edges) {                                             // colli: la larghezza cresce da 0 a quella del logo
        const a = P[e.a], b = P[e.b];
        const L = Math.hypot(a.x - b.x, a.y - b.y) / (dpr * sc);                // lunghezza a video: un braccio troppo lungo si assottiglia e si spezza
        const target = smooth(e.th - 0.1, e.th + 0.06, this.conn) * (1 - smooth(REACH_FULL, REACH_NONE, L));
        e.v += (target - e.v) * k(target > e.v ? 9 : 5);
        if (e.v < 0.02) continue;
        live++;
        ctx.strokeStyle = css(mix(a.rgb, b.rgb, 0.5));
        ctx.lineWidth = (NECK_MIN + (NECK_MAX - NECK_MIN) * e.v) * gain * dpr * (a.s + b.s) / 2 * Math.min(1, 0.4 + e.v * 1.4);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      // impulsi: una goccia che corre lungo il collo e lo fa gonfiare al passaggio
      const want = Math.round(this.conn * 5);
      while (this.signals.length < want && live > 6) {
        const e = this.edges[(Math.random() * this.edges.length) | 0];
        if (e.v > 0.7) this.signals.push({ e, p: 0, sp: 0.7 + Math.random() * 1.0, dir: Math.random() < 0.5 ? 1 : -1 });
        else break;
      }
      this.signals = this.signals.filter(g => {
        g.p += g.sp * dt;
        if (g.p >= 1 || g.e.v < 0.4) return false;
        const a = P[g.dir > 0 ? g.e.a : g.e.b], b = P[g.dir > 0 ? g.e.b : g.e.a];
        const x = a.x + (b.x - a.x) * g.p, y = a.y + (b.y - a.y) * g.p;
        const r = NECK_MAX * 0.62 * gain * dpr * (a.s + b.s) / 2 * Math.sin(g.p * Math.PI) * clamp(g.e.v);
        ctx.fillStyle = css(mix(WHITE, acc, 0.25));
        ctx.beginPath(); ctx.arc(x, y, Math.max(0.1, r), 0, TAU); ctx.fill();
        return true;
      });
      const order = P.map((_, i) => i).sort((i, j) => P[j].z - P[i].z);         // dalle lontane alle vicine
      for (const i of order) {                                                  // sfere piene
        const p = P[i];
        ctx.fillStyle = p.col;
        ctx.beginPath(); ctx.arc(p.x, p.y, NODE_R * p.size * p.s * p.pulse * gain * dpr, 0, TAU); ctx.fill();
      }
    }
  }
  root.NeuralBrain = NeuralBrain;
})(typeof window !== 'undefined' ? window : globalThis);
