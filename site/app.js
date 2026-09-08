/* Do Markets Know Inflation First? — interactive results (Chart.js 4).
   Every number on this page comes from site/data/*.json, exported by
   src/export_site_data.py from the pipeline's committed tables. */
(() => {
'use strict';

// ---------- theme tokens (read from CSS so light/dark stay in one place) ----------
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const T = () => ({
  ink: css('--ink'), ink2: css('--ink2'), muted: css('--muted'), grid: css('--grid'), base: css('--base'),
  surface: css('--surface'), s1: css('--s1'), s2: css('--s2'), s3: css('--s3'), s4: css('--s4'),
  s1deep: css('--s1-deep'), s1wash: css('--s1-wash'),
  tipBg: css('--tip-bg'), tipInk: css('--tip-ink'), tipInk2: css('--tip-ink2'),
});
Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.animation.duration = 250;

// ---------- formatting ----------
const isNum = (v) => typeof v === 'number' && !Number.isNaN(v);
const f3 = (v) => isNum(v) ? v.toFixed(3) : '—';
const f2 = (v) => isNum(v) ? v.toFixed(2) : '—';
const f1 = (v) => isNum(v) ? v.toFixed(1) : '—';
const pct = (v) => isNum(v) ? Math.round(v * 100) + '%' : '—';
const pv = (p) => !isNum(p) ? '—' : p < 0.001 ? 'p < 0.001' : p < 0.01 ? 'p = ' + p.toFixed(3) : 'p = ' + p.toFixed(2);
const int = (v) => isNum(v) ? Math.round(v).toLocaleString('en-US') : '—';
const monthName = (ym) => { const [y, m] = ym.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' }); };
const dateLong = (iso) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-US',
  { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
const dayWord = (d) => d === 0 ? 'release day' : d === 1 ? '1 day before release' : d + ' days before release';

// ---------- plugins ----------
// vertical hairline through the hovered x on line charts
const crosshair = {
  id: 'crosshair',
  afterDatasetsDraw(chart) {
    const active = chart.tooltip && chart.tooltip.getActiveElements ? chart.tooltip.getActiveElements() : [];
    if (!active.length) return;
    const x = active[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
    ctx.save(); ctx.strokeStyle = T().base; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
  },
};
// value on every column cap (used only where the y axis is hidden)
const capLabels = {
  id: 'capLabels',
  afterDatasetsDraw(chart, _args, opts) {
    const ctx = chart.ctx, t = T();
    ctx.save(); ctx.fillStyle = t.ink2; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.font = '11.5px ' + Chart.defaults.font.family;
    chart.data.datasets.forEach((ds, i) => {
      if (!chart.isDatasetVisible(i)) return;
      chart.getDatasetMeta(i).data.forEach((bar, j) => {
        const v = ds.data[j];
        if (!isNum(v) || (opts.min != null && v < opts.min)) return;
        ctx.fillText(opts.format ? opts.format(v) : f3(v), bar.x, bar.y - 4);
      });
    });
    ctx.restore();
  },
};
// hairline at the day currently selected in the distribution explorer
const dayMarker = {
  id: 'dayMarker',
  afterDatasetsDraw(chart, _args, opts) {
    if (!isNum(opts.d)) return;
    const x = chart.scales.x.getPixelForValue(opts.d), { top, bottom, left, right } = chart.chartArea;
    if (x < left || x > right) return;
    const ctx = chart.ctx, t = T();
    ctx.save(); ctx.strokeStyle = t.ink2; ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
    ctx.fillStyle = t.ink2; ctx.font = '11px ' + Chart.defaults.font.family; ctx.textAlign = x > (left + right) / 2 ? 'right' : 'left';
    ctx.fillText('selected day', x + (x > (left + right) / 2 ? -5 : 5), top + 12);
    ctx.restore();
  },
};

// ---------- shared option builders ----------
function tooltipOpts(t, cb) {
  return Object.assign({
    backgroundColor: t.tipBg, titleColor: t.tipInk2, bodyColor: t.tipInk, footerColor: t.tipInk2,
    padding: 10, cornerRadius: 6, boxPadding: 4, usePointStyle: true, titleMarginBottom: 6,
    titleFont: { weight: '500' }, bodyFont: { weight: '600' }, footerFont: { weight: '400' },
  }, cb || {});
}
function legendOpts(t, extra) {
  return Object.assign({ position: 'top', align: 'end',
    labels: { usePointStyle: true, pointStyleWidth: 18, boxHeight: 6, color: t.ink, padding: 14 } }, extra || {});
}
function axisX(t, extra) {
  return Object.assign({ grid: { display: false }, border: { color: t.base }, ticks: { color: t.muted, maxRotation: 0 } }, extra || {});
}
function axisY(t, extra) {
  return Object.assign({ grid: { color: t.grid, lineWidth: 1 }, border: { display: false },
    ticks: { color: t.muted, padding: 6 }, title: { display: false, color: t.muted } }, extra || {});
}
const line = (label, color, data, extra) => Object.assign({ label, data, borderColor: color, backgroundColor: color,
  borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: T().surface,
  pointStyle: 'line', tension: 0, spanGaps: true }, extra || {});

// ---------- state ----------
const S = { data: null, horizon: 1, metric: 'mae', sample: 'headline', ds: { cleveland: true, naive_last: false, naive_avg: false },
  event: null, dayIdx: 0, playing: null, charts: {}, tables: {} };

function table(container, columns, rows) {
  container.replaceChildren();
  const tbl = document.createElement('table'), thead = document.createElement('thead'), tbody = document.createElement('tbody');
  const tr = document.createElement('tr');
  columns.forEach((c) => { const th = document.createElement('th'); th.textContent = c; tr.appendChild(th); });
  thead.appendChild(tr);
  rows.forEach((r) => { const tr = document.createElement('tr');
    r.forEach((v) => { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); }); tbody.appendChild(tr); });
  tbl.append(thead, tbody); container.appendChild(tbl);
}
function destroy(key) { if (S.charts[key]) { S.charts[key].destroy(); delete S.charts[key]; } }

// ---------- KPIs ----------
function renderKpis() {
  const h = S.data.summary.headline, t = T(), box = document.getElementById('kpis');
  const tiles = [
    { label: "Kalshi's average miss, 1 day before release", value: f3(h.kalshi_mae_1d), unit: 'pp', key: 's1', delta: 'mean absolute error · ' + h.n + ' releases' },
    { label: 'Cleveland Fed nowcast, read the same day', value: f3(h.cleveland_mae_1d), unit: 'pp', key: 's2', delta: 'the professional benchmark' },
    { label: 'Diebold–Mariano test of equal accuracy', value: pv(h.dm_p_1d), unit: '', delta: 't = ' + f2(h.dm_t_1d) + ' · the gap is not luck' },
    { label: 'Months the market was closer', value: h.kalshi_closer_1d + ' of ' + h.n, unit: '', delta: 'one day before the release' },
  ];
  box.replaceChildren(...tiles.map((k) => {
    const d = document.createElement('div'); d.className = 'kpi';
    const l = document.createElement('p'); l.className = 'label';
    if (k.key) { const s = document.createElement('span'); s.className = 'key'; s.style.background = t[k.key]; l.appendChild(s); }
    l.appendChild(document.createTextNode(k.label));
    const v = document.createElement('p'); v.className = 'value'; v.textContent = k.value;
    if (k.unit) { const u = document.createElement('small'); u.textContent = k.unit; v.appendChild(u); }
    const dl = document.createElement('p'); dl.className = 'delta'; dl.textContent = k.delta;
    d.append(l, v, dl); return d;
  }));
}

// ---------- 1. timeline ----------
function timelineRows() {
  const rows = S.data.comparison.rows.filter((r) => r.horizon_days === S.horizon);
  const byMonth = new Map(rows.map((r) => [r.month, r]));
  const months = [...new Set(S.data.comparison.rows.map((r) => r.month))].sort();
  return months.map((m) => byMonth.get(m) || { month: m });
}
function renderTimeline() {
  destroy('timeline');
  const t = T(), rows = timelineRows(), labels = rows.map((r) => r.month);
  const pick = (k) => rows.map((r) => isNum(r[k]) ? r[k] : null);
  const data = { labels, datasets: [
    line('Actual CPI (first release)', t.ink, pick('actual_first_release'), { pointRadius: 3, pointBackgroundColor: t.ink, pointBorderColor: t.surface, pointBorderWidth: 1.5, pointStyle: 'circle', order: 0 }),
    line('Kalshi implied mean', t.s1, pick('kalshi_implied_mean')),
    line('Cleveland Fed nowcast', t.s2, pick('cleveland_nowcast'), { hidden: !S.ds.cleveland }),
    line('Naive: last released print', t.s3, pick('naive_last_print'), { hidden: !S.ds.naive_last }),
    line('Naive: mean of last 12 prints', t.s4, pick('naive_avg_12m'), { hidden: !S.ds.naive_avg }),
  ] };
  S.charts.timeline = new Chart(document.getElementById('timeline'), {
    type: 'line', data, plugins: [crosshair],
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: legendOpts(t, { labels: { usePointStyle: true, pointStyleWidth: 18, boxHeight: 6, color: t.ink, padding: 14, filter: (item, data) => !data.datasets[item.datasetIndex].hidden } }), tooltip: tooltipOpts(t, { callbacks: {
        title: (items) => { const r = rows[items[0].dataIndex];
          return monthName(r.month) + ' CPI · read ' + dayWord(S.horizon) + (r.release_date ? ' (' + dateLong(r.release_date).replace(/^\w+, /, '') + ')' : ''); },
        label: (c) => (isNum(c.parsed.y) ? c.parsed.y.toFixed(3) : '—') + '   ' + c.dataset.label,
      } }) },
      scales: { x: axisX(t, { ticks: { color: t.muted, maxRotation: 0, autoSkip: false,
                  callback: (v) => labels[v].endsWith('-01') ? labels[v].slice(0, 4) : '' } }),
                y: axisY(t, { title: { display: true, text: 'CPI, month-over-month (%)', color: t.muted } }) } },
  });
  if (S.tables.timeline) table(document.getElementById('table-timeline'),
    ['Month', 'Read on', 'Actual', 'Kalshi', 'Cleveland Fed', 'Naive last', 'Naive 12-mo'],
    rows.map((r) => [monthName(r.month), r.snapshot_date || '—', f1(r.actual_first_release), f3(r.kalshi_implied_mean), f3(r.cleveland_nowcast), f1(r.naive_last_print), f2(r.naive_avg_12m)]));
}

// ---------- 2. error by horizon ----------
const HORIZONS = [30, 14, 7, 1];
const HLABEL = { 30: '30 days out', 14: '14 days out', 7: '7 days out', 1: '1 day out' };
function accRow(sample, h, fc) { return S.data.summary.accuracy.find((r) => r.sample === sample && r.horizon_days === h && r.forecaster === fc); }
function dmRow(sample, h, b) { return S.data.summary.dm.find((r) => r.sample === sample && r.horizon_days === h && r.benchmark === b); }
function renderError() {
  destroy('error');
  const t = T(), m = S.metric, s = S.sample;
  const k = HORIZONS.map((h) => accRow(s, h, 'kalshi')[m]), c = HORIZONS.map((h) => accRow(s, h, 'cleveland')[m]);
  const bar = (label, color, data) => ({ label, data, backgroundColor: color, borderRadius: 4, borderSkipped: 'start',
    maxBarThickness: 40, categoryPercentage: 0.55, barPercentage: 0.9, pointStyle: 'rect' });
  S.charts.error = new Chart(document.getElementById('error'), {
    type: 'bar', data: { labels: HORIZONS.map((h) => HLABEL[h]), datasets: [bar('Kalshi implied mean', t.s1, k), bar('Cleveland Fed nowcast', t.s2, c)] },
    plugins: [capLabels],
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 8 } },
      plugins: { capLabels: { format: f3 }, legend: legendOpts(t), tooltip: tooltipOpts(t, { callbacks: {
        title: (items) => HLABEL[HORIZONS[items[0].dataIndex]] + ' · ' + accRow(s, HORIZONS[items[0].dataIndex], 'kalshi').n + ' releases',
        label: (x) => x.parsed.y.toFixed(3) + ' pp   ' + x.dataset.label,
        footer: (items) => { const d = dmRow(s, HORIZONS[items[0].dataIndex], 'cleveland');
          return 'Diebold–Mariano: ' + pv(d.dm_p) + ' (t = ' + f2(d.dm_t) + ') · Kalshi closer in ' + d.kalshi_closer + ' of ' + d.n; },
      } }) },
      scales: { x: axisX(t), y: { display: false, beginAtZero: true, suggestedMax: Math.max(...k, ...c) * 1.18 } } },
  });
  const note = HORIZONS.map((h) => { const d = dmRow(s, h, 'cleveland'); return HLABEL[h].replace(' out', '') + ': ' + pv(d.dm_p); }).join('  ·  ');
  document.getElementById('error-note').textContent = (m === 'mae' ? 'Mean absolute error' : 'Root mean squared error') +
    ', ' + (s === 'headline' ? 'headline sample (October 2025 excluded: never published by the BLS)' : 'all settled releases') +
    '. Diebold–Mariano test, Kalshi vs. Cleveland Fed, absolute-error loss — ' + note + '.';
  if (S.tables.error) table(document.getElementById('table-error'),
    ['Days before release', 'Releases', 'Kalshi MAE', 'Cleveland MAE', 'Kalshi RMSE', 'Cleveland RMSE', 'Kalshi bias', 'Cleveland bias', 'DM t', 'DM p', 'Kalshi closer'],
    HORIZONS.map((h) => { const a = accRow(s, h, 'kalshi'), b = accRow(s, h, 'cleveland'), d = dmRow(s, h, 'cleveland');
      return [h, a.n, f3(a.mae), f3(b.mae), f3(a.rmse), f3(b.rmse), (a.bias >= 0 ? '+' : '') + f3(a.bias), (b.bias >= 0 ? '+' : '') + f3(b.bias), f2(d.dm_t), f3(d.dm_p), d.kalshi_closer + ' / ' + d.n]; }));
}

// ---------- 3. distribution explorer ----------
function currentEvent() { return S.data.events.events.find((e) => e.ticker === S.event); }
function alignedCleveland(ev) {
  // the nowcast available on each Kalshi day: latest published on or before that date (d' >= d)
  const pts = ev.cleveland.slice().sort((a, b) => b.d - a.d);
  return ev.days.map((day) => { let v = null; for (const p of pts) { if (p.d >= day.d) v = p.v; else break; } return v; });
}
function renderDist() {
  const ev = currentEvent(), day = ev.days[S.dayIdx], t = T();
  document.getElementById('day-label').textContent = dayWord(day.d) + ' · ' + dateLong(day.date);
  destroy('dist');
  const colors = day.p.map((_, i) => i === day.true_idx ? t.s1deep : t.s1);
  S.charts.dist = new Chart(document.getElementById('dist'), {
    type: 'bar', data: { labels: day.labels, datasets: [{ label: 'Market-implied probability', data: day.p, backgroundColor: colors,
      borderRadius: 4, borderSkipped: 'start', maxBarThickness: 34, categoryPercentage: 0.7, barPercentage: 0.9 }] },
    plugins: [capLabels],
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 160 },
      layout: { padding: { top: 6 } },
      plugins: { capLabels: { format: pct, min: 0.015 }, legend: { display: false }, tooltip: tooltipOpts(t, { displayColors: false, callbacks: {
        title: (items) => 'CPI print ' + day.labels[items[0].dataIndex] + '%' + (items[0].dataIndex === day.true_idx ? ' · what the BLS printed' : ''),
        label: (x) => pct(x.parsed.y) + '   market-implied probability',
      } }) },
      scales: { x: axisX(t, { title: { display: true, text: 'Month-over-month CPI print (%)', color: t.muted } }),
                y: { display: false, beginAtZero: true, suggestedMax: Math.max(...day.p) * 1.2 } } },
  });
  const stats = [
    ['Implied mean', f3(day.mean), 'pp'], ['Implied SD', f3(day.sd), 'pp'],
    ['Probability on the actual print', pct(day.p_true), ''], ['Actual print', f1(ev.actual), '%'],
    ['Contracts quoted', String(day.n), ''], ['Average bid–ask spread', (day.spread * 100).toFixed(1), '¢'],
    ['Contracts traded that day', int(day.volume), ''], ['Monotonicity fix', (day.mono * 100).toFixed(1), '¢'],
  ];
  document.getElementById('dist-stats').replaceChildren(...stats.map(([l, v, u]) => {
    const d = document.createElement('div'); d.className = 'stat';
    const a = document.createElement('span'); a.className = 'label'; a.textContent = l;
    const b = document.createElement('span'); b.className = 'value'; b.textContent = v;
    if (u) { const s = document.createElement('small'); s.textContent = u; b.appendChild(s); }
    d.append(a, b); return d; }));
  if (S.charts.evolution) { S.charts.evolution.options.plugins.dayMarker.d = day.d; S.charts.evolution.update('none'); }
  if (S.tables.dist) table(document.getElementById('table-dist'), ['CPI print (%)', 'Probability'],
    day.labels.map((l, i) => [l + (i === day.true_idx ? '  ← actual' : ''), pct(day.p[i])]));
}
function renderEvolution() {
  destroy('evolution');
  const ev = currentEvent(), t = T(), days = ev.days, cl = alignedCleveland(ev);
  const maxD = days[0].d, sdOf = new Map(days.map((d) => [d.d, d.sd]));
  const pt = (d, y) => ({ x: d.d, y });
  S.charts.evolution = new Chart(document.getElementById('evolution'), {
    type: 'line', plugins: [crosshair, dayMarker],
    data: { datasets: [
      { label: '_band', data: days.map((d) => pt(d, d.mean + d.sd)), fill: '+1', backgroundColor: t.s1wash, borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, pointStyle: false },
      { label: '_band', data: days.map((d) => pt(d, d.mean - d.sd)), fill: false, borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, pointStyle: false },
      line('Kalshi implied mean (±1 SD band)', t.s1, days.map((d) => pt(d, d.mean))),
      line('Cleveland Fed nowcast', t.s2, days.map((d, i) => pt(d, cl[i]))),
      line('Actual print (first release)', t.ink, [{ x: maxD, y: ev.actual }, { x: 0, y: ev.actual }], { borderWidth: 1.5 }),
    ] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { dayMarker: { d: days[S.dayIdx].d },
        legend: legendOpts(t, { labels: { usePointStyle: true, pointStyleWidth: 18, boxHeight: 6, color: t.ink, padding: 14, filter: (i) => !i.text.startsWith('_') } }),
        tooltip: tooltipOpts(t, { filter: (i) => !i.dataset.label.startsWith('_'), callbacks: {
          title: (items) => { const d = items[0].parsed.x; const day = days.find((x) => x.d === d); return dayWord(d) + (day ? ' · ' + dateLong(day.date) : ''); },
          label: (x) => { const v = x.parsed.y; if (!isNum(v)) return '—   ' + x.dataset.label;
            if (x.datasetIndex === 2) return v.toFixed(3) + ' ± ' + f3(sdOf.get(x.parsed.x)) + '   Kalshi implied mean ± SD';
            return v.toFixed(3) + '   ' + x.dataset.label; },
        } }) },
      scales: { x: axisX(t, { type: 'linear', reverse: true, min: 0, max: maxD, title: { display: true, text: 'Days before release', color: t.muted }, ticks: { color: t.muted, maxRotation: 0, stepSize: maxD > 90 ? 30 : maxD > 40 ? 10 : 5 } }),
                y: axisY(t, { title: { display: true, text: 'CPI, month-over-month (%)', color: t.muted } }) } },
  });
}
function setEvent(ticker, dayIdx) {
  S.event = ticker;
  const ev = currentEvent();
  const slider = document.getElementById('day-slider');
  slider.max = ev.days.length - 1;
  if (dayIdx == null) { // start a week out, a mid-story day
    let best = 0, bd = Infinity; ev.days.forEach((d, i) => { const dd = Math.abs(d.d - 7); if (dd < bd) { bd = dd; best = i; } }); dayIdx = best; }
  S.dayIdx = dayIdx; slider.value = dayIdx;
  renderEvolution(); renderDist();
}
function stopPlay() { if (S.playing) { clearInterval(S.playing); S.playing = null; document.getElementById('play').textContent = '▶'; } }

// ---------- 4. accuracy vs days before release ----------
function renderCurve() {
  destroy('curve');
  const t = T(), rows = S.data.curve.rows;
  S.charts.curve = new Chart(document.getElementById('curve'), {
    type: 'line', plugins: [crosshair],
    data: { datasets: [
      line('Kalshi implied mean', t.s1, rows.map((r) => ({ x: r.d, y: r.kalshi_mae }))),
      line('Cleveland Fed nowcast', t.s2, rows.map((r) => ({ x: r.d, y: r.cleveland_mae }))),
    ] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: legendOpts(t), tooltip: tooltipOpts(t, { callbacks: {
        title: (items) => { const r = rows[items[0].dataIndex]; return dayWord(r.d) + ' · ' + r.n + ' releases'; },
        label: (x) => x.parsed.y.toFixed(3) + ' pp   ' + x.dataset.label,
      } }) },
      scales: { x: axisX(t, { type: 'linear', reverse: true, min: 0, max: Math.max(...rows.map((r) => r.d)), title: { display: true, text: 'Days before release', color: t.muted }, ticks: { color: t.muted, maxRotation: 0, stepSize: 10 } }),
                y: axisY(t, { beginAtZero: true, title: { display: true, text: 'Mean absolute error (pp)', color: t.muted } }) } },
  });
  if (S.tables.curve) table(document.getElementById('table-curve'), ['Days before release', 'Releases', 'Kalshi MAE', 'Cleveland MAE'],
    rows.map((r) => [r.d, r.n, f3(r.kalshi_mae), f3(r.cleveland_mae)]));
}

// ---------- wiring ----------
function seg(id, attr, onPick) {
  const box = document.getElementById(id);
  box.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
    box.querySelectorAll('button').forEach((x) => { x.classList.remove('on'); x.setAttribute('aria-checked', 'false'); });
    b.classList.add('on'); b.setAttribute('aria-checked', 'true'); onPick(b.dataset[attr]);
  }));
}
function renderAll() { renderKpis(); renderTimeline(); renderError(); renderEvolution(); renderDist(); renderCurve(); }

async function main() {
  const [summary, comparison, events, curve] = await Promise.all(
    ['summary', 'comparison', 'events', 'horizon_curve'].map((n) => fetch('data/' + n + '.json').then((r) => r.json())));
  S.data = { summary, comparison, events, curve };

  seg('horizon-seg', 'h', (v) => { S.horizon = Number(v); renderTimeline(); });
  document.querySelectorAll('#series-toggles input').forEach((cb) => cb.addEventListener('change', () => {
    S.ds[cb.dataset.ds] = cb.checked; renderTimeline(); }));
  seg('metric-seg', 'm', (v) => { S.metric = v; renderError(); });
  seg('sample-seg', 's', (v) => { S.sample = v; renderError(); });

  const sel = document.getElementById('event-select');
  events.events.slice().sort((a, b) => b.month.localeCompare(a.month)).forEach((e) => {
    const o = document.createElement('option'); o.value = e.ticker;
    o.textContent = monthName(e.month) + ' CPI · printed ' + f1(e.actual) + '%' + (e.headline ? '' : ' (no BLS release)'); sel.appendChild(o); });
  sel.addEventListener('change', () => { stopPlay(); setEvent(sel.value); });
  const slider = document.getElementById('day-slider');
  slider.addEventListener('input', () => { S.dayIdx = Number(slider.value); renderDist(); });
  document.getElementById('play').addEventListener('click', () => {
    if (S.playing) return stopPlay();
    const ev = currentEvent(); if (S.dayIdx >= ev.days.length - 1) S.dayIdx = 0;
    document.getElementById('play').textContent = '❚❚';
    S.playing = setInterval(() => { if (S.dayIdx >= ev.days.length - 1) return stopPlay();
      S.dayIdx += 1; slider.value = S.dayIdx; renderDist(); }, 320);
  });
  document.querySelectorAll('button[data-table]').forEach((b) => b.addEventListener('click', () => {
    const k = b.dataset.table, on = b.getAttribute('aria-pressed') !== 'true';
    b.setAttribute('aria-pressed', String(on)); S.tables[k] = on;
    document.getElementById('table-' + k).hidden = !on;
    ({ timeline: renderTimeline, error: renderError, dist: renderDist, curve: renderCurve })[k]();
  }));

  const latest = events.events.slice().sort((a, b) => b.month.localeCompare(a.month))[0];
  sel.value = latest.ticker; S.event = latest.ticker;
  renderKpis(); renderTimeline(); renderError(); setEvent(latest.ticker); renderCurve();
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', renderAll);
}
main().catch((e) => { console.error(e); document.getElementById('kpis').textContent = 'Could not load the data files.'; });
})();
