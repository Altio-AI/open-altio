/* A case opened in place inside an opened event, in the pane the opened event gives a case
   (registerEventPane 'case', drawn where the Cases tab's toolbar and table were); ‹ Cases or
   Escape go back to them (ctx.back). While it is open the address names the case (?case=), so a
   copied link opens it.

   The top line: ‹ Cases, the case number, its qualifiers in small grey words. Then Outcomes and
   Event date as a label: value list across the width; The patient and About the report side by
   side; Reactions, one table, a row per reaction and a column per suspect drug (the event's drug
   first, each head linking the US label it was read on, on DailyMed); The drugs and their Therapy
   dates; any copies of the case; last FDA's line about the narrative. Each part is headed as a
   breakdown group is, each table in the event's own table style.

   Every fact is the case window's own (casedialog.js caseParts), laid out here so each value reads
   on one line: FDA's own wording, the source and the rule go in the value's tip, and only a value
   that differs from what FDA wrote gets the quiet dotted underline. Long lists show their first 10
   rows, then "N more ..." opens the rest. */

import { NARRATIVE, THERAPY_HEADS, caseAddress, caseParts, drugHeads, findCase } from './casedialog.js';
import { DECHAL, OUTCOME, RECHAL, REPORTER, REPT, ROLE, SEX, UNUSABLE_SERIOUS, freqWords } from './codes.js';
import { countryName } from './countries.js';
import { registerEventPane } from './event.js';
import { actions } from './events.js';
import { dailymed, flagTip, flagWords, labelName, labelsOn, versionTip } from './labels.js';
import { termShown } from './meddra.js';
import { showProblem } from './overlays.js';
import { putAddress } from './router.js';
import { api } from './server.js';
import { esc, fdaDay, skeletonRows, tip } from './util.js';

const FIRST = 10; // rows a long list shows before its "N more"
const ONSET_AT = THERAPY_HEADS.length - 1; // the therapy rows' time to onset, their last cell
const plural = (n, one, many = `${one}s`) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

// ---- one line a value ----------------------------------------------------------------------------
// Whether a value says what FDA wrote: the same words (case, spacing and punctuation aside), FDA's code
// read through the app's own code tables (F, Female), FDA's date in the app's form, or the same number
// in FDA's unit (65 YR, 65 years). Anything else is the cleaning at work (a converted weight, FDA's
// filler read as Not given, a company's cleaned name, a route family) and is underlined.
const norm = (s) => String(s ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '');
const CODES = [OUTCOME, SEX, REPT, ROLE, DECHAL, RECHAL];
const OCCP = { MD: 1, PH: 2, OT: 3, HP: 3, LW: 4, CN: 5 }; // FDA's occp_cod as the reporter types read it (rule reporter-type)
const UNIT = { YR: 'year', YEAR: 'year', MON: 'month', WK: 'week', DY: 'day', DAY: 'day', HR: 'hour', MIN: 'minute', SEC: 'second', DEC: 'decade', KG: 'kg', LBS: 'lb', GMS: 'g' };
function sameAsFda(shown, raw) {
  const s = norm(shown), r = norm(raw);
  if (s === r) return true;
  if (!s || s === 'notgiven') return false;
  if (CODES.some((m) => Object.hasOwn(m, raw) && norm(m[raw]) === s)) return true;
  if (OCCP[raw] && norm(REPORTER[OCCP[raw]]) === s) return true;
  const named = countryName(raw);
  if (named && named !== raw && [named, `${named} (${raw})`].some((w) => norm(w) === s)) return true;
  const coded = /^(.*) \(([A-Z]{2})\)$/.exec(shown);
  if (coded && norm(coded[1]) === r) return true;
  if (/^\d{8}$|^\d{6}$/.test(raw) && fdaDay(raw) === shown) return true;
  if (/^\d{6}$/.test(raw) && new Date(Date.UTC(+raw.slice(0, 4), +raw.slice(4, 6) - 1)).toLocaleString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }) === shown) return true;
  const words = String(raw).split(/,\s*/).map((x) => freqWords(x)).filter(Boolean);
  if (words.length && words.every((w) => s.includes(norm(w)))) return true;
  const a = /^([\d.]+)\s*([A-Za-z]+)$/.exec(String(raw).trim()), b = /^([\d.]+)\s*([A-Za-z]+)/.exec(String(shown).trim());
  return !!(a && b && Number(a[1]) === Number(b[1]) && UNIT[a[2].toUpperCase()] && b[2].toLowerCase().startsWith(UNIT[a[2].toUpperCase()]));
}

// what goes from a window's value into its tip: FDA's own words (.oa-fda), the source or the rule
// (.oa-case-note), a class's other choices and how it was chosen, the current PT, a quiet chip's words
const INTO_TIP = '.oa-case-note, .oa-class-could, .oa-class-how, .oa-pt, .oa-chip, .oa-flag-reason';
const words = (el) => el.textContent.replace(/\s+/g, ' ').trim();
function oneSegment(node, more) {
  const fda = [...node.querySelectorAll('.oa-fda')].map((x) => words(x).replace(/^FDA:\s*/, ''));
  node.querySelectorAll('.oa-fda').forEach((x) => x.remove());
  const notes = [...node.querySelectorAll(INTO_TIP)].map(words).filter(Boolean);
  node.querySelectorAll(INTO_TIP).forEach((x) => x.remove());
  // a block in a value reads inline; a tip on a part keeps its words, without the dotted mark, which
  // here says only that a value differs from FDA's
  node.querySelectorAll('div, p').forEach((x) => x.replaceWith(...x.childNodes));
  node.querySelectorAll('.oa-has-tip').forEach((x) => x.classList.remove('oa-has-tip'));
  const box = document.createElement('div');
  box.append(...node.childNodes);
  const changed = fda.some((raw) => !sameAsFda(words(box), raw));
  const said = [...fda.map((raw) => `FDA: ${raw}`), ...notes, ...more].filter(Boolean);
  const html = box.innerHTML.trim();
  if (!said.length) return html;
  return `<span class="oa-cv-v${changed ? ' oa-cv-changed' : ''}" ${tip(said.join(' · '))}>${html}</span>`;
}
// A value as the window draws it, on one line: a value of several lines (a drug's indications,
// Stopped and restarted) joined with commas
export function oneLine(html, more = []) {
  const t = document.createElement('template');
  t.innerHTML = html || '';
  t.content.querySelectorAll('.oa-atc-code').forEach((x) => x.after(' '));
  t.content.querySelectorAll('wbr').forEach((x) => x.remove());
  const lines = [...t.content.children].filter((x) => x.matches('.oa-case-line'));
  if (lines.length) return lines.map((x, i) => oneSegment(x, i ? [] : more)).join('<span class="oa-faint">, </span>');
  return oneSegment(t.content, more);
}

// ---- the parts -----------------------------------------------------------------------------------
// headed as the breakdown groups are: the title, its grey subtitle, one hairline
const groupHead = (title, sub = '') => `<p class="oa-cv-gt"><span class="oa-cv-gtitle">${esc(title)}</span>${sub ? ` <span class="oa-cv-gsub">${esc(sub)}</span>` : ''}</p>`;
const part = (title, sub, body, cls = '') => `<section class="oa-cv-part${cls ? ` ${cls}` : ''}">${title ? groupHead(title, sub) : ''}${body}</section>`;
const fields = (pairs) => `<dl class="field-list oa-fields oa-cv-fields">${pairs.filter(Boolean).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
const headCells = (list) => list.map(([w, said]) => `<th scope="col"${said ? ` ${tip(said)}` : ''}>${esc(w)}</th>`).join('');
const table = (head, body, cls = '') => `<div class="oa-cv-scroll"><table class="case-table oa-ec-table oa-cv-table${cls ? ` ${cls}` : ''}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
// the rows past the first 10 hidden, and the button that shows them
const folded = (i) => (i >= FIRST ? ' hidden data-cv-more' : '');
const more = (n, one, many) => (n > FIRST ? `<button type="button" class="oa-link oa-cv-more" data-act="cv-more">${plural(n - FIRST, `more ${one}`, `more ${many}`)}</button>` : '');

// the event's drug among a case's suspects: its ingredients are the drug's
function ownOf(drug, c) {
  const want = norm(drug);
  const ingredient = new Map((c.drug || []).map((d) => [d.drug_seq, d.ingredient_T]));
  return (d) => !!want && [d.name, ingredient.get(d.drug_seq), (d.label?.ingredients || []).join(' and '), (d.label?.ingredients || []).join(', ')].some((x) => x && norm(x) === want);
}

// Reactions: a row per reaction, the event's own first; a column per suspect drug, the event's drug
// first, each cell the label's answer in its short words (its whole wording in the tip), each head
// linking the label it was read on
function reactionsPart(ctx, c, p, flags) {
  const pts = new Set((ctx.reaction || []).map(norm));
  const theirs = (r) => pts.has(norm(r.pt_T)) || pts.has(norm(r.pt)) || pts.has(norm(r.current_pt_T?.name));
  const reac = [...(c.reac || [])].sort((a, b) => theirs(b) - theirs(a));
  const isOwn = ownOf(ctx.drug, c);
  const drugs = [...(flags?.drugs || [])].sort((a, b) => isOwn(b) - isOwn(a));
  const head = (d) => {
    const cls = isOwn(d) ? ' class="oa-cv-own"' : '';
    if (d.label) return `<th scope="col"${cls}><a class="oa-cv-label" href="${dailymed(d.label)}" target="_blank" rel="noopener" ${tip(`${labelName(d.label)}: opens on DailyMed in a new tab. ${versionTip()}`)}>${esc(d.name)}</a></th>`;
    const none = !d.coded || Object.values(d.flags).some((f) => f.outcome === 'no_label');
    return `<th scope="col"${cls}><span ${tip(none ? `No US prescription label was found for ${d.name}.` : `${d.name}: read on its forms' labels; each answer's tip names the label.`)}>${esc(d.name)}</span></th>`;
  };
  const cell = (d, r) => {
    const f = d.flags[r.pt];
    if (!f) return `<td class="oa-faint" ${tip(`No answer for ${d.name} and this reaction`)}>–</td>`;
    const quiet = f.outcome === 'uncertain' || /\(/.test(flagWords(f.outcome));
    return `<td${quiet ? ' class="oa-faint"' : ''}><span ${tip(flagTip(f, d.name))}>${esc(flagWords(f.outcome))}</span></td>`;
  };
  const rows = reac.map((r, i) => `<tr${folded(i)}><td>${oneLine(termShown(r.pt_T, r.pt, r.current_pt_T, p.v), r.soc_T ? [`System organ class: ${r.soc_T}, in MedDRA ${p.v}`] : [])}</td>${drugs.map((d) => cell(d, r)).join('')}</tr>`).join('');
  const body = rows || `<tr><td class="oa-faint">None recorded</td>${drugs.map(() => '<td></td>').join('')}</tr>`;
  const about = drugs.length ? '<button type="button" class="oa-link oa-cv-about" data-act="about">About the label flags</button>' : '';
  const n = reac.length;
  const sub = drugs.length ? `${n.toLocaleString('en-US')}, each against every suspect drug's US label` : plural(n, 'reaction');
  return part('Reactions', sub, `${table(`<th scope="col">Reaction</th>${drugs.map(head).join('')}`, body, 'oa-cv-reac')}
    <div class="oa-cv-under">${more(n, 'reaction', 'reactions')}${about}</div>`);
}

// The drugs, suspects first, and their therapy dates
function drugsPart(c, p) {
  const heads = drugHeads(p.classes);
  const alongside = p.ordered.findIndex((d) => d.role_T === 'C');
  const suspects = alongside < 0 ? p.ordered.length : alongside;
  let real = 0;
  const rows = p.ordered.map((d, i) => {
    const divider = i > 0 && i === alongside ? `<tr class="oa-case-divider"${folded(real)}><th colspan="${heads.length}" scope="rowgroup"><span>Taken alongside</span></th></tr>` : '';
    return `${divider}<tr${folded(real++)}>${p.drugCells(d).map((x) => `<td>${oneLine(x)}</td>`).join('')}</tr>`;
  }).join('');
  const sub = p.ordered.length ? [suspects ? `${suspects.toLocaleString('en-US')} suspect` : '', p.ordered.length - suspects ? `${(p.ordered.length - suspects).toLocaleString('en-US')} taken alongside` : ''].filter(Boolean).join(', ') : '';
  const drugs = part('The drugs', sub, `${table(headCells(heads), rows || `<tr><td colspan="${heads.length}" class="oa-faint">None recorded</td></tr>`, 'oa-cv-drugs')}
    ${p.ordered.length > FIRST ? `<div class="oa-cv-under">${more(p.ordered.length, 'drug', 'drugs')}</div>` : ''}`);
  if (!p.ther) return drugs;
  const t = document.createElement('template');
  t.innerHTML = `<table><tbody>${p.ther}</tbody></table>`;
  const ther = [...t.content.querySelectorAll('tbody > tr')];
  const cellHtml = (td) => `<td${td.dataset.tip ? ` ${tip(td.dataset.tip)}` : ''}>${oneLine(td.innerHTML)}</td>`;
  // a drug's time to onset on its first therapy row only, its later rows' cell empty, so it cannot
  // read as the next row's value
  const onsetHtml = (td) => (td?.textContent.trim() ? `<td>${oneLine(td.innerHTML, ['Counted from the first dose of this drug'])}</td>` : '<td></td>');
  const therRows = ther.map((tr, i) => {
    const cells = [...tr.children];
    return `<tr${folded(i)}>${cells.slice(0, ONSET_AT).map(cellHtml).join('')}${onsetHtml(cells[ONSET_AT])}</tr>`;
  }).join('');
  return `${drugs}${part('Therapy dates', 'when each drug was taken, as the report gives it', `${table(headCells(THERAPY_HEADS), therRows, 'oa-cv-ther')}
    ${ther.length > FIRST ? `<div class="oa-cv-under">${more(ther.length, 'therapy row', 'therapy rows')}</div>` : ''}`)}`;
}

// the copies FDA holds of the case: why it is shown or set aside, in the release's own sentences, and each copy
function copiesPart(c, p) {
  const group = c.group || [];
  if (!group.length && !p.reasons.length) return '';
  const why = p.reasons.map((line) => `<p class="oa-cv-note">${line.replace(/data-act="case-jump"/g, 'data-act="cv-jump"')}</p>`).join('');
  const rows = group.map((g) => `<tr><td><button type="button" class="oa-link" data-act="cv-jump" data-era="${esc(g.era_T)}" data-key="${esc(g.case_key_T)}">Case ${esc(g.case_key_T)}</button></td><td>${esc(g.era_T === 'legacy' ? 'AERS' : 'FAERS')}</td><td>${esc(fdaDayIso(g.first_fda_dt_T))}</td><td>${g.dup_kept_T ? 'Kept' : '<span class="oa-faint">Set aside</span>'}</td></tr>`).join('');
  return part('Probable duplicates', group.length ? plural(group.length, 'copy', 'copies') : '', `${why}${rows ? table(headCells([['Case'], ['FDA system'], ['First received'], ['Kept or set aside']]), rows) : ''}`);
}
const fdaDayIso = (iso) => (iso ? fdaDay(String(iso).slice(0, 10).replace(/-/g, '')) : 'Not given');

function topLine(c, p, key) {
  const q = c ? [...p.qualifiers.map((x) => [x.serious ? 'serious' : x.words, x.tip]),
    ...(c.dup_kept_T === false ? [['set aside', 'A probable duplicate of another case, set aside: Probable duplicates below says why']] : []),
    ...(p.unusable ? [['no usable drug or reaction', `${UNUSABLE_SERIOUS} (fixed rule: no-drug-or-reaction)`]] : [])] : [];
  return `<div class="oa-cv-top"><button type="button" class="oa-link oa-cv-back" data-act="cv-back" ${tip("Back to this event's cases (Escape)")}>‹ Cases</button>
    <span class="oa-cv-case">Case ${esc(c?.case_key_T || key)}</span>${q.length ? `<span class="oa-cv-q">${q.map(([w, t]) => `<span ${tip(t)}>${esc(w)}</span>`).join(' · ')}</span>` : ''}</div>`;
}

// FDA's line about the narrative, last: where the event is narrow its first half, the whole sentence
// in its tip, so it still reads on one line
function narrative() {
  const [head, rest = ''] = NARRATIVE.replace(/\.$/, '').split(/(?= in its public files)/);
  return `<p class="oa-cv-narrative" ${tip(NARRATIVE)}>${esc(head)}<span class="oa-cv-narrative-rest">${esc(rest)}</span>.</p>`;
}

function viewHtml(ctx, c, flags) {
  const p = caseParts(c, flags);
  const outcomes = p.outcomeCells.length ? p.outcomeCells.map((x) => oneLine(x)).join(', ') : `<span class="oa-faint">${esc(p.noOutcome)}</span>`;
  const happened = fields([
    ['Outcomes', outcomes],
    p.backs.length ? ['Came back when the drug was given again', p.backs.map((x) => oneLine(x)).join(', ')] : null,
    ['Event date', oneLine(p.eventDay)],
  ]);
  const one = (pairs) => fields(pairs.filter(Boolean).map(([k, v]) => [k, oneLine(v)]));
  return `${topLine(c, p)}
    <div class="oa-cv-body">
      ${part('', '', happened, 'oa-cv-happened')}
      <div class="oa-cv-pair">${part('The patient', '', one(p.patient))}${part('About the report', '', one(p.report))}</div>
      ${reactionsPart(ctx, c, p, flags)}
      ${drugsPart(c, p)}
      ${copiesPart(c, p)}
      ${narrative()}
    </div>`;
}

// ---- open and close ------------------------------------------------------------------------------
const open = new Set(); // the cases drawn in place: { el, ctx, era, key }
let last = null; // the one opened last: Escape goes back from it

async function show(view, era, key) {
  Object.assign(view, { era, key });
  putAddress(caseAddress({ era, key }));
  view.el.innerHTML = `<div class="oa-cv">${topLine(null, null, key)}<div class="oa-cv-body">${skeletonRows(4)}</div></div>`;
  try {
    const c = await findCase(era, key);
    // the flags come before the case is drawn, so nothing moves in it once it is
    const flags = labelsOn() ? await api(`/api/labels/case/${encodeURIComponent(c.era_T)}/${encodeURIComponent(c.case_key_T)}`) : null;
    if (view.key === key && open.has(view)) view.el.innerHTML = `<div class="oa-cv">${viewHtml(view.ctx, c, flags)}</div>`;
  } catch (err) {
    if (view.key !== key || !open.has(view)) return;
    if (err.message !== 'not found') { showProblem(err); return; }
    view.el.innerHTML = `<div class="oa-cv">${topLine(null, null, key)}<div class="oa-cv-body"><p class="oa-cv-note">There is no case ${esc(key)} in this release. A case FDA has deleted is taken out of the release.</p></div></div>`;
  }
}

// The pane's part of the opened event's contract: draw(pane, ctx) with ctx.caseId ('<era>/<key>')
// and ctx.back(), -> { update(ctx), close() }
export function draw(el, ctx) {
  const [era, key] = String(ctx.caseId).split('/');
  const view = { el, ctx, era, key };
  open.add(view);
  last = view;
  show(view, era, key);
  return {
    update: (next) => { view.ctx = next; const [e, k] = String(next.caseId).split('/'); if (k !== view.key) show(view, e, k); },
    close: () => done(view),
  };
}
export const CASE_PANE = { draw };
const viewOf = (el) => [...open].find((v) => v.el.contains(el));
// a case closed: the address names it no more
function done(view) {
  open.delete(view);
  view.el.innerHTML = '';
  if (last === view) last = null;
  if (new URLSearchParams(location.search).get('case') === view.key) putAddress(caseAddress(null));
}
// back to the Cases tab, as it was
function back(view) {
  done(view);
  view.ctx.back();
}

actions({
  'cv-back': (el) => { const v = viewOf(el); if (v) back(v); },
  // a long list's rest, opened in place
  'cv-more': (el) => {
    el.closest('.oa-cv-part')?.querySelectorAll('tr[data-cv-more]').forEach((tr) => { tr.hidden = false; tr.removeAttribute('data-cv-more'); });
    const under = el.parentElement;
    el.remove();
    if (under && !under.children.length) under.remove();
  },
  // a copy of the case opens in its place, ‹ Cases going back to the table as before
  'cv-jump': (el) => { const v = viewOf(el); if (v) show(v, el.dataset.era, el.dataset.key); },
});

// Escape goes back, unless it is closing something else first (a menu, a dialog) or typing is under way
window.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || e.defaultPrevented || !last || !open.has(last)) return;
  if (document.querySelector('dialog[open], :popover-open')) return;
  if (e.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
  back(last);
}, true);

registerEventPane('case', CASE_PANE);
