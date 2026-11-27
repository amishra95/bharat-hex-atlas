/* Bharat Hex Atlas: canvas hex renderer, lenses, advisors, City View and Explorer. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const DATA = {};
const FILES = ["hexes", "districts", "states", "cities", "wonders", "edges", "rivers", "meta"];

// ---------------------------------------------------------------- formatting
const fmtInt = n => n == null || isNaN(n) ? "–" : Math.round(n).toLocaleString("en-IN");
function fmtBig(n) {
  if (n == null || isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e7) return (n / 1e7).toFixed(a >= 1e9 ? 0 : 1) + " cr";
  if (a >= 1e5) return (n / 1e5).toFixed(a >= 1e6 ? 0 : 1) + " lakh";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return (Math.round(n * 10) / 10).toString();
}
const fmtRs = cr => cr == null || isNaN(cr) ? "–" : (cr >= 1e5 ? "₹" + (cr / 1e5).toFixed(cr >= 1e6 ? 1 : 2) + " lakh cr" : "₹" + fmtInt(cr) + " cr");
const fmtPct = v => v == null || isNaN(v) ? "–" : (Math.round(v * 10) / 10) + "%";
function fmtVal(v, unit) {
  if (v == null || isNaN(v)) return "–";
  if (unit === "%") return fmtPct(v);
  if (unit === "₹ crore") return fmtRs(v);
  if (unit === "₹") return "₹" + fmtInt(v);
  if (unit === "people") return fmtBig(v);
  const s = Math.abs(v) >= 100 ? fmtInt(v) : (Math.round(v * 10) / 10).toString();
  return unit && unit !== "" ? s + " " + unit : s;
}

// ---------------------------------------------------------------- palettes
const SEQ = ["#1b2f45", "#24506a", "#2c7489", "#3b9898", "#68b98f", "#a9d27e", "#efe38a"];
const HEAT = ["#25324a", "#4a3866", "#7a3b72", "#ad4567", "#d75f50", "#ee8f40", "#f6c84c"];
const DIV_GOOD = ["#b3473c", "#d27a52", "#e3b07a", "#d9d4ad", "#9cc69a", "#5ea88f", "#2f7f7d"];
const GREEN = ["#20302a", "#264a33", "#2e6a3a", "#3f8a41", "#64a84a", "#97c45a", "#cfe07a"];
const BLUE = ["#1a2738", "#1f3c5c", "#235882", "#2d76a6", "#4b97c4", "#7bb9dc", "#b9dcf0"];
const TERRAIN_COL = {
  ocean: "#1c4566", coast: "#2a6687", lake: "#3a82a8", grassland: "#5c8f3c", plains: "#98a04e",
  desert: "#e2cc93", tundra: "#9a9580", snow: "#e6ecef",
};
const FEATURE_TINT = { forest: "#2f5e2c", rainforest: "#1f4a24", marsh: "#4f6f5a", floodplain: "#88a35a" };
const STATE_COLS = ["#c9735a", "#d3a24f", "#8fae5b", "#5aa39a", "#6c8fd1", "#a07ad0", "#d07aa6", "#c4875c",
  "#7fb3c7", "#b7b45c", "#6fae7e", "#d2885c", "#8b9ad3", "#c76f7e", "#5fb2b0", "#b38fd6", "#cf9e6a", "#83b46c"];
const REL_COL = { hindu: "#f0913a", muslim: "#3f9e5a", christian: "#5c8fd6", sikh: "#e6c34a", buddhist: "#c2552f", jain: "#d9cfa3", other: "#9a8fb0", unspecified: "#556270" };
const POWER_COL = { coal: "#5b4b43", solar: "#f2c544", wind: "#9fd3e6", hydro: "#3d86c6", nuclear: "#b04fd0", gas_oil: "#e27a3f", bio_waste: "#7fb05b", unknown: "#8a8f96" };
const SECTION_COL = { A: "#7fb05b", B: "#8a6d4c", C: "#d0864a", D: "#e6c04d", E: "#5fb0a5", F: "#c9735a", G: "#d3a24f", H: "#8b9ad3",
  I: "#d07aa6", J: "#5aa7e0", K: "#e6c04d", L: "#b7b45c", M: "#6c8fd1", N: "#9a8fb0", O: "#c76f7e", P: "#a07ad0", Q: "#5fb2b0", R: "#cf9e6a", S: "#8a8f96", T: "#556270" };

function lerpHex(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const r = (pa >> 16) + ((pb >> 16) - (pa >> 16)) * t, g = ((pa >> 8) & 255) + (((pb >> 8) & 255) - ((pa >> 8) & 255)) * t,
    bl = (pa & 255) + ((pb & 255) - (pa & 255)) * t;
  return `rgb(${r | 0},${g | 0},${bl | 0})`;
}

// ---------------------------------------------------------------- state
const view = { cx: 0, cy: 0, scale: 0.35, w: 0, h: 0, dpr: 1 };
let lens = null, selected = null, hover = -1, selDistrict = -1;
let N = 0, HX, D, DCOL, LENSES = [], lensVals = null, lensBreaks = null;
const canvas = $("#map"), ctx = canvas.getContext("2d");
const R = 14.4337; // hex circumradius in km (25 km across flats)
const CORNERS = [...Array(6)].map((_, i) => { const a = Math.PI / 180 * (60 * i - 30); return [Math.cos(a), Math.sin(a)]; });

async function load() {
  const res = await Promise.all(FILES.map(f => fetch(`data/${f}.json`).then(r => { if (!r.ok) throw new Error(f); return r.json(); })));
  FILES.forEach((f, i) => DATA[f] = res[i]);
  HX = DATA.hexes; N = HX.q.length;
  D = DATA.districts;
  DCOL = Object.fromEntries(D.cols.map((c, i) => [c, i]));
  D.byDix = new Map(D.rows.map(r => [r[0], r]));
  HX.key = new Map(); for (let i = 0; i < N; i++) HX.key.set(HX.q[i] + "," + HX.r[i], i);
  HX.distHexes = new Map(); for (let i = 0; i < N; i++) { const d = HX.d[i]; if (d >= 0) { if (!HX.distHexes.has(d)) HX.distHexes.set(d, []); HX.distHexes.get(d).push(i); } }
  DATA.cityByHex = new Map(); DATA.cities.forEach((c, ix) => { c.ix = ix; });
  buildBorders();
  buildLenses();
  buildYieldsBar();
  buildAdvisors();
  buildSearch();
  if (window.innerWidth < 820) $("#legend").classList.add("collapsed");
  setLens("terrain");
  resize();
  home();
  $("#loading").remove();
}

function dget(dix, col) { const r = D.byDix.get(dix); return r ? r[DCOL[col]] : null; }

// ---------------------------------------------------------------- borders (state, district, coast)
let BORDERS = { state: [], district: [], coast: [] };
const NB = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
// edge k of pointy-top hex lies between corners k and k+1; map neighbour direction to edge index
const DIR_EDGE = [0, 5, 4, 3, 2, 1];
function buildBorders() {
  for (let i = 0; i < N; i++) {
    const ki = HX.kind[i];
    if (ki !== 0 && ki !== 3) continue;
    for (let n = 0; n < 6; n++) {
      const j = HX.key.get((HX.q[i] + NB[n][0]) + "," + (HX.r[i] + NB[n][1]));
      const e = DIR_EDGE[n];
      if (j === undefined) continue;
      const kj = HX.kind[j];
      if (kj === 2) { BORDERS.coast.push([i, e]); continue; }
      if (kj === 1) { BORDERS.state.push([i, e, 1]); continue; }
      if (j < i && (kj === 0 || kj === 3)) continue;
      if (HX.s[i] !== HX.s[j]) BORDERS.state.push([i, e, 0]);
      else if (HX.d[i] !== HX.d[j]) BORDERS.district.push([i, e]);
    }
  }
}

// ---------------------------------------------------------------- lenses
function quantileBreaks(vals, k = 7) {
  const v = vals.filter(x => x != null && !isNaN(x)).sort((a, b) => a - b);
  if (!v.length) return [];
  const out = [];
  for (let i = 1; i < k; i++) out.push(v[Math.min(v.length - 1, Math.floor(v.length * i / k))]);
  return out;
}
function classify(v, br) { let c = 0; while (c < br.length && v > br[c]) c++; return c; }

function districtLens(id, col, pal, opts = {}) {
  const m = D.meta[col];
  return {
    id, name: opts.name || m.label, group: opts.group || m.group, pal: opts.pal || pal,
    src: m.source, unit: m.unit, better: m.better, scope: "district", col,
    value: i => { const d = HX.d[i]; if (d < 0) return null; return dget(d, col); },
    note: opts.note,
  };
}

function buildLenses() {
  const sum = (a, b) => (a || 0) + (b || 0);
  LENSES = [
    { id: "terrain", name: "Terrain & yields", group: "Map", special: "terrain", src: "ESA WorldCover 2021 · elevation tiles · WorldClim" },
    { id: "political", name: "States", group: "Map", special: "political", src: "geoBoundaries / LGD" },
    { id: "pop", name: "Population density", group: "People", pal: HEAT, unit: "/km²", src: "GHS-POP 2025 (JRC)", scope: "hex",
      value: i => HX.pop[i] == null ? null : HX.pop[i] / HX.area_km2, log: true },
    { id: "urban", name: "Built-up land", group: "People", pal: HEAT, unit: "km²", src: "GHSL built-up surface 2025", scope: "hex",
      value: i => HX.built[i], log: true },
    districtLens("women_10yr", "women_10yr", DIV_GOOD, { name: "Schooling: women 10+ years", group: "Society · NFHS-6" }),
    districtLens("women_internet", "women_internet", DIV_GOOD, { name: "Internet: women ever online", group: "Society · NFHS-6" }),
    districtLens("stunted", "stunted", DIV_GOOD.slice().reverse(), { name: "Child stunting", group: "Society · NFHS-6" }),
    districtLens("insurance", "insurance", DIV_GOOD, { name: "Health insurance", group: "Society · NFHS-6" }),
    districtLens("child_marriage", "child_marriage", DIV_GOOD.slice().reverse(), { name: "Married before 18", group: "Society · NFHS-6" }),
    { id: "food", name: "Food", group: "Yields", pal: GREEN, src: "Cropland & grassland, ESA WorldCover 2021", scope: "hex", value: i => HX.kind[i] === 0 ? HX.yf[i] : null, pips: true },
    { id: "prod", name: "Production", group: "Yields", pal: HEAT, src: "Industry, mines, power (OSM 2026)", scope: "hex", value: i => HX.kind[i] === 0 ? HX.yp[i] : null, pips: true },
    { id: "gold", name: "Gold (GDP)", group: "Yields", pal: ["#2b2a20", "#4a4224", "#6e5f29", "#96812e", "#bea237", "#e0c249", "#f6e07a"], unit: "₹ crore", src: "GSDP 2024-25, split by population + non-residential built-up", scope: "hex", value: i => HX.gdp[i], log: true },
    { id: "gdppc", ...districtLens("gdppc", "gdp_pc", DIV_GOOD, { name: "Income: GDP per person", group: "Economy" }) },
    { id: "science", name: "Science", group: "Yields", pal: BLUE, src: "Universities, colleges, research (OSM)", scope: "hex", value: i => HX.kind[i] === 0 ? HX.ys[i] : null, pips: true },
    { id: "culture", name: "Culture", group: "Yields", pal: ["#24203a", "#3b2d5a", "#55397a", "#73459a", "#9655b6", "#ba6fcf", "#ddb0ea"], src: "World Heritage, monuments, museums", scope: "hex", value: i => HX.kind[i] === 0 ? HX.yc[i] : null, pips: true },
    { id: "faith", name: "Faith", group: "Yields", special: "faith", src: "Places of worship mapped in OSM", scope: "hex" },
    { id: "workforce", ...districtLens("workforce", "agri_share_state", SEQ, { name: "Workers in farming (state)", group: "Economy" }) },
    { id: "power", name: "Power", group: "Infrastructure", special: "power", src: "Power plants mapped in OSM", scope: "hex" },
    { id: "transport", name: "Rail & roads", group: "Infrastructure", pal: SEQ, unit: "km", src: "OSM rail + motorway/trunk/primary", scope: "hex",
      value: i => HX.kind[i] === 0 ? sum(HX.rail[i], HX.road[i]) : null, log: true, overlay: "edges" },
    { id: "forest", name: "Forest cover", group: "Environment", pal: GREEN, unit: "%", src: "ESA WorldCover 2021 tree cover", scope: "hex", value: i => HX.kind[i] === 2 ? null : HX.tree[i] },
    { id: "elev", name: "Elevation", group: "Environment", pal: ["#2d5a3d", "#5f8a49", "#a9a35c", "#c69a5a", "#a8735a", "#8f8a8f", "#eef1f3"], unit: "m", src: "AWS Terrain Tiles", scope: "hex", value: i => HX.kind[i] === 2 ? null : HX.elev[i] },
    { id: "rain", name: "Monsoon rainfall", group: "Environment", pal: BLUE, unit: "mm/yr", src: "WorldClim 2.1 normals", scope: "hex", value: i => HX.kind[i] === 2 ? null : HX.rain[i], log: true },
    { id: "disasters", name: "Disasters", group: "Environment", pal: HEAT, src: "IBTrACS cyclones (≥34 kt) + USGS quakes M4.5+, since 1990", scope: "hex",
      value: i => HX.kind[i] === 2 ? null : ((HX.cyc[i] || 0) * 2 + (HX.scyc[i] || 0) * 3 + Math.sqrt(HX.eqn[i] || 0) * 2) || null, unit: "risk pts" },
  ];
  for (const L of LENSES) {
    if (L.special || !L.value) continue;
  }
  const ORDER = ["Map", "Yields", "People", "Society · NFHS-6", "Economy", "Infrastructure", "Environment"];
  const groups = Object.fromEntries(ORDER.map(g => [g, []]));
  LENSES.forEach(L => (groups[L.group] ||= []).push(L));
  const host = $("#lens-list");
  host.innerHTML = Object.entries(groups).map(([g, ls]) => `<div class="lens-group"><h4>${esc(g)}</h4>` +
    ls.map(L => `<button class="lens-btn" data-lens="${L.id}" aria-pressed="false"><span class="sw" style="background:${swatch(L)}"></span>${esc(L.name)}</button>`).join("") + "</div>").join("");
  host.addEventListener("click", e => { const b = e.target.closest(".lens-btn"); if (b) setLens(b.dataset.lens); });
}
function swatch(L) {
  if (L.special === "terrain") return `linear-gradient(135deg, ${TERRAIN_COL.grassland}, ${TERRAIN_COL.desert})`;
  if (L.special === "political") return `linear-gradient(135deg, ${STATE_COLS[0]}, ${STATE_COLS[4]})`;
  if (L.special === "faith") return `linear-gradient(135deg, ${REL_COL.hindu}, ${REL_COL.muslim})`;
  if (L.special === "power") return `linear-gradient(135deg, ${POWER_COL.coal}, ${POWER_COL.solar})`;
  const p = L.pal || SEQ; return `linear-gradient(135deg, ${p[1]}, ${p[p.length - 1]})`;
}

function setLens(id) {
  lens = LENSES.find(l => l.id === id) || LENSES[0];
  $$(".lens-btn").forEach(b => b.setAttribute("aria-pressed", b.dataset.lens === lens.id));
  lensVals = null; lensBreaks = null;
  if (lens.value) {
    lensVals = new Float64Array(N).fill(NaN);
    for (let i = 0; i < N; i++) { if (HX.kind[i] !== 0) continue; const v = lens.value(i); if (v != null && !isNaN(v)) lensVals[i] = v; }
    if (lens.pips) lensBreaks = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5];
    else if (lens.scope === "district") {
      const vals = D.rows.map(r => r[DCOL[lens.col]]).filter(v => v != null);
      lensBreaks = quantileBreaks(vals);
    } else {
      const vals = []; for (let i = 0; i < N; i++) if (!isNaN(lensVals[i]) && (!lens.log || lensVals[i] > 0)) vals.push(lensVals[i]);
      lensBreaks = quantileBreaks(vals);
    }
  }
  renderLegend();
  draw();
}

function lensColor(i) {
  const k = HX.kind[i];
  if (k === 2) return HX.t[i] === 0 ? TERRAIN_COL.ocean : TERRAIN_COL.coast;
  if (k === 1) return "#3a4148";
  if (k === 3) return "#4b4f55";
  if (lens.special === "terrain") return terrainColor(i);
  if (lens.special === "political") return HX.s[i] >= 0 ? STATE_COLS[HX.s[i] % STATE_COLS.length] : "#555";
  if (lens.special === "faith") {
    const r = HX.rel[i]; if (!r) return "#28323c";
    const tot = Object.values(r).reduce((a, b) => a + b, 0);
    const top = Object.entries(r).filter(([k]) => k !== "unspecified" && k !== "other").sort((a, b) => b[1] - a[1])[0];
    const base = top ? REL_COL[top[0]] : REL_COL.unspecified;
    const t = Math.min(1, Math.log10(1 + tot) / 2.6);
    return lerpHex("#1e2730", base.startsWith("#") ? base : "#888888", 0.25 + 0.75 * t);
  }
  if (lens.special === "power") {
    if (!HX.pmw[i] && !HX.pn[i]) return "#24303a";
    const c = POWER_COL[HX.psrc[i]] || POWER_COL.unknown;
    const t = Math.min(1, Math.log10(1 + (HX.pmw[i] || 5)) / 3.5);
    return lerpHex("#24303a", c, 0.35 + 0.65 * t);
  }
  const v = lensVals[i];
  if (isNaN(v)) return "#262d34";
  if (lens.log && v <= 0) return lens.pal[0];
  return lens.pal[classify(v, lensBreaks)];
}
function terrainColor(i) {
  const t = DATA.meta.meta.terrain[HX.t[i]], f = DATA.meta.meta.features[HX.f[i]];
  let c = TERRAIN_COL[t] || "#777";
  if (FEATURE_TINT[f]) c = lerpHex(c, FEATURE_TINT[f], f === "floodplain" ? 0.45 : 0.62);
  if (f === "mountains") c = lerpHex(c, "#8c8374", 0.55);
  if (f === "hills") c = lerpHex(c, "#7d6f52", 0.18);
  return c;
}

function renderLegend() {
  const L = lens, el = $("#legend");
  let body = "";
  if (L.special === "terrain") {
    const items = [["Grassland", TERRAIN_COL.grassland], ["Plains", TERRAIN_COL.plains], ["Desert", TERRAIN_COL.desert], ["Cold desert", TERRAIN_COL.tundra],
      ["Snow & ice", TERRAIN_COL.snow], ["Forest", lerpHex(TERRAIN_COL.grassland, FEATURE_TINT.forest, .62)], ["Rainforest", lerpHex(TERRAIN_COL.grassland, FEATURE_TINT.rainforest, .62)],
      ["Mangrove & marsh", lerpHex(TERRAIN_COL.grassland, FEATURE_TINT.marsh, .62)], ["Mountains", lerpHex(TERRAIN_COL.plains, "#8c8374", .55)], ["Floodplain", lerpHex(TERRAIN_COL.plains, FEATURE_TINT.floodplain, .45)]];
    body = `<div class="cats">${items.map(([n, c]) => `<div><i style="background:${c}"></i>${n}</div>`).join("")}</div><div class="src">Zoom in to see yield pips, resources and roads.</div>`;
  } else if (L.special === "political") {
    body = `<div class="src">${DATA.states.names.length} states and union territories, ${fmtInt(D.rows.filter(r => r[3] !== "none" || true).length)} districts.</div>`;
  } else if (L.special === "faith") {
    body = `<div class="cats">${Object.entries(REL_COL).slice(0, 7).map(([k, c]) => `<div><i style="background:${c}"></i>${k[0].toUpperCase() + k.slice(1)}</div>`).join("")}</div>
      <div class="src">Hue = most-mapped tradition, brightness = number of places of worship mapped. OSM coverage is uneven.</div>`;
  } else if (L.special === "power") {
    body = `<div class="cats">${Object.entries(POWER_COL).map(([k, c]) => `<div><i style="background:${c}"></i>${k.replace("_", " / ")}</div>`).join("")}</div><div class="src">Largest source by mapped capacity in each hex.</div>`;
  } else {
    const br = lensBreaks || [];
    const ticks = L.pips ? ["1", "2", "3", "4", "5", "6"] : [br[0], br[Math.floor(br.length / 2)], br[br.length - 1]].map(v => fmtVal(v, L.unit));
    body = `<div class="ramp">${L.pal.map(c => `<span style="background:${c}"></span>`).join("")}</div>
      <div class="ticks">${ticks.map(t => `<span>${esc(t)}</span>`).join("")}</div>`;
    if (L.better) body += `<div class="src">${L.better === "high" ? "Higher is better" : "Lower is better"}${L.scope === "district" ? " · coloured by district" : ""}</div>`;
    else if (L.scope === "district") body += `<div class="src">Coloured by district</div>`;
    if (L.pips) body += `<div class="src">Pips 1–6 are sextiles of the real quantity across India's tiles.</div>`;
  }
  el.innerHTML = `<h3 tabindex="0" role="button" aria-label="${esc(L.name)} legend, toggle">${esc(L.name)}</h3><div class="src">${esc(L.src || "")}</div>${body}`;
  const h = el.querySelector("h3");
  h.onclick = () => el.classList.toggle("collapsed");
  h.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.classList.toggle("collapsed"); } };
}

// ---------------------------------------------------------------- drawing
function toScreen(x, y) { return [(x - view.cx) * view.scale + view.w / 2, (view.cy - y) * view.scale + view.h / 2]; }
function toWorld(sx, sy) { return [(sx - view.w / 2) / view.scale + view.cx, view.cy - (sy - view.h / 2) / view.scale]; }

function resize() {
  const r = canvas.getBoundingClientRect();
  view.dpr = Math.min(2, window.devicePixelRatio || 1);
  view.w = r.width; view.h = r.height;
  canvas.width = r.width * view.dpr; canvas.height = r.height * view.dpr;
  draw();
}
function home() {
  let minx = 1e9, maxx = -1e9, miny = 1e9, maxy = -1e9;
  for (let i = 0; i < N; i++) if (HX.kind[i] === 0) { minx = Math.min(minx, HX.x[i]); maxx = Math.max(maxx, HX.x[i]); miny = Math.min(miny, HX.y[i]); maxy = Math.max(maxy, HX.y[i]); }
  view.cx = (minx + maxx) / 2; view.cy = (miny + maxy) / 2;
  view.scale = Math.min(view.w / (maxx - minx + 60), view.h / (maxy - miny + 60));
  draw();
}

let raf = 0;
function draw() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); }); }

function hexPath(sx, sy, rad) {
  ctx.moveTo(sx + CORNERS[0][0] * rad, sy - CORNERS[0][1] * rad);
  for (let k = 1; k < 6; k++) ctx.lineTo(sx + CORNERS[k][0] * rad, sy - CORNERS[k][1] * rad);
  ctx.closePath();
}

function render() {
  if (!HX) return;
  const { dpr, w, h, scale } = view;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#123049"; ctx.fillRect(0, 0, w, h);
  const rad = R * scale + 0.35;
  const pad = rad * 2;
  const vis = [];
  for (let i = 0; i < N; i++) {
    const [sx, sy] = toScreen(HX.x[i], HX.y[i]);
    if (sx < -pad || sy < -pad || sx > w + pad || sy > h + pad) continue;
    vis.push(i);
    ctx.beginPath(); hexPath(sx, sy, rad);
    ctx.fillStyle = lensColor(i); ctx.fill();
  }
  // grid lines when zoomed in
  if (scale > 1.4) {
    ctx.strokeStyle = "rgba(0,0,0,.16)"; ctx.lineWidth = 1; ctx.beginPath();
    for (const i of vis) { if (HX.kind[i] === 2) continue; const [sx, sy] = toScreen(HX.x[i], HX.y[i]); hexPath(sx, sy, R * scale); }
    ctx.stroke();
  }
  // claimed territory hatching
  ctx.save(); ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 1;
  for (const i of vis) if (HX.kind[i] === 3) { const [sx, sy] = toScreen(HX.x[i], HX.y[i]); ctx.beginPath(); ctx.moveTo(sx - rad, sy + rad * .5); ctx.lineTo(sx + rad * .5, sy - rad); ctx.stroke(); }
  ctx.restore();

  if (lens.special === "terrain") drawTerrainDetail(vis);
  drawRivers();
  if (lens.overlay === "edges" || (lens.special === "terrain" && scale > 1.1)) drawEdges();
  drawBorders();
  if (selDistrict >= 0) drawDistrictOutline(selDistrict);
  if (lens.special === "terrain" && scale > 2.4) drawYields(vis);
  if (lens.special === "terrain" && scale > 1.6) drawResources(vis);
  drawWonders();
  drawCities();
  if (hover >= 0) { const [sx, sy] = toScreen(HX.x[hover], HX.y[hover]); ctx.beginPath(); hexPath(sx, sy, R * scale); ctx.strokeStyle = "rgba(255,240,200,.85)"; ctx.lineWidth = 2; ctx.stroke(); }
  if (selected && selected.type === "hex") { const i = selected.i; const [sx, sy] = toScreen(HX.x[i], HX.y[i]); ctx.beginPath(); hexPath(sx, sy, R * scale); ctx.strokeStyle = "#f0cf7e"; ctx.lineWidth = 3; ctx.stroke(); }
}

function edgeLine(i, e) {
  const [sx, sy] = toScreen(HX.x[i], HX.y[i]); const rad = R * view.scale;
  const a = CORNERS[e], b = CORNERS[(e + 1) % 6];
  ctx.moveTo(sx + a[0] * rad, sy - a[1] * rad); ctx.lineTo(sx + b[0] * rad, sy - b[1] * rad);
}
function drawBorders() {
  const s = view.scale;
  if (s > 0.9) {
    ctx.beginPath(); for (const [i, e] of BORDERS.district) edgeLine(i, e);
    ctx.strokeStyle = "rgba(255,255,255,.16)"; ctx.lineWidth = 1; ctx.stroke();
  }
  ctx.beginPath(); for (const [i, e] of BORDERS.coast) edgeLine(i, e);
  ctx.strokeStyle = "rgba(225,214,170,.55)"; ctx.lineWidth = 1.2; ctx.stroke();
  ctx.beginPath(); for (const [i, e, ext] of BORDERS.state) if (!ext) edgeLine(i, e);
  ctx.strokeStyle = lens.special === "political" ? "rgba(20,20,20,.75)" : "rgba(255,236,190,.55)"; ctx.lineWidth = s > 1 ? 2 : 1.3; ctx.stroke();
  ctx.beginPath(); for (const [i, e, ext] of BORDERS.state) if (ext) edgeLine(i, e);
  ctx.strokeStyle = "#e0b24a"; ctx.lineWidth = s > 1 ? 3 : 2; ctx.stroke();
}
function drawDistrictOutline(dix) {
  const hs = HX.distHexes.get(dix) || [];
  const set = new Set(hs);
  ctx.beginPath();
  for (const i of hs) for (let n = 0; n < 6; n++) {
    const j = HX.key.get((HX.q[i] + NB[n][0]) + "," + (HX.r[i] + NB[n][1]));
    if (j === undefined || !set.has(j)) edgeLine(i, DIR_EDGE[n]);
  }
  ctx.strokeStyle = "#f6e07a"; ctx.lineWidth = 2.5; ctx.setLineDash([6, 4]); ctx.stroke(); ctx.setLineDash([]);
}
function drawRivers() {
  const s = view.scale;
  const minKm = s < 0.5 ? 900 : s < 1 ? 500 : s < 2 ? 250 : 150;
  ctx.strokeStyle = "rgba(110,175,220,.85)"; ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const rv of DATA.rivers) {
    if (rv.km < minKm) continue;
    ctx.lineWidth = Math.max(0.8, Math.min(3, (rv.km / 1200) * s * 1.6));
    ctx.beginPath();
    for (const line of rv.lines) { line.forEach((p, k) => { const [sx, sy] = toScreen(p[0], p[1]); k ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); }); }
    ctx.stroke();
  }
}
function drawEdges() {
  const s = view.scale;
  ctx.lineCap = "round";
  ctx.beginPath();
  for (const [a, b] of DATA.edges.rail) { const [x1, y1] = toScreen(HX.x[a], HX.y[a]), [x2, y2] = toScreen(HX.x[b], HX.y[b]); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); }
  ctx.strokeStyle = "rgba(30,24,20,.8)"; ctx.lineWidth = Math.max(1, s * 1.2); ctx.stroke();
  if (s > 1.2) { ctx.setLineDash([3, 3]); ctx.strokeStyle = "rgba(230,220,200,.7)"; ctx.lineWidth = Math.max(.6, s * .5); ctx.stroke(); ctx.setLineDash([]); }
  for (const lvl of [1, 2, 3]) {
    if (lvl === 1 && s < 1) continue;
    ctx.beginPath();
    for (const [a, b, l] of DATA.edges.road) { if (l !== lvl) continue; const [x1, y1] = toScreen(HX.x[a], HX.y[a]), [x2, y2] = toScreen(HX.x[b], HX.y[b]); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); }
    ctx.strokeStyle = lvl === 3 ? "rgba(246,200,90,.95)" : lvl === 2 ? "rgba(214,160,90,.85)" : "rgba(190,150,110,.6)";
    ctx.lineWidth = Math.max(.7, s * (lvl === 3 ? 1.1 : lvl === 2 ? .8 : .5)); ctx.stroke();
  }
}
function drawTerrainDetail(vis) {
  const s = view.scale; if (s < 0.75) return;
  const rad = R * s;
  for (const i of vis) {
    if (HX.kind[i] === 2) continue;
    const f = HX.f[i];
    const [sx, sy] = toScreen(HX.x[i], HX.y[i]);
    const fade = HX.kind[i] === 1 ? 0.35 : 1;
    if (f === 2) { // mountains
      ctx.fillStyle = `rgba(70,62,55,${.9 * fade})`; ctx.beginPath();
      ctx.moveTo(sx - rad * .62, sy + rad * .38); ctx.lineTo(sx - rad * .12, sy - rad * .5); ctx.lineTo(sx + rad * .2, sy + rad * .05); ctx.lineTo(sx + rad * .38, sy - rad * .28); ctx.lineTo(sx + rad * .66, sy + rad * .38); ctx.closePath(); ctx.fill();
      if ((HX.elev[i] || 0) > 3500) { ctx.fillStyle = `rgba(245,248,250,${.9 * fade})`; ctx.beginPath(); ctx.moveTo(sx - rad * .28, sy - rad * .15); ctx.lineTo(sx - rad * .12, sy - rad * .5); ctx.lineTo(sx + rad * .02, sy - rad * .2); ctx.closePath(); ctx.fill(); }
    } else if (f === 1) { // hills
      ctx.strokeStyle = `rgba(60,50,35,${.55 * fade})`; ctx.lineWidth = Math.max(1, s * .9);
      ctx.beginPath(); ctx.arc(sx - rad * .22, sy + rad * .2, rad * .3, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke();
      ctx.beginPath(); ctx.arc(sx + rad * .25, sy + rad * .28, rad * .24, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke();
    } else if (f === 3 || f === 4) { // forest / rainforest
      const n = f === 4 ? 5 : 3;
      ctx.fillStyle = f === 4 ? `rgba(14,48,22,${.85 * fade})` : `rgba(24,62,30,${.8 * fade})`;
      for (let k = 0; k < n; k++) {
        const a = k * 2.4 + i, ox = Math.cos(a) * rad * .38, oy = Math.sin(a) * rad * .3;
        ctx.beginPath(); ctx.moveTo(sx + ox, sy + oy - rad * .3); ctx.lineTo(sx + ox - rad * .16, sy + oy + rad * .12); ctx.lineTo(sx + ox + rad * .16, sy + oy + rad * .12); ctx.closePath(); ctx.fill();
      }
    } else if (f === 5) { // marsh / mangrove
      ctx.strokeStyle = `rgba(30,70,60,${.8 * fade})`; ctx.lineWidth = Math.max(1, s * .8);
      for (let k = -1; k <= 1; k++) { ctx.beginPath(); ctx.moveTo(sx - rad * .45, sy + k * rad * .25); ctx.lineTo(sx + rad * .45, sy + k * rad * .25); ctx.stroke(); }
    } else if (f === 6 && s > 1.3) { // floodplain
      ctx.strokeStyle = "rgba(70,110,140,.45)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(sx - rad * .5, sy + rad * .35); ctx.quadraticCurveTo(sx, sy - rad * .1, sx + rad * .5, sy + rad * .35); ctx.stroke();
    }
    if (HX.kind[i] === 0 && s > 1.1 && HX.built[i] > 25) { // urban sprawl
      const n = Math.min(9, Math.round(HX.built[i] / 25));
      ctx.fillStyle = "rgba(225,215,195,.7)";
      for (let k = 0; k < n; k++) { const a = k * 2.1 + i * .7, rr = rad * (.15 + .45 * ((k * 37) % 10) / 10); ctx.fillRect(sx + Math.cos(a) * rr - s * 1.2, sy + Math.sin(a) * rr - s * 1.2, s * 2.4, s * 2.4); }
    }
  }
}
const YCOL = ["#8fc152", "#d0864a", "#e6c04d", "#5aa7e0", "#c27adf", "#e8e3d0"];
function drawYields(vis) {
  // the tile's three strongest yields as numbered badges along its lower edge
  const s = view.scale, rr = Math.max(5, Math.min(9, s * 2.2));
  ctx.font = `700 ${Math.round(rr * 1.15)}px Inter, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const i of vis) {
    if (HX.kind[i] !== 0) continue;
    const ys = [HX.yf[i], HX.yp[i], HX.yg[i], HX.ys[i], HX.yc[i], HX.yr[i]].map((v, k) => [v, k]).filter(([v]) => v > 0)
      .sort((a, b) => b[0] - a[0]).slice(0, 3);
    const [sx, sy] = toScreen(HX.x[i], HX.y[i]);
    const y0 = sy + R * s * .5;
    ys.forEach(([v, k], p) => {
      const x = sx + (p - (ys.length - 1) / 2) * rr * 2.3;
      ctx.beginPath(); ctx.arc(x, y0, rr, 0, 7); ctx.fillStyle = YCOL[k]; ctx.fill();
      ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.45)"; ctx.stroke();
      ctx.fillStyle = k === 5 || k === 2 || k === 0 ? "#1a1a1a" : "#fff"; ctx.fillText(v, x, y0 + .5);
    });
  }
}
const RES_ABBR = { coal: ["Co", "#2c2622"], iron: ["Fe", "#7a5a4c"], bauxite: ["Al", "#b5704f"], limestone: ["Ls", "#d8d3c4"], copper: ["Cu", "#c47a43"],
  gold: ["Au", "#e6c04d"], diamonds: ["Di", "#cfe9f5"], manganese: ["Mn", "#8b6b8a"], chromite: ["Cr", "#5e7d6e"], zinc: ["Zn", "#9aa7b2"], mica: ["Mi", "#c9c2a8"],
  uranium: ["U", "#8fd35b"], marble: ["Mb", "#eee"], stone: ["St", "#a7a29a"], salt: ["Sa", "#f3f3f3"], sand: ["Sd", "#d9c38c"], oil: ["Oil", "#222"],
  tea: ["Tea", "#4f8a3a"], coffee: ["Cf", "#6b4a2e"], rubber: ["Rb", "#3b5d3b"], coconut: ["Cn", "#7a9a3a"], cashew: ["Cs", "#c99a50"], mango: ["Mg", "#e8a23a"],
  banana: ["Bn", "#e6d24a"], apples: ["Ap", "#c9443b"], "oil palm": ["Op", "#5d7d2a"], areca: ["Ar", "#8a7d3a"], spices: ["Sp", "#a3452c"], citrus: ["Ci", "#f0a030"],
  grapes: ["Gr", "#7b3f8a"], sugarcane: ["Sc", "#9cc65a"], cotton: ["Ct", "#f2f2ea"], rice: ["Ri", "#d7cf8a"], saffron: ["Sf", "#e05a2a"], pomegranate: ["Pg", "#b8323a"] };
function drawResources(vis) {
  const s = view.scale, rr = Math.max(5, s * 3.2);
  ctx.font = `600 ${Math.max(7, rr * .8)}px Inter, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const i of vis) {
    if (HX.kind[i] !== 0 || !HX.res[i]) continue;
    const r0 = HX.res[i].split(",")[0]; const [ab, col] = RES_ABBR[r0] || [r0.slice(0, 2), "#888"];
    const [sx, sy] = toScreen(HX.x[i], HX.y[i]);
    const x = sx + R * s * .42, y = sy - R * s * .42;
    ctx.beginPath(); ctx.arc(x, y, rr, 0, 7); ctx.fillStyle = col; ctx.fill(); ctx.lineWidth = 1.2; ctx.strokeStyle = "#f0cf7e"; ctx.stroke();
    ctx.fillStyle = ["#222", "#2c2622", "#6b4a2e", "#3b5d3b", "#4f8a3a", "#7b3f8a", "#5d7d2a", "#7a5a4c", "#a3452c", "#b8323a", "#c9443b"].includes(col) ? "#fff" : "#111";
    ctx.fillText(ab, x, y + .5);
  }
}
let cityRects = [];
function drawCities() {
  const s = view.scale;
  const minPop = s < 0.35 ? 8e6 : s < 0.5 ? 3e6 : s < 0.8 ? 1.2e6 : s < 1.3 ? 5e5 : s < 2.2 ? 2e5 : s < 3.5 ? 1e5 : 0;
  cityRects = [];
  const placed = [];
  ctx.textBaseline = "middle";
  for (const c of DATA.cities) {
    if (c.pop < minPop) break;
    const [sx, sy] = toScreen(c.xy[0], c.xy[1]);
    if (sx < -100 || sy < -40 || sx > view.w + 100 || sy > view.h + 40) continue;
    if (c.belt && s < 1.3) continue; // dense rural belts only labelled once zoomed in
    const big = c.pop >= 5e6 && !c.belt;
    const fs = big ? 13 : c.pop >= 1e6 && !c.belt ? 12 : 11;
    ctx.font = `${big ? 700 : 600} ${fs}px Inter, sans-serif`;
    const label = c.name, popl = fmtBig(c.pop);
    const tw = ctx.measureText(label).width; ctx.font = `500 ${fs - 2}px Inter, sans-serif`; const pw = ctx.measureText(popl).width;
    const bw = tw + pw + 22, bh = fs + 9, bx = sx - bw / 2, by = sy - bh - 6;
    if (placed.some(r => bx < r[0] + r[2] && bx + bw > r[0] && by < r[1] + r[3] && by + bh > r[1])) continue;
    placed.push([bx, by, bw, bh]);
    ctx.beginPath(); ctx.arc(sx, sy, big ? 4.5 : 3.5, 0, 7); ctx.fillStyle = c.capital ? "#f0cf7e" : "#fff"; ctx.fill(); ctx.strokeStyle = "#111"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = selected && selected.type === "city" && selected.c === c ? "rgba(70,55,20,.97)" : "rgba(16,26,36,.92)";
    roundRect(bx, by, bw, bh, 5); ctx.fill();
    ctx.strokeStyle = c.capital ? "#d6a84a" : "rgba(214,168,74,.45)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = c.belt ? "#c9bfa5" : "#f2e6c4"; ctx.font = `${c.belt ? "italic 500" : big ? 700 : 600} ${fs}px Inter, sans-serif`; ctx.textAlign = "left"; ctx.fillText(label, bx + 7, by + bh / 2 + .5);
    ctx.fillStyle = "#9fb1bf"; ctx.font = `500 ${fs - 2}px Inter, sans-serif`; ctx.fillText(popl, bx + 15 + tw, by + bh / 2 + .5);
    cityRects.push([bx, by, bw, bh, c]);
  }
}
function roundRect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
let wonderPts = [];
function drawWonders() {
  const s = view.scale; wonderPts = [];
  if (s < 0.55) return;
  const all = [...DATA.wonders.heritage.map(w => [w, "#f0cf7e"]), ...(s > 1 ? DATA.wonders.parks.filter(p => (p.area_km2 || 0) > (s > 2 ? 0 : 800)).map(w => [w, "#8fd18a"]) : []), ...DATA.wonders.peaks.map(w => [w, "#e9eef2"])];
  for (const [w, col] of all) {
    const [sx, sy] = toScreen(w.xy[0], w.xy[1]);
    if (sx < -20 || sy < -20 || sx > view.w + 20 || sy > view.h + 20) continue;
    const r = Math.max(5, Math.min(9, s * 3.2));
    star(sx, sy, r, col);
    wonderPts.push([sx, sy, r + 3, w]);
    if (s > 2.2) { ctx.font = "600 11px Inter, sans-serif"; ctx.textAlign = "center"; ctx.fillStyle = "rgba(10,14,18,.75)"; const tw = ctx.measureText(w.name).width; ctx.fillRect(sx - tw / 2 - 4, sy + r + 2, tw + 8, 15); ctx.fillStyle = col; ctx.fillText(w.name, sx, sy + r + 10); }
  }
}
function star(x, y, r, col) {
  ctx.beginPath();
  for (let k = 0; k < 10; k++) { const a = -Math.PI / 2 + k * Math.PI / 5, rr = k % 2 ? r * .45 : r; ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
  ctx.closePath(); ctx.fillStyle = col; ctx.fill(); ctx.strokeStyle = "rgba(20,15,5,.9)"; ctx.lineWidth = 1.2; ctx.stroke();
}

// ---------------------------------------------------------------- picking
function pickHex(sx, sy) {
  const [x, y] = toWorld(sx, sy);
  const q = (Math.sqrt(3) / 3 * x - y / 3) / R, r = (2 / 3 * y) / R;
  let rq = Math.round(q), rr = Math.round(r), rs = Math.round(-q - r);
  const dq = Math.abs(rq - q), dr = Math.abs(rr - r), ds = Math.abs(rs + q + r);
  if (dq > dr && dq > ds) rq = -rr - rs; else if (dr > ds) rr = -rq - rs;
  const i = HX.key.get(rq + "," + rr);
  return i === undefined ? -1 : i;
}
function pickCity(sx, sy) { for (const [x, y, w, h, c] of cityRects) if (sx >= x && sx <= x + w && sy >= y && sy <= y + h) return c; return null; }
function pickWonder(sx, sy) { for (const [x, y, r, w] of wonderPts) if ((sx - x) ** 2 + (sy - y) ** 2 < r * r) return w; return null; }

// ---------------------------------------------------------------- interaction
let drag = null; const pointers = new Map();
canvas.addEventListener("pointerdown", e => { canvas.setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.offsetX, e.offsetY]); drag = { x: e.offsetX, y: e.offsetY, cx: view.cx, cy: view.cy, moved: false, d0: null, s0: view.scale }; canvas.classList.add("dragging"); });
canvas.addEventListener("pointermove", e => {
  if (pointers.has(e.pointerId)) pointers.set(e.pointerId, [e.offsetX, e.offsetY]);
  if (drag && pointers.size === 2) {
    const [a, b] = [...pointers.values()]; const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
    if (!drag.d0) drag.d0 = d; zoomAt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, drag.s0 * d / drag.d0, true); drag.moved = true; return;
  }
  if (drag) {
    const dx = e.offsetX - drag.x, dy = e.offsetY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (drag.moved) { view.cx = drag.cx - dx / view.scale; view.cy = drag.cy + dy / view.scale; hideTip(); draw(); }
    return;
  }
  const i = pickHex(e.offsetX, e.offsetY);
  if (i !== hover) { hover = i; draw(); }
  showTip(e.offsetX, e.offsetY, i);
});
canvas.addEventListener("pointerup", e => {
  pointers.delete(e.pointerId); canvas.classList.remove("dragging");
  if (drag && !drag.moved) {
    const c = pickCity(e.offsetX, e.offsetY), w = pickWonder(e.offsetX, e.offsetY);
    if (c) selectCity(c); else if (w) selectWonder(w); else { const i = pickHex(e.offsetX, e.offsetY); if (i >= 0) selectHex(i); }
  }
  if (pointers.size === 0) drag = null;
});
canvas.addEventListener("pointerleave", () => { hover = -1; hideTip(); draw(); });
canvas.addEventListener("wheel", e => { e.preventDefault(); zoomAt(e.offsetX, e.offsetY, view.scale * Math.exp(-e.deltaY * 0.0015)); }, { passive: false });
function zoomAt(sx, sy, ns, abs) {
  ns = Math.max(0.15, Math.min(14, ns));
  const [wx, wy] = toWorld(sx, sy);
  view.scale = ns; const [nx, ny] = toWorld(sx, sy);
  view.cx += wx - nx; view.cy += wy - ny; draw();
}
$("#zin").onclick = () => zoomAt(view.w / 2, view.h / 2, view.scale * 1.5);
$("#zout").onclick = () => zoomAt(view.w / 2, view.h / 2, view.scale / 1.5);
$("#zhome").onclick = home;
window.addEventListener("resize", resize);
function flyTo(x, y, scale) { view.cx = x; view.cy = y; if (scale) view.scale = scale; draw(); }

function showTip(sx, sy, i) {
  const tip = $("#tooltip");
  const c = pickCity(sx, sy), w = pickWonder(sx, sy);
  let html = "";
  if (c) html = `<b>${esc(c.name)}</b><br>${fmtBig(c.pop)} people (2025) · ${esc(c.state || "")}<br><span class="muted">Click for City View</span>`;
  else if (w) html = `<b>${esc(w.name)}</b><br>${w.type === "heritage" ? "World Heritage Site" : w.type === "natural" ? "Natural World Heritage Site" : w.type === "peak" ? `Peak · ${fmtInt(w.elev_m)} m` : esc(w.kind || "Protected area")}`;
  else if (i >= 0 && HX.kind[i] !== 2) {
    const d = HX.d[i];
    const name = d >= 0 ? dget(d, "name") : (HX.kind[i] === 1 ? "Neighbouring country" : "");
    html = `<b>${esc(name)}</b>${d >= 0 ? `, ${esc(dget(d, "state"))}` : ""}<br>${esc(tileTitle(i))}`;
    if (lens.value && HX.kind[i] === 0) html += `<br>${esc(lens.name)}: <b>${esc(lens.pips ? (lensVals[i] || 0) + " pips" : fmtVal(lens.value(i), lens.unit))}</b>`;
    else if (HX.kind[i] === 0) html += `<br>${fmtBig(HX.pop[i])} people · ${fmtRs(HX.gdp[i])}`;
  }
  if (!html) return hideTip();
  tip.innerHTML = html; tip.style.display = "block";
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = Math.min(view.w - tw - 8, sx + 14) + "px"; tip.style.top = Math.min(view.h - th - 8, sy + 14) + "px";
}
function hideTip() { $("#tooltip").style.display = "none"; }
function tileTitle(i) {
  const t = DATA.meta.meta.terrain[HX.t[i]], f = DATA.meta.meta.features[HX.f[i]];
  const T = { grassland: "Grassland", plains: "Plains", desert: "Desert", tundra: "Cold desert", snow: "Snow & ice", lake: "Lake", coast: "Coast", ocean: "Ocean" }[t] || t;
  const F = { hills: "Hills", mountains: "Mountains", forest: "Forest", rainforest: "Rainforest", marsh: "Marsh / mangrove", floodplain: "Floodplain" }[f];
  return F ? `${T} · ${F}` : T;
}

// ---------------------------------------------------------------- info panel
const YNAMES = [["food", "Food", "yf"], ["prod", "Prod.", "yp"], ["gold", "Gold", "yg"], ["sci", "Science", "ys"], ["cult", "Culture", "yc"], ["faith", "Faith", "yr"]];
function selectHex(i) {
  selected = { type: "hex", i }; selDistrict = HX.d[i];
  const k = HX.kind[i], d = HX.d[i];
  let html = "";
  if (k === 1) html = `<div class="info-head"><div><h2>Beyond the border</h2><div class="sub">Neighbouring country, outside the dataset.</div></div></div>`;
  else if (k === 3) html = `<div class="info-head"><div><h2>Gilgit-Baltistan</h2><div class="sub">Inside India's official boundary (Ladakh), administered by Pakistan. No Indian statistics are collected here.</div></div></div>`;
  else {
    const raw = { food: `${fmtInt((HX.crop[i] || 0) / 100 * HX.area_km2)} km² crops`, prod: `${HX.ind[i] ? HX.ind[i] + " km² ind." : (HX.mine[i] ? HX.mine[i] + " mines" : (HX.pmw[i] ? fmtInt(HX.pmw[i]) + " MW" : ""))}`,
      gold: fmtRs(HX.gdp[i]), sci: `${HX.univ[i] + HX.college[i]} colleges`, cult: `${HX.herit[i] + HX.museum[i]} sites`, faith: `${HX.worship[i]} mapped` };
    html = `<div class="info-head"><div><h2>${esc(tileTitle(i))}</h2><div class="sub">${d >= 0 ? esc(dget(d, "name")) + " district, " + esc(dget(d, "state")) : ""} · ${HX.lat[i].toFixed(2)}°N ${HX.lon[i].toFixed(2)}°E</div></div></div>
      <div class="ytable">${YNAMES.map(([id, n, c], ix) => `<div class="ycell" title="${esc(n)}"><div class="n" style="color:${YCOL[ix]}">${HX[c][i]}</div><div class="l">${n}</div><div class="raw">${esc(raw[id])}</div></div>`).join("")}</div>
      <div class="kv">
        <span>Population (2025)</span><span>${fmtInt(HX.pop[i])}</span>
        <span>GDP 2024-25 (modelled)</span><span>${fmtRs(HX.gdp[i])}</span>
        <span>Elevation</span><span>${fmtInt(HX.elev[i])} m${HX.relief[i] > 300 ? ` (relief ${fmtInt(HX.relief[i])} m)` : ""}</span>
        <span>Rainfall · temperature</span><span>${fmtInt(HX.rain[i])} mm · ${HX.temp[i]}°C</span>
        <span>Tree cover · cropland</span><span>${HX.tree[i]}% · ${HX.crop[i]}%</span>
        <span>Built-up</span><span>${HX.built[i] ?? 0} km²</span>
        ${HX.rail[i] || HX.road[i] ? `<span>Rail · major roads</span><span>${fmtInt(HX.rail[i])} · ${fmtInt(HX.road[i])} km</span>` : ""}
        ${HX.pmw[i] ? `<span>Power plants</span><span>${HX.pn[i]} · ${fmtInt(HX.pmw[i])} MW (${esc(HX.psrc[i])})</span>` : ""}
        ${HX.air[i] ? `<span>Airport</span><span>${{ L: "Major", M: "Regional", s: "Airstrip" }[HX.air[i]]}</span>` : ""}
        ${HX.port[i] ? `<span>Port facilities</span><span>${HX.port[i]}</span>` : ""}
        ${HX.mil[i] ? `<span>Military land</span><span>${HX.mil[i]} km²</span>` : ""}
        ${HX.cyc[i] ? `<span>Cyclones since 1990</span><span>${HX.cyc[i]}${HX.scyc[i] ? ` (${HX.scyc[i]} severe)` : ""}</span>` : ""}
        ${HX.eq[i] ? `<span>Quakes M4.5+ since 1990</span><span>${HX.eq[i]} (max ${HX.eqmax[i]})</span>` : ""}
      </div>`;
    if (HX.res[i]) html += `<div class="sec">Resources</div>${HX.res[i].split(",").map(r => `<span class="pill res">${esc(r)}</span>`).join("")}`;
    if (HX.rel[i]) { const r = HX.rel[i]; html += `<div class="sec">Places of worship mapped</div>${Object.entries(r).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span class="pill" style="background:${REL_COL[k]}33;color:#eee">${esc(k)} ${v}</span>`).join("")}`; }
    const cityHere = DATA.cities.find(c => c.hexes.some(([h]) => h === i) && c.pop >= 100000);
    if (cityHere) html += `<div class="sec">City</div><button class="btn" data-city="${cityHere.ix}">Open City View: ${esc(cityHere.name)}</button>`;
    if (d >= 0) html += districtSummary(d);
  }
  $("#info-body").innerHTML = html;
  bindInfoButtons();
  draw();
}
function districtSummary(d) {
  const r = D.byDix.get(d); if (!r) return "";
  const g = c => r[DCOL[c]];
  const nf = g("women_10yr") != null;
  return `<div class="sec">District: ${esc(g("name"))}</div>
  <div class="kv">
    <span>Population 2025</span><span>${fmtBig(g("pop"))}</span>
    <span>GDP per person</span><span>₹${fmtInt(g("gdp_pc"))}</span>
    ${nf ? `<span>Women with 10+ yrs school</span><span>${fmtPct(g("women_10yr"))}</span>
    <span>Women ever online</span><span>${fmtPct(g("women_internet"))}</span>
    <span>Child stunting</span><span>${fmtPct(g("stunted"))}</span>
    <span>Health insurance</span><span>${fmtPct(g("insurance"))}</span>` : `<span>NFHS-6</span><span>not surveyed</span>`}
  </div>
  ${r[3] === "state" ? `<div class="note">NFHS-6 has no separate estimate for this district, so its state's values are shown.</div>` : ""}
  <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap"><button class="btn ghost" data-explore="${d}">Open in Explorer</button></div>`;
}
function bindInfoButtons() {
  $$("#info-body [data-city]").forEach(b => b.onclick = () => openCity(DATA.cities[+b.dataset.city]));
  $$("#info-body [data-explore]").forEach(b => b.onclick = () => openExplorer(+b.dataset.explore));
}
function selectCity(c) {
  selected = { type: "city", c }; selDistrict = c.d ?? -1;
  $("#info-body").innerHTML = `<div class="info-head"><div><h2>${esc(c.name)}</h2><div class="sub">${esc(c.state || "")} · ${fmtInt(c.pop)} people (2025)</div></div></div>
    ${c.epithets.map(e => `<span class="epithet" title="${esc(e.why)}">${esc(e.title)}</span>`).join("")}
    <div class="sec">Districts</div>${c.districts.length ? c.districts.map(x => `<span class="pill">${esc(x.name)}</span>`).join("") : '<span class="muted">No specialist districts</span>'}
    <div class="kv" style="margin-top:10px">
      <span>Urban area</span><span>${fmtInt(c.area)} km²</span>
      <span>GDP 2024-25 (modelled)</span><span>${fmtRs(c.gdp_cr)}</span>
      <span>Human Development Index</span><span>${c.hdi ?? "–"}</span>
      <span>Growth since 2000</span><span>${c.pop2000 ? "+" + Math.round((c.pop / c.pop2000 - 1) * 100) + "%" : "–"}</span>
    </div>
    <div style="margin-top:12px"><button class="btn" data-city="${c.ix}">Open City View</button></div>`;
  bindInfoButtons(); draw();
}
function selectWonder(w) {
  selected = { type: "wonder", w };
  const typ = w.type === "heritage" ? "World Heritage Site (cultural)" : w.type === "natural" ? "World Heritage Site (natural)" : w.type === "peak" ? "Mountain peak" : (w.kind || "Protected area");
  $("#info-body").innerHTML = `<div class="info-head"><div><h2>${esc(w.name)}</h2><div class="sub">${esc(typ)}</div></div></div>
    <div class="kv">
      ${w.visitors_dom ? `<span>Domestic visitors (2024)</span><span>${fmtBig(w.visitors_dom)}</span>` : ""}
      ${w.visitors_for ? `<span>Foreign visitors (2024)</span><span>${fmtBig(w.visitors_for)}</span>` : ""}
      ${w.area_km2 ? `<span>Area</span><span>${fmtInt(w.area_km2)} km²</span>` : ""}
      ${w.elev_m ? `<span>Elevation</span><span>${fmtInt(w.elev_m)} m</span>` : ""}
      <span>Location</span><span>${w.lat.toFixed(2)}°N ${w.lon.toFixed(2)}°E</span>
    </div>
    <div class="note">Source: ${esc(w.source)}${w.wikidata ? ` · <a href="https://www.wikidata.org/wiki/${esc(w.wikidata)}" target="_blank" rel="noopener" style="color:var(--gold-2)">Wikidata</a>` : ""}</div>`;
  if (w.hex != null) selDistrict = HX.d[w.hex];
  draw();
}

// ---------------------------------------------------------------- top yields
function buildYieldsBar() {
  const n = DATA.meta.national;
  const cropKm2 = (() => { let s = 0; for (let i = 0; i < N; i++) if (HX.kind[i] === 0) s += (HX.crop[i] || 0) / 100 * HX.area_km2; return s; })();
  const items = [
    ["pop", fmtBig(n.pop), "people", "GHS-POP 2025 population (JRC), summed over India's tiles"],
    ["food", fmtBig(cropKm2) + " km²", "cropland", "Food: cropland area from ESA WorldCover 2021"],
    ["prod", fmtInt(n.power_mw / 1000) + " GW", "mapped power", "Production: generating capacity of power plants tagged in OpenStreetMap"],
    ["gold", fmtRs(n.gdp_cr), "GDP 24-25", "Gold: sum of state GSDP 2024-25 (MoSPI), current prices"],
    ["sci", fmtInt(n.univ + n.college), "colleges", "Science: universities and colleges mapped in OpenStreetMap"],
    ["cult", DATA.wonders.heritage.length, "World Heritage", "Culture: UNESCO World Heritage Sites in India"],
    ["faith", fmtBig(n.worship), "places of worship", "Faith: places of worship mapped in OpenStreetMap"],
  ];
  $("#yields").innerHTML = items.map(([k, v, l, t]) => `<div class="yield" title="${esc(t)}"><span class="ico ${k}"></span><b>${esc(v)}</b><small>${esc(l)}</small></div>`).join("");
}

// ---------------------------------------------------------------- search
function buildSearch() {
  const inp = $("#search"), ul = $("#search-results");
  const idx = [...DATA.cities.filter(c => c.pop >= 50000).map(c => ({ t: "city", name: c.name, sub: `City · ${c.state || ""} · ${fmtBig(c.pop)}`, c, aka: c.aka.join(" ") })),
    ...D.rows.map(r => ({ t: "district", name: r[1], sub: `District · ${r[2]}`, dix: r[0] }))];
  let items = [], act = 0;
  const render_ = () => { ul.innerHTML = items.map((it, k) => `<li role="option" class="${k === act ? "active" : ""}" data-k="${k}"><span>${esc(it.name)}</span><small>${esc(it.sub)}</small></li>`).join(""); ul.style.display = items.length ? "block" : "none"; };
  inp.addEventListener("input", () => {
    const q = inp.value.trim().toLowerCase(); act = 0;
    if (q.length < 2) { items = []; return render_(); }
    items = idx.filter(it => it.name.toLowerCase().includes(q) || (it.aka || "").toLowerCase().includes(q))
      .sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || ((b.c?.pop || 0) - (a.c?.pop || 0))).slice(0, 12);
    render_();
  });
  inp.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { act = Math.min(items.length - 1, act + 1); render_(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { act = Math.max(0, act - 1); render_(); e.preventDefault(); }
    else if (e.key === "Enter" && items[act]) go(items[act]);
    else if (e.key === "Escape") { items = []; render_(); }
  });
  ul.addEventListener("click", e => { const li = e.target.closest("li"); if (li) go(items[+li.dataset.k]); });
  function go(it) {
    items = []; render_(); inp.value = it.name; inp.blur();
    if (it.t === "city") { flyTo(it.c.xy[0], it.c.xy[1], Math.max(view.scale, 2.4)); selectCity(it.c); }
    else focusDistrict(it.dix);
  }
}
function focusDistrict(dix) {
  const hs = HX.distHexes.get(dix);
  const xy = D.xy[D.rows.findIndex(r => r[0] === dix)];
  if (hs && hs.length) { selectHex(hs[Math.floor(hs.length / 2)]); }
  selDistrict = dix;
  if (xy) flyTo(xy[0], xy[1], Math.max(view.scale, 2.2));
}

// ---------------------------------------------------------------- modal helpers
function openModal(html, onMount) {
  $("#modal-content").innerHTML = html; $("#modal").hidden = false;
  $(".modal-card").scrollTop = 0;
  onMount && onMount();
  $(".modal-close").focus();
}
function closeModal() { $("#modal").hidden = true; $("#modal-content").innerHTML = ""; }
$(".modal-close").onclick = closeModal;
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });

// ---------------------------------------------------------------- City View
// Köppen-Geiger classes as numbered in Beck et al. (2018/2023), used by GHSL UCDB
const KOPPEN = [null, "Tropical rainforest (Af)", "Tropical monsoon (Am)", "Tropical savanna (Aw)", "Hot desert (BWh)", "Cold desert (BWk)",
  "Hot semi-arid (BSh)", "Cold semi-arid (BSk)", "Hot-summer Mediterranean (Csa)", "Warm-summer Mediterranean (Csb)", "Cold-summer Mediterranean (Csc)",
  "Humid subtropical, dry winter (Cwa)", "Subtropical highland (Cwb)", "Cold subtropical highland (Cwc)", "Humid subtropical (Cfa)", "Oceanic (Cfb)",
  "Subpolar oceanic (Cfc)", "Dsa", "Dsb", "Dsc", "Dsd", "Monsoon continental (Dwa)", "Dwb", "Dwc", "Dwd", "Dfa", "Dfb", "Subarctic (Dfc)", "Dfd", "Tundra (ET)", "Ice cap (EF)"];
const DIST_COL = { campus: "#5aa7e0", commercial: "#e6c04d", industrial: "#d0864a", harbor: "#3d86c6", aerodrome: "#9fd3e6", encampment: "#c9735a",
  holy: "#e8e3d0", theater: "#c27adf", entertainment: "#d07aa6", gov: "#f0cf7e", power: "#e27a3f", datacenter: "#5fb0a5" };
const DIST_GLYPH = { campus: "S", commercial: "₹", industrial: "P", harbor: "H", aerodrome: "A", encampment: "M", holy: "F", theater: "C", entertainment: "E", gov: "G", power: "W", datacenter: "D" };
function openCity(c) {
  const st = DATA.states.rows.find(r => r.state === c.state) || {};
  const secs = DATA.states.plfs_sections;
  const mix = Object.entries(c.workforce || {}).sort((a, b) => b[1] - a[1]);
  const totW = mix.reduce((a, [, v]) => a + v, 0);
  const kn = ((c.workforce.J || 0) + (c.workforce.M || 0));
  const allIndia = DATA.states.rows.reduce((acc, r) => acc, null);
  const dots = mix.flatMap(([s, v]) => Array(Math.round(v / Math.max(1, totW) * 100)).fill(s)).slice(0, 100);
  const nearW = DATA.wonders.heritage.filter(w => Math.hypot(w.xy[0] - c.xy[0], w.xy[1] - c.xy[1]) < 60);
  const haz = c.haz || {};
  const hazTxt = [["FLO", "floods"], ["TCY", "cyclones"], ["EAR", "earthquakes"], ["HEW", "heatwaves"], ["DRO", "droughts"], ["LAN", "landslides"]].filter(([k]) => haz[k]).map(([k, n]) => `${haz[k]} ${n}`).join(", ");
  const cn = c.counts;
  openModal(`
    <div class="modal-head"><h2 id="modal-title">${esc(c.name)}</h2>
      <p>${esc(c.state || "")}${c.capital ? " · capital" : ""} · GHSL urban centre covering ${fmtInt(c.area)} km²${c.aka.length > 1 ? ` (takes in ${esc(c.aka.slice(1, 6).join(", "))}${c.aka.length > 6 ? "…" : ""})` : ""}</p>
      <div>${c.epithets.map(e => `<span class="epithet" title="${esc(e.why)}">${esc(e.title)}</span>`).join("")}</div>
    </div>
    <div class="modal-body">
      <div class="stat-row">
        <div class="stat"><div class="v">${fmtBig(c.pop)}</div><div class="k">Citizens (2025)</div></div>
        <div class="stat"><div class="v">${c.pop2000 ? "+" + Math.round((c.pop / c.pop2000 - 1) * 100) + "%" : "–"}</div><div class="k">Growth since 2000</div></div>
        <div class="stat"><div class="v">${fmtRs(c.gdp_cr)}</div><div class="k">GDP 2024-25 (modelled)</div></div>
        <div class="stat"><div class="v">${c.hdi ?? "–"}</div><div class="k">HDI (2020)</div></div>
        <div class="stat"><div class="v">${c.life_exp ?? "–"}</div><div class="k">Life expectancy</div></div>
        <div class="stat"><div class="v">${c.school_yrs ?? "–"}</div><div class="k">Expected years of school</div></div>
      </div>
      <div class="grid2">
        <div class="card"><h3>Districts</h3>
          ${c.districts.length ? c.districts.map(x => `<div class="district-card"><div class="badge" style="background:${DIST_COL[x.id] || "#888"}">${DIST_GLYPH[x.id] || "•"}</div><div><b>${esc(x.name)}</b><small>${esc(x.why)}</small></div></div>`).join("") : `<p class="muted">No district clears the specialisation thresholds.</p>`}
          ${c.epithets.length ? `<div class="sec">Why the title</div>${c.epithets.map(e => `<div class="note"><b>${esc(e.title)}</b>: ${esc(e.why)}</div>`).join("")}` : ""}
          <div class="note">A district appears when the city has notably more of something than India's cities on average (location quotient), counted from OpenStreetMap features inside the city's GHSL footprint, plus NIRF 2025 ranks and OurAirports.</div>
        </div>
        <div class="card"><h3>Citizens at work</h3>
          ${totW ? `<p style="margin:0 0 6px">${fmtBig(totW)} workers (urban worker-population ratio ${c.wpr_urban}%). Each dot is 1% of them.</p>
          <div class="citizens">${dots.map(s => `<i title="${esc(secs[s])}" style="background:${SECTION_COL[s]}"></i>`).join("")}</div>
          <table class="rank">${mix.slice(0, 9).map(([s, v]) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${SECTION_COL[s]};margin-right:6px"></i>${esc(secs[s])}</td><td class="n">${fmtBig(v)}</td><td class="n">${(v / totW * 100).toFixed(1)}%</td></tr>`).join("")}</table>
          <div class="note">${fmtPct(kn / totW * 100)} work in ICT or professional & scientific services. Mix = ${esc(c.state)}'s urban workforce in PLFS 2025 (Table 27), applied to this city's 2025 population. PLFS doesn't publish city-level tables.</div>` : `<p class="muted">PLFS workforce data unavailable for this state.</p>`}
        </div>
      </div>
      <div class="grid3" style="margin-top:16px">
        <div class="card"><h3>Buildings</h3><table class="rank">
          ${[["Universities", cn.university], ["Colleges", cn.college], ["Research institutes", cn.research], ["Schools", cn.school], ["Hospitals", cn.hospital], ["Clinics", cn.clinic],
             ["Banks", cn.bank], ["Company & IT offices", cn.office], ["Factories / works", cn.works], ["Museums", cn.museum], ["Theatres & arts", cn.arts], ["Stadiums", cn.stadium],
             ["Rail stations", cn.rail_station], ["Metro stations", cn.metro_station], ["Data centres", cn.data_center], ["Places of worship", cn.worship]]
             .filter(([, v]) => v).map(([k, v]) => `<tr><td>${k}</td><td class="n">${fmtInt(v)}</td></tr>`).join("")}
          </table><div class="note">Mapped in OpenStreetMap inside the city footprint.</div></div>
        <div class="card"><h3>Land & climate</h3><div class="kv">
          <span>Built-up area</span><span>${c.built_km2 ?? "–"} km²</span>
          <span>Avg building height</span><span>${c.bldg_h ?? "–"} m</span>
          <span>Greenness (NDVI)</span><span>${c.green ?? "–"}</span>
          <span>Mean temperature</span><span>${c.temp ?? "–"}°C</span>
          <span>Annual rainfall</span><span>${fmtInt(c.rain)} mm</span>
          <span>Elevation</span><span>${fmtInt(c.elev)} m</span>
          <span>River basin</span><span>${esc(c.basin || "–")}</span>
          <span>Climate (Köppen)</span><span>${esc(KOPPEN[+c.climate] || c.climate || "–")}</span>
          <span>CO₂ emitted (2022)</span><span>${c.co2_t ? fmtBig(c.co2_t) + " t" : "–"}</span>
        </div></div>
        <div class="card"><h3>Hazards & wonders</h3>
          <div class="kv">
            <span>Disasters recorded (to 2015)</span><span>${hazTxt || "–"}</span>
            <span>Pop. in 1-in-100-yr flood zone</span><span>${c.flood100_share != null ? fmtPct(c.flood100_share * (c.flood100_share <= 1 ? 100 : 1)) : "–"}</span>
          </div>
          ${nearW.length ? `<div class="sec">World Heritage nearby</div>${nearW.map(w => `<div>★ ${esc(w.name)}${w.visitors_dom ? ` <span class="muted">(${fmtBig(w.visitors_dom)} visitors)</span>` : ""}</div>`).join("")}` : ""}
          ${c.nirf.length ? `<div class="sec">Great institutions (NIRF 2025)</div>${c.nirf.map(n => `<div>#${n.rank} ${esc(n.category)}: ${esc(n.name)}</div>`).join("")}` : ""}
        </div>
      </div>
      <p class="note">Population, HDI, life expectancy, schooling, built-up, emissions, hazards and climate come from the GHSL Urban Centre Database R2024A, which draws cities by population density rather than municipal limits. That is why dense rural belts (e.g. around Patna or along Kerala's coast) form very large "cities".</p>
    </div>`);
}

// ---------------------------------------------------------------- Explorer
const EX = { x: "women_10yr", y: "gdp_pc", sort: "pop", dir: -1, filter: "", state: "", sel: null };
function openExplorer(dix) {
  if (dix != null) EX.sel = dix;
  const opts = Object.entries(D.meta).map(([k, m]) => `<option value="${k}">${esc(m.group)} · ${esc(m.label)}</option>`).join("");
  openModal(`
    <div class="modal-head"><h2 id="modal-title">Explorer</h2><p>Any column for any of India's ${D.rows.length} districts, as a sortable table and a scatter plot. Click a row or a dot to find the district on the map.</p></div>
    <div class="modal-body">
      <div class="ex-controls">
        <label>X axis<select id="ex-x">${opts}</select></label>
        <label>Y axis<select id="ex-y">${opts}</select></label>
        <label>State<select id="ex-state"><option value="">All India</option>${DATA.states.names.map(s => `<option>${esc(s)}</option>`).join("")}</select></label>
        <label>Filter<input id="ex-q" placeholder="District name…"></label>
        <button class="btn ghost" id="ex-csv">Copy as CSV</button>
      </div>
      <div class="ex-wrap"><div class="ex-table" id="ex-table"></div><div><canvas id="scatter"></canvas><div class="note" id="ex-note"></div></div></div>
    </div>`, () => {
    $("#ex-x").value = EX.x; $("#ex-y").value = EX.y; $("#ex-state").value = EX.state; $("#ex-q").value = EX.filter;
    $("#ex-x").onchange = e => { EX.x = e.target.value; exRender(); };
    $("#ex-y").onchange = e => { EX.y = e.target.value; exRender(); };
    $("#ex-state").onchange = e => { EX.state = e.target.value; exRender(); };
    $("#ex-q").oninput = e => { EX.filter = e.target.value.toLowerCase(); exRender(); };
    $("#ex-csv").onclick = exCsv;
    exRender();
  });
}
function exRows() {
  return D.rows.filter(r => (!EX.state || r[2] === EX.state) && (!EX.filter || r[1].toLowerCase().includes(EX.filter)));
}
function exRender() {
  const rows = exRows();
  const cols = ["name", "pop", EX.x, EX.y].filter((c, i, a) => a.indexOf(c) === i);
  const sc = DCOL[EX.sort] ?? DCOL.pop;
  rows.sort((a, b) => { const va = a[sc], vb = b[sc]; if (va == null) return 1; if (vb == null) return -1; return (va > vb ? 1 : va < vb ? -1 : 0) * EX.dir; });
  const lab = c => c === "name" ? "District" : c === "state" ? "State" : D.meta[c].label;
  $("#ex-table").innerHTML = `<table><thead><tr>${cols.map(c => `<th data-c="${c}" class="${c === "name" || c === "state" ? "" : "num"}">${esc(lab(c))}${EX.sort === c ? (EX.dir < 0 ? " ▾" : " ▴") : ""}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr data-d="${r[0]}" class="${r[0] === EX.sel ? "sel" : ""}">${cols.map(c => c === "name" ? `<td>${esc(r[1])}${r[3] === "state" ? " <span class='muted' title='NFHS-6 state value'>†</span>" : ""}<br><small class="muted">${esc(r[2])}</small></td>` : `<td class="num">${esc(fmtVal(r[DCOL[c]], D.meta[c].unit))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  $$("#ex-table th").forEach(th => th.onclick = () => { const c = th.dataset.c; if (EX.sort === c) EX.dir *= -1; else { EX.sort = c; EX.dir = -1; } exRender(); });
  $$("#ex-table tbody tr").forEach(tr => tr.onclick = () => exPick(+tr.dataset.d));
  exScatter(rows);
}
function exPick(dix) {
  EX.sel = dix; closeModal(); focusDistrict(dix);
}
let exPts = [];
function exScatter(rows) {
  const cv = $("#scatter"); const r = cv.getBoundingClientRect(); const dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = r.width * dpr; cv.height = r.height * dpr;
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W_ = r.width, H_ = r.height, m = { l: 74, r: 18, t: 14, b: 44 };
  const tick = (v, unit) => unit === "₹" ? "₹" + fmtBig(v) : unit === "₹ crore" ? fmtRs(v) : unit === "people" ? fmtBig(v) : fmtVal(v, unit);
  const xi = DCOL[EX.x], yi = DCOL[EX.y];
  const pts = rows.filter(rr => rr[xi] != null && rr[yi] != null);
  const logx = ["pop", "gdp_cr", "gdp_pc", "density", "area_km2", "power_mw"].includes(EX.x), logy = ["pop", "gdp_cr", "gdp_pc", "density", "area_km2", "power_mw"].includes(EX.y);
  const tx = v => logx ? Math.log10(Math.max(v, 1e-3)) : v, ty = v => logy ? Math.log10(Math.max(v, 1e-3)) : v;
  const xs = pts.map(p => tx(p[xi])), ys = pts.map(p => ty(p[yi]));
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)], [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const sx = v => m.l + (tx(v) - x0) / ((x1 - x0) || 1) * (W_ - m.l - m.r), sy = v => H_ - m.b - (ty(v) - y0) / ((y1 - y0) || 1) * (H_ - m.t - m.b);
  g.fillStyle = "#0f1a24"; g.fillRect(0, 0, W_, H_);
  g.strokeStyle = "#23333f"; g.lineWidth = 1; g.font = "11px Inter, sans-serif"; g.fillStyle = "#7f8a93";
  for (let k = 0; k <= 4; k++) {
    const vx = x0 + (x1 - x0) * k / 4, vy = y0 + (y1 - y0) * k / 4;
    const px = m.l + (W_ - m.l - m.r) * k / 4, py = H_ - m.b - (H_ - m.t - m.b) * k / 4;
    g.beginPath(); g.moveTo(px, m.t); g.lineTo(px, H_ - m.b); g.moveTo(m.l, py); g.lineTo(W_ - m.r, py); g.stroke();
    g.textAlign = k === 0 ? "left" : k === 4 ? "right" : "center"; g.fillText(tick(logx ? 10 ** vx : vx, D.meta[EX.x].unit), px, H_ - m.b + 14);
    g.textAlign = "right"; g.fillText(tick(logy ? 10 ** vy : vy, D.meta[EX.y].unit), m.l - 6, py + 4);
  }
  g.fillStyle = "#b9b2a0"; g.textAlign = "center"; g.fillText(D.meta[EX.x].label + (logx ? " (log)" : ""), (W_ + m.l) / 2, H_ - 8);
  g.save(); g.translate(12, (H_ - m.b) / 2); g.rotate(-Math.PI / 2); g.fillText(D.meta[EX.y].label + (logy ? " (log)" : ""), 0, 0); g.restore();
  exPts = [];
  const sidx = Object.fromEntries(DATA.states.names.map((s, i) => [s, i]));
  for (const p of pts) {
    const x = sx(p[xi]), y = sy(p[yi]);
    const rad = Math.max(2.5, Math.min(9, Math.sqrt((p[DCOL.pop] || 0) / 3e5) * 2.2));
    g.beginPath(); g.arc(x, y, rad, 0, 7); g.fillStyle = STATE_COLS[(sidx[p[2]] || 0) % STATE_COLS.length] + "cc"; g.fill();
    if (p[0] === EX.sel) { g.lineWidth = 2.5; g.strokeStyle = "#f6e07a"; g.stroke(); }
    exPts.push([x, y, rad, p]);
  }
  // Pearson r
  const n = pts.length; const mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sxx = 0, syy = 0; for (let k = 0; k < n; k++) { sxy += (xs[k] - mx) * (ys[k] - my); sxx += (xs[k] - mx) ** 2; syy += (ys[k] - my) ** 2; }
  const rr = sxy / Math.sqrt(sxx * syy);
  $("#ex-note").innerHTML = `${n} districts · correlation r = ${isFinite(rr) ? rr.toFixed(2) : "–"}${logx || logy ? " (on log scale)" : ""}. Dot size = population, colour = state.<br>Sources: X: ${esc(D.meta[EX.x].source)}. Y: ${esc(D.meta[EX.y].source)}. † = NFHS-6 state value.`;
  cv.onmousemove = e => { const hit = exPts.find(([x, y, r_]) => (e.offsetX - x) ** 2 + (e.offsetY - y) ** 2 < (r_ + 2) ** 2); cv.title = hit ? `${hit[3][1]}, ${hit[3][2]}\n${D.meta[EX.x].label}: ${fmtVal(hit[3][xi], D.meta[EX.x].unit)}\n${D.meta[EX.y].label}: ${fmtVal(hit[3][yi], D.meta[EX.y].unit)}` : ""; cv.style.cursor = hit ? "pointer" : "default"; };
  cv.onclick = e => { const hit = exPts.find(([x, y, r_]) => (e.offsetX - x) ** 2 + (e.offsetY - y) ** 2 < (r_ + 2) ** 2); if (hit) exPick(hit[3][0]); };
}
function exCsv() {
  const rows = exRows();
  const cols = D.cols;
  const head = cols.map(c => D.meta[c] ? `${D.meta[c].label}${D.meta[c].unit ? " (" + D.meta[c].unit + ")" : ""}` : c);
  const csv = [head, ...rows.map(r => r.map(v => v == null ? "" : typeof v === "string" && /[",]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v))].map(r => r.join(",")).join("\n");
  const btn = $("#ex-csv");
  const done = ok => { btn.textContent = ok ? `Copied ${rows.length} rows` : "Copy failed: select the table instead"; setTimeout(() => btn.textContent = "Copy as CSV", 2200); };
  try { navigator.clipboard.writeText(csv).then(() => done(true), () => done(false)); } catch (e) { done(false); }
}

// ---------------------------------------------------------------- Advisors
function rankTable(rows, val, fmt, n = 8, onClick) {
  return `<table class="rank">${rows.slice(0, n).map((r, k) => `<tr data-k="${k}"><td>${k + 1}. ${esc(r.name || r.state)}</td><td class="n">${fmt(val(r))}</td></tr>`).join("")}</table>`;
}
function stateRows() { return DATA.states.rows.filter(r => r.pop > 0); }
const ADVISORS = [
  { id: "domestic", name: "Domestic", sub: "People & cities", col: "#e7a27a", glyph: "D", render: advDomestic },
  { id: "economic", name: "Economic", sub: "Gold & trade", col: "#e6c04d", glyph: "E", render: advEconomic },
  { id: "labour", name: "Labour", sub: "Citizens at work", col: "#d0864a", glyph: "L", render: advLabour },
  { id: "science", name: "Science", sub: "Campuses & skills", col: "#5aa7e0", glyph: "S", render: advScience },
  { id: "culture", name: "Culture", sub: "Wonders & heritage", col: "#c27adf", glyph: "C", render: advCulture },
  { id: "faith", name: "Faith", sub: "Holy sites", col: "#e8e3d0", glyph: "F", render: advFaith },
  { id: "health", name: "Health", sub: "NFHS-6", col: "#5fb2b0", glyph: "H", render: advHealth },
  { id: "military", name: "Military", sub: "Bases & borders", col: "#c9735a", glyph: "M", render: advMilitary },
  { id: "environment", name: "Environment", sub: "Disasters & power", col: "#8fc152", glyph: "N", render: advEnvironment },
];
function buildAdvisors() {
  const host = $("#advisors");
  host.innerHTML = ADVISORS.map(a => `<button class="adv" data-a="${a.id}"><span class="face" style="background:${a.col}">${a.glyph}</span><span class="t"><b>${a.name}</b><small>${a.sub}</small></span></button>`).join("")
    + `<button class="adv explorer" data-a="explorer"><span class="face">⌕</span><span class="t"><b>Explorer</b><small>Every district, any column</small></span></button>`
    + `<button class="adv" data-a="about"><span class="face" style="background:#7f8a93">i</span><span class="t"><b>How it's made</b><small>${DATA.meta.meta.sources.length} data sources</small></span></button>`;
  host.addEventListener("click", e => {
    const b = e.target.closest(".adv"); if (!b) return;
    const id = b.dataset.a;
    if (id === "explorer") return openExplorer();
    if (id === "about") return openAbout();
    const a = ADVISORS.find(x => x.id === id);
    openModal(`<div class="modal-head"><h2 id="modal-title">${a.name} Advisor</h2><p>${a.sub}</p></div><div class="modal-body">${a.render()}</div>`, () => {
      $$("#modal-content [data-lens]").forEach(el => el.onclick = () => { closeModal(); setLens(el.dataset.lens); });
      $$("#modal-content [data-cityix]").forEach(el => el.onclick = () => { openCity(DATA.cities[+el.dataset.cityix]); });
      $$("#modal-content [data-state]").forEach(el => el.onclick = () => { closeModal(); setLens("political"); });
    });
  });
}
const lensBtn = (id, label) => `<button class="btn ghost" data-lens="${id}">Show ${esc(label)} lens</button>`;
function natAvg(col) { const rs = D.rows.filter(r => r[DCOL[col]] != null && r[DCOL.pop]); const w = rs.reduce((a, r) => a + r[DCOL.pop], 0); return rs.reduce((a, r) => a + r[DCOL[col]] * r[DCOL.pop], 0) / w; }
function topDistricts(col, n = 8, dir = -1, minPop = 2e5) {
  return D.rows.filter(r => r[DCOL[col]] != null && (r[DCOL.pop] || 0) >= minPop).sort((a, b) => (a[DCOL[col]] - b[DCOL[col]]) * dir).slice(0, n)
    .map(r => ({ name: `${r[1]}, ${r[2]}`, v: r[DCOL[col]] }));
}
function advDomestic() {
  const n = DATA.meta.national, cs = DATA.cities;
  const big = cs.filter(c => c.pop >= 1e6), urbanPop = cs.reduce((a, c) => a + c.pop, 0);
  const fastest = cs.filter(c => c.pop >= 1e6 && c.pop2000).map(c => ({ ...c, g: c.pop / c.pop2000 - 1 })).sort((a, b) => b.g - a.g);
  const dens = topDistricts("density", 6);
  return `<p class="quote">“${fmtBig(n.pop)} citizens, and ${fmtBig(urbanPop)} of them live in what GHSL counts as urban centres. ${big.length} cities have passed a million.”</p>
  <div class="stat-row"><div class="stat"><div class="v">${fmtBig(n.pop)}</div><div class="k">Population 2025 (GHS-POP)</div></div>
  <div class="stat"><div class="v">${fmtPct(urbanPop / n.pop * 100)}</div><div class="k">In urban centres ≥50k (GHSL)</div></div>
  <div class="stat"><div class="v">${big.length}</div><div class="k">Million-plus cities</div></div>
  <div class="stat"><div class="v">${n.districts}</div><div class="k">Districts</div></div></div>
  <div class="grid3"><div class="card"><h3>Largest cities</h3><table class="rank">${cs.slice(0, 10).map(c => `<tr data-cityix="${c.ix}"><td>${esc(c.name)}</td><td class="n">${fmtBig(c.pop)}</td></tr>`).join("")}</table></div>
  <div class="card"><h3>Fastest-growing since 2000</h3><table class="rank">${fastest.slice(0, 10).map(c => `<tr data-cityix="${c.ix}"><td>${esc(c.name)}</td><td class="n">+${Math.round(c.g * 100)}%</td></tr>`).join("")}</table></div>
  <div class="card"><h3>Densest districts</h3>${rankTable(dens, r => r.v, v => fmtInt(v) + "/km²", 6)}<div class="note">GHS-POP 2025 ÷ district area</div></div></div>
  <div style="margin-top:14px">${lensBtn("pop", "Population density")} ${lensBtn("urban", "Built-up land")}</div>`;
}
function advEconomic() {
  const S = stateRows().filter(r => r.gdp_cr).sort((a, b) => b.gdp_cr - a.gdp_cr);
  const pc = S.slice().sort((a, b) => b.gdp_pc - a.gdp_pc);
  const n = DATA.meta.national;
  const top5 = S.slice(0, 5).reduce((a, r) => a + r.gdp_cr, 0) / n.gdp_cr;
  const rich = topDistricts("gdp_pc", 8), poor = topDistricts("gdp_pc", 8, 1);
  return `<p class="quote">“Our treasury holds ${fmtRs(n.gdp_cr)} of output for 2024-25. Five states earn ${Math.round(top5 * 100)}% of it, and per person, ${esc(pc[0].state)} produces ${(pc[0].gdp_pc / pc[pc.length - 1].gdp_pc).toFixed(1)}× what ${esc(pc[pc.length - 1].state)} does.”</p>
  <div class="grid3"><div class="card"><h3>GSDP 2024-25</h3>${rankTable(S, r => r.gdp_cr, fmtRs, 10)}<div class="note">MoSPI, current prices${S.some(r => !r.gsdp_reported) ? "; * estimated where MoSPI publishes none" : ""}</div></div>
  <div class="card"><h3>Richest districts per person</h3>${rankTable(rich, r => r.v, v => "₹" + fmtInt(v), 8)}</div>
  <div class="card"><h3>Poorest districts per person</h3>${rankTable(poor, r => r.v, v => "₹" + fmtInt(v), 8)}</div></div>
  <div class="note">District GDP is modelled: each state's official GSDP is spread across its land, half by population and half by non-residential built-up area (offices, factories, shops) from GHSL 2025.</div>
  <div style="margin-top:14px">${lensBtn("gold", "Gold")} ${lensBtn("gdppc", "Income")}</div>`;
}
function advLabour() {
  const S = stateRows().filter(r => r.plfs_A != null);
  const secs = DATA.states.plfs_sections;
  const ict = S.slice().sort((a, b) => b.plfs_J - a.plfs_J), man = S.slice().sort((a, b) => b.plfs_C - a.plfs_C), agri = S.slice().sort((a, b) => b.plfs_A - a.plfs_A);
  const fem = S.slice().sort((a, b) => b.wpr_female - a.wpr_female);
  return `<p class="quote">“Most of our citizens still work the land. Agriculture employs ${fmtPct(agri[0].plfs_A)} of workers in ${esc(agri[0].state)}, while in ${esc(ict[0].state)} ${fmtPct(ict[0].plfs_J)} work in information & communication.”</p>
  <div class="grid3"><div class="card"><h3>Farming share</h3>${rankTable(agri, r => r.plfs_A, fmtPct, 8)}</div>
  <div class="card"><h3>Manufacturing share</h3>${rankTable(man, r => r.plfs_C, fmtPct, 8)}</div>
  <div class="card"><h3>ICT share</h3>${rankTable(ict, r => r.plfs_J, fmtPct, 8)}</div></div>
  <div class="grid2" style="margin-top:14px"><div class="card"><h3>Women at work</h3>${rankTable(fem, r => r.wpr_female, fmtPct, 8)}<div class="note">Female worker-population ratio, all ages (PLFS 2025 Table 17.0)</div></div>
  <div class="card"><h3>How PLFS sorts work</h3><div class="citizens" style="gap:6px">${Object.entries(secs).map(([k, v]) => `<span class="pill" style="background:${SECTION_COL[k]}33;color:#eee">${k} · ${esc(v)}</span>`).join("")}</div></div></div>
  <div class="note">Source: Periodic Labour Force Survey Annual Report 2025 (Jan–Dec 2025), usual status (ps+ss), Table 27.</div>
  <div style="margin-top:14px">${lensBtn("workforce", "Workforce")}</div>`;
}
function advScience() {
  const nirf = DATA.wonders.nirf.filter(x => x.category === "Overall" || x.category === "Research Institutions");
  const net = topDistricts("women_internet", 8), lowNet = topDistricts("women_internet", 8, 1);
  const camp = DATA.cities.filter(c => c.districts.some(d => d.id === "campus")).slice(0, 10);
  return `<p class="quote">“${fmtInt(DATA.meta.national.univ)} universities and ${fmtInt(DATA.meta.national.college)} colleges are on our maps. But a woman in ${esc(lowNet[0].name)} is still far less likely to have ever gone online than one in ${esc(net[0].name)}.”</p>
  <div class="grid3"><div class="card"><h3>NIRF 2025: overall</h3><table class="rank">${nirf.filter(x => x.category === "Overall").map(x => `<tr><td>${x.rank}. ${esc(x.name)}</td><td class="n">${x.score ?? ""}</td></tr>`).join("")}</table></div>
  <div class="card"><h3>Women online: highest</h3>${rankTable(net, r => r.v, fmtPct, 8)}<div class="note">NFHS-6, women who have ever used the internet</div></div>
  <div class="card"><h3>Women online: lowest</h3>${rankTable(lowNet, r => r.v, fmtPct, 8)}</div></div>
  <div class="card" style="margin-top:14px"><h3>Cities with a Campus district</h3>${camp.map(c => `<span class="pill" data-cityix="${c.ix}" style="cursor:pointer">${esc(c.name)}</span>`).join("")}</div>
  <div style="margin-top:14px">${lensBtn("science", "Science")} ${lensBtn("women_10yr", "Schooling")} ${lensBtn("women_internet", "Internet")}</div>`;
}
function advCulture() {
  const W_ = DATA.wonders.heritage.slice().sort((a, b) => ((b.visitors_dom || 0) + (b.visitors_for || 0)) - ((a.visitors_dom || 0) + (a.visitors_for || 0)));
  const nat = W_.filter(w => w.type === "natural");
  return `<p class="quote">“${W_.length} World Heritage Wonders stand in our lands. The Taj Mahal alone drew ${fmtBig((W_[0].visitors_dom || 0) + (W_[0].visitors_for || 0))} visitors in 2024.”</p>
  <div class="grid2"><div class="card"><h3>Wonders by visitors (2024)</h3><table class="rank">${W_.filter(w => w.visitors_dom || w.visitors_for).map(w => `<tr><td>★ ${esc(w.name)}</td><td class="n">${fmtBig((w.visitors_dom || 0) + (w.visitors_for || 0))}</td></tr>`).join("")}</table>
  <div class="note">ASI ticketed monuments, India Tourism Data Compendium 2025 (via press coverage). Only the top-10 domestic and top-10 foreign are published.</div></div>
  <div class="card"><h3>All World Heritage Wonders</h3><div>${W_.map(w => `<span class="pill" style="background:${w.type === "natural" ? "#23301f" : "#2c2516"};color:${w.type === "natural" ? "#cfe3b0" : "#f0cf7e"}">${esc(w.name)}</span>`).join("")}</div>
  <div class="note">${nat.length} natural, ${W_.length - nat.length} cultural or mixed. UNESCO list via Wikidata.</div></div></div>
  <div style="margin-top:14px">${lensBtn("culture", "Culture")}</div>`;
}
function advFaith() {
  const n = DATA.meta.national, rel = n.worship_rel;
  const tot = Object.values(rel).reduce((a, b) => a + b, 0);
  const holy = DATA.cities.filter(c => c.districts.some(d => d.id === "holy")).slice(0, 14);
  const dens = topDistricts("worship_per100k", 8);
  return `<p class="quote">“Volunteers have mapped ${fmtBig(tot)} places of worship across the land. That is a measure of mapping as much as of faith, so read it with care.”</p>
  <div class="grid3"><div class="card"><h3>Mapped by tradition</h3><table class="rank">${Object.entries(rel).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${REL_COL[k] || "#888"};margin-right:6px"></i>${esc(k)}</td><td class="n">${fmtInt(v)}</td></tr>`).join("")}</table></div>
  <div class="card"><h3>Densest districts</h3>${rankTable(dens, r => r.v, v => fmtInt(v) + " /100k", 8)}</div>
  <div class="card"><h3>Cities with a Holy Site district</h3>${holy.map(c => `<span class="pill" data-cityix="${c.ix}" style="cursor:pointer">${esc(c.name)}</span>`).join("")}</div></div>
  <div class="note">OpenStreetMap amenity=place_of_worship, religion tag. Unlike Census 2011, this is not a count of believers; India has no newer official religion data.</div>
  <div style="margin-top:14px">${lensBtn("faith", "Faith")}</div>`;
}
function advHealth() {
  const st = topDistricts("stunted", 8), lo = topDistricts("stunted", 8, 1), ins = topDistricts("insurance", 8, 1);
  const avg = natAvg("stunted");
  return `<p class="quote">“About ${Math.round(avg)}% of our children under five are stunted, population-weighted across districts. In ${esc(st[0].name)} it is ${fmtPct(st[0].v)}, while in ${esc(lo[0].name)} it is ${fmtPct(lo[0].v)}.”</p>
  <div class="grid3"><div class="card"><h3>Most stunting</h3>${rankTable(st, r => r.v, fmtPct, 8)}</div>
  <div class="card"><h3>Least stunting</h3>${rankTable(lo, r => r.v, fmtPct, 8)}</div>
  <div class="card"><h3>Least insured</h3>${rankTable(ins, r => r.v, fmtPct, 8)}</div></div>
  <div class="note">NFHS-6 (2023-24) district fact sheets. Manipur was not surveyed.</div>
  <div style="margin-top:14px">${lensBtn("stunted", "Stunting")} ${lensBtn("insurance", "Insurance")} ${lensBtn("child_marriage", "Child marriage")}</div>`;
}
function advMilitary() {
  const S = stateRows().slice().sort((a, b) => (b.military_km2 || 0) - (a.military_km2 || 0));
  const cities = DATA.cities.filter(c => c.districts.some(d => d.id === "encampment")).slice(0, 14);
  const peaks = DATA.wonders.peaks;
  return `<p class="quote">“Our frontier climbs to ${fmtInt(peaks[0]?.elev_m)} m at ${esc(peaks[0]?.name || "")}. Mapped military land is largest in ${esc(S[0].state)}.”</p>
  <div class="grid3"><div class="card"><h3>Military land mapped</h3>${rankTable(S, r => r.military_km2, v => fmtInt(v) + " km²", 8)}<div class="note">OSM landuse=military; sensitive sites are often unmapped.</div></div>
  <div class="card"><h3>Cities with an Encampment</h3>${cities.map(c => `<span class="pill" data-cityix="${c.ix}" style="cursor:pointer">${esc(c.name)}</span>`).join("")}</div>
  <div class="card"><h3>High ground</h3><table class="rank">${peaks.map(p => `<tr><td>▲ ${esc(p.name)}</td><td class="n">${fmtInt(p.elev_m)} m</td></tr>`).join("")}</table></div></div>
  <div style="margin-top:14px">${lensBtn("elev", "Elevation")} ${lensBtn("political", "States")}</div>`;
}
function advEnvironment() {
  const storms = DATA.wonders.storms.slice(0, 8), quakes = DATA.wonders.big_quakes.slice(0, 8);
  const ps = DATA.meta.national.power_src, psn = DATA.meta.national.power_src_n;
  const tot = Object.values(ps).reduce((a, b) => a + b, 0);
  const cyc = topDistricts("cyclones", 6, -1, 0);
  return `<p class="quote">“Since 1990, ${DATA.wonders.storm_count} storms of tropical-storm strength have formed in our seas, and ${fmtInt(DATA.wonders.quake_count_india)} earthquakes of M4.5 or more have struck inside our borders. Plan for both.”</p>
  <div class="grid3"><div class="card"><h3>Strongest storms since 1990</h3><table class="rank">${storms.map(s => `<tr><td>${esc(s.name === "NOT_NAMED" ? "Unnamed" : s.name)} (${s.year})</td><td class="n">${s.wind} kt</td></tr>`).join("")}</table><div class="note">IBTrACS v04r01, North Indian basin</div></div>
  <div class="card"><h3>Largest earthquakes since 1990</h3><table class="rank">${quakes.map(q => `<tr><td>${esc(q.place)}</td><td class="n">M${q.mag}</td></tr>`).join("")}</table><div class="note">USGS ComCat, incl. neighbouring countries in frame</div></div>
  <div class="card"><h3>Mapped power capacity</h3><table class="rank">${Object.entries(ps).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${POWER_COL[k] || "#888"};margin-right:6px"></i>${esc(k.replace("_", " / "))}</td><td class="n">${fmtInt(v / 1000)} GW · ${fmtInt(psn[k])} plants</td></tr>`).join("")}</table>
  <div class="note">Only plants with a capacity tag count toward GW (${fmtInt(tot / 1000)} GW total). Official installed capacity is higher.</div></div></div>
  <div style="margin-top:14px">${lensBtn("disasters", "Disasters")} ${lensBtn("power", "Power")} ${lensBtn("forest", "Forest")} ${lensBtn("rain", "Rainfall")}</div>`;
}
function openAbout() {
  const m = DATA.meta.meta;
  openModal(`<div class="modal-head"><h2 id="modal-title">How this map is made</h2><p>Every tile is a 25 km hexagon (541 km²) on an equal-area projection of India. Each source below was reconciled onto that grid or onto India's ${DATA.meta.national.districts} districts, then translated into game language.</p></div>
  <div class="modal-body">
    <div class="grid2">
      <div class="card"><h3>Game ↔ reality</h3><table class="rank">
        <tr><td><span class="ico food"></span> Food</td><td>Cropland + grassland area; coasts fish; floodplains</td></tr>
        <tr><td><span class="ico prod"></span> Production</td><td>Industrial land, factories, mines, power MW, timber</td></tr>
        <tr><td><span class="ico gold"></span> Gold</td><td>GDP 2024-25: state GSDP split by people + non-residential buildings</td></tr>
        <tr><td><span class="ico sci"></span> Science</td><td>Universities, colleges, research institutes</td></tr>
        <tr><td><span class="ico cult"></span> Culture</td><td>Monuments, museums, arts; +2 on World Heritage tiles</td></tr>
        <tr><td><span class="ico faith"></span> Faith</td><td>Mapped places of worship</td></tr>
        <tr><td>Districts (city)</td><td>Location quotients vs. India's cities</td></tr>
        <tr><td>Citizens</td><td>PLFS 2025 urban workforce mix × 2025 population</td></tr>
        <tr><td>Wonders</td><td>UNESCO list; ranked by 2024 ASI footfall</td></tr>
        <tr><td>Natural wonders</td><td>Parks & tiger reserves by area; highest peaks</td></tr>
        <tr><td>Terrain</td><td>WorldCover land cover + relief + rainfall</td></tr>
      </table><div class="note">Yield pips are sextiles: a tile showing 6 Food is in the top sixth of India's tiles that produce any food.</div></div>
      <div class="card"><h3>Caveats</h3>${m.caveats.map(c => `<p style="margin:0 0 8px;line-height:1.45">${esc(c)}</p>`).join("")}<div class="note">Built ${esc(m.built)}.</div></div>
    </div>
    <h3 style="margin:18px 0 10px;color:var(--gold-2)">${m.sources.length} sources</h3>
    <ul class="src-list">${m.sources.map(s => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a><br><span class="muted">${esc(s.use)}</span></li>`).join("")}</ul>
  </div>`);
}

load().catch(err => { $("#loading").textContent = "Could not load data: " + err.message; console.error(err); });
