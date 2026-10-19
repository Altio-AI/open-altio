/* Cases: the list of a scope's cases, a page at a time, sorted by a header or, on a phone, by one choice. */

import { OUTCOME, SEX, UNUSABLE_SERIOUS, labelOf, noOutcome } from './codes.js';
import { countryName } from './countries.js';
import { actions } from './events.js';
import { classTag } from './classes.js';
import { icon } from './icons.js';
import { ptMark, ptNote } from './meddra.js';
import { bodySkeleton, refresh, scopeNow } from './scope.js';
import { eras } from './state.js';
import { strataBlock } from './statistics.js';
import { day, esc, num, sortMark, tip } from './util.js';

// a sortable header goes highest first, then lowest first, then back to the list's own order
const SORTS = { received: { desc: 'newest', asc: 'oldest' }, age: { desc: 'age', asc: 'age-asc' } };
export const caseSort = (sc) => (sc.sortCol ? SORTS[sc.sortCol][sc.sortDir < 0 ? 'desc' : 'asc'] : 'newest');

function ageText(c) {
  if (c.age_years_T == null) return '';
  if (c.age_years_T < 2) return `${Math.round(c.age_years_T * 12)} mo`;
  return `${Math.floor(c.age_years_T)}`;
}

export function casesTable(sc) {
  const s = sc.summary, list = sc.cases;
  if (!s || !list) return bodySkeleton(sc);
  if (!s.cases) return '<p class="oa-empty">No cases match these filters.</p>';
  const from = (list.page - 1) * list.size + 1, to = from + list.cases.length - 1;
  const pages = Math.ceil(s.cases / list.size);
  const head = (label, col, hint) => {
    const state = sc.sortCol === col ? (sc.sortDir < 0 ? 'desc' : 'asc') : 'none';
    return `<button type="button" class="sort-head oa-sortable" data-act="sort" data-col="${col}" ${tip(hint)}>${label}${sortMark(state)}</button>`;
  };
  const bySoc = list.meddra_version != null;
  // with the system organ class column the narrower columns leave the reactions their room
  const widths = bySoc
    ? ['132px', '100px', '56px', '64px', '100px', '17%', '', '130px', '140px']
    : ['132px', '120px', '64px', '76px', '120px', '17%', '', '150px'];
  const rows = list.cases.map((c, i) => {
    const suspects = c.drugs.filter((d) => d[2] === 'PS' || d[2] === 'SS');
    // FDA's text exactly as written; a viewer with MedDRA's licensed part sees the current PT beside
    const reac = c.reactions;
    const pts = c.current_pts_T || [];
    const reacShown = reac.slice(0, 3).map((t, j) => `${esc(t)}${ptMark(pts[j], list.meddra_version)}`).join(', ');
    // the system organs of its reactions, for a viewer with MedDRA's licensed part: the first in full
    const socs = c.socs_T || [];
    const socCell = bySoc ? `<td class="oa-wrap">${socs.length ? `${esc(socs[0])}${socs.length > 1 ? ` <span class="oa-more" ${tip(socs.slice(1).join(', '))}>+${socs.length - 1}</span>` : ''}` : ''}</td>` : '';
    const flag = !c.dup_kept_T ? `<span class="oa-chip oa-chip-aside" ${tip('A probable duplicate of another case; left out of counts by default')}>Set aside</span>`
      : c.probable_duplicate_T ? `<span class="oa-chip" ${tip('Kept from a group of probable duplicates')}>Kept</span>` : '';
    return `<tr data-act="case" data-i="${i}" tabindex="0">
      <td><span class="case-key">${esc(c.case_key_T)}</span>${c.era_T === 'legacy' ? ` <span class="oa-era" ${tip(`From AERS, FDA's system before ${eras().FAERS[0]}`)}>AERS</span>` : ''} ${flag}</td>
      <td>${day(c.group_first_dt_T)}</td>
      <td class="oa-num">${ageText(c)}</td>
      <td>${esc(c.sex_T == null ? '' : labelOf(SEX, c.sex_T))}</td>
      <td class="oa-wrap">${c.country_T ? esc(countryName(c.country_T)) : `<span class="oa-faint" ${tip('The report gives no country')}>Not given</span>`}</td>
      <td class="oa-wrap">${suspects.slice(0, 2).map((d) => `${esc(d[0])}${classTag(d[3])}`).join(', ')}${suspects.length > 2 ? ` <span class="oa-more" ${tip(suspects.slice(2).map((d) => d[0]).join(', '))}>+${suspects.length - 2}</span>` : ''}</td>
      <td class="oa-wrap">${reacShown}${reac.length > 3 ? ` <span class="oa-more" ${tip(reac.slice(3).join(', '))}>+${reac.length - 3}</span>` : ''}</td>
      <td class="oa-wrap">${c.outcomes_T?.length ? esc(c.outcomes_T.map((o) => labelOf(OUTCOME, o)).join(', ')) : `<span class="oa-faint" ${tip(noOutcome(c.rept_cod))}>None given</span>`}${c.serious_no_drug_or_reaction_T ? ` <span class="oa-chip oa-chip-serious" ${tip(UNUSABLE_SERIOUS)}>No usable drug or reaction</span>` : ''}</td>${socCell}
    </tr>`;
  }).join('');
  // on a phone the cards have no headers to click, so sorting is one choice above them
  const now = `${sc.sortCol || 'received'}:${sc.sortCol ? sc.sortDir : -1}`;
  const sortPick = `<label class="oa-sort-phone"><span>Sort</span><select class="field-input" data-sort-phone>${[['received:-1', 'Newest first'], ['received:1', 'Oldest first'], ['age:-1', 'Oldest patients first'], ['age:1', 'Youngest patients first']].map(([v, w]) => `<option value="${v}" ${v === now ? 'selected' : ''}>${w}</option>`).join('')}</select></label>`;
  return `${ptNote(list.meddra_version)}${sortPick}<div class="oa-cases-frame"><table class="case-table oa-cases oa-freeze${bySoc ? ' oa-soc' : ''}">
    <colgroup>${widths.map((w) => `<col${w ? ` style="width:${w}"` : ''}>`).join('')}</colgroup>
    <thead><tr><th>Case</th><th>${head('Received', 'received', 'Sort by the date FDA first received the case')}</th><th class="oa-num">${head('Age', 'age', 'Sort by age')}</th><th>Sex</th><th>Country</th><th>Suspect drugs</th><th>Reactions</th><th>Outcome</th>${bySoc ? `<th ${tip("The system organ class of each reaction's current PT, in MedDRA " + list.meddra_version)}>System organ class</th>` : ''}</tr></thead>
    <tbody>${rows}</tbody></table></div>
    <nav class="oa-pager" aria-label="Pages">
      <span>Cases ${num(from)} to ${num(to)} of ${num(s.cases)}</span>
      <button type="button" class="btn" data-act="page" data-v="-1" ${list.page <= 1 ? 'disabled' : ''}>${icon('arrowLeft')}<span>Previous</span></button>
      <span class="oa-faint">Page ${num(list.page)} of ${num(pages)}</span>
      <button type="button" class="btn" data-act="page" data-v="1" ${list.page >= pages ? 'disabled' : ''}><span>Next</span>${icon('arrowRight')}</button>
    </nav>${strataBlock(sc)}`;
}

actions({
  sort: (el) => {
    const sc = scopeNow(); const col = el.dataset.col;
    if (sc.sortCol !== col) { sc.sortCol = col; sc.sortDir = -1; } else if (sc.sortDir < 0) sc.sortDir = 1; else { sc.sortCol = null; sc.sortDir = 0; }
    refresh(sc);
  },
  page: (el) => { const sc = scopeNow(); sc.page = Math.max(1, sc.page + +el.dataset.v); refresh(sc, { keepPage: true }); document.querySelector('.frame-page')?.scrollTo({ top: 0 }); },
});

document.addEventListener('change', (e) => {
  if (!e.target.matches?.('[data-sort-phone]')) return;
  const sc = scopeNow(); const [col, dir] = e.target.value.split(':');
  sc.sortCol = col; sc.sortDir = +dir;
  refresh(sc);
});
