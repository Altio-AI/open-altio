/* SQL on the release's tables, under Tables and SQL: the box, its examples, a page of rows, and the
   whole result downloaded as one file. The server runs one read-only query at a time (rule sql-limits). */

import { whoLine } from './classes.js';
import { csvCap, saveFile } from './downloads.js';
import { actions } from './events.js';
import { host, slot } from './host.js';
import { icon } from './icons.js';
import { closeMenus, popMenu, toast } from './overlays.js';
import { post } from './server.js';
import { S, whoOn } from './state.js';
import { esc, fix, focusBox, num, tip } from './util.js';

// a few questions to start from, each a query a person can run as it is
const EXAMPLES = [
  ['Cases per year for a product', `-- Cases per year FDA first received them, for one product as a suspect
SELECT year(c.first_fda_dt_T) AS year, count(*) AS cases
FROM case_dedup_T c
SEMI JOIN (
  SELECT era_T, primaryid, quarter_T FROM drug_dedup_T
  WHERE prod_ai_norm_T = 'SEMAGLUTIDE' AND role_cod IN ('PS', 'SS')
) d USING (era_T, primaryid, quarter_T)
GROUP BY 1
ORDER BY 1`],
  ['Reactions reported most for a product', `-- The reactions reported most for one product as a suspect
SELECT r.pt AS reaction, count(DISTINCT r.era_T || r.primaryid) AS cases
FROM reac_dedup_T r
SEMI JOIN (
  SELECT era_T, primaryid, quarter_T FROM drug_dedup_T
  WHERE prod_ai_norm_T = 'SEMAGLUTIDE' AND role_cod IN ('PS', 'SS')
) d USING (era_T, primaryid, quarter_T)
GROUP BY 1
ORDER BY 2 DESC
LIMIT 50`],
  ['Outcomes for a product and a reaction', `-- Outcomes of the cases naming one product as a suspect and one reaction
SELECT o.outc_cod AS outcome, count(*) AS cases
FROM outc_dedup_T o
SEMI JOIN (
  SELECT era_T, primaryid, quarter_T FROM drug_dedup_T
  WHERE prod_ai_norm_T = 'SEMAGLUTIDE' AND role_cod IN ('PS', 'SS')
) d USING (era_T, primaryid, quarter_T)
SEMI JOIN (
  SELECT era_T, primaryid, quarter_T FROM reac_dedup_T WHERE lower(pt) = 'pancreatitis'
) r USING (era_T, primaryid, quarter_T)
GROUP BY 1
ORDER BY 2 DESC`],
  ['Countries for a reaction', `-- Where the cases of one reaction happened (FDA's own country text)
SELECT coalesce(c.occr_country, c.reporter_country) AS country, count(*) AS cases
FROM case_dedup_T c
SEMI JOIN (
  SELECT era_T, primaryid, quarter_T FROM reac_dedup_T WHERE lower(pt) = 'tendon rupture'
) r USING (era_T, primaryid, quarter_T)
GROUP BY 1
ORDER BY 2 DESC
LIMIT 30`],
  ['Groups of probable duplicates', `-- The largest groups of probable duplicates, and the case each keeps
SELECT dup_group_T, count(*) AS cases,
       max(CASE WHEN dup_kept_T THEN case_key_T END) AS kept_case
FROM case_latest_T
WHERE probable_duplicate_T
GROUP BY 1
ORDER BY 2 DESC
LIMIT 50`],
  ['Names a product is reported under', `-- Every name reported for one active ingredient
SELECT drugname, count(*) AS drug_rows
FROM drug_latest_T
WHERE prod_ai_norm_T = 'SEMAGLUTIDE'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 50`],
];

export function sqlBox() {
  const sq = S.sql || (S.sql = { text: EXAMPLES[0][1], result: null, running: false });
  return `<div class="oa-sql-head"><h2 class="oa-card-sub">Ask in SQL</h2><span class="oa-faint">Any table on the left, by its name. One read-only query${S.me?.sql_seconds ? `, up to ${S.me.sql_seconds} seconds` : ''}.</span></div>
    <textarea class="oa-sql-text" id="oa-sql-text" spellcheck="false" autocapitalize="off" aria-label="Query">${esc(sq.text)}</textarea>
    <div class="oa-sql-foot"><button type="button" class="btn" data-act="sql-examples" aria-haspopup="menu">${icon('document')}<span>Start from an example</span>${icon('chevronDown')}</button><button type="button" class="btn btn-primary" data-act="sql-run">Run</button></div>`;
}

export async function runSql(text, page) {
  S.sql.text = document.getElementById('oa-sql-text')?.value ?? text;
  S.sql.ran = text; S.sql.running = true; S.sql.note = '';
  document.getElementById('oa-sql-result').innerHTML = sqlResult();
  const r = await post('/api/sql', { sql: text, page });
  S.sql.running = false; S.sql.result = r;
  const out = document.getElementById('oa-sql-result');
  if (out) out.innerHTML = sqlResult();
}

export function sqlResult() {
  const sq = S.sql;
  if (!sq) return '';
  if (sq.running) return '<p class="oa-note">Running…</p>';
  const r = sq.result;
  if (!r) return '';
  if (r.problem) return `<p class="banner">${esc(r.problem)}</p>`;
  const from = r.total ? (r.page - 1) * r.size + 1 : 0;
  const to = from ? from + r.rows.length - 1 : 0;
  const pages = Math.max(1, Math.ceil(r.total / r.size));
  const csvOk = r.total + 1 <= csvCap(); // one file: its rows and the header line
  const most = S.downloads?.sql_download_rows ?? Infinity; // rule sql-result-download
  // a column is numbers when every value in it that is there is a number
  const numCol = (r.columns || []).map((_, i) => r.rows.some((row) => row[i] != null) && r.rows.every((row) => row[i] == null || typeof row[i] === 'number' || /^-?\d+(\.\d+)?$/.test(String(row[i]))));
  return `<div class="oa-sql-bar">
      <span class="oa-sql-total"><strong>${num(r.total)}</strong> row${r.total === 1 ? '' : 's'} <span class="oa-faint">· ${fix(r.seconds)} s</span></span>
      ${pages > 1 ? `<span class="oa-sql-pager"><span class="oa-faint">Rows ${num(from)} to ${num(to)}</span>
        <button type="button" class="icon-btn" data-act="sql-page" data-v="-1" ${r.page <= 1 ? 'disabled' : ''} aria-label="Previous rows" ${tip(`Previous ${num(r.size)} rows`)}>${icon('arrowLeft')}</button>
        <button type="button" class="icon-btn" data-act="sql-page" data-v="1" ${r.page >= pages ? 'disabled' : ''} aria-label="Next rows" ${tip(`Next ${num(r.size)} rows`)}>${icon('arrowRight')}</button></span>` : ''}
      <span class="oa-spacer"></span>
      ${r.total > most ? '<span class="oa-faint">Too many rows to download</span>' : r.total ? `<span class="oa-faint">Download all ${num(r.total)} rows</span>
        <button type="button" class="btn" data-act="sql-download" data-v="csv" ${csvOk ? '' : `disabled ${tip(`CSV stops at ${num(csvCap())} lines a file, with its header; use Parquet`)}`}>${icon('download')}<span>CSV</span></button>
        <button type="button" class="btn" data-act="sql-download" data-v="parquet">${icon('download')}<span>Parquet</span></button>` : ''}
    </div>
    ${r.total > most ? `<p class="oa-note">This result has ${num(r.total)} rows; a SQL result downloads up to ${num(most)}. Download the tables it reads instead, from the list of tables on this page, and run the query on your own machine.</p>` : ''}
    ${sq.note ? `<p class="banner">${esc(sq.note)}</p>` : ''}
    ${r.total ? `<div class="dashboard-frame"><table class="dashboard-table oa-sql-table oa-freeze"><thead><tr>${r.columns.map((c, i) => `<th${numCol[i] ? ' class="oa-num"' : ''}>${esc(c)}</th>`).join('')}</tr></thead>
    <tbody>${r.rows.map((row) => `<tr>${row.map((v, i) => `<td${numCol[i] ? ' class="oa-num"' : ''}>${v == null ? '<span class="oa-faint">NULL</span>' : esc(Array.isArray(v) ? v.join(', ') : v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '<p class="oa-note">The query gave no rows.</p>'}
    ${whoOn() && r.columns?.some((c) => /atc/i.test(c)) ? `<p class="oa-note">${whoLine()}</p>` : ''}
    ${slot('sql-download-note') || '<p class="oa-note">Downloads take the whole result, not just this page.</p>'}`;
}

// a SQL result, whole: the server runs the query again and sends one file
async function downloadSql(fmt, el) {
  const sq = S.sql;
  if (!sq?.ran || !sq.result) return;
  el.disabled = true;
  toast(`Writing all ${num(sq.result.total)} rows as ${fmt === 'csv' ? 'CSV' : 'Parquet'}`);
  const r = await fetch('/api/sql/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sql: sq.ran, format: fmt }) }).catch(() => null);
  el.disabled = false;
  if (r?.status === 401) { host.signedOut(); return; }
  if (!r?.ok) {
    sq.note = (r && (await r.json().catch(() => ({}))).problem) || 'The download did not start. Try again.';
    const out = document.getElementById('oa-sql-result');
    if (out) out.innerHTML = sqlResult();
    return;
  }
  const name = (r.headers.get('content-disposition') || '').match(/filename="?([^";]+)"?/)?.[1] || `sql-result.${fmt}`;
  const url = URL.createObjectURL(await r.blob());
  saveFile(url, name);
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

actions({
  'sql-run': () => runSql(document.getElementById('oa-sql-text').value, 1),
  'sql-download': (el) => downloadSql(el.dataset.v, el),
  'sql-examples': (el) => {
    const menu = popMenu(el, EXAMPLES.map(([label], i) => `<button type="button" class="menu-item" data-act="sql-example" data-i="${i}">${esc(label)}</button>`).join(''), 'oa-examples');
    // over its button, so the query box it fills stays in sight
    const r = el.getBoundingClientRect();
    menu.style.setProperty('--menu-top', `${Math.max(12, r.top - menu.offsetHeight - 6)}px`);
    menu.style.setProperty('--menu-left', `${r.left}px`);
  },
  'sql-example': (el) => {
    const text = EXAMPLES[+el.dataset.i][1];
    closeMenus();
    document.getElementById('oa-sql-text').value = text;
    runSql(text, 1);
  },
  'sql-page': (el) => runSql(S.sql.ran, (S.sql.result?.page || 1) + +el.dataset.v),
  'sql-insert': (el) => {
    const ta = document.getElementById('oa-sql-text');
    const at = ta.selectionStart ?? ta.value.length;
    ta.value = ta.value.slice(0, at) + el.dataset.v + ta.value.slice(ta.selectionEnd ?? at);
    focusBox(ta);
    ta.selectionStart = ta.selectionEnd = at + el.dataset.v.length;
  },
});
