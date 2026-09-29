"""Self-contained live dashboard page for the firehose sim.

Served at /sim/dashboard; polls /sim/metrics (Prometheus exposition,
same origin) once per second and draws rate/gauge charts on canvas.
No external assets — works offline.
"""

DASHBOARD_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>firehose sim dashboard</title>
<style>
  :root { color-scheme: dark; }
  body { background:#111; color:#ddd; font:13px/1.4 monospace; margin:16px; }
  h1 { font-size:16px; margin:0 0 4px; }
  .sub { color:#888; margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; max-width:1400px; }
  .card { background:#1a1a1a; border:1px solid #333; border-radius:6px; padding:10px; }
  .card h2 { font-size:12px; margin:0 0 8px; color:#aaa; font-weight:normal; }
  canvas { width:100%; height:180px; display:block; }
  .legend { margin-top:6px; }
  .legend span { margin-right:14px; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:4px; }
  #status { float:right; color:#888; }
</style>
</head>
<body>
<h1>firehose sim dashboard <span id="status">starting...</span></h1>
<div class="sub">polls /sim/metrics every 1s &middot; rates computed client-side over the poll window</div>
<div class="grid" id="grid"></div>
<script>
const CHARTS = [
  { key: "firehose_messages_total", title: "messages/s delivered (rate)", mode: "rate" },
  { key: "firehose_bytes_total",    title: "MB/s delivered (rate)",     mode: "rate", scale: 1e-6 },
  { key: "firehose_dropped_total",  title: "inbox evictions/s (rate)",  mode: "rate" },
  { key: "firehose_connections",    title: "active websocket connections", mode: "gauge" },
  { key: "firehose_consumers",      title: "active kafka consumers",    mode: "gauge" },
  { key: "sim_backlog",             title: "sim feed backlog (produced - consumed)", mode: "gauge" },
];
const MAX_POINTS = 300;
const COLORS = ["#e5b567","#7dc4e4","#b58e5d","#8cbd56","#d46a6a","#9d7cd8","#6ac3bf","#d88f6a"];
const state = new Map();  // chartKey -> Map(seriesKey -> {label, color, data:[], lastRaw, lastT})

for (const c of CHARTS) {
  state.set(c.key, new Map());
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `<h2>${c.title}</h2><canvas id="cv-${c.key}"></canvas><div class="legend" id="lg-${c.key}"></div>`;
  document.getElementById("grid").appendChild(card);
}

function parseLabels(s) {
  const out = {};
  for (const m of s.matchAll(/(\\w+)="([^"]*)"/g)) out[m[1]] = m[2];
  return out;
}

function scrape(text) {
  const samples = [];
  for (const line of text.split("\\n")) {
    if (!line || line.startsWith("#")) continue;
    const i = line.lastIndexOf(" ");
    if (i < 0) continue;
    samples.push([line.slice(0, i), parseFloat(line.slice(i + 1))]);
  }
  return samples;
}

function update(chart, samples, now) {
  const series = state.get(chart.key);
  for (const [name, value] of samples) {
    if (name !== chart.key && !name.startsWith(chart.key + "{")) continue;
    const labels = name.includes("{") ? name.slice(name.indexOf("{") + 1, -1) : "";
    const l = parseLabels(labels);
    const sk = Object.entries(l).map(([k, v]) => `${k}=${v}`).join(",") || "total";
    let s = series.get(sk);
    if (!s) {
      s = { label: sk, color: COLORS[series.size % COLORS.length], data: [], lastRaw: null, lastT: null };
      series.set(sk, s);
    }
    const v = value * (chart.scale || 1);
    if (chart.mode === "rate") {
      if (s.lastRaw !== null) {
        const dt = now - s.lastT;
        if (dt > 0) s.data.push(Math.max(0, (v - s.lastRaw) / dt));
      }
    } else {
      s.data.push(v);
    }
    s.lastRaw = v; s.lastT = now;
    if (s.data.length > MAX_POINTS) s.data.shift();
  }
}

function draw(chart) {
  const canvas = document.getElementById("cv-" + chart.key);
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#2a2a2a";
  ctx.beginPath();
  for (let i = 1; i < 4; i++) { ctx.moveTo(0, h * i / 4); ctx.lineTo(w, h * i / 4); }
  ctx.stroke();

  const series = [...state.get(chart.key).values()];
  let max = 0;
  for (const s of series) for (const v of s.data) if (v > max) max = v;
  if (max <= 0) max = 1;

  const legend = document.getElementById("lg-" + chart.key);
  legend.innerHTML = "";
  for (const s of series) {
    if (!s.data.length) continue;
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    const n = s.data.length;
    for (let i = 0; i < n; i++) {
      const x = i / Math.max(1, MAX_POINTS - 1) * w;
      const y = h - 4 - (s.data[i] / max) * (h - 12);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
    const latest = s.data[s.data.length - 1];
    legend.innerHTML += `<span><span class="dot" style="background:${s.color}"></span>` +
      `${s.label}: ${latest >= 100 ? latest.toFixed(0) : latest.toFixed(1)}</span>`;
  }
}

async function poll() {
  try {
    const res = await fetch("/sim/metrics", { cache: "no-store" });
    const now = performance.now() / 1000;
    const samples = scrape(await res.text());
    for (const c of CHARTS) { update(c, samples, now); draw(c); }
    document.getElementById("status").textContent = "live (samples: " + samples.length + ")";
  } catch (e) {
    document.getElementById("status").textContent = "fetch failed: " + e;
  }
}
poll();
setInterval(poll, 1000);
</script>
</body>
</html>
"""
