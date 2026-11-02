/* An opened event's duplicates in its cases table, read only. Under a case's number, "N duplicates":
   the reports the release sets aside as copies of it (rule dup-shown-copy: each group shows one
   copy, and its dup_other_cases_T names the others). Pressed, each copy is a row of its own under
   the case, lined up with the table: its number in Case, the day FDA first received it under
   Received, and across the rest one sentence of what the two reports agree on and one of what
   clashes, worked out from both reports' own fields (event-dups-words.js). With Include duplicates
   ticked, a copy shows as a case too, marked Duplicate. Both reports are read whole (/api/case)
   when the line is first opened. */

import { findCase } from './casedialog.js';
import { countryName } from './countries.js';
import { icon } from './icons.js';
import { day, esc, tip } from './util.js';
import { sameness } from './event-dups-words.js';

// per pane: { open: Set of 'era:key', lines: { 'era:key': [...] } }
const held = (P) => (P.dups ??= { open: new Set(), lines: {} });
export const keyOf = (c) => `${c.era_T}:${c.case_key_T}`;
const copiesOf = (c) => (c.dup_kept_T && c.probable_duplicate_T ? c.dup_other_cases_T || [] : []);

// a copy set aside, shown because Include duplicates is ticked
export const setAside = (c) => c.dup_kept_T === false;

// under a case's number: its duplicates to open, or the mark of a copy set aside
export function dupsUnder(P, c) {
  if (setAside(c)) return `<span class="oa-ec-dupmark" ${tip(`A duplicate: likely the same patient as case ${c.dup_shown_case_T}, which is counted in its place`)}>Duplicate</span>`;
  const n = copiesOf(c).length;
  if (!n) return '';
  const open = held(P).open.has(keyOf(c));
  return `<button type="button" class="oa-ec-dupbtn" data-act="ec-dups" data-key="${esc(keyOf(c))}" aria-expanded="${open}" ${tip(`${n === 1 ? 'Another report is' : `${n} other reports are`} likely the same patient. Press to see why`)}><span>${n} ${n === 1 ? 'duplicate' : 'duplicates'}</span>${icon('chevronDown')}</button>`;
}

// the copies' rows under an opened case, lined up with the table's columns
export function dupRows(P, c, cols) {
  const d = held(P), k = keyOf(c);
  if (!d.open.has(k)) return '';
  const all = cols.length + 1;
  const dated = cols[0] === 'received';
  const lines = d.lines[k];
  if (!lines) return copiesOf(c).map(() => `<tr class="oa-ec-duprow" data-of="${esc(k)}"><td colspan="${all}"><span class="skeleton skeleton-row"></span></td></tr>`).join('');
  return lines.map((l) => `<tr class="oa-ec-duprow" data-of="${esc(k)}">
    <td class="oa-ec-dupkey"><button type="button" class="case-key oa-ec-dupcase" data-act="ec-dupcase" data-era="${esc(l.era)}" data-key="${esc(l.key)}" ${tip(`Open case ${l.key}`)}>${esc(l.key)}</button></td>
    ${dated ? `<td class="oa-ec-nowrap">${l.received ? day(l.received) : ''}</td>` : ''}
    <td colspan="${all - (dated ? 2 : 1)}" class="oa-ec-dupwhy"><div class="oa-ec-dupsay">${l.failed ? '<span class="oa-faint">Could not read this report.</span>' : lineHtml(l.said)}</div></td></tr>`).join('');
}

// a copy's sentence wraps inside the part of the table in view, never under its right edge when the
// table scrolls sideways
const seen = new ResizeObserver((all) => { for (const e of all) fitLines(e.target); });
export function fitDupLines(body) {
  if (!body) return;
  seen.observe(body);
  fitLines(body);
}
function fitLines(body) {
  if (!body.isConnected) { seen.unobserve(body); return; }
  for (const say of body.querySelectorAll('.oa-ec-dupsay')) {
    const td = say.parentElement, st = getComputedStyle(td);
    say.style.maxWidth = `${Math.max(240, body.clientWidth - td.offsetLeft - parseFloat(st.paddingLeft) - parseFloat(st.paddingRight))}px`;
  }
}

// one line: what agrees, each phrase with its tip; then what clashes, or that nothing does
function lineHtml(r) {
  const phrase = (p) => `<span class="oa-ec-dupphrase" ${tip(p.tip)}>${esc(p.words)}</span>`;
  const agreed = [r.parts.map(phrase).join(', '), r.path ? phrase(r.path) : '', r.link ? phrase(r.link) : ''].filter(Boolean).join('; ');
  const clash = r.clashes.length
    ? `<span class="oa-ec-dupclash">${r.clashes.map((x, i) => `<span class="oa-ec-dupphrase" ${tip(x.tip)}>${esc(i ? x.words : x.words.charAt(0).toUpperCase() + x.words.slice(1))}</span>`).join('; ')}.</span>`
    : '<span class="oa-ec-dupnone">Nothing contradicts it.</span>';
  return `${esc(r.lead)}: ${agreed}. ${clash}`;
}

// A case's duplicates opened or closed (`c` the case); opened the first time, both reports are read
// and compared, and `repaint` draws the rows again
export async function toggleDups(P, c, repaint) {
  const d = held(P), k = keyOf(c);
  if (d.open.has(k)) { d.open.delete(k); repaint(); return; }
  d.open.add(k);
  repaint();
  if (d.lines[k]) return;
  const keys = copiesOf(c);
  try {
    const kept = await findCase(c.era_T, c.case_key_T);
    const era = new Map((kept.group || []).map((g) => [g.case_key_T, g.era_T]));
    const copies = await Promise.all(keys.map((key) => findCase(era.get(key) || '', key).catch(() => null)));
    let prev = null;
    d.lines[k] = keys.map((key, i) => {
      const copy = copies[i];
      if (!copy) return { era: era.get(key) || '', key, failed: true };
      const said = sameness(kept, copy, { product: P.ctx.drug, event: P.eventName(), countryName, prev });
      prev = said.sig;
      return { era: copy.era_T, key, received: copy.first_fda_dt_T, said };
    });
  } catch {
    d.lines[k] = keys.map((key) => ({ era: '', key, failed: true }));
  }
  repaint();
}
