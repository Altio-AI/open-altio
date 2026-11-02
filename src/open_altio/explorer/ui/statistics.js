/* A pair's ROR within each age band and each sex (/api/statistics/strata), under the cases of a
   product's Cases tab narrowed to one reaction. The filters do not change these numbers: every
   release works them out once, on its own cases. */

import { SEX } from './codes.js';
import { api } from './server.js';
import { S, ages } from './state.js';
import { esc, fig, num, ruleTag, tip } from './util.js';

const faint = (text, words) => `<span class="oa-faint oa-has-tip" ${tip(words)}>${text}</span>`;
const ror = (r) => (r.ror == null ? '' : `${fig(r.ror)} ${faint(`${fig(r.ror_lower)} to ${fig(r.ror_upper)}`, '95% interval of the ROR')}`);

// a combination's statistics are its ingredients' own (rule statistics-cases)
const combined = (sc) => (sc.info?.ingredients?.length ?? 0) > 1;

// The ROR by age band and by sex of the pair a product's case list is narrowed to, one reaction,
// for the list to show under its cases: fetched once a pair, none where the statistics name no
// such pair (rule ror-strata).
const strataFor = (sc) => (sc.product && !combined(sc) && sc.f.pts?.length === 1 && S.me?.statistics !== false ? `${sc.product}\n${sc.f.pts[0]}` : '');

export async function loadStrata(sc) {
  const key = strataFor(sc);
  if (key === (sc.strata?.key ?? '')) return;
  if (!key) { sc.strata = null; return; }
  const [ingredient, reaction] = key.split('\n');
  const got = await api(`/api/statistics/strata?${new URLSearchParams({ ingredient, reaction })}`).catch(() => null);
  sc.strata = { key, got };
}

const STRATA_HEAD = { age_band: 'Age band', sex: 'Sex' };
const strataName = (by, v) => esc((by === 'age_band' ? ages()[v] : SEX[v]) ?? v);

export function strataBlock(sc) {
  const got = sc.strata?.key === strataFor(sc) ? sc.strata.got : null;
  if (!got) return '';
  const tables = got.parts.map((p) => `<table class="case-table oa-strata-table"><thead><tr><th>${STRATA_HEAD[p.by] ?? esc(p.by)}</th><th class="oa-num">Cases</th><th class="oa-num" ${tip('Reporting odds ratio within this group alone. In grey, its 95% interval; empty where a cell of its table is 0')}>ROR</th></tr></thead>
      <tbody>${p.strata.map((s) => `<tr><td>${strataName(p.by, s.stratum)}</td><td class="oa-num">${num(s.cases)}</td><td class="oa-num">${ror(s)}</td></tr>`).join('')}</tbody></table>`).join('');
  return `<section class="oa-strata" aria-label="ROR by age band and by sex">
      <h3 class="case-section">ROR by age band and by sex</h3>
      <p class="oa-note">For ${esc(got.ingredient)} and ${esc(got.reaction)}, on the ${num(got.cases)} cases the statistics count for them; the filters do not change it. ${ruleTag('ror-strata', 'fixed rule: ror-strata')}</p>
      <div class="oa-case-cols">${tables}</div></section>`;
}
