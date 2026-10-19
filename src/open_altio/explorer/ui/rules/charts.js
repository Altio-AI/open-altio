/* The evidence charts: one card of the release's methods.json drawn as an SVG at the width it
   has, in the explorer's chart look. The title is the card's claim; under it, the reading guide
   says what one bar or point is and what is compared, then the question the chart answers. */

import { esc, num } from '../util.js';

const value = (unit, v) => (v == null ? '' : unit === 'percent' ? `${Number(v).toFixed(1)}%` : num(v));
// a label from the data, read inside a sentence: its first letter small, unless it is an acronym
const lower = (s) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
export const andList = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);

function readingGuide(chart) {
  const x = lower(chart.x.label);
  const y = lower(chart.y.label);
  const names = chart.series.map((s) => lower(s.name));
  if (chart.type === 'stacked_bar') return `A bar is one ${x}; its height is ${y}${names.length > 1 ? `, split into ${andList(names)}` : ''}.`;
  if (chart.type === 'stacked_area') return `At each ${x} the bands add up to the ${y}: ${andList(names)}.`;
  return `Each point is the ${y} in one ${x}${names.length > 1 ? `, one line each for ${andList(names)}` : ''}.`;
}

function niceMax(v, unit) {
  if (unit === 'percent' && v > 50) return 100;
  const p = 10 ** Math.floor(Math.log10(v || 1));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

// how wide a label's text is drawn, near enough: the axis's small figures run about this wide
const textWidth = (text) => String(text).length * 6.4;

function draw(card, width) {
  const c = card.chart;
  const xs = c.x.values;
  const n = xs.length;
  const small = width < 480;
  const H = small ? 180 : 210;
  const tops = xs.map((_, i) => (c.type !== 'line' ? c.series.reduce((a, s) => a + (s.values[i] || 0), 0) : Math.max(...c.series.map((s) => s.values[i] || 0))));
  const max = niceMax(Math.max(...tops), c.y.unit);
  const ticks = [0, max / 2, max].map((t) => [t, value(c.y.unit, t).replace('.0%', '%')]);
  // the left margin holds the widest number on the y axis, so none is cut at the chart's edge
  const m = { l: Math.max(small ? 40 : 52, Math.ceil(Math.max(...ticks.map(([, w]) => textWidth(w)))) + 10), r: 10, t: 22, b: 26 };
  const pw = width - m.l - m.r;
  const ph = H - m.t - m.b;
  const yAt = (v) => m.t + ph - (v / max) * ph;
  const step = pw / n;
  const xMid = (i) => m.l + step * (i + 0.5);
  const parts = [];
  for (const [t, words] of ticks) {
    parts.push(`<line class="oa-grid" x1="${m.l}" x2="${m.l + pw}" y1="${yAt(t)}" y2="${yAt(t)}"/>`);
    parts.push(`<text class="oa-axis" x="${m.l - 6}" y="${yAt(t) + 4}" text-anchor="end">${words}</text>`);
  }
  // x labels left to right, each kept inside the chart and left out where it would touch the last
  const every = Math.max(1, Math.ceil(n / (small ? 4 : 8)));
  let lastRight = -Infinity;
  xs.forEach((x, i) => {
    if (i % every !== 0) return;
    const w = textWidth(x);
    let at = xMid(i);
    let anchor = 'middle';
    let left = at - w / 2;
    if (left < 2) { at = Math.max(2, xMid(i) - step / 2); anchor = 'start'; left = at; }
    if (left + w > width - 2) { at = width - 2; anchor = 'end'; left = at - w; }
    if (left < lastRight + 10) return;
    lastRight = left + w;
    parts.push(`<text class="oa-axis" x="${at}" y="${H - 8}" style="text-anchor:${anchor}">${esc(x)}</text>`);
  });
  if (c.type === 'stacked_bar') {
    const bw = Math.max(2, step * 0.72);
    xs.forEach((x, i) => {
      let acc = 0;
      c.series.forEach((s, k) => {
        const v = s.values[i] || 0;
        if (!v) return;
        const y0 = yAt(acc);
        const y1 = yAt(acc + v);
        acc += v;
        parts.push(`<rect class="oa-s${k}" x="${xMid(i) - bw / 2}" y="${y1}" width="${bw}" height="${Math.max(0.5, y0 - y1)}" data-tip="${esc(`${x}: ${s.name}, ${value(c.y.unit, v)}`)}"/>`);
      });
    });
  } else if (c.type === 'stacked_area') {
    const acc = xs.map(() => 0);
    c.series.forEach((s, k) => {
      const low = xs.map((_, i) => `${xMid(i)},${yAt(acc[i])}`);
      xs.forEach((_, i) => { acc[i] += s.values[i] || 0; });
      const high = xs.map((_, i) => `${xMid(i)},${yAt(acc[i])}`);
      parts.push(`<polygon class="oa-s${k} oa-area" points="${[...high, ...low.reverse()].join(' ')}"/>`);
    });
  } else {
    c.series.forEach((s, k) => {
      parts.push(`<polyline class="oa-line oa-s${k}" points="${xs.map((_, i) => `${xMid(i)},${yAt(s.values[i] || 0)}`).join(' ')}"/>`);
    });
  }
  if (c.type !== 'stacked_bar') {
    // a column per x value that names every series' value on hover
    xs.forEach((x, i) => {
      const words = c.series.map((s) => `${s.name} ${value(c.y.unit, s.values[i])}`).join(', ');
      parts.push(`<rect class="oa-hit" x="${m.l + step * i}" y="${m.t}" width="${step}" height="${ph}" data-tip="${esc(`${x}: ${words}`)}"/>`);
    });
  }
  if (c.note) {
    const i = xs.findIndex((x) => String(x) === String(c.note.x));
    if (i >= 0) {
      // beside its line, moved in as far as it must to stay in the chart
      const w = textWidth(c.note.text);
      const right = xMid(i) <= m.l + pw * 0.7;
      const left = Math.max(2, Math.min(right ? xMid(i) + 5 : xMid(i) - 5 - w, width - 2 - w));
      parts.push(`<line class="oa-note-line" x1="${xMid(i)}" x2="${xMid(i)}" y1="${m.t - 4}" y2="${m.t + ph}"/>`);
      parts.push(`<text class="oa-note-text" x="${left}" y="${m.t - 8}">${esc(c.note.text)}</text>`);
    }
  }
  return `<svg class="oa-evidence-svg" width="${width}" height="${H}" viewBox="0 0 ${width} ${H}" role="img" aria-label="${esc(card.title)}">${parts.join('')}</svg>`;
}

// the figure around a chart; the drawing is filled in once its width is known (drawCharts)
export function evidence(card, notebookUrl) {
  const c = card.chart;
  return `<figure class="oa-evidence" data-card="${esc(card.id)}">
    <figcaption><h4 class="oa-claim">${esc(card.title)}</h4>
      <p class="oa-claim-sub">${esc(readingGuide(c))}${c.question ? ` ${esc(c.question)}` : ''}</p></figcaption>
    <div class="oa-evidence-chart" data-card="${esc(card.id)}"></div>
    ${c.series.length > 1 ? `<ul class="oa-legend">${c.series.map((s, k) => `<li><span class="oa-key oa-s${k}"></span>${esc(s.name)}</li>`).join('')}</ul>` : ''}
    <p class="oa-evidence-text">${esc(card.two_sentences)}</p>
    <p class="oa-evidence-foot"><span class="oa-chip ${card.tag.kind === 'documented' ? 'oa-chip-quiet' : ''}">${esc(card.tag.label)}</span>
      <a class="oa-rule-link" href="${esc(notebookUrl)}" target="_blank" rel="noopener">Rerun the evidence</a></p>
  </figure>`;
}

export function drawCharts(root, cards) {
  root.querySelectorAll('.oa-evidence-chart[data-card]').forEach((box) => {
    const card = cards.find((x) => x.id === box.dataset.card);
    const w = Math.floor(box.clientWidth);
    if (!card || w <= 0 || box.dataset.w === String(w)) return;
    box.dataset.w = String(w);
    // a card whose data is missing from a small release has no x values to draw
    box.innerHTML = card.chart.x.values.length ? draw(card, w) : '<p class="oa-faint oa-evidence-none">This release has no data for this chart.</p>';
  });
}
