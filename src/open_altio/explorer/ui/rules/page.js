/* How we clean FAERS: the page at /methods (its old address /rules forwards there), and the "Your
   rules" notice in the header line of every page that shows counts, when the release was built
   with someone's own rules. Drawn from /api/rules in the explorer's frame; where a host routes
   someone signed out here, under its plain head, read only. Top: today's line; then the story (story.js), whose boxes hold every rule (homes.js). On a
   person's own copy the switches and the Rebuild bar work as they always have (edit.js). */

import { actions } from '../events.js';
import { asOf, framed, improveBtn } from '../frame.js';
import { report } from '../host.js';
import { icon, markSvg } from '../icons.js';
import { closeMenus, popMenu } from '../overlays.js';
import { current, drawn, render } from '../router.js';
import { api } from '../server.js';
import { citeText } from '../tablewords.js';
import { day, esc, num, sinceWords } from '../util.js';
import { drawCharts } from './charts.js';
import { anyChoice, summary } from './choices.js';
import { editActs, paintBar, resume, sayRebuilt } from './edit.js';
import { homeOf, openBox } from './homes.js';
import { differenceRows, limitsList, openRow, rulesContext, yoursBox } from './rows.js';
import { levels, path, storyOf } from './story.js';

let ctx = null;
let S = null;
let failed = '';
const loaded = api('/api/rules')
  .then((data) => {
    ctx = rulesContext(data);
    S = storyOf(ctx);
    resume(ctx);
    // a page that shows counts was drawn before the rules came: draw it again, with its notice
    if (anyChoice(ctx.built) && current() && current().page !== 'methods') render();
  })
  .catch((err) => { failed = err.message || String(err); });

const TITLE = 'How we clean FAERS';
const plain = (content) => `<div class="oa-plain">
    <header class="oa-plain-head"><a class="brand-home" href="/" aria-label="Open Altio">${markSvg()}<span class="brand-name">Open Altio</span></a><div class="oa-corner">${asOf(ctx?.data.release.quarters[1].toUpperCase())}${improveBtn()}</div></header>
    ${content}
  </div>`;
const asked = () => (new URLSearchParams(location.search).get('open') || '').split(',')[0];
// the address names the box or rule open, so a link to one opens it
function keepOpen(name) {
  const p = new URLSearchParams(location.search);
  if (name) p.set('open', name); else p.delete('open');
  history.replaceState(null, '', `${location.pathname}${p.size ? `?${p}` : ''}${location.hash}`);
}

// today's line: when and how the release was built and from which quarters, MedDRA, and how to cite
// it; how current the data is the page says once, in its corner
function todayLine() {
  const { release, meddra } = ctx.data;
  const rules = anyChoice(ctx.built) ? 'your rules' : "Altio's standard rules";
  const parts = [
    `This release was built ${day(release.built_at)} from ${sinceWords(release.quarters)}, with ${rules}`,
    meddra ? `MedDRA ${esc(meddra.version)}` : '',
    release.labels_as_of ? `Labels as of ${day(release.labels_as_of)}` : '',
    '<button type="button" class="oa-link" data-act="m-cite" aria-haspopup="dialog">How to cite</button>',
  ].filter(Boolean);
  return `<p class="oa-subtitle oa-m-line">${parts.join('<span class="oa-dot">·</span>')}</p>`;
}

const out = (href, words) => `<a class="oa-rule-link" href="${esc(href)}" target="_blank" rel="noopener">${words}${icon('external')}</a>`;
function page(inFrame, chosen) {
  const docs = 'https://altio-ai.github.io/open-altio/customise';
  return `<main class="product-page oa-rules oa-m-page${inFrame ? '' : ' oa-rules-public'}">
    <div class="oa-title-row"><h1 class="product-title">${TITLE}</h1></div>
    ${todayLine()}
    ${anyChoice(ctx.built) ? yoursBox(ctx) : ''}
    ${levels(ctx, S, chosen)}
    ${limitsList(ctx.M)}
    <p class="oa-note oa-m-foot">How to change it: ${out(`${docs}/rules/`, 'Change a rule')} ${out(`${docs}/rebuild/`, "Rebuild from FDA's files")}</p>
    <div class="oa-rebuild-slot" id="oa-rebuild"></div>
  </main>`;
}

// ---- a box opened, and a rule in it; one the address names was reported as read on arrival,
// and the address stays as it came ----
function openItem(id, rule, quiet = false) {
  if (!S.ITEMS[id]) return;
  closeMenus();
  if (document.querySelector('dialog.oa-m-dialog[open]')) return; // one box at a time
  const dlg = openBox(ctx, S, id, () => { keepOpen(null); paintBar(); });
  if (!quiet) keepOpen(rule || id);
  paintBar();
  requestAnimationFrame(() => {
    drawCharts(dlg, ctx.M.insights);
    const li = rule && dlg.querySelector(`#rule-${CSS.escape(rule)}`);
    if (!li) return;
    toggleRow(li.querySelector('.oa-rule-head'), quiet);
    // a step's first rule opens under the step's head, which may hold its switch and WHO's citation
    const step = li.closest('.oa-rule-group');
    (step?.querySelector('.oa-rule') === li ? step : li).scrollIntoView({ block: 'start' });
  });
}
// a row opens in place; the address names the last rule opened
function toggleRow(head, quiet = false) {
  const li = head.closest('.oa-rule');
  const open = li.dataset.open !== 'true';
  li.dataset.open = String(open);
  head.setAttribute('aria-expanded', String(open));
  if (open) { openRow(li, ctx); drawCharts(li, ctx.M.insights); } else li.querySelector('.oa-rule-body')?.remove();
  if (/^(card|limit)-/.test(head.dataset.id)) return;
  if (quiet) return;
  if (open) report('rule', { rule: head.dataset.id });
  keepOpen(open ? head.dataset.id : li.closest('dialog')?.dataset.box);
}

// the question chosen; every path is drawn once to take the tallest, so a swap never changes the height
const questionOf = (id) => S.QUESTIONS.find((q) => q.id === id);
function choose(id) {
  const q = questionOf(id);
  if (!q) return;
  document.querySelectorAll('[data-act="m-pick"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.q === id)));
  document.getElementById('oa-m-path').innerHTML = path(ctx, S, q);
  history.replaceState(null, '', `${location.pathname}${location.search}#${id}`);
}
function holdHeight() {
  const box = document.getElementById('oa-m-path');
  if (!box) return;
  const here = questionOf(document.querySelector('[data-act="m-pick"][aria-selected="true"]').dataset.q);
  box.style.minHeight = '';
  const tallest = Math.max(...S.QUESTIONS.map((q) => { box.innerHTML = path(ctx, S, q); return box.offsetHeight; }));
  box.style.minHeight = `${tallest}px`;
  box.innerHTML = path(ctx, S, here);
}

// ---- a rule named in the address: open the box that holds it ----
function goToRule(name, quiet = false) {
  const id = homeOf[name];
  if (!S.ITEMS[id]) return;
  const q = S.QUESTIONS.find((x) => [...x.clean, ...x.boxes, x.answer].includes(id));
  if (q && !document.querySelector(`#oa-m-path [data-item="${id}"]`)) choose(q.id);
  document.querySelector(`[data-item="${id}"]`)?.scrollIntoView({ block: 'center' });
  openItem(id, name, quiet);
}
// drawn in the explorer's frame, or under the plain head where a host routes someone signed out here
function draw(app, route) {
  const inFrame = !route.plain;
  const frame = (content) => (inFrame ? framed(content, 'methods') : plain(content));
  if (!ctx) {
    app.innerHTML = frame(`<main class="product-page oa-rules${inFrame ? '' : ' oa-rules-public'}"><div class="oa-title-row"><h1 class="product-title">${TITLE}</h1></div>
      ${failed ? `<p class="oa-empty">Could not load the rules: ${esc(failed)}</p>` : '<p class="oa-subtitle"><span class="skeleton oa-count-skeleton"></span></p><div class="panel oa-journey"><span class="skeleton oa-chart-skeleton"></span></div>'}</main>`);
    if (!failed) loaded.then(() => { if (current() === route) draw(app, route); });
    return;
  }
  const chosen = questionOf(location.hash.slice(1)) || S.QUESTIONS[0];
  app.innerHTML = frame(page(inFrame, chosen));
  paintBar();
  holdHeight();
  if (questionOf(location.hash.slice(1))) document.getElementById('answer').scrollIntoView({ block: 'start' });
  // ?open= names a box, which opens, or a rule, whose box opens on it
  const named = asked();
  if (S.ITEMS[named]) openItem(named, null, true);
  else if (homeOf[named]) goToRule(named, true);
}

// the notice: in the header line of a page with counts, opening the list of what differs
export function rulesNotice() {
  if (!ctx || !anyChoice(ctx.built)) return '';
  return `<span class="oa-dot">·</span><button type="button" class="oa-link oa-yours-notice" data-act="rules-yours" aria-haspopup="menu">${esc(summary(ctx.built))}</button>`;
}

function yoursMenu(el) {
  const rows = differenceRows(ctx, (rule, word, what) => `<a class="menu-item" href="/methods?open=${encodeURIComponent(rule.name)}"><span class="oa-chip ${word === 'Off' ? 'oa-chip-aside' : ''}">${word}</span><span class="menu-choice-words">${esc(rule.title)}${what ? `<span class="oa-yours-what">${what}</span>` : ''}</span></a>`);
  const altio = ctx.data.standard ? ` Altio's standard release has ${num(ctx.A.steps[ctx.M.steps.at(-1).id].after)} cases.` : '';
  popMenu(el, `<p class="menu-heading">${esc(summary(ctx.built))}</p>${rows}<p class="menu-footnote">Every count here follows them.${altio} <a href="/methods">See how we clean FAERS</a></p>`, 'oa-yours-menu');
}

function citeMenu(el) {
  const { release } = ctx.data;
  const text = citeText(release.name, release);
  const file = ctx.link('CITATION.cff');
  popMenu(el, `<p class="menu-heading">How to cite this release</p><p class="oa-cite-text oa-m-cite">${esc(text)}</p><p class="menu-footnote">From the project's <a href="${esc(file)}" target="_blank" rel="noopener">CITATION.cff</a>.</p>`, 'oa-m-cite-menu');
}

drawn('methods', (r, app) => draw(app, r));
actions({
  ...editActs,
  'rules-yours': (el) => yoursMenu(el),
  'm-cite': (el) => citeMenu(el),
  'm-box': (el) => openItem(el.dataset.item),
  'm-pick': (el) => choose(el.dataset.q),
  'rule-toggle': (el) => { closeMenus(); toggleRow(el); },
});

// the charts and the paths are drawn at the width they have
let redraw = false;
addEventListener('resize', () => {
  if (redraw || !ctx) return;
  redraw = true;
  requestAnimationFrame(() => {
    redraw = false;
    const dlg = document.querySelector('dialog.oa-m-dialog');
    if (dlg) drawCharts(dlg, ctx.M.insights);
    if (current()?.page === 'methods') holdHeight();
  });
});
document.addEventListener('DOMContentLoaded', sayRebuilt, { once: true });
