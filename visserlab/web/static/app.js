/* VisserLab: веб-интерфейс. Протокол сборщика — docs/COLLECTOR.md. */
(() => {
'use strict';

/* ================= утилиты ================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const num = s => parseFloat(String(s).replace(',', '.'));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const isPhone = () => matchMedia('(max-width: 760px)').matches;
const BY = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) ? 'телефон' : 'ПК';
function fmtClock(sec) {
  if (sec == null || !isFinite(sec)) return '—:—';
  const s = Math.round(sec), a = Math.abs(s), h = Math.floor(a / 3600), m = Math.floor(a % 3600 / 60), ss = a % 60;
  return (s < 0 ? '−' : '') + (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(ss).padStart(2, '0');
}
function fmtDur(sec) {
  if (sec == null || !isFinite(sec)) return '—:—:—';
  const a = Math.max(0, Math.round(sec));
  return Math.floor(a / 3600) + ':' + String(Math.floor(a % 3600 / 60)).padStart(2, '0') + ':' + String(a % 60).padStart(2, '0');
}
function fmtV(v, dp = 2) {
  if (v == null || typeof v !== 'number' || !isFinite(v)) return '—';
  const s = Math.abs(v) >= 10000 ? Math.round(v).toLocaleString('ru-RU') : v.toFixed(dp).replace('.', ',');
  return s.replace('-', '−');
}
const hhmmss = t => new Date(t * 1000).toTimeString().slice(0, 8);
function lowerBound(arr, x) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < x) lo = m + 1; else hi = m; } return lo; }
function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { return null; } }

/* ================= иконки ================= */
const IC = {
  thermo: '<path d="M10 3a2 2 0 0 0-2 2v7.3a3.5 3.5 0 1 0 4 0V5a2 2 0 0 0-2-2z"/><path d="M10 9v5"/>',
  thermal: '<rect x="2.5" y="5" width="15" height="10.5" rx="2"/><circle cx="10" cy="10.25" r="3"/><path d="M5 3h4"/><path d="M14.5 7.5h.01"/>',
  cam: '<rect x="2.5" y="5.5" width="11" height="9" rx="2"/><path d="M13.5 9l4-2.5v7l-4-2.5"/>',
  gas: '<circle cx="10" cy="10" r="2.6"/><circle cx="4" cy="10" r="1.8"/><circle cx="16" cy="10" r="1.8"/><path d="M5.8 10h1.6M12.6 10h1.6"/>',
  drop: '<path d="M10 3.3s-5 5.5-5 9a5 5 0 0 0 10 0c0-3.5-5-9-5-9z"/>',
  gauge: '<path d="M3.5 14a6.5 6.5 0 1 1 13 0"/><path d="M10 14l3.3-4.2"/><circle cx="10" cy="14" r="1"/>',
  o2: '<circle cx="8.5" cy="10" r="4.8"/><path d="M14.5 13.2h3l-3 3.3h3"/>',
  syringe: '<path d="M14 3l3 3M15.5 4.5L7 13l-3 .8.8-3L13.3 2.3"/><path d="M4 16l-2 2M9 8.5l2 2M11.2 6.3l2 2"/>',
  scale: '<path d="M3 16h14l-1.6-7.5H4.6z"/><path d="M7.8 8.5a2.2 2.2 0 0 1 4.4 0"/>',
  calc: '<path d="M15 4H5.5l5 6-5 6H15"/>',
  chip: '<rect x="5" y="5" width="10" height="10" rx="1.5"/><path d="M8 2.5V5M12 2.5V5M8 15v2.5M12 15v2.5M2.5 8H5M2.5 12H5M15 8h2.5M15 12h2.5"/>',
  manual: '<path d="M4 16h3l9-9-3-3-9 9z"/><path d="M11.5 5.5l3 3"/>',
  device: '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M6 8h8M6 12h5"/>',
  sok: '<circle cx="10" cy="10" r="7.5"/><path d="M6.6 10.2l2.4 2.4 4.5-4.9"/>',
  swarn: '<path d="M10 2.8l7.8 13.7H2.2z"/><path d="M10 8v3.6M10 14.2h.01"/>',
  scrit: '<path d="M7 2.5h6l4.5 4.5v6L13 17.5H7L2.5 13V7z"/><path d="M7.6 7.6l4.8 4.8M12.4 7.6l-4.8 4.8"/>',
  lock: '<rect x="4.5" y="9" width="11" height="8" rx="1.5"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9"/>',
  erase: '<path d="M8 16.5h9"/><path d="M3.5 12.5l7-7 5 5-6 6H7.5z"/>',
  home: '<path d="M3 9.5L10 3.5l7 6"/><path d="M5 8v8.5h10V8"/>',
  chev: '<path d="M6 4l4 4-4 4"/>',
  more: '<circle cx="4" cy="10" r=".9"/><circle cx="10" cy="10" r=".9"/><circle cx="16" cy="10" r=".9"/>',
  check: '<path d="M4 10.5l3.5 3.5L16 5.5"/>',
  wide: '<path d="M3 10h14M6 7l-3 3 3 3M14 7l3 3-3 3"/>',
  x: '<path d="M5 5l10 10M15 5L5 15"/>',
  search: '<circle cx="9" cy="9" r="5.5"/><path d="M13 13l4 4"/>',
  refresh: '<path d="M16 10a6 6 0 1 1-1.8-4.3"/><path d="M16.5 3v4h-4"/>',
  stop: '<rect x="5.5" y="5.5" width="9" height="9" rx="1.5"/>',
};
const icon = (k, cls = 'i') => `<svg class="${cls}" viewBox="0 0 20 20" aria-hidden="true">${IC[k] || IC.device}</svg>`;
const KIND = {
  scalar: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 11l3-4 3 3 3-6 3.5 5"/></svg>',
  points: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="4" cy="10" r="1.6"/><circle cx="8.5" cy="6" r="1.6"/><circle cx="12.5" cy="9" r="1.6"/></svg>',
  frame: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 8h12M8 3v10"/></svg>',
  profile: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 12c3 0 3-8 6.5-8s3.5 6 6.5 6"/></svg>',
  video: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.5v9l7.5-4.5z"/></svg>',
};
const KIND_NAME = { scalar: 'временной ряд', points: 'точки', frame: 'кадр', profile: 'профиль', video: 'видео' };
const kindGroup = k => (k === 'scalar' || k === 'points') ? 'ts' : k;
const JG = { user: '✎', mark: '▸', sys: '·', state: '●', set: '⚙', manual: '✚', warn: '⚠', crit: '✕' };
const JCLS = { mark: 'user', state: 'sys' };
const MARK_KINDS = ['user', 'mark', 'manual', 'set', 'warn', 'crit'];

/* ================= состояние ================= */
const S = {
  up: null, why: 'web', port: 8765, off: 0, config: { preroll_s: 300 },
  state: 'idle', run: null, done: null, lastRun: null,
  inventory: [], templates: {}, found: {}, searching: false, lastSearch: null, runs: [],
  scan: { run: false, ids: [], cur: null, frac: 0, text: '', done: {} }, ports: null,
  devices: {}, order: [], devStatus: {},
  alarms: { level: 'ok', items: [] }, events: [], last: {},
  series: {}, frames: {}, profHist: {},
  panels: [], layoutKey: null,
  screen: 'home', view: 'tiles', showMissing: false, sel: new Set(), template: '', draftName: '', cfgDev: null, drafts: {},
  win: 300, cursor: null, pin: null, jf: 'all', ptab: 'graphs', noteT: null,
  openDevs: new Set(), moreDevs: new Set(),
};
let CH = {};
const nowS = () => Date.now() / 1000 + S.off;
const refT = () => (S.run && S.run.t0 != null) ? S.run.t0 : nowS();
const endT = () => S.done ? S.done.end : nowS();
function startT() {
  const r = S.run; if (!r) return nowS() - 300;
  if (r.t0 != null) return r.t0 - (r.preroll != null ? r.preroll : S.config.preroll_s);
  return Math.max(r.prepared || 0, nowS() - S.config.preroll_s);
}

/* ================= связь ================= */
const L = { ws: null, seq: 0, wait: new Map() };
function connect() {
  const q = new URLSearchParams(location.search).get('t');
  if (q) store('vl.token', q);
  const tok = q || store('vl.token');
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws${tok ? '?t=' + encodeURIComponent(tok) : ''}`);
  L.ws = ws;
  ws.onmessage = e => { try { onMessage(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  ws.onclose = e => { L.ws = null; failAll('Нет связи с веб-сервером'); setUp(null, e.code === 4401 ? 'token' : 'web'); setTimeout(connect, 2000); };
}
function failAll(msg) { for (const w of L.wait.values()) w.rej(new Error(msg)); L.wait.clear(); }
function request(cmd, args = {}) {
  return new Promise((res, rej) => {
    if (!L.ws || L.ws.readyState !== 1 || !S.up) { rej(new Error(S.up === false ? 'Сборщик не запущен' : 'Нет связи с веб-сервером')); return; }
    const id = ++L.seq; L.wait.set(id, { res, rej });
    L.ws.send(JSON.stringify({ id, cmd, args }));
  });
}
async function run(cmd, args = {}, ok) {
  try { const r = await request(cmd, args); if (ok) toast(ok); return r; }
  catch (e) { toast(e.message); return undefined; }
}
function setUp(up, why = '', port) {
  S.up = up; S.why = why; if (port) S.port = port;
  if (!up) failAll(why === 'collector' ? 'Сборщик не запущен' : 'Нет связи с веб-сервером');
  const d = $('#down');
  d.hidden = !!up;
  document.body.classList.toggle('has-down', !up);
  if (!up) d.innerHTML = why === 'collector' ? `Сборщик не запущен. Запустите: <code>python -m visserlab collect</code>`
    : why === 'token' ? 'Нужна ссылка с токеном. Её печатает <code>python -m visserlab web --host 0.0.0.0</code>'
    : 'Нет связи с веб-сервером';
  if (S.screen === 'home') renderHome();
}
function onMessage(m) {
  switch (m.type) {
    case 'reply': { const w = L.wait.get(m.id); if (w) { L.wait.delete(m.id); m.ok ? w.res(m.result) : w.rej(new Error(m.error)); } break; }
    case 'collector': setUp(m.up, m.up ? '' : 'collector', m.port); if (m.up) hello(); break;
    case 'state': onState(m); break;
    case 'status': onStatus(m); break;
    case 'data': onData(m); break;
    case 'frame': onFrame(m); break;
    case 'event': onEvent(m.event); break;
    case 'device': onDevice(m.device); break;
    case 'device_status': S.devStatus[m.id] = { ...(S.devStatus[m.id] || {}), status: m.status, reason: m.reason }; break;
    case 'found': S.found = m.found; if (S.screen === 'select') { keepName(); renderSelect(); } break;
    case 'inventory': S.inventory = m.inventory; S.found = m.found; if (S.screen === 'select') { keepName(); renderSelect(); } else if (S.screen === 'settings') renderSettings(); break;
    case 'scan': onScan(m.scan); break;
    case 'lag': hello(); break;
  }
}

/* ================= модель ================= */
async function hello() {
  const snap = await request('hello', { frames: true }).catch(() => null);
  if (snap) applyHello(snap);
}
function applyHello(s) {
  S.off = s.t - Date.now() / 1000;
  S.config = s.config || S.config;
  S.inventory = s.inventory; S.templates = s.templates; S.lastRun = s.last_run;
  for (const i of s.inventory) if (i.found) S.found[i.id] = i.found;
  if (s.scan) S.scan = s.scan;
  if (s.state === 'idle') {
    S.state = 'idle';
    if (S.done) { rerender(); return; }
    if (S.run && S.screen === 'exp') { finishRun(s.last_run); return; }
    S.run = null;
    if (S.screen === 'exp') go('home'); else rerender();
    return;
  }
  S.done = null;
  S.state = s.state;
  const ss = s.session;
  S.run = { name: ss.name, note: ss.note, t0: ss.t0, pauses: ss.pauses, prepared: ss.prepared, preroll: ss.t0 != null ? ss.preroll : null, dir: ss.dir };
  setDevices(s.devices);
  S.alarms = s.alarms; S.events = s.events.slice(); S.last = { ...s.last };
  S.series = {}; S.frames = {}; S.profHist = {};
  loadHistory();
  loadLayout();
  rerender();
}
function setDevices(list) {
  S.devices = {}; S.order = []; CH = {};
  for (const d of list) addDevice(d);
}
function addDevice(d) {
  if (!S.devices[d.id]) S.order.push(d.id);
  for (const cid of Object.keys(CH)) if (CH[cid].dev === d.id) delete CH[cid];
  S.devices[d.id] = d;
  S.devStatus[d.id] = { ...(S.devStatus[d.id] || {}), status: d.status, reason: d.reason };
  for (const c of d.channels) CH[`${d.id}:${c.key}`] = { ...c, id: `${d.id}:${c.key}`, dev: d.id };
}
function loadHistory() {
  for (const c of Object.values(CH)) {
    if (c.kind !== 'scalar' && c.kind !== 'points') continue;
    request('history', { channel: c.id, points: 4000 }).then(r => {
      const cur = S.series[c.id] || { t: [], v: [] };
      const lastT = r.t.length ? r.t[r.t.length - 1] : -Infinity;
      const i = lowerBound(cur.t, lastT + 1e-6);
      S.series[c.id] = { t: r.t.concat(cur.t.slice(i)), v: r.v.concat(cur.v.slice(i)) };
    }).catch(() => {});
  }
}
function onState(m) {
  const prev = S.state;
  S.lastRun = m.last_run;
  if (m.state === 'idle') {
    S.state = 'idle';
    if (S.run && S.screen === 'exp' && prev !== 'prep') finishRun(m.last_run);
    else { S.run = null; if (S.screen === 'exp') go('home'); else rerender(); }
    return;
  }
  if (prev === 'idle' || !S.run) { S.state = m.state; hello(); return; }
  S.state = m.state; S.run.t0 = m.t0; S.run.pauses = m.pauses; S.run.dir = m.dir;
  if (m.t0 != null && S.run.preroll == null) S.run.preroll = m.t0 - Math.max(S.run.prepared, m.t0 - S.config.preroll_s);
  if (S.screen === 'exp') { renderCtrl(); updateTimeline(); renderJournal(); }
  else if (S.screen === 'home') renderHome();
}
function finishRun(lr) {
  const r = S.run;
  const dur = lr && lr.duration_s != null ? lr.duration_s : (r.t0 ? nowS() - r.t0 : 0);
  S.done = { dir: lr ? lr.dir : r.dir, duration: dur, end: (r.t0 || nowS()) + dur };
  S.state = 'idle';
  if (S.screen === 'exp') { renderCtrl(); renderDock(); updateTop(); updateTimeline(); } else rerender();
}
function leaveDone() { S.done = null; S.run = null; S.devices = {}; S.order = []; CH = {}; S.series = {}; S.frames = {}; S.events = []; S.panels = []; }
function onStatus(m) {
  S.off = m.t - Date.now() / 1000;
  S.alarms = m.alarms;
  Object.assign(S.last, m.last);
  for (const [id, d] of Object.entries(m.devices)) S.devStatus[id] = d;
  if (S.state === 'prep') trimPrep();
}
function trimPrep() {
  const edge = nowS() - S.config.preroll_s;
  for (const s of Object.values(S.series)) { const i = lowerBound(s.t, edge); if (i > 200) { s.t.splice(0, i); s.v.splice(0, i); } }
}
function onData(m) {
  if (S.done) return;
  for (const [cid, pts] of Object.entries(m.ch)) {
    const s = S.series[cid] || (S.series[cid] = { t: [], v: [] });
    for (const [t, v] of pts) if (v != null && (!s.t.length || t > s.t[s.t.length - 1])) { s.t.push(t); s.v.push(v); }
    if (pts.length) S.last[cid] = pts[pts.length - 1][1];
  }
}
const DT = { '<u2': Uint16Array, '<i2': Int16Array, '<f4': Float32Array, '<f8': Float64Array, '|u1': Uint8Array, '<u1': Uint8Array };
function b64buf(b64) { const s = atob(b64), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u.buffer; }
function onFrame(m) {
  if (S.done || !CH[m.ch]) return;
  if (m.format === 'jpeg') { const img = new Image(); img.src = 'data:image/jpeg;base64,' + m.b64; S.frames[m.ch] = { t: m.t, img }; return; }
  const A = DT[m.dtype]; if (!A) return;
  const data = new A(b64buf(m.b64));
  S.frames[m.ch] = { t: m.t, data, shape: m.shape };
  if (CH[m.ch].kind === 'profile') {
    const h = S.profHist[m.ch] || (S.profHist[m.ch] = []);
    if (!h.length || m.t - h[h.length - 1].t >= 10) { h.push({ t: m.t, data }); if (h.length > 45) h.shift(); }
  }
}
function onEvent(e) {
  if (!S.run || S.done) return;
  S.events.push(e);
  if (e.kind === 'set' && e.device && e.changes && S.devices[e.device])
    for (const [k, [, nv]] of Object.entries(e.changes)) S.devices[e.device].settings[k] = nv;
  if (S.screen === 'exp') { renderJournal(true); updateTimeline(); }
}
function onDevice(d) {
  if (!S.run) return;
  addDevice(d);
  let changed = false;
  for (const p of S.panels) { const n = p.series.filter(id => CH[id]); if (n.length !== p.series.length) { p.series = n; changed = true; } }
  if (changed) { S.panels = S.panels.filter(p => p.series.length); saveLayout(); }
  if (S.screen === 'exp') { renderDevList(); if (changed) renderDock(); }
}

/* ================= раскладка панелей ================= */
let pSeq = 0;
function mkPanel(series, w = 1) { return { id: 'p' + (++pSeq), kind: kindGroup(CH[series[0]].kind), series: [...series], w }; }
function devViz(id) { return Object.keys(CH).filter(c => CH[c].dev === id); }
function groupForNew(ids) {
  const out = [], byUnit = {};
  for (const id of ids) { const c = CH[id]; if (kindGroup(c.kind) !== 'ts') { out.push([id]); continue; } (byUnit[c.unit] = byUnit[c.unit] || []).push(id); }
  return [...Object.values(byUnit), ...out];
}
function defaultLayout() {
  const rank = { direct: 0, child: 1, calc: 2 };
  const ids = S.order.filter(i => S.devices[i].group in rank).sort((a, b) => rank[S.devices[a].group] - rank[S.devices[b].group]);
  const out = [];
  for (const id of ids) {
    const viz = devViz(id).filter(c => !CH[c].hidden && !(CH[c].at && CH[c].at.length === 3));
    for (const g of groupForNew(viz)) out.push(mkPanel(g));
  }
  const wide = out.find(p => p.kind === 'ts' && p.series.length > 1) || out.find(p => p.kind === 'ts');
  if (wide) { wide.w = 2; out.splice(out.indexOf(wide), 1); out.unshift(wide); }
  return out.slice(0, 8);
}
function loadLayout() {
  S.layoutKey = S.run ? `vl.layout.${Math.round(S.run.prepared)}` : null;
  let saved = null;
  try { saved = JSON.parse(store(S.layoutKey) || 'null'); } catch { saved = null; }
  if (Array.isArray(saved)) {
    S.panels = saved.map(p => ({ ...p, series: p.series.filter(id => CH[id]) })).filter(p => p.series.length);
    pSeq = Math.max(0, ...S.panels.map(p => +String(p.id).slice(1) || 0));
  } else S.panels = defaultLayout();
}
function saveLayout() { if (S.layoutKey) store(S.layoutKey, JSON.stringify(S.panels)); }

/* ================= навигация ================= */
function go(screen) {
  if (S.screen === 'exp' && screen !== 'exp' && S.done) leaveDone();
  S.screen = screen;
  for (const s of ['home', 'select', 'settings', 'exp', 'analysis']) {
    const el = $('#s-' + s); el.hidden = s !== screen;
    if (s !== screen) el.innerHTML = '';        // иначе id полей формы двоятся с окном прибора
  }
  closeCtx(); hideTip();
  rerender();
}
function rerender() {
  ({ home: renderHome, select: renderSelect, settings: renderSettings, exp: renderExp, analysis: renderAnalysis })[S.screen]();
}

/* ================= индикатор состояния ================= */
function statHTML(tag = 'button') {
  const s = S.alarms, lvl = s.level || 'ok', n = (s.items || []).length;
  const tip = lvl === 'ok' ? 'Всё в норме' : s.items.map(a => (a.level === 'crit' ? '✕ ' : '⚠ ') + a.text).join('\n');
  return `<${tag} class="stat ${lvl}"${tag === 'button' ? ' data-act="alarmFilter"' : ''} data-tip="${esc(tip)}" aria-label="${esc(tip)}">${icon({ ok: 'sok', warn: 'swarn', crit: 'scrit' }[lvl])}<b>${n}</b></${tag}>`;
}
const statKey = () => (S.alarms.level || 'ok') + (S.alarms.items || []).map(a => a.text).join('|');

/* ================= окно 0 ================= */
function renderHome() {
  const busy = S.state !== 'idle' && S.run;
  const tpls = Object.entries(S.templates);
  $('#s-home').innerHTML = `<div class="home">
    <header class="brand"><h1>Visser Lab</h1><p>регистратор опытов</p></header>
    <div id="plate">${busy ? plateHTML() : ''}</div>
    <div class="acts2">
      <button class="big" data-act="new" ${busy || !S.up ? 'disabled' : ''}><b>Новый опыт</b><span>${busy ? 'Сначала завершите текущий' : 'Выбрать приборы и начать'}</span></button>
      <button class="big" data-act="analysis"><b>Анализ</b><span>Разбор завершённых опытов</span></button>
    </div>
    <div class="cols2">
      <div><div class="lbl">Шаблоны опытов</div><ul class="list">${tpls.length ? tpls.map(([, t]) => `<li><span>${esc(t.name)}</span><span>приборов: ${t.devices.length}</span></li>`).join('') : '<li><span class="empty-note">нет</span></li>'}</ul></div>
      <div><div class="lbl">Недавние опыты</div><ul class="list" id="runsList">${runsHTML(6)}</ul></div>
    </div>
  </div>`;
  if (S.up) loadRuns();
}
function runsHTML(n) {
  if (!S.runs.length) return '<li><span class="empty-note">пока нет</span></li>';
  return S.runs.slice(0, n).map(x => `<li><span><b>${esc(x.name)}</b>${x.note ? ' · ' + esc(x.note) : ''}</span><span class="num">${esc((x.started || '').slice(5, 16))} · ${x.duration_s != null ? fmtDur(x.duration_s) : 'не завершён'}</span></li>`).join('');
}
async function loadRuns() {
  const r = await request('runs', { limit: 30 }).catch(() => null);
  if (!r) return;
  S.runs = r;
  const el = $('#runsList'); if (el) el.innerHTML = runsHTML(6);
  if (S.screen === 'analysis') renderAnalysis();
}
function plateHTML() {
  const r = S.run, st = S.state;
  const label = { rec: 'Идёт опыт · запись', pause: 'Идёт опыт · пауза', prep: 'Подготовка' }[st];
  return `<div class="plate ${st}">
    <div><div class="st"><span class="dot ${st === 'rec' ? 'rec' : st === 'pause' ? 'warn' : 'ok'}"></span>${label}</div>
      <h2>${esc(r.name)}</h2>
      <div class="meta"><span class="num" id="plateTime">${r.t0 != null ? fmtDur(nowS() - r.t0) : '—:—:—'}</span><span>приборов: ${S.order.filter(i => S.devices[i].group !== 'gateway').length}</span><span id="plateStat">${statHTML('span')}</span></div></div>
    <div class="acts">${st === 'prep' ? '<button class="btn" data-act="cancelPrep">Отменить</button>' : ''}<button class="btn primary" data-act="toExp">Перейти к опыту →</button></div>
  </div>`;
}
function updateHomePlate() {
  if (S.state === 'idle' || !S.run) return;
  const t = $('#plateTime'); if (t && S.run.t0 != null) t.textContent = fmtDur(nowS() - S.run.t0);
  const a = $('#plateStat'); if (a && a.dataset.k !== statKey()) { a.dataset.k = statKey(); a.innerHTML = statHTML('span'); }
}

/* ================= шаг 1: приборы ================= */
const invById = id => S.inventory.find(i => i.id === id);
function needsOf(inv) {
  if (inv.group !== 'calc') return [];
  return [...new Set(Object.values(inv.settings).map(String).filter(v => /^[\w.-]+:[\w.-]+$/.test(v)).map(v => v.split(':')[0]))];
}
function statusOf(inv) {
  if (inv.group === 'manual') return 'manual';
  if (inv.group === 'calc') return 'calc';
  if (S.scan.run && S.scan.cur === inv.id) return 'scanning';
  if (S.scan.run && S.scan.ids.includes(inv.id)) return 'queued';
  if (S.searching) return 'checking';
  const f = S.found[inv.id];
  return f ? (f.ok ? 'ok' : 'missing') : 'unknown';
}
function devAvailable(inv) {
  const st = statusOf(inv);
  if (['missing', 'checking', 'scanning', 'queued'].includes(st)) return false;
  return needsOf(inv).every(n => S.sel.has(n));
}
function connOf(inv) {
  const s = inv.settings || {};
  if (inv.parent) return 'через ' + ((invById(inv.parent) || {}).name || inv.parent);
  if (inv.group === 'manual') return 'ручной ввод';
  if (inv.group === 'calc') return 'из ' + needsOf(inv).map(n => (invById(n) || {}).name || n).join(', ');
  const parts = [];
  if (s.port) parts.push(s.port);
  if (s.baud) parts.push(s.baud + ' бод');
  if (s.addr != null) parts.push('адр. ' + s.addr);
  return parts.join(' · ');
}
function statusChip(st, inv) {
  const note = inv && (S.found[inv.id] || {}).note;
  return { checking: '<span class="chip chk"><span class="dot chk"></span>проверяю…</span>', ok: '<span class="chip ok"><span class="dot ok"></span>найден</span>',
    missing: `<span class="chip err"${note ? ` data-tip="${esc(note)}"` : ''}><span class="dot err"></span>не найден</span>`, unknown: '<span class="chip">не проверен</span>',
    scanning: `<span class="chip chk"><span class="dot chk"></span>перебор <span class="num" data-scanpct>${Math.round(S.scan.frac * 100)}%</span></span>`,
    queued: '<span class="chip">в очереди</span>',
    manual: '<span class="chip">ручной ввод</span>', calc: '<span class="chip">вычисляемый</span>' }[st] || '';
}
function renderSelect() {
  const inv = S.inventory;
  const selectable = inv.filter(i => i.group !== 'gateway');
  const hw = selectable.filter(i => !['manual', 'calc'].includes(i.group));
  const ls = S.lastSearch ? `проверено в ${hhmmss(S.lastSearch)} · найдено ${hw.filter(i => statusOf(i) === 'ok').length} из ${hw.length}` : 'не проверялись';
  const lost = inv.filter(i => i.scan && !i.parent && statusOf(i) !== 'ok'), busy = S.searching || S.scan.run || !S.up;
  const groups = [{ title: 'Прямое подключение', items: inv.filter(i => i.group === 'direct') }];
  for (const g of inv.filter(i => i.group === 'gateway')) groups.push({ title: 'Через ' + g.name, gw: g, items: inv.filter(i => i.parent === g.id) });
  groups.push({ title: 'Ручные и вычисляемые', items: inv.filter(i => ['manual', 'calc'].includes(i.group)) });
  const body = groups.filter(g => g.items.length).map(g => {
    const shown = g.items.filter(i => S.showMissing || statusOf(i) !== 'missing');
    const hidden = g.items.length - shown.length;
    let head = `<div class="grp-h"><span class="lbl">${esc(g.title)}</span>`;
    if (g.gw) { const st = statusOf(g.gw); head += st === 'ok' ? '<span class="chip ok"><span class="dot ok"></span>шлюз на связи</span>' : statusChip(st); }
    head += hidden ? `<button class="hid" data-act="showMissing" data-tip="Показать">скрыто: ${hidden}</button>` : '';
    head += '</div>';
    const items = shown.map(i => S.view === 'tiles' ? tileHTML(i) : rowHTML(i)).join('');
    return `<div class="grp">${head}${S.view === 'tiles' ? `<div class="tiles">${items}</div>` : `<div class="rows">${items}</div>`}</div>`;
  }).join('');
  $('#s-select').innerHTML = `<div class="wiz">
    <div class="wiz-h"><button class="icon-btn" data-act="home" data-tip="Главная" aria-label="Главная">${icon('home')}</button><h2>Новый опыт</h2>
      <div class="steps"><span class="on">1 Приборы</span><span>2 Настройки</span><span>3 Опыт</span></div></div>
    <div class="wiz-row">
      <label class="field"><span class="lbl">Название</span><input type="text" id="runNameNew" value="${esc(S.draftName)}"></label>
      <label class="field"><span class="lbl">Шаблон</span><select id="tplSel"><option value="">—</option>${Object.entries(S.templates).map(([k, t]) => `<option value="${esc(k)}"${k === S.template ? ' selected' : ''}>${esc(t.name)}</option>`).join('')}</select></label>
    </div>
    <div class="toolbar">
      <button class="btn" data-act="refresh" ${busy ? 'disabled' : ''} data-tip="Проверить на текущих настройках">${icon('refresh')}${S.searching ? 'Проверяю…' : 'Обновить'}</button>
      ${S.scan.run ? `<button class="btn warn" data-act="scanStop">${icon('stop')}Стоп</button>`
        : `<button class="btn" data-act="scanAll" ${busy || !lost.length ? 'disabled' : ''} data-tip="Перебор у ненайденных: ${esc([...new Set(lost.map(i => i.scan))].join('; ') || '—')}">${icon('search')}Поиск</button>`}
      ${S.scan.run ? scanLine() : `<span class="num" style="color:var(--muted);font-size:12.5px">${ls}</span>`}
      <span class="sp"></span>
      <label class="sw"><input type="checkbox" id="showMissing" ${S.showMissing ? 'checked' : ''}><span></span>Показать недоступные</label>
      <div class="seg" role="group" aria-label="Вид"><button data-act="view" data-v="tiles" aria-pressed="${S.view === 'tiles'}">Плитки</button><button data-act="view" data-v="list" aria-pressed="${S.view === 'list'}">Список</button></div>
    </div>
    ${body}
    <div class="wiz-f"><span>Выбрано: <b class="num">${S.sel.size}</b></span><span class="sp"></span>
      <button class="btn" data-act="toSettings" ${S.sel.size ? '' : 'disabled'}>Настройки →</button>
      <button class="btn primary" data-act="prepare" ${S.sel.size && S.up && !S.scan.run ? '' : 'disabled'}>Сразу в опыт →</button></div>
  </div>`;
}
function scanPct() { const sc = S.scan, k = Math.max(0, sc.ids.indexOf(sc.cur)); return Math.round(100 * (k + (sc.cur ? sc.frac : 0)) / (sc.ids.length || 1)); }
function scanText() { const sc = S.scan, d = sc.cur && invById(sc.cur); return (d ? d.name + ' · ' : '') + (sc.text || '…'); }
function scanLine() {
  const p = scanPct();
  return `<span class="scan-p" id="scanP"><span class="bar" role="progressbar" aria-label="Перебор" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p}"><i style="width:${p}%"></i></span><span class="txt num">${esc(scanText())}</span></span>`;
}
function updateScan() {
  const el = $('#scanP'); if (!el) return;
  const p = scanPct();
  el.querySelector('i').style.width = p + '%'; el.querySelector('.bar').setAttribute('aria-valuenow', p);
  el.querySelector('.txt').textContent = scanText();
  $$('[data-scanpct]').forEach(e => e.textContent = Math.round(S.scan.frac * 100) + '%');
}
function onScan(sc) {
  const prev = S.scan; S.scan = sc;
  for (const [id, r] of Object.entries(sc.done || {}))           // найденное перебором важнее черновика из ⚙
    if (r.ok && !(prev.done || {})[id] && S.drafts[id]) for (const k of Object.keys(r.settings || {})) delete S.drafts[id][k];
  if (prev.run && !sc.run) {
    const res = Object.entries(sc.done || {});
    if (res.length === 1) { const [id, r] = res[0], d = invById(id); toast(`${d ? d.name : id}: ${r.ok ? connOf(d) : r.note}`); }
    else if (res.length) toast(`Найдено ${res.filter(([, r]) => r.ok).length} из ${res.length}`);
  }
  const redraw = prev.run !== sc.run || prev.cur !== sc.cur;
  if (S.screen === 'select') { if (redraw) { keepName(); renderSelect(); } else updateScan(); }
  else if (S.screen === 'settings' && redraw) renderSettings();
}
async function startScan(ids, port) {
  const args = { settings: S.drafts, by: BY };
  if (ids) args.devices = ids;
  if (port) args.port = port;
  await run('scan', args);
}
function loadPorts() { return request('ports').then(r => { S.ports = r; }).catch(() => {}); }
function portOptions(cur) {
  const list = (S.ports || []).slice();
  if (cur && !list.some(p => p.port === cur)) list.unshift({ port: cur, desc: 'нет в системе', used: [] });
  return list.map(p => `<option value="${esc(p.port)}"${p.port === cur ? ' selected' : ''}>${esc([p.port, p.desc, ...p.used].filter(Boolean).join(' · '))}</option>`).join('');
}
function scanBtn(i) {
  if (statusOf(i) !== 'missing' || !i.scan || i.parent) return '';
  return `<button class="btn sm" data-act="scanOne" data-dev="${esc(i.id)}" data-tip="Перебор: ${esc(i.scan)}"${S.scan.run || S.searching || !S.up ? ' disabled' : ''}>Перебор</button>`;
}
function whyOff(inv) {
  const st = statusOf(inv);
  if (st === 'missing') return (S.found[inv.id] || {}).note || 'не ответил';
  const miss = needsOf(inv).filter(n => !S.sel.has(n));
  return miss.length ? 'нужен ' + miss.map(n => (invById(n) || {}).name || n).join(', ') : '';
}
function tileHTML(i) {
  const on = S.sel.has(i.id), av = devAvailable(i), st = statusOf(i), why = st === 'missing' ? '' : whyOff(i);
  return `<div class="tile${av || on ? '' : ' off'}" role="button" tabindex="0" data-act="sel" data-dev="${esc(i.id)}" aria-pressed="${on}">
    <span class="ck">${on ? icon('check') : ''}</span><span class="ic">${icon(i.icon)}</span>
    <span class="nm">${esc(i.name)}</span><span class="md">${esc(i.model)}</span><span class="cn">${esc(connOf(i))}</span>
    <span class="row">${statusChip(st, i)}${why ? `<span class="md">${esc(why)}</span>` : ''}<span class="sp"></span>${scanBtn(i)}<button class="icon-btn" data-act="gear" data-dev="${esc(i.id)}" data-tip="Настройки" aria-label="Настройки ${esc(i.name)}">⚙</button></span>
  </div>`;
}
function rowHTML(i) {
  const on = S.sel.has(i.id), av = devAvailable(i);
  return `<div class="rowi${av || on ? '' : ' off'}" role="button" tabindex="0" data-act="sel" data-dev="${esc(i.id)}" aria-pressed="${on}">
    <span class="ck2">${on ? icon('check') : ''}</span>${icon(i.icon)}<b>${esc(i.name)}</b><span class="md">${esc(i.model)}</span><span class="cn">${esc(connOf(i))}</span>${statusChip(statusOf(i), i)}<span>${scanBtn(i)}</span>
    <button class="icon-btn" data-act="gear" data-dev="${esc(i.id)}" data-tip="Настройки" aria-label="Настройки ${esc(i.name)}">⚙</button></div>`;
}
async function runRefresh() {
  if (S.searching || S.scan.run) return;
  S.searching = true; keepName(); renderSelect();
  loadPorts();
  const res = await request('discover', { settings: S.drafts }).catch(e => { toast(e.message); return null; });
  S.searching = false;
  if (res) { S.found = res; S.lastSearch = nowS(); for (const id of [...S.sel]) { const i = invById(id); if (i && !devAvailable(i)) S.sel.delete(id); } }
  if (S.screen === 'select') { keepName(); renderSelect(); }
}
function keepName() { const el = $('#runNameNew'); if (el) S.draftName = el.value; }

/* ================= шаг 1.1: настройки ================= */
function renderSettings() {
  const ids = S.inventory.map(i => i.id).filter(i => S.sel.has(i));
  if (!ids.length) { go('select'); return; }
  if (!S.cfgDev || !S.sel.has(S.cfgDev)) S.cfgDev = ids[0];
  const d = invById(S.cfgDev), vals = { ...d.settings, ...(S.drafts[d.id] || {}) };
  const nChanged = id => Object.keys(S.drafts[id] || {}).length;
  $('#s-settings').innerHTML = `<div class="wiz">
    <div class="wiz-h"><button class="icon-btn" data-act="home" data-tip="Главная" aria-label="Главная">${icon('home')}</button><h2>Настройки приборов</h2>
      <div class="steps"><span>1 Приборы</span><span class="on">2 Настройки</span><span>3 Опыт</span></div></div>
    <div class="cfg">
      <nav class="cfg-list">${ids.map(i => { const x = invById(i); return `<button data-act="cfgDev" data-dev="${esc(i)}" aria-current="${i === S.cfgDev}">${icon(x.icon)}<span>${esc(x.name)}<br><small>${nChanged(i) ? 'изменено: ' + nChanged(i) : 'по умолчанию'}</small></span></button>`; }).join('')}</nav>
      <div class="card">
        <div class="card-h">${icon(d.icon)}<h3>${esc(d.name)}</h3><span class="chip">${esc(d.model)}</span><span style="flex:1"></span><button class="btn sm ghost" data-act="cfgReset" data-dev="${esc(d.id)}">По умолчанию</button></div>
        <div class="form" id="cfgForm" data-dev="${esc(d.id)}">${formHTML(d.id, d.schema, vals, false, false)}</div>
      </div>
    </div>
    <div class="wiz-f"><button class="btn" data-act="toSelect">← Приборы</button><span class="sp"></span><button class="btn primary" data-act="prepare" ${S.up && !S.scan.run ? '' : 'disabled'}>В опыт →</button></div>
  </div>`;
}

/* ---------- форма из схемы драйвера ---------- */
function formHTML(devId, schema, vals, lockNonLive, actionsOn) {
  return schema.map(f => {
    const id = `f-${devId}-${f.key}`, v = vals[f.key];
    if (f.type === 'info') return `<div class="f-row"><span class="f-l">${esc(f.label)}</span><span class="f-info">${esc(f.hint)}</span></div>`;
    const locked = lockNonLive && !f.live;
    const dis = locked || (f.type === 'action' && !actionsOn) ? ' disabled' : '';
    let ctl = '';
    if (f.type === 'select') ctl = `<select id="${id}" data-k="${f.key}"${dis}>${f.options.map(([ov, ol]) => `<option value="${esc(ov)}"${String(ov) === String(v) ? ' selected' : ''}>${esc(ol)}</option>`).join('')}</select>`;
    else if (f.type === 'port' && S.ports) ctl = `<select id="${id}" data-k="${f.key}"${dis}>${portOptions(String(v ?? ''))}</select>`;
    else if (f.type === 'number') ctl = `<input id="${id}" data-k="${f.key}" type="number" inputmode="decimal"${f.min != null ? ` min="${f.min}"` : ''}${f.max != null ? ` max="${f.max}"` : ''}${f.step != null ? ` step="${f.step}"` : ''} value="${esc(v)}"${dis}>`;
    else if (f.type === 'toggle') ctl = `<label class="sw"><input id="${id}" data-k="${f.key}" type="checkbox"${v ? ' checked' : ''}${dis}><span></span></label>`;
    else if (f.type === 'action') ctl = `<button type="button" id="${id}" class="btn sm" data-act="devAction" data-dev="${esc(devId)}" data-k="${f.key}"${dis}>${esc(f.label)}</button>`;
    else ctl = `<input id="${id}" data-k="${f.key}" type="text" value="${esc(v)}"${dis}>`;
    const hint = f.hint ? `<span class="ii" tabindex="0" data-tip="${esc(f.hint)}" aria-label="${esc(f.hint)}">i</span>` : '';
    const live = f.live ? '<em data-tip="Можно менять во время записи">на ходу</em>' : '';
    const lock = locked ? `<span class="lk" data-tip="Меняется на паузе" aria-label="Меняется на паузе">${icon('lock')}</span>` : '';
    return `<div class="f-row"><label class="f-l" for="${id}">${esc(f.label)}${live}${hint}${lock}</label>
      <div class="f-c">${ctl}${f.unit && f.type !== 'action' ? `<span class="unit">${esc(f.unit)}</span>` : ''}</div></div>`;
  }).join('');
}
function readForm(root) {
  const o = {};
  $$('[data-k]', root).forEach(el => { if (el.tagName === 'BUTTON') return; o[el.dataset.k] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? num(el.value) : el.value; });
  return o;
}
const same = (a, b) => String(a) === String(b);

/* ================= создание опыта ================= */
async function prepare() {
  keepName();
  const devices = S.inventory.map(i => i.id).filter(i => S.sel.has(i));
  const settings = {};
  for (const id of devices) if (S.drafts[id] && Object.keys(S.drafts[id]).length) settings[id] = S.drafts[id];
  const snap = await run('prepare', { name: S.draftName.trim(), devices, template: S.template || null, settings, by: BY });
  if (!snap) return;
  S.done = null; S.run = null;
  applyHello(snap);
  S.ptab = S.panels.length ? 'graphs' : 'devs';
  go('exp');
}

/* ================= панель опыта ================= */
function renderExp() {
  if (!S.run) { go('home'); return; }
  $('#s-exp').innerHTML = `
    <header class="topbar">
      <button class="icon-btn" data-act="home" data-tip="Главная" aria-label="Главная">${icon('home')}</button>
      <span class="runname" style="display:inline-flex;align-items:center">${esc(S.run.name)}</span>
      <span class="state" id="statePill"></span>
      <div class="clock num" id="clock" data-tip="От старта записи"></div>
      <span id="statBox"></span>
      <div class="ctrl" id="ctrl"></div>
    </header>
    <div class="timeline">
      <div class="tl" id="tl"></div>
      <div class="seg" role="group" aria-label="Окно времени">${[[60, '1 мин'], [300, '5 мин'], [1800, '30 мин'], ['all', 'Всё']].map(([v, l]) => `<button data-act="win" data-v="${v}" aria-pressed="${String(S.win) === String(v)}">${l}</button>`).join('')}</div>
    </div>
    <div class="work">
      <aside class="side">
        <div class="side-h"><span class="lbl">Приборы<span class="ii" tabindex="0" data-tip="Тащите график на поле справа, на панель — наложение.\nAlt — все графики прибора.\nДвойной клик — окно прибора, правый — меню." aria-label="Как пользоваться">i</span></span></div>
        <div class="devlist" id="devList"></div>
        <div class="journal">
          <div class="j-h"><span class="lbl">Журнал<span class="ii" tabindex="0" data-tip="Время заметки — по первому нажатию клавиши.\nПустой Enter — метка.\nЩелчок по записи — отметка на графиках." aria-label="Как пользоваться">i</span></span><div class="j-f">${[['all', 'Все'], ['user', 'Заметки'], ['sys', 'Система'], ['warn', 'Оповещения']].map(([v, l]) => `<button data-act="jf" data-v="${v}" aria-pressed="${S.jf === v}">${l}</button>`).join('')}</div></div>
          <ol class="j-list" id="jList"></ol>
          <form class="j-in" id="jForm"><span class="tchip" id="jT" hidden></span><input type="text" id="jInput" placeholder="Заметка" autocomplete="off" aria-label="Заметка в журнал"><button class="btn sm primary" type="submit" aria-label="В журнал">⏎</button></form>
        </div>
      </aside>
      <main class="dock" id="dock"></main>
    </div>
    <nav class="ptabs">${[['devs', 'Приборы'], ['graphs', 'Графики'], ['journal', 'Журнал']].map(([v, l]) => `<button data-act="ptab" data-v="${v}" aria-pressed="${S.ptab === v}">${l}</button>`).join('')}</nav>`;
  $('#s-exp').dataset.ptab = S.ptab;
  renderCtrl(); renderDevList(); renderJournal(true); renderDock(); updateTop(); updateTimeline();
}
function renderCtrl() {
  const pill = $('#statePill'); if (!pill) return;
  const st = S.done ? 'done' : S.state;
  pill.className = 'state ' + st;
  pill.innerHTML = `<span class="dot"></span>${{ prep: 'Подготовка', rec: 'Запись', pause: 'Пауза', done: 'Завершён', idle: 'Нет опыта' }[st]}`;
  if (st === 'pause') pill.dataset.tip = 'Запись продолжается, отрезок помечен';
  else if (st === 'prep') pill.dataset.tip = `На диск не пишется, держим ${fmtClock(S.config.preroll_s)} предзаписи`;
  else delete pill.dataset.tip;
  const stopOff = `<button class="btn" aria-disabled="true" data-tip="Стоп — только из паузы">■ Стоп</button>`;
  const c = $('#ctrl');
  if (st === 'prep') c.innerHTML = `<button class="btn rec" data-act="start">● Старт</button><button class="btn" disabled>❚❚ Пауза</button>${stopOff}`;
  else if (st === 'rec') c.innerHTML = `<button class="btn warn" data-act="pause">❚❚ Пауза</button>${stopOff}`;
  else if (st === 'pause') c.innerHTML = `<button class="btn primary" data-act="resume">▶ Продолжить</button><button class="btn rec" data-act="stop">■ Стоп</button>`;
  else c.innerHTML = `<button class="btn" data-act="home">На главную</button>`;
}
function updateTop() {
  const ck = $('#clock'); if (!ck) return;
  const txt = S.run.t0 == null ? '—:—:—' : fmtDur(endT() - S.run.t0);
  if (ck.textContent !== txt) ck.textContent = txt;
  const box = $('#statBox');
  if (box.dataset.k !== statKey()) { box.dataset.k = statKey(); box.innerHTML = statHTML(); }
}

/* ---------- список приборов ---------- */
function renderDevList() {
  const el = $('#devList'); if (!el) return;
  const ids = S.order;
  const block = i => {
    const d = S.devices[i], vis = devViz(i), hid = vis.filter(c => CH[c].hidden);
    const row = c => `<div class="v${CH[c].hidden ? ' hid' : ''}" data-drag="chan" data-dev="${esc(i)}" data-chan="${esc(c)}">${KIND[CH[c].kind]}<span class="nm">${esc(CH[c].name)}</span><span class="vv" data-cv="${esc(c)}"></span>${CH[c].at && CH[c].at.length === 3 && (d.actions || []).includes('roi_del') ? `<button class="icon-btn" data-act="roiDel" data-dev="${esc(i)}" data-key="${esc(CH[c].key)}" data-tip="Удалить точку" aria-label="Удалить точку">${icon('x')}</button>` : ''}</div>`;
    return `<div class="dev${S.openDevs.has(i) ? ' open' : ''}${S.moreDevs.has(i) ? ' more' : ''}" data-devrow="${esc(i)}">
      <div class="dev-h" data-drag="dev" data-dev="${esc(i)}">
        ${icon('chev', 'i chev')}<span class="dot" data-st="${esc(i)}"></span>${icon(d.icon)}<span class="nm">${esc(d.name)}</span>
        <span class="vv" data-dv="${esc(i)}"></span><span class="all">все: ${vis.length}</span>
        <button class="icon-btn" data-act="devMenu" data-dev="${esc(i)}" aria-label="Меню ${esc(d.name)}">${icon('more')}</button></div>
      <div class="vz">${vis.filter(c => !CH[c].hidden).map(row).join('')}${hid.map(row).join('')}${hid.length ? `<div class="more-row" data-act="more" data-dev="${esc(i)}">${S.moreDevs.has(i) ? 'скрыть' : 'ещё ' + hid.length}</div>` : ''}</div>
    </div>`;
  };
  const gw = ids.filter(i => S.devices[i].group === 'gateway');
  let html = ids.filter(i => S.devices[i].group === 'direct').map(block).join('');
  for (const g of gw) html += `<div class="gw" data-gw="${esc(g)}">${icon('chip')}<b>${esc(S.devices[g].name)}</b><span class="dot" data-st="${esc(g)}"></span></div>` + ids.filter(i => S.devices[i].parent === g).map(block).join('');
  const rest = ids.filter(i => ['manual', 'calc'].includes(S.devices[i].group));
  if (rest.length) html += `<div class="gw"><b>Ручные и вычисляемые</b></div>` + rest.map(block).join('');
  el.innerHTML = html;
  updateSide();
}
function updateSide() {
  for (const i of S.order) {
    const d = S.devices[i], st = (S.devStatus[i] || {}).status || d.status;
    const dot = $(`[data-st="${CSS.escape(i)}"]`);
    const cls = S.done ? '' : d.group === 'manual' || d.group === 'calc' ? '' : { ok: 'ok', lost: 'err', stale: 'warn', wait: 'chk' }[st] || '';
    if (dot) dot.className = 'dot ' + cls;
    if (d.group === 'gateway') { const g = $(`[data-gw="${CSS.escape(i)}"]`); if (g) g.classList.toggle('err', st === 'lost'); continue; }
    const row = $(`[data-devrow="${CSS.escape(i)}"]`); if (!row) continue;
    row.classList.toggle('lost', st === 'lost' && !S.done);
    const dv = $(`[data-dv="${CSS.escape(i)}"]`);
    if (st === 'lost' && !S.done) { dv.textContent = 'нет связи'; dv.classList.add('stale'); dv.dataset.tip = (S.devStatus[i] || {}).reason || ''; }
    else {
      dv.classList.remove('stale'); delete dv.dataset.tip;
      const c = devViz(i).find(c => !CH[c].hidden && (CH[c].kind === 'scalar' || CH[c].kind === 'points'));
      const fr = devViz(i).find(c => CH[c].kind === 'frame');
      dv.textContent = c ? `${fmtV(S.last[c], CH[c].dp)} ${CH[c].unit}` : fr ? `${fmtV(CH[fr].rate, 0)} к/с` : '';
    }
    for (const c of devViz(i)) {
      const el = $(`[data-cv="${CSS.escape(c)}"]`); if (!el) continue;
      const k = CH[c].kind;
      el.textContent = (k === 'scalar' || k === 'points') ? `${fmtV(S.last[c], CH[c].dp)} ${CH[c].unit}` : KIND_NAME[k];
    }
  }
}

/* ---------- журнал ---------- */
function renderJournal(scroll) {
  const el = $('#jList'); if (!el) return;
  const t0 = S.run.t0;
  const flt = { all: null, user: ['user', 'mark', 'manual'], sys: ['sys', 'set', 'state'], warn: ['warn', 'crit'] }[S.jf];
  const items = S.events.filter(j => !flt || flt.includes(j.kind));
  const stick = scroll || el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
  el.innerHTML = items.map(j => `<li class="${JCLS[j.kind] || j.kind}${S.pin === j.t ? ' pin' : ''}" data-act="jpin" data-a="${j.t}">
    <time>${t0 != null ? fmtClock(j.t - t0) : hhmmss(j.t).slice(0, 5)}</time><span class="g">${JG[j.kind] || '·'}</span>
    <span class="tx">${esc(j.text)}${j.by ? ` <span class="by">· ${esc(j.by)}</span>` : ''}</span></li>`).join('');
  if (stick) el.scrollTop = el.scrollHeight;
}

/* ---------- панели ---------- */
const colorVar = i => `var(--s${(i % 8) + 1})`;
function colorOf(cid) { let h = 0; for (const ch of cid) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h % 8; }
function seriesColors(p) {
  const used = new Set(), out = {};
  for (const id of p.series) { let c = colorOf(id); let n = 0; while (used.has(c) && n++ < 8) c = (c + 1) % 8; used.add(c); out[id] = c; }
  return out;
}
const unitsOf = p => { const u = []; for (const id of p.series) if (CH[id] && !u.includes(CH[id].unit)) u.push(CH[id].unit); return u; };
const findPanel = id => S.panels.find(p => p.id === id);
function panelTitle(p) {
  const devs = [...new Set(p.series.map(id => CH[id].dev))];
  const dn = d => esc(S.devices[d] ? S.devices[d].name : d);
  if (p.kind !== 'ts' || p.series.length === 1) return `${dn(devs[0])} <small>· ${esc(CH[p.series[0]].name)}</small>`;
  return devs.map(dn).join(' + ');
}
function panelHTML(p) {
  const wc = p.w === 2 ? ' w2' : p.w === 3 ? ' w3' : '';
  const dev = S.devices[CH[p.series[0]].dev];
  const roi = p.kind === 'frame' && dev && (dev.actions || []).includes('roi_add');
  const hasRoi = p.kind === 'frame' && devViz(dev.id).some(c => CH[c].at && CH[c].at.length === 3);
  return `<section class="panel${wc}" data-panel="${p.id}">
    <header class="p-h"><span class="t">${panelTitle(p)}${roi ? '<span class="ii" tabindex="0" data-tip="Клик по кадру — точка замера.\nПравый клик по точке — удалить." aria-label="Точки замера">i</span>' : ''}</span><div class="p-tools">
      ${roi ? `<button class="icon-btn" data-act="roiClear" data-dev="${esc(dev.id)}" data-tip="Удалить все точки" aria-label="Удалить все точки"${hasRoi ? '' : ' hidden'}>${icon('erase')}</button>` : ''}
      <button class="icon-btn" data-act="wide" data-p="${p.id}" data-tip="Ширина: 1 → 2 → вся строка" aria-label="Ширина панели">${icon('wide')}</button>
      <button class="icon-btn" data-act="closePanel" data-p="${p.id}" data-tip="Убрать панель" aria-label="Убрать панель">${icon('x')}</button></div></header>
    <div class="p-lg" data-lg="${p.id}"></div>
    <div class="p-b"><canvas data-cv-panel="${p.id}"${roi ? ' class="clickable"' : ''}></canvas></div>
    <div class="drop"></div>
  </section>`;
}
function renderDock() {
  const dock = $('#dock'); if (!dock) return;
  dock.classList.toggle('empty', !S.panels.length);
  dock.innerHTML = (S.done ? `<div class="done-bar"><b>Опыт завершён · ${fmtDur(S.done.duration)}</b><code>${esc(S.done.dir || '')}</code><span class="sp"></span><button class="btn sm primary" data-act="home">На главную</button></div>` : '')
    + `<div class="dgrid">` + S.panels.map(panelHTML).join('')
    + `<div class="dropzone" data-zone="1"><div><b>${isPhone() ? 'Нажмите на график в «Приборах»' : 'Перетащите график сюда'}</b><p>${isPhone() ? 'Долгое нажатие на прибор — все графики' : 'Alt — все графики прибора'}</p></div><div class="drop"></div></div></div>`;
  S.panels.forEach(renderLegend);
  frameCache.clear();
}
function renderLegend(p) {
  const el = $(`[data-lg="${p.id}"]`); if (!el) return;
  if (p.kind === 'frame') { el.innerHTML = `<span class="lg" data-finfo="${p.id}"></span>`; return; }
  if (p.kind === 'video') { el.innerHTML = ''; return; }
  const col = seriesColors(p), units = unitsOf(p);
  el.innerHTML = p.series.map(id => {
    const c = CH[id], right = units.length > 1 && units.indexOf(c.unit) === 1;
    const pref = p.series.length > 1 && c.dev !== CH[p.series[0]].dev ? esc(S.devices[c.dev].name) + ' · ' : '';
    return `<span class="lg" style="--c:${colorVar(col[id])}"><i class="${c.kind === 'points' ? 'pt' : ''}"></i>${pref}${esc(c.name)}${right ? ' <span class="ax">справа</span>' : ''} <b data-lv="${p.id}|${esc(id)}">—</b>${p.kind === 'profile' ? '' : ' ' + esc(c.unit)}${p.series.length > 1 ? `<button class="rx" data-act="rmSeries" data-p="${p.id}" data-c="${esc(id)}" aria-label="Убрать ${esc(c.name)}">×</button>` : ''}</span>`;
  }).join('') + (p.kind === 'profile' ? `<span class="lg"><i style="background:var(--faint)"></i>−5 мин</span>` : '');
}

/* ---------- правила наложения ---------- */
function compat(p, id, unitsSoFar) {
  const c = CH[id], k = kindGroup(c.kind);
  if (p.series.includes(id)) return 'уже на панели';
  if (p.kind === 'frame') return 'На кадр не накладывается. Поставьте на нём точку замера';
  if (p.kind === 'video') return 'На видео не накладывается';
  if (k === 'frame' || k === 'video') return 'Кадр и видео — только своей панелью';
  if (k !== p.kind) return p.kind === 'profile' ? 'На профиль накладывается только профиль' : 'Профиль не накладывается на временной ряд';
  if (!unitsSoFar.includes(c.unit) && unitsSoFar.length >= 2) return `Третья единица (${c.unit}): у панели уже две оси`;
  return null;
}
function planDrop(target, ids) {
  if (target.type === 'new') {
    const groups = groupForNew(ids);
    return { ok: true, label: groups.length > 1 ? `Новые панели: ${groups.length}` : 'Новая панель', apply: () => { groups.forEach(g => S.panels.push(mkPanel(g))); } };
  }
  const p = findPanel(target.id), units = unitsOf(p), ok = [], bad = [];
  for (const id of ids) { const why = compat(p, id, units); if (why) bad.push(why); else { ok.push(id); if (!units.includes(CH[id].unit)) units.push(CH[id].unit); } }
  if (!ok.length) return { ok: false, label: bad[0] };
  return { ok: true, label: ok.length < ids.length ? `Наложить ${ok.length} из ${ids.length}` : 'Наложить', apply: () => { p.series.push(...ok); if (bad.length) toast(`Наложено ${ok.length} из ${ids.length}. ${bad.find(b => b !== 'уже на панели') || ''}`); } };
}
function addPanels(ids) { planDrop({ type: 'new' }, ids).apply(); saveLayout(); renderDock(); }

/* ================= рисование ================= */
let TOK = null;
function readTok() {
  const cs = getComputedStyle(document.documentElement), g = k => cs.getPropertyValue(k).trim();
  TOK = { fg: g('--fg'), muted: g('--muted'), faint: g('--faint'), grid: g('--grid'), panel: g('--panel'), accent: g('--accent'), pause: g('--pause'), rec: g('--rec'), err: g('--err'), s: [1, 2, 3, 4, 5, 6, 7, 8].map(i => g('--s' + i)) };
}
function sizeCanvas(cv) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return null;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function drawAll() {
  readTok();
  for (const p of S.panels) {
    const cv = $(`[data-cv-panel="${p.id}"]`); if (!cv) continue;
    const g = sizeCanvas(cv); if (!g) continue;
    if (p.kind === 'ts') drawTS(p, g); else if (p.kind === 'frame') drawFrame(p, g); else if (p.kind === 'profile') drawProfile(p, g); else if (p.kind === 'video') drawVideo(p, g);
  }
}
function niceStep(range, n) { const raw = range / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p; return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p; }
const T_STEPS = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];
const MIN_SPAN = { '°C': 2, 'ppm': 200, '%': 2, 'Па': 20, 'г/м³': 1, 'г': 1, 'Ом': 1 };
const fmtAxis = (v, st) => { const dp = st >= 1 ? 0 : st >= .1 ? 1 : 2; return Math.abs(v) >= 10000 ? (v / 1000).toFixed(0) + 'k' : v.toFixed(dp).replace('.', ',').replace('-', '−'); };
function yRange(p, units, tA, tB) {
  return units.map(u => {
    let mn = Infinity, mx = -Infinity;
    const scan = (d, i0, i1) => { for (let i = i0; i < i1; i++) { const v = d.v[i]; if (v < mn) mn = v; if (v > mx) mx = v; } };
    for (const id of p.series) { if (CH[id].unit !== u) continue; const d = S.series[id]; if (d) scan(d, Math.max(0, lowerBound(d.t, tA) - 1), Math.min(d.v.length, lowerBound(d.t, tB) + 1)); }
    if (!isFinite(mn)) for (const id of p.series) { if (CH[id].unit !== u) continue; const d = S.series[id]; if (d) scan(d, 0, d.v.length); }
    if (!isFinite(mn)) { mn = 0; mx = 1; }
    const ms = MIN_SPAN[u] || 1; if (mx - mn < ms) { const c = (mx + mn) / 2; mn = c - ms / 2; mx = c + ms / 2; }
    const pad = (mx - mn) * .08; mn -= pad; mx += pad;
    return { u, mn, mx, st: niceStep(mx - mn, 4) };
  });
}
function drawTS(p, { ctx, w, h }) {
  const ref = refT(), tEnd = endT() - ref;
  const tStart = S.win === 'all' ? startT() - ref : tEnd - S.win;
  const units = unitsOf(p), L = 50, R = units.length > 1 ? 50 : 14, T = 8, B = 22, pw = w - L - R, ph = h - T - B;
  if (pw < 20 || ph < 20 || tEnd <= tStart) return;
  const X = t => L + (t - tStart) / (tEnd - tStart) * pw;
  const ys = yRange(p, units, tStart + ref, tEnd + ref);
  const Y = (v, k) => T + ph - (v - ys[k].mn) / (ys[k].mx - ys[k].mn) * ph;
  p.geo = { L, pw, tStart, tEnd };
  ctx.font = '11px "JetBrains Mono", ui-monospace, monospace'; ctx.textBaseline = 'middle';
  for (const [a, b] of (S.run.pauses || [])) {
    const xa = X(a - ref), xb = X((b != null ? b : endT()) - ref); if (xb < L || xa > L + pw) continue;
    ctx.save(); ctx.globalAlpha = .13; ctx.fillStyle = TOK.pause; ctx.fillRect(Math.max(L, xa), T, Math.min(L + pw, xb) - Math.max(L, xa), ph); ctx.restore();
  }
  if (S.run.t0 == null || tStart < 0) { const b = X(S.run.t0 == null ? tEnd : 0); ctx.save(); ctx.globalAlpha = .05; ctx.fillStyle = TOK.fg; ctx.fillRect(L, T, Math.max(0, Math.min(pw, b - L)), ph); ctx.restore(); }
  ctx.strokeStyle = TOK.grid; ctx.lineWidth = 1; ctx.fillStyle = TOK.muted; ctx.textAlign = 'right';
  const y0 = ys[0];
  for (let v = Math.ceil(y0.mn / y0.st) * y0.st; v <= y0.mx; v += y0.st) { const y = Math.round(Y(v, 0)) + .5; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke(); ctx.fillText(fmtAxis(v, y0.st), L - 6, y); }
  if (ys[1]) { ctx.textAlign = 'left'; const y1 = ys[1]; for (let v = Math.ceil(y1.mn / y1.st) * y1.st; v <= y1.mx; v += y1.st) ctx.fillText(fmtAxis(v, y1.st), L + pw + 6, Y(v, 1)); }
  ctx.fillStyle = TOK.faint; ctx.textAlign = 'left'; ctx.fillText(units[0] || '', 4, T + 4); if (units[1]) { ctx.textAlign = 'right'; ctx.fillText(units[1], w - 4, T + 4); }
  const span = tEnd - tStart, st = T_STEPS.find(s => span / s <= 7) || 7200;
  ctx.textAlign = 'center'; ctx.fillStyle = TOK.muted; ctx.textBaseline = 'alphabetic';
  for (let t = Math.ceil(tStart / st) * st; t <= tEnd; t += st) { const x = Math.round(X(t)) + .5; ctx.strokeStyle = TOK.grid; ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + ph); ctx.stroke(); ctx.fillText(st >= 60 ? String(Math.round(t / 60)).replace('-', '−') : fmtClock(t), x, h - 6); }
  ctx.textAlign = 'left'; ctx.fillStyle = TOK.faint; ctx.fillText(st >= 60 ? 't, мин' : 't, мин:с', 4, h - 6);
  ctx.save(); ctx.beginPath(); ctx.rect(L, T, pw, ph); ctx.clip();
  if (S.run.t0 != null && 0 >= tStart) { ctx.strokeStyle = TOK.rec; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(X(0) + .5, T); ctx.lineTo(X(0) + .5, T + ph); ctx.stroke(); }
  for (const j of S.events) {
    if (!MARK_KINDS.includes(j.kind)) continue;
    const x = X(j.t - ref); if (x < L || x > L + pw) continue;
    const pinned = S.pin === j.t;
    ctx.strokeStyle = j.kind === 'crit' ? TOK.err : j.kind === 'warn' ? TOK.pause : pinned ? TOK.accent : TOK.faint;
    ctx.lineWidth = pinned ? 2 : 1; ctx.setLineDash(pinned ? [] : [3, 3]);
    ctx.beginPath(); ctx.moveTo(Math.round(x) + .5, T); ctx.lineTo(Math.round(x) + .5, T + ph); ctx.stroke();
  }
  ctx.setLineDash([]);
  const col = seriesColors(p);
  for (const id of p.series) {
    const d = S.series[id]; if (!d || !d.t.length) continue;
    const k = units.indexOf(CH[id].unit), color = TOK.s[col[id]];
    const i0 = Math.max(0, lowerBound(d.t, tStart + ref) - 1), i1 = Math.min(d.t.length, lowerBound(d.t, tEnd + ref) + 1);
    if (CH[id].kind === 'points') {
      for (let i = i0; i < i1; i++) { ctx.beginPath(); ctx.arc(X(d.t[i] - ref), Y(d.v[i], k), 4, 0, Math.PI * 2); ctx.fillStyle = TOK.panel; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = color; ctx.stroke(); }
      continue;
    }
    const gap = CH[id].rate ? 3 / CH[id].rate + .5 : 30;
    ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.lineJoin = 'round'; ctx.beginPath();
    let bx = null, first, mn, mx, last, prevT = null, started = false;
    const flush = () => { if (bx == null) return; if (!started) { ctx.moveTo(bx, first); started = true; } else ctx.lineTo(bx, first); if (mn !== mx) { ctx.lineTo(bx, mn); ctx.lineTo(bx, mx); } ctx.lineTo(bx, last); };
    for (let i = i0; i < i1; i++) {
      const t = d.t[i]; if (prevT != null && t - prevT > gap) { flush(); bx = null; started = false; }
      prevT = t; const x = Math.round(X(t - ref)), y = Y(d.v[i], k);
      if (x !== bx) { flush(); bx = x; first = mn = mx = last = y; } else { if (y < mn) mn = y; if (y > mx) mx = y; last = y; }
    }
    flush(); ctx.stroke();
    const li = i1 - 1; if (li >= 0 && d.t[li] - ref <= tEnd && d.t[li] - ref >= tStart) { ctx.beginPath(); ctx.arc(X(d.t[li] - ref), Y(d.v[li], k), 2.6, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); }
  }
  if (S.cursor != null && S.cursor >= tStart && S.cursor <= tEnd) { ctx.strokeStyle = TOK.fg; ctx.globalAlpha = .45; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(Math.round(X(S.cursor)) + .5, T); ctx.lineTo(Math.round(X(S.cursor)) + .5, T + ph); ctx.stroke(); ctx.globalAlpha = 1; }
  ctx.restore();
  for (const id of p.series) {
    const b = $(`[data-lv="${p.id}|${CSS.escape(id)}"]`); if (!b) continue;
    const d = S.series[id]; let v = null;
    if (d && d.v.length) {
      if (S.cursor != null) {
        const tc = S.cursor + ref, i = clamp(lowerBound(d.t, tc), 0, d.v.length - 1);
        const j = (i > 0 && Math.abs(d.t[i - 1] - tc) < Math.abs(d.t[i] - tc)) ? i - 1 : i;
        v = CH[id].kind === 'points' && Math.abs(d.t[j] - tc) > 30 ? null : d.v[j];
      } else v = d.v[d.v.length - 1];
    }
    const txt = fmtV(v, CH[id].dp); if (b.textContent !== txt) b.textContent = txt;
  }
}

/* ---------- кадр ---------- */
function lut(stops) { const o = new Uint8ClampedArray(768); for (let i = 0; i < 256; i++) { const x = i / 255; let j = 0; while (j < stops.length - 2 && x > stops[j + 1][0]) j++; const a = stops[j], b = stops[j + 1], f = (x - a[0]) / ((b[0] - a[0]) || 1); for (let k = 0; k < 3; k++) o[i * 3 + k] = a[k + 1] + (b[k + 1] - a[k + 1]) * f; } return o; }
const IRON = lut([[0, 0, 0, 14], [.18, 40, 0, 112], [.38, 146, 0, 146], [.58, 226, 46, 40], [.76, 255, 142, 0], [.9, 255, 222, 44], [1, 255, 255, 232]]);
const frameCache = new Map();
function frameImage(cid) {
  const f = S.frames[cid], c = CH[cid]; if (!f || !f.data) return null;
  const hit = frameCache.get(cid); if (hit && hit.t === f.t) return hit;
  const [H, W] = f.shape, sc = c.scale != null ? c.scale : 1, of = c.offset || 0, d = f.data;
  let mn = Infinity, mx = -Infinity;
  for (let i = 0; i < d.length; i++) { const v = d[i]; if (v < mn) mn = v; if (v > mx) mx = v; }
  if (mx - mn < 1e-9) mx = mn + 1;
  const cv = hit ? hit.cv : document.createElement('canvas'); cv.width = W; cv.height = H;
  const cx = cv.getContext('2d'), img = cx.createImageData(W, H), k = 255 / (mx - mn);
  for (let i = 0; i < d.length; i++) { const q = clamp(Math.round((d[i] - mn) * k), 0, 255) * 3; img.data[i * 4] = IRON[q]; img.data[i * 4 + 1] = IRON[q + 1]; img.data[i * 4 + 2] = IRON[q + 2]; img.data[i * 4 + 3] = 255; }
  cx.putImageData(img, 0, 0);
  const out = { t: f.t, cv, W, H, mn: mn * sc + of, mx: mx * sc + of, raw: d, sc, of };
  frameCache.set(cid, out);
  return out;
}
function drawFrame(p, { ctx, w, h }) {
  const cid = p.series[0], fi = frameImage(cid);
  const info = $(`[data-finfo="${p.id}"]`);
  if (!fi) { ctx.fillStyle = TOK.muted; ctx.font = '12px "Golos Text", system-ui'; ctx.fillText('ждём кадр…', 12, 20); return; }
  const bw = 12, room = w - bw - 44, sc = Math.min(room / fi.W, (h - 8) / fi.H), dw = fi.W * sc, dh = fi.H * sc, ox = Math.max(4, (room - dw) / 2), oy = (h - dh) / 2;
  ctx.imageSmoothingEnabled = true; ctx.drawImage(fi.cv, ox, oy, dw, dh);
  p.geo = { ox, oy, sc, W: fi.W, H: fi.H };
  const dev = CH[cid].dev, fkey = CH[cid].key;
  ctx.font = '10px "JetBrains Mono", ui-monospace, monospace'; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  const tag = (tx, x, y) => { ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(x, y - 13, ctx.measureText(tx).width + 6, 13); ctx.fillStyle = '#fff'; ctx.fillText(tx, x + 3, y - 6.5); };
  for (const r of devViz(dev)) {
    const c = CH[r]; if (!c.at || c.at[0] !== fkey) continue;
    const label = c.name.replace(/^(точка|зона) /, '') + (typeof S.last[r] === 'number' ? ' ' + fmtV(S.last[r], 1) : '');
    if (c.at.length >= 5) {                     // зона или полоса профиля: прямоугольник, задаётся в настройках
      const x = ox + c.at[1] * sc, y = oy + c.at[2] * sc;
      ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = 1; ctx.setLineDash([4, 3]); ctx.strokeRect(x + .5, y + .5, c.at[3] * sc, c.at[4] * sc); ctx.setLineDash([]);
      tag(label, x, Math.max(y, oy + 13));
      continue;
    }
    const x = ox + (c.at[1] + .5) * sc, y = oy + (c.at[2] + .5) * sc;
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(x - 5, y); ctx.lineTo(x + 5, y); ctx.moveTo(x, y - 5); ctx.lineTo(x, y + 5); ctx.stroke();
    tag(label, x + 6, y);
  }
  const bx = ox + dw + 12;
  for (let i = 0; i < dh; i++) { const q = Math.round((1 - i / dh) * 255) * 3; ctx.fillStyle = `rgb(${IRON[q]},${IRON[q + 1]},${IRON[q + 2]})`; ctx.fillRect(bx, oy + i, bw, 1.5); }
  ctx.fillStyle = TOK.muted; ctx.fillText(fmtV(fi.mx, 0) + '°', bx + bw + 4, oy + 6); ctx.fillText(fmtV(fi.mn, 0) + '°', bx + bw + 4, oy + dh - 6);
  if (info) { const d = S.devices[dev]; const txt = `${fmtV(CH[cid].rate, 0)} к/с${d.settings.eps != null ? ' · ε ' + fmtV(d.settings.eps, 2) : ''} · ${fmtV(fi.mn, 1)}…${fmtV(fi.mx, 1)} ${CH[cid].unit}`; if (info.textContent !== txt) info.textContent = txt; }
}
function drawProfile(p, { ctx, w, h }) {
  const cid = p.series[0], f = S.frames[cid], c = CH[cid];
  if (!f || !f.data) { ctx.fillStyle = TOK.muted; ctx.font = '12px "Golos Text", system-ui'; ctx.fillText('ждём профиль…', 12, 20); return; }
  const L = 50, R = 14, T = 8, B = 24, pw = w - L - R, ph = h - T - B; if (pw < 20 || ph < 20) return;
  const [a0, a1, au] = c.axis && c.axis.length ? c.axis : [0, f.data.length - 1, ''];
  const phys = arr => Array.from(arr, v => v * (c.scale != null ? c.scale : 1) + (c.offset || 0));
  const cur = phys(f.data);
  const hist = S.profHist[cid] || [], target = f.t - 300;
  const old = hist.length && hist[0].t <= target + 10 ? phys(hist.reduce((b, x) => Math.abs(x.t - target) < Math.abs(b.t - target) ? x : b).data) : null;
  const all = old ? cur.concat(old) : cur;
  let mn = Math.min(...all), mx = Math.max(...all); if (mx - mn < 4) { mn -= 2; mx += 2; } const pad = (mx - mn) * .08; mn -= pad; mx += pad;
  const st = niceStep(mx - mn, 4), n = cur.length;
  const X = i => L + i / Math.max(1, n - 1) * pw, Y = v => T + ph - (v - mn) / (mx - mn) * ph;
  ctx.font = '11px "JetBrains Mono", ui-monospace, monospace'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right'; ctx.fillStyle = TOK.muted; ctx.strokeStyle = TOK.grid; ctx.lineWidth = 1;
  for (let v = Math.ceil(mn / st) * st; v <= mx; v += st) { const y = Math.round(Y(v)) + .5; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke(); ctx.fillText(fmtAxis(v, st), L - 6, y); }
  ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  const xs = niceStep(a1 - a0, 6);
  for (let x = Math.ceil(a0 / xs) * xs; x <= a1 + 1e-9; x += xs) { const xx = Math.round(L + (x - a0) / (a1 - a0 || 1) * pw) + .5; ctx.beginPath(); ctx.moveTo(xx, T); ctx.lineTo(xx, T + ph); ctx.stroke(); ctx.fillText(fmtAxis(x, xs), xx, h - 7); }
  ctx.fillStyle = TOK.faint; ctx.textAlign = 'left'; ctx.fillText(c.unit, 4, T + 8); if (au) { ctx.textAlign = 'right'; ctx.fillText(au, w - 4, h - 7); }
  const line = (arr, color, dash) => { ctx.strokeStyle = color; ctx.lineWidth = 1.7; ctx.setLineDash(dash); ctx.beginPath(); arr.forEach((v, i) => i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))); ctx.stroke(); ctx.setLineDash([]); };
  if (old) line(old, TOK.faint, [4, 3]);
  line(cur, TOK.s[seriesColors(p)[cid]], []);
  const b = $(`[data-lv="${p.id}|${CSS.escape(cid)}"]`); if (b) b.textContent = `макс ${fmtV(Math.max(...cur), 1)} ${c.unit}`;
}
function drawVideo(p, { ctx, w, h }) {
  const f = S.frames[p.series[0]];
  if (!f || !f.img || !f.img.complete || !f.img.naturalWidth) { ctx.fillStyle = TOK.muted; ctx.font = '12px "Golos Text", system-ui'; ctx.fillText('ждём кадр…', 12, 20); return; }
  const sc = Math.min(w / f.img.naturalWidth, h / f.img.naturalHeight), dw = f.img.naturalWidth * sc, dh = f.img.naturalHeight * sc;
  ctx.drawImage(f.img, (w - dw) / 2, (h - dh) / 2, dw, dh);
}

/* ---------- шкала времени ---------- */
function updateTimeline() {
  const el = $('#tl'); if (!el || !S.run) return;
  const r = S.run, ref = refT(), a0 = startT() - ref, a1 = endT() - ref, span = (a1 - a0) || 1;
  const P = x => clamp((x - a0) / span * 100, 0, 100);
  let h = '';
  if (r.t0 == null) h += `<i class="prep" style="left:0;width:100%"></i><span class="tx" style="left:8px">предзапись ${fmtClock(S.config.preroll_s)}</span>`;
  else {
    h += `<i class="pre" style="left:0;width:${P(0)}%"></i><i class="recd" style="left:${P(0)}%;width:${100 - P(0)}%"></i>`;
    for (const [a, b] of r.pauses || []) { const bb = (b != null ? b : endT()) - ref; h += `<i class="pz" style="left:${P(a - ref)}%;width:${P(bb) - P(a - ref)}%"></i>`; }
    for (const j of S.events) if (MARK_KINDS.includes(j.kind)) h += `<b class="${j.kind === 'mark' ? 'user' : j.kind}" style="left:${P(j.t - ref)}%"></b>`;
    h += `<span class="tx" style="left:6px">${fmtClock(a0)}</span><span class="tx" style="left:calc(${P(0)}% + 5px)">0:00</span>`;
  }
  const ws = S.win === 'all' ? a0 : Math.max(a0, a1 - S.win);
  h += `<span class="win" style="left:${P(ws)}%;width:${100 - P(ws)}%"></span>`;
  el.innerHTML = h;
}

/* ================= перетаскивание ================= */
let drag = null;
function onDown(e) {
  if (S.screen !== 'exp' || e.button !== 0) return;
  const el = e.target.closest('[data-drag]'); if (!el || e.target.closest('[data-act]')) return;
  if (e.pointerType === 'mouse') e.preventDefault();           // не начинать выделение текста
  drag = { x0: e.clientX, y0: e.clientY, devId: el.dataset.dev, chan: el.dataset.chan || null, onHead: !el.dataset.chan, alt: e.altKey, touch: e.pointerType !== 'mouse', lpFired: false, started: false, el };
  if (drag.touch) drag.lp = setTimeout(() => {
    if (!drag || drag.started) return;
    drag.lpFired = true; if (navigator.vibrate) navigator.vibrate(18);
    if (isPhone()) { const ids = drag.onHead ? devViz(drag.devId) : [drag.chan]; addPanels(ids); toast(drag.onHead ? `${S.devices[drag.devId].name}: графиков добавлено — ${ids.length}` : 'График добавлен'); drag = null; return; }
    el.classList.add('lp');
  }, 450);
}
const dragIds = () => (drag.onHead || drag.alt) ? devViz(drag.devId) : [drag.chan];
function onMove(e) {
  if (!drag) return;
  if (!drag.started) {
    if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 6) return;
    if (drag.touch && !drag.lpFired) { clearTimeout(drag.lp); drag = null; return; }
    if (drag.onHead && !drag.alt && !e.altKey && !drag.lpFired) { drag = null; return; }
    drag.started = true; clearTimeout(drag.lp); closeCtx(); hideTip();
    document.body.classList.add('dragging'); const sel = getSelection(); if (sel) sel.removeAllRanges();
  }
  if (e.pointerType === 'mouse') drag.alt = drag.alt || e.altKey;
  const ids = dragIds();
  const g = $('#ghost'); g.hidden = false; g.style.left = e.clientX + 'px'; g.style.top = e.clientY + 'px';
  const d = S.devices[drag.devId];
  g.innerHTML = ids.length > 1 ? `${icon(d.icon)}${esc(d.name)} <span class="n">все: ${ids.length}</span>` : `${KIND[CH[ids[0]].kind].replace('<svg', '<svg class="i" style="width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.5"')}${esc(d.name)} · ${esc(CH[ids[0]].name)}`;
  const tgt = targetAt(e.clientX, e.clientY);
  $$('.d-ok, .d-bad').forEach(x => x.classList.remove('d-ok', 'd-bad'));
  drag.plan = null;
  if (tgt) { const plan = planDrop(tgt, ids); drag.plan = plan; tgt.el.classList.add(plan.ok ? 'd-ok' : 'd-bad'); const dz = $('.drop', tgt.el); if (dz) dz.textContent = plan.label; }
}
function onUp() {
  if (!drag) return;
  clearTimeout(drag.lp); drag.el.classList.remove('lp'); document.body.classList.remove('dragging');
  if (drag.started) {
    $('#ghost').hidden = true; $$('.d-ok, .d-bad').forEach(x => x.classList.remove('d-ok', 'd-bad'));
    if (drag.plan && drag.plan.ok) { drag.plan.apply(); saveLayout(); renderDock(); } else if (drag.plan) toast(drag.plan.label);
  } else if (isPhone() && drag.chan && !drag.lpFired) { addPanels([drag.chan]); toast('График добавлен'); }
  drag = null;
}
function targetAt(x, y) {
  const el = document.elementFromPoint(x, y); if (!el) return null;
  const p = el.closest('[data-panel]'); if (p) return { type: 'panel', id: p.dataset.panel, el: p };
  const z = el.closest('.dropzone'); if (z) return { type: 'new', el: z };
  const d = el.closest('.dock'); if (d) return { type: 'new', el: $('.dropzone', d) };
  return null;
}
document.addEventListener('pointerdown', onDown);
document.addEventListener('pointermove', onMove);
document.addEventListener('pointerup', onUp);
document.addEventListener('pointercancel', () => { if (drag) { clearTimeout(drag.lp); drag.el.classList.remove('lp'); document.body.classList.remove('dragging'); $('#ghost').hidden = true; drag = null; } });
document.addEventListener('touchmove', e => { if (drag && (drag.started || drag.lpFired)) e.preventDefault(); }, { passive: false });
addEventListener('keydown', e => { if (e.key === 'Alt') { document.body.classList.add('alt'); e.preventDefault(); } if (e.key === 'Escape') { closeCtx(); closeModal(); } });
addEventListener('keyup', e => { if (e.key === 'Alt') { document.body.classList.remove('alt'); e.preventDefault(); } });
addEventListener('blur', () => document.body.classList.remove('alt'));

/* курсор времени: наведение синхронно по всем графикам */
document.addEventListener('pointermove', e => {
  if (S.screen !== 'exp' || drag) return;
  const cv = e.target.closest && e.target.closest('canvas[data-cv-panel]');
  if (!cv) { S.cursor = null; return; }
  const p = findPanel(cv.dataset.cvPanel); if (!p || p.kind !== 'ts' || !p.geo) { S.cursor = null; return; }
  const x = e.clientX - cv.getBoundingClientRect().left;
  S.cursor = x < p.geo.L || x > p.geo.L + p.geo.pw ? null : p.geo.tStart + (x - p.geo.L) / p.geo.pw * (p.geo.tEnd - p.geo.tStart);
});

/* ================= окно прибора ================= */
let M = null;
function openDevWin(devId, tab) {
  const d = S.devices[devId] || invById(devId);
  if (!d) return;
  const live = !!S.devices[devId] && !S.done;
  const canAdd = live && (d.actions || []).includes('add');
  M = { id: devId, live, tab: tab || (canAdd ? 'input' : 'set'), draft: { ...(live ? d.settings : { ...d.settings, ...(S.drafts[devId] || {}) }) } };
  renderModal(); $('#modal').hidden = false;
  if (!S.ports) loadPorts().then(() => { if (M && M.tab === 'set' && S.ports) { M.draft = { ...M.draft, ...readForm($('#mForm')) }; renderModal(); } });
}

/* ---------- окно перебора: выбрать порт и начать ---------- */
let SW = null;
function openScanWin(id) {
  const d = invById(id); if (!d) return;
  const pf = (d.schema || []).find(f => f.type === 'port');
  if (!pf) { startScan([id]); return; }
  M = null; SW = { id, port: String({ ...d.settings, ...(S.drafts[id] || {}) }[pf.key] ?? '') };
  renderScanWin(); $('#modal').hidden = false;
  loadPorts().then(() => { if (SW) { SW.port = $('#scanPort').value; renderScanWin(); } });
}
function renderScanWin() {
  const d = invById(SW.id); if (!d) { closeModal(); return; }
  $('#modal').innerHTML = `<div class="modal narrow" role="dialog" aria-modal="true" aria-label="Перебор: ${esc(d.name)}">
    <div class="m-h"><span class="ic">${icon('search')}</span><h3>Перебор · ${esc(d.name)}</h3><button class="icon-btn" data-act="mClose" aria-label="Закрыть">${icon('x')}</button>
      <div class="sub"><span>${esc(d.model)}</span><span class="mono">${esc(connOf(d))}</span></div></div>
    <div class="m-b"><div class="form">
      <div class="f-row"><label class="f-l" for="scanPort">Порт</label><div class="f-c"><select id="scanPort">${portOptions(SW.port)}</select></div></div>
      <div class="f-row"><span class="f-l">Перебираем</span><span class="f-info">${esc(d.scan)}</span></div>
    </div></div>
    <div class="m-f"><span class="sp"></span><button class="btn" data-act="mClose">Отмена</button><button class="btn primary" data-act="scanGo">Начать</button></div>
  </div>`;
}
function devOf(M) { return M.live ? S.devices[M.id] : invById(M.id); }
function renderModal() {
  const d = devOf(M); if (!d) { closeModal(); return; }
  const lock = M.live && S.state === 'rec';
  const canAdd = M.live && (d.actions || []).includes('add');
  const tabs = [['set', 'Настройки'], ...(d.channels ? [['ch', 'Каналы']] : []), ...(M.live ? [['diag', 'Диагностика']] : []), ...(canAdd ? [['input', 'Ввод отсчёта']] : [])];
  const stt = (S.devStatus[M.id] || {}).status;
  const status = !M.live ? statusChip(statusOf(d)) : stt === 'ok' ? '<span class="chip ok"><span class="dot ok"></span>на связи</span>' : stt === 'lost' ? `<span class="chip err"><span class="dot err"></span>нет связи</span>` : stt === 'stale' ? '<span class="chip err"><span class="dot warn"></span>нет данных</span>' : '';
  let body = '';
  if (M.tab === 'set') body = `<div class="form" id="mForm">${formHTML(M.id, d.schema, M.draft, lock, M.live)}</div>${lock && d.schema.some(f => f.type !== 'info' && f.type !== 'action' && !f.live) ? '<p class="lockline">Идёт запись: поля с замком меняются на паузе.</p>' : ''}`;
  else if (M.tab === 'ch') body = `<table class="t"><thead><tr><th>Канал</th><th>Тип</th><th>Ед.</th><th>Частота</th></tr></thead><tbody>${d.channels.map(c => `<tr><td>${esc(c.name)}</td><td>${KIND_NAME[c.kind]}</td><td class="mono">${esc(c.unit || '—')}</td><td class="mono">${c.rate ? (c.rate >= 1 ? fmtV(c.rate, c.rate % 1 ? 1 : 0) + ' Гц' : 'раз в ' + fmtV(1 / c.rate, 0) + ' с') : c.kind === 'points' ? 'вручную' : 'по входам'}</td></tr>`).join('')}</tbody></table>`;
  else if (M.tab === 'diag') { const ds = S.devStatus[M.id] || {}; body = `<dl class="kv"><dt>Статус</dt><dd>${esc({ ok: 'на связи', lost: 'нет связи', stale: 'нет данных', wait: 'ждём данных' }[ds.status] || ds.status || '—')}</dd>${ds.reason ? `<dt>Причина</dt><dd>${esc(ds.reason)}</dd>` : ''}<dt>Последний отсчёт</dt><dd class="num">${ds.age != null ? fmtV(ds.age, 1) + ' с назад' : '—'}</dd><dt>Драйвер</dt><dd class="mono">${esc(d.driver)}</dd></dl>${['direct', 'gateway', 'child'].includes(d.group) ? '<p><button class="btn sm" data-act="reconnect">Переподключить</button></p>' : ''}`; }
  else if (M.tab === 'input') { const c = d.channels[0]; body = `<div class="form"><div class="f-row"><label class="f-l" for="mVal">${esc(c.name)}</label><div class="f-c"><input type="number" id="mVal" step="any" inputmode="decimal"><span class="unit">${esc(c.unit)}</span><button class="btn sm primary" data-act="manualAdd">Записать</button></div></div></div>`; }
  $('#modal').innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(d.name)}">
    <div class="m-h"><span class="ic">${icon(d.icon)}</span><h3>${esc(d.name)}</h3><button class="icon-btn" data-act="mClose" aria-label="Закрыть">${icon('x')}</button>
      <div class="sub"><span>${esc(d.model)}</span>${M.live ? '' : `<span class="mono">${esc(connOf(d))}</span>`}${status}</div></div>
    <div class="m-tabs" role="tablist">${tabs.map(([v, l]) => `<button role="tab" data-act="mTab" data-v="${v}" aria-selected="${M.tab === v}">${l}</button>`).join('')}</div>
    <div class="m-b">${body}</div>
    <div class="m-f">${M.tab === 'set' ? `<button class="btn ghost" data-act="mReset">По умолчанию</button>` : ''}<span class="sp"></span><button class="btn" data-act="mClose">Закрыть</button>${M.tab === 'set' ? '<button class="btn primary" data-act="mApply">Применить</button>' : ''}</div>
  </div>`;
  if (M.tab === 'input') setTimeout(() => { const el = $('#mVal'); if (el) el.focus(); }, 0);
}
function closeModal() { $('#modal').hidden = true; M = null; SW = null; }
async function applyModal() {
  const d = devOf(M);
  M.draft = { ...M.draft, ...readForm($('#mForm')) };
  const changes = {};
  for (const f of d.schema) if (f.type !== 'info' && f.type !== 'action' && !same(M.draft[f.key], d.settings[f.key])) changes[f.key] = M.draft[f.key];
  if (!M.live) {                                // шаг 1: настройки уходят в prepare
    const cur = { ...(S.drafts[M.id] || {}) };
    for (const f of d.schema) if (f.key in M.draft) { if (same(M.draft[f.key], d.settings[f.key])) delete cur[f.key]; else cur[f.key] = M.draft[f.key]; }
    S.drafts[M.id] = cur; closeModal(); toast('Настройки сохранены до старта опыта'); rerender(); return;
  }
  if (!Object.keys(changes).length) { closeModal(); toast('Изменений нет'); return; }
  const r = await run('set', { device: M.id, changes, by: BY });
  if (r) { closeModal(); toast(`${d.name}: изменений ${Object.keys(r.changed).length}`); }
}
function defaultsOf(schema) { const o = {}; for (const f of schema) if (f.type !== 'info' && f.type !== 'action') o[f.key] = f.default; return o; }

/* ================= контекстное меню ================= */
function showCtx(html, x, y) { const c = $('#ctx'); c.innerHTML = html; c.hidden = false; const r = c.getBoundingClientRect(); c.style.left = Math.min(x, innerWidth - r.width - 8) + 'px'; c.style.top = Math.min(y, innerHeight - r.height - 8) + 'px'; }
function openCtx(x, y, devId) {
  const d = S.devices[devId]; if (!d) return;
  showCtx(`<button data-act="ctxOpen" data-dev="${esc(devId)}">Окно прибора <small>двойной клик</small></button>
    ${d.group === 'gateway' ? '' : `<button data-act="ctxAll" data-dev="${esc(devId)}">Все графики <small>Alt + тащить</small></button>`}
    ${S.done ? '' : `<button data-act="ctxReconnect" data-dev="${esc(devId)}">Переподключить</button>`}`, x, y);
}
function closeCtx() { $('#ctx').hidden = true; }
function roiAt(cv, p, e) {
  const rc = cv.getBoundingClientRect(), x = e.clientX - rc.left, y = e.clientY - rc.top, dev = CH[p.series[0]].dev, fkey = CH[p.series[0]].key;
  return devViz(dev).map(c => CH[c]).find(c => c.at && c.at.length === 3 && c.at[0] === fkey && Math.hypot(p.geo.ox + (c.at[1] + .5) * p.geo.sc - x, p.geo.oy + (c.at[2] + .5) * p.geo.sc - y) < 10);
}
document.addEventListener('contextmenu', e => {
  if (S.screen !== 'exp') return;
  const h = e.target.closest('[data-drag="dev"]'), g = e.target.closest('[data-gw]'), cv = e.target.closest('canvas[data-cv-panel]');
  if (h) { e.preventDefault(); openCtx(e.clientX, e.clientY, h.dataset.dev); }
  else if (g && g.dataset.gw) { e.preventDefault(); openCtx(e.clientX, e.clientY, g.dataset.gw); }
  else if (cv && !S.done) {
    const p = findPanel(cv.dataset.cvPanel); if (!p || p.kind !== 'frame' || !p.geo) return;
    const dev = CH[p.series[0]].dev; if (!(S.devices[dev].actions || []).includes('roi_del')) return;
    const q = roiAt(cv, p, e); const any = devViz(dev).some(c => CH[c].at && CH[c].at.length === 3); if (!any) return;
    e.preventDefault();
    showCtx((q ? `<button data-act="roiDel" data-dev="${esc(dev)}" data-key="${esc(q.key)}">Удалить ${esc(q.name)}</button>` : '') + `<button data-act="roiClear" data-dev="${esc(dev)}">Удалить все точки</button>`, e.clientX, e.clientY);
  }
});
document.addEventListener('dblclick', e => {
  if (S.screen !== 'exp') return;
  const h = e.target.closest('[data-drag="dev"]'); if (h) { openDevWin(h.dataset.dev); return; }
  const g = e.target.closest('[data-gw]'); if (g && g.dataset.gw) openDevWin(g.dataset.gw);
});

/* ================= анализ (пока список) ================= */
function renderAnalysis() {
  $('#s-analysis').innerHTML = `<div class="an">
    <div class="wiz-h"><button class="icon-btn" data-act="home" data-tip="Главная" aria-label="Главная">${icon('home')}</button><h2 style="margin:0;font:600 20px/1.2 var(--f-brand)">Анализ</h2></div>
    <p class="note" style="border:0;padding:0">Разбор опыта будет открываться отдельным окном. Пока — список опытов на диске.</p>
    <div class="an-t"><table class="t"><thead><tr><th>Опыт</th><th>Начало</th><th>Длительность</th><th>Приборов</th><th>Заметка</th><th>Папка</th></tr></thead><tbody>
      ${S.runs.map(x => `<tr><td><b>${esc(x.name)}</b></td><td class="mono">${esc(x.started || '—')}</td><td class="mono">${x.duration_s != null ? fmtDur(x.duration_s) : 'не завершён'}</td><td class="mono">${x.devices}</td><td>${esc(x.note)}</td><td class="mono">${esc(x.run)}</td></tr>`).join('') || '<tr><td colspan="6" class="empty-note">пока нет</td></tr>'}
    </tbody></table></div></div>`;
}

/* ================= действия ================= */
let toastT = 0;
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, 3500); }
function setPtab(v) { S.ptab = v; $('#s-exp').dataset.ptab = v; $$('[data-act="ptab"]').forEach(x => x.setAttribute('aria-pressed', x.dataset.v === v)); if (v === 'journal') renderJournal(true); }
const ACT = {
  home: () => { closeModal(); go('home'); },
  toExp: () => go('exp'),
  cancelPrep: () => run('cancel', { by: BY }),
  new: () => { S.sel = new Set(); S.drafts = {}; S.template = ''; S.draftName = `опыт_${hhmmss(nowS()).slice(0, 5).replace(':', '')}`; go('select'); if (!S.lastSearch) runRefresh(); else loadPorts(); },
  analysis: () => { closeModal(); go('analysis'); loadRuns(); },
  refresh: runRefresh,
  scanAll: () => { keepName(); startScan(null); },
  scanOne: (b, e) => { e.stopPropagation(); keepName(); openScanWin(b.dataset.dev); },
  scanGo: () => { const id = SW.id, port = $('#scanPort').value; closeModal(); startScan([id], port); },
  scanStop: () => run('scan_stop'),
  showMissing: () => { keepName(); S.showMissing = true; renderSelect(); },
  view: b => { keepName(); S.view = b.dataset.v; renderSelect(); },
  sel: b => {
    const i = invById(b.dataset.dev);
    if (!S.sel.has(i.id) && !devAvailable(i)) {
      const st = statusOf(i);
      toast(st === 'missing' ? `${i.name} не найден. ${i.scan ? 'Перебор или ⚙' : 'Параметры — в ⚙'}` : st === 'scanning' || st === 'queued' ? `${i.name}: идёт перебор` : st === 'checking' ? `${i.name}: проверяю…` : `${i.name}: ${whyOff(i)}`);
      return;
    }
    S.sel.has(i.id) ? S.sel.delete(i.id) : S.sel.add(i.id);
    for (const x of S.inventory) if (S.sel.has(x.id) && needsOf(x).some(n => !S.sel.has(n))) S.sel.delete(x.id);
    keepName(); renderSelect();
  },
  gear: (b, e) => { e.stopPropagation(); keepName(); openDevWin(b.dataset.dev, 'set'); },
  toSettings: () => { keepName(); go('settings'); },
  toSelect: () => go('select'),
  prepare: () => prepare(),
  cfgDev: b => { S.cfgDev = b.dataset.dev; renderSettings(); },
  cfgReset: b => { delete S.drafts[b.dataset.dev]; renderSettings(); },
  start: () => run('start', { by: BY }), pause: () => run('pause', { by: BY }), resume: () => run('resume', { by: BY }), stop: () => run('stop', { by: BY }),
  win: b => { S.win = b.dataset.v === 'all' ? 'all' : +b.dataset.v; $$('[data-act="win"]').forEach(x => x.setAttribute('aria-pressed', x === b)); updateTimeline(); },
  wide: b => { const p = findPanel(b.dataset.p), g = $('.dgrid'); const cols = g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 1; const order = cols >= 3 ? [1, 2, 3] : [1, 3]; p.w = order[(order.indexOf(p.w) + 1) % order.length]; saveLayout(); renderDock(); },
  closePanel: b => { S.panels = S.panels.filter(p => p.id !== b.dataset.p); saveLayout(); renderDock(); },
  rmSeries: b => { const p = findPanel(b.dataset.p); p.series = p.series.filter(id => id !== b.dataset.c); saveLayout(); renderDock(); },
  more: b => { const id = b.dataset.dev; S.moreDevs.has(id) ? S.moreDevs.delete(id) : S.moreDevs.add(id); renderDevList(); },
  jf: b => { S.jf = b.dataset.v; $$('[data-act="jf"]').forEach(x => x.setAttribute('aria-pressed', x === b)); renderJournal(true); },
  alarmFilter: () => { S.jf = 'warn'; if (isPhone()) setPtab('journal'); $$('[data-act="jf"]').forEach(x => x.setAttribute('aria-pressed', x.dataset.v === 'warn')); renderJournal(true); },
  jpin: b => { const a = +b.dataset.a; S.pin = S.pin === a ? null : a; if (S.pin != null && S.win !== 'all' && a < endT() - S.win) { S.win = 'all'; $$('[data-act="win"]').forEach(x => x.setAttribute('aria-pressed', x.dataset.v === 'all')); updateTimeline(); } renderJournal(); },
  ptab: b => setPtab(b.dataset.v),
  devMenu: (b, e) => { e.stopPropagation(); const r = b.getBoundingClientRect(); openCtx(r.left, r.bottom + 4, b.dataset.dev); },
  ctxOpen: b => { closeCtx(); openDevWin(b.dataset.dev); },
  ctxAll: b => { closeCtx(); const ids = devViz(b.dataset.dev); addPanels(ids); toast(`${S.devices[b.dataset.dev].name}: графиков добавлено — ${ids.length}`); },
  ctxReconnect: b => { closeCtx(); run('action', { device: b.dataset.dev, name: 'reconnect', by: BY }); },
  roiDel: b => { closeCtx(); run('action', { device: b.dataset.dev, name: 'roi_del', args: { key: b.dataset.key }, by: BY }); },
  roiClear: b => { closeCtx(); run('action', { device: b.dataset.dev, name: 'roi_clear', by: BY }); },
  mClose: closeModal, mApply: applyModal,
  mTab: b => { if (M.tab === 'set') M.draft = { ...M.draft, ...readForm($('#mForm')) }; M.tab = b.dataset.v; renderModal(); },
  mReset: () => { M.draft = { ...M.draft, ...defaultsOf(devOf(M).schema) }; renderModal(); },
  devAction: b => run('action', { device: b.dataset.dev, name: b.dataset.k, by: BY }),
  reconnect: () => { run('action', { device: M.id, name: 'reconnect', by: BY }); closeModal(); },
  manualAdd: async () => {
    const v = num($('#mVal').value); if (!isFinite(v)) { toast('Введите число'); return; }
    const r = await run('action', { device: M.id, name: 'add', args: { value: v }, by: BY });
    if (r) { closeModal(); toast('Отсчёт записан'); }
  },
};
document.addEventListener('click', e => {
  const hd = e.target.closest('.dev-h');
  if (hd && !e.target.closest('[data-act]')) { const id = hd.dataset.dev; hd.parentElement.classList.toggle('open'); S.openDevs.has(id) ? S.openDevs.delete(id) : S.openDevs.add(id); return; }
  const b = e.target.closest('[data-act]');
  if (!b) { if (!e.target.closest('.ctx')) closeCtx(); if (e.target.id === 'modal') closeModal(); return; }
  if (b.disabled || b.getAttribute('aria-disabled') === 'true') return;
  if (!b.closest('.ctx')) closeCtx();
  const f = ACT[b.dataset.act]; if (f) f(b, e);
});
document.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[role="button"][data-act]')) { e.preventDefault(); e.target.click(); } });
document.addEventListener('change', e => {
  if (e.target.id === 'showMissing') { keepName(); S.showMissing = e.target.checked; renderSelect(); }
  else if (e.target.id === 'tplSel') {
    keepName(); S.template = e.target.value; const t = S.templates[S.template];
    if (t) { S.sel = new Set(t.devices.filter(i => { const x = invById(i); return x && statusOf(x) !== 'missing'; })); if (!S.draftName || /^опыт_/.test(S.draftName)) S.draftName = t.name; }
    renderSelect();
  }
  else if (e.target.closest('#cfgForm')) {
    const id = $('#cfgForm').dataset.dev, d = invById(id), vals = readForm($('#cfgForm')), cur = {};
    for (const [k, v] of Object.entries(vals)) if (!same(v, d.settings[k])) cur[k] = v;
    S.drafts[id] = cur; renderSettings();
  }
});
/* журнал: время заметки = первое нажатие клавиши */
document.addEventListener('input', e => {
  if (e.target.id !== 'jInput') return;
  const v = e.target.value;
  if (v && S.noteT == null) S.noteT = nowS(); if (!v) S.noteT = null;
  const chip = $('#jT'); chip.hidden = S.noteT == null;
  if (S.noteT != null) chip.textContent = S.run.t0 != null ? fmtClock(S.noteT - S.run.t0) : hhmmss(S.noteT);
});
document.addEventListener('submit', async e => {
  if (e.target.id !== 'jForm') return; e.preventDefault();
  if (S.done) { toast('Опыт завершён'); return; }
  const inp = $('#jInput'), text = inp.value.trim(), t = S.noteT;
  inp.value = ''; S.noteT = null; $('#jT').hidden = true;
  await run(text ? 'note' : 'mark', text ? { text, t, by: BY } : { by: BY });
});
/* точка замера: клик по кадру */
document.addEventListener('click', e => {
  const cv = e.target.closest && e.target.closest('canvas[data-cv-panel]'); if (!cv || S.done) return;
  const p = findPanel(cv.dataset.cvPanel); if (!p || p.kind !== 'frame' || !p.geo) return;
  const dev = CH[p.series[0]].dev; if (!(S.devices[dev].actions || []).includes('roi_add') || roiAt(cv, p, e)) return;
  const rc = cv.getBoundingClientRect(), x = Math.floor((e.clientX - rc.left - p.geo.ox) / p.geo.sc), y = Math.floor((e.clientY - rc.top - p.geo.oy) / p.geo.sc);
  if (x < 0 || y < 0 || x >= p.geo.W || y >= p.geo.H) return;
  run('action', { device: dev, name: 'roi_add', args: { x, y }, by: BY }).then(r => { if (r && r.name) { S.openDevs.add(dev); renderDevList(); $$('[data-act="roiClear"]').forEach(b => b.hidden = false); toast(`Точка ${r.name}`); } });
});

/* ================= подсказки ================= */
const tipEl = $('#tip'); let tipT = 0, tipFor = null;
function showTip(el) {
  const txt = el.dataset.tip; if (!txt || !document.contains(el)) return;
  tipEl.textContent = txt; tipEl.hidden = false;
  const r = el.getBoundingClientRect(), t = tipEl.getBoundingClientRect();
  let y = r.bottom + 8; if (y + t.height > innerHeight - 8) y = r.top - t.height - 8;
  tipEl.style.left = clamp(r.left + r.width / 2 - t.width / 2, 8, innerWidth - t.width - 8) + 'px'; tipEl.style.top = Math.max(8, y) + 'px';
}
function hideTip() { clearTimeout(tipT); tipEl.hidden = true; tipFor = null; }
document.addEventListener('mouseover', e => {
  const el = e.target.closest && e.target.closest('[data-tip]');
  if (el === tipFor) return; hideTip(); if (!el || drag) return;
  tipFor = el; tipT = setTimeout(() => showTip(el), 350);
});
document.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('[data-tip]'); if (el && el.matches(':focus-visible')) { hideTip(); tipFor = el; showTip(el); } });
document.addEventListener('focusout', hideTip);
document.addEventListener('pointerdown', hideTip, true);
addEventListener('scroll', hideTip, true);

/* ================= цикл ================= */
let lastDraw = 0, lastSide = 0;
function loop(now) {
  if (S.screen === 'exp' && S.run) {
    updateTop();
    if (now - lastDraw > 90) { drawAll(); lastDraw = now; }
    if (now - lastSide > 350) { updateSide(); updateTimeline(); lastSide = now; }
  } else if (S.screen === 'home' && now - lastSide > 500) { updateHomePlate(); lastSide = now; }
  requestAnimationFrame(loop);
}

go('home');
connect();
requestAnimationFrame(loop);
})();
