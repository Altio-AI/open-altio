/* Tables and SQL: the release's tables by layer (with downloads), the table picked with every column
   in words, and SQL on the same tables (sql.js). */

import { whoLine } from './classes.js';
import { loadDownloads } from './downloads.js';
import { actions } from './events.js';
import { framed } from './frame.js';
import { icon } from './icons.js';
import { dialog, showProblem, toast } from './overlays.js';
import { current, drawn } from './router.js';
import { api } from './server.js';
import { runSql, sqlBox, sqlResult } from './sql.js';
import { S, whoOn } from './state.js';
import { GROUP_WORDS, TABLE_WORDS, citeText, columnWords, isClassTable, isFdaColumn, tableFrom } from './tablewords.js';
import { day, esc, foundFirst, foundOrder, num, sinceWords, size, skeletonRows, tip } from './util.js';

// the catalogue: every table by layer, with its rows, and downloads for a table, a layer or all
function catalogue() {
  if (!S.schema) return skeletonRows(3);
  const q = (S.tableFind || '').trim().toLowerCase();
  const pick = S.relTable || 'case_dedup_T';
  const groups = Object.keys(GROUP_WORDS).map((g) => {
    const list = foundFirst(S.schema.filter((t) => t.group === g).map((t) => {
      if (!q) return [t, '', 0];
      const named = foundOrder(q, t.name, TABLE_WORDS[t.name]);
      if (named >= 0) return [t, '', named];
      const [col] = foundFirst(t.columns, q, ([c]) => foundOrder(q, c, columnWords(c)));
      return col ? [t, col[0], foundOrder(q, col[0], columnWords(col[0]))] : [t, '', -1];
    }), q, ([, , at]) => at);
    if (!list.length) return '';
    const [head, line] = GROUP_WORDS[g];
    return `<section class="oa-cat-group">
      <div class="oa-cat-group-head"><h2 class="oa-cat-group-name">${esc(head)}</h2>
        <button type="button" class="icon-btn" data-act="download" data-what="layer" data-v="${g}" aria-label="Download the ${esc(head)} tables" ${tip(`Download these ${list.length} tables as Parquet`)}>${icon('download')}</button></div>
      ${q ? '' : `<p class="oa-cat-group-line">${esc(line())}</p>`}
      ${list.map(([t, col]) => `<div class="oa-cat-row" data-current="${t.name === pick}">
        <button type="button" class="oa-cat-pick" data-act="table-pick" data-v="${esc(t.name)}" aria-current="${t.name === pick}"><code>${esc(t.name)}</code><span class="oa-cat-rows">${num(t.rows)}</span>${col ? `<span class="oa-cat-hit">has <code>${esc(col)}</code></span>` : ''}</button>
        <button type="button" class="icon-btn" data-act="download" data-what="table" data-v="${esc(t.name)}" aria-label="Download ${esc(t.name)}" ${tip(`Download ${t.name} as Parquet${t.bytes ? `, ${size(t.bytes)}` : ''}`)}>${icon('download')}</button></div>`).join('')}
    </section>`;
  }).join('');
  return groups || '<p class="oa-pane-none">No table or column by that name.</p>';
}

// the table picked: what it holds, what it is made from, and every column in words
function tableCard() {
  if (!S.schema) return skeletonRows(2);
  const t = S.schema.find((x) => x.name === (S.relTable || 'case_dedup_T')) || S.schema[0];
  const layer = GROUP_WORDS[t.group][0];
  const q = (S.colFind || '').trim().toLowerCase();
  const cols = foundFirst(t.columns, q, ([c]) => foundOrder(q, c, columnWords(c)));
  const ours = t.columns.filter(([c]) => !isFdaColumn(c)).length;
  return `<div class="oa-card-head">
      <div class="oa-card-name"><h2><code>${esc(t.name)}</code></h2><span class="oa-chip oa-chip-quiet">${esc(layer)}</span>${t.view ? `<span class="oa-chip" ${tip('Today a view over the _latest_T tables, in views.sql. Proposed: written as its own file so it downloads like the others.')}>proposed file</span>` : ''}</div>
      <div class="oa-card-acts"><button type="button" class="btn" data-act="table-query" data-v="${esc(t.name)}" ${tip('Put a query of this table in the box below and run it')}>${icon('search')}<span>Query it</span></button>
        <button type="button" class="btn" data-act="download" data-what="table" data-v="${esc(t.name)}">${icon('download')}<span>Download${t.bytes ? `, ${size(t.bytes)}` : ''}</span></button></div>
    </div>
    <p class="oa-card-what">${esc(TABLE_WORDS[t.name] || '')}</p>
    <dl class="oa-card-facts">
      <dt>Made from</dt><dd>${esc(tableFrom(t.name))}${isClassTable(t.name) && whoOn() ? ` ${whoLine()}` : ''}</dd>
      <dt>Rows</dt><dd>${num(t.rows)}</dd>
      <dt>Columns</dt><dd>${t.columns.length}: ${t.columns.length - ours} as FDA published them${ours ? `, ${ours} worked out by Open Altio` : ''}</dd>
      ${t.columns.some(([c]) => c === 'primaryid') ? '<dt>Joins on</dt><dd><code>era_T</code>, <code>primaryid</code> and <code>quarter_T</code></dd>' : ''}
    </dl>
    <div class="oa-card-cols-bar"><h3 class="oa-card-sub">Its columns</h3>
      <div class="search-bar oa-col-find"><span class="search-icon">${icon('search')}</span><input class="search-input" id="oa-col-find" type="search" autocomplete="off" aria-label="Find a column" placeholder="Find a column" value="${esc(S.colFind || '')}"></div></div>
    <div class="oa-card-cols"><table class="oa-coltable oa-freeze"><colgroup><col class="oa-cc-name"><col class="oa-cc-type"><col class="oa-cc-from"><col></colgroup>
      <thead><tr><th>Column</th><th>Type</th><th>From</th><th>What it is</th></tr></thead>
      <tbody>${cols.map(([c, ty]) => `<tr><td><button type="button" class="oa-col" data-act="sql-insert" data-v="${esc(c)}" ${tip('Put it in the query')}><code>${esc(c)}</code></button></td><td class="oa-faint">${esc(ty.toLowerCase())}</td>
        <td>${isFdaColumn(c) ? 'FDA' : '<span class="oa-chip" ' + tip('Worked out by Open Altio; FDA\'s own columns never change') + '>Open Altio</span>'}</td><td>${esc(columnWords(c)) || '<span class="oa-faint">As FDA defines it</span>'}</td></tr>`).join('') || '<tr><td colspan="4" class="oa-faint">No column by that name.</td></tr>'}</tbody></table></div>`;
}

// The table list stays in view: it sticks where the side panel sits, and reaches down to the page's
// bottom edge from wherever its top is, so its end is never below the window.
function fitCatalogue() {
  const cat = document.querySelector('.oa-catalogue');
  if (!cat) return;
  if (getComputedStyle(cat).position !== 'sticky') { cat.style.height = ''; return; }
  const page = cat.closest('.frame-page');
  const gap = parseFloat(getComputedStyle(page).paddingBottom) || 0;
  cat.style.height = `${Math.max(320, Math.round(window.innerHeight - cat.getBoundingClientRect().top - gap))}px`;
}
let fitQueued = false;
const queueFit = () => { if (fitQueued) return; fitQueued = true; requestAnimationFrame(() => { fitQueued = false; fitCatalogue(); }); };
document.addEventListener('scroll', queueFit, true);
window.addEventListener('resize', queueFit);

function releasePage() {
  const m = S.manifest;
  return framed(`<main class="product-page oa-release">
    <div class="oa-title-row"><h1 class="product-title">Tables and SQL</h1></div>
    <div class="oa-release-bar"><p class="oa-subtitle">${m ? `Built ${day(m.built_at)} from ${sinceWords(m.quarters)}. Pick a table to see what it holds and what it is made from, ask any table in SQL, and download a table, a layer or the whole release.` : '&nbsp;'}</p>
      <div class="oa-release-acts"><button type="button" class="btn" data-act="cite">Cite this release</button>
        <button type="button" class="btn btn-primary" data-act="download" data-what="all">${icon('download')}<span>Download every table${m ? `, ${size(m.release_bytes)}` : ''}</span></button></div></div>
    ${S.downloads && !S.downloads.on ? `<p class="banner oa-downloads-off">${esc(S.downloads.why)}</p>` : ''}
    <div class="oa-workspace">
      <aside class="panel oa-catalogue">
        <div class="search-bar oa-table-find"><span class="search-icon">${icon('search')}</span><input class="search-input" id="oa-table-find" type="search" autocomplete="off" aria-label="Find a table or a column" placeholder="Find a table or a column" value="${esc(S.tableFind || '')}"></div>
        <p class="oa-cat-key">FDA's columns are kept as FDA published them. Columns ending in <code>_T</code> are Open Altio's, worked out from them.</p>
        <div class="oa-cat-cols"><span>Table</span><span class="oa-num">Rows</span></div>
        <div id="oa-catalogue">${catalogue()}</div>
      </aside>
      <div class="oa-work">
        <section class="panel oa-table-card" id="oa-table-card">${tableCard()}</section>
        <section class="panel oa-sql-editor">${sqlBox()}</section>
        <div id="oa-sql-result">${sqlResult()}</div>
      </div>
    </div>
  </main>`, 'release');
}

drawn('release', (r, app) => {
  app.innerHTML = releasePage();
  fitCatalogue();
  const need = [];
  if (!S.schema) need.push(api('/api/schema').then((x) => { S.schema = x; }));
  if (!S.manifest) need.push(api('/api/manifest').then((x) => { S.manifest = x; }));
  if (!S.downloads) need.push(loadDownloads());
  if (need.length) Promise.all(need).then(() => { if (current()?.page === 'release') { const keep = document.getElementById('oa-sql-text')?.value; app.innerHTML = releasePage(); fitCatalogue(); if (keep != null && S.sql) document.getElementById('oa-sql-text').value = keep; } }).catch(showProblem);
});

actions({
  'table-pick': (el) => {
    S.relTable = el.dataset.v; S.colFind = '';
    document.getElementById('oa-catalogue').innerHTML = catalogue();
    document.getElementById('oa-table-card').innerHTML = tableCard();
  },
  'table-query': (el) => {
    const t = S.schema.find((x) => x.name === el.dataset.v);
    const text = `-- 100 rows of ${t.name}, in no particular order\nSELECT *\nFROM ${t.name}\nLIMIT 100`;
    document.getElementById('oa-sql-text').value = text;
    runSql(text, 1).then(() => document.getElementById('oa-sql-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  },
  cite: () => {
    const m = S.manifest;
    const text = citeText(m?.release || S.release?.release || '', m);
    dialog('Cite this release', `<p class="panel oa-cite-text">${esc(text)}</p>`,
      `<button type="button" class="btn btn-primary" data-act="cite-copy" data-v="${esc(text)}">Copy</button>`);
  },
  'cite-copy': (el) => { navigator.clipboard?.writeText(el.dataset.v).then(() => toast('Copied.'), () => toast('Copying was blocked; select the text instead.')); },
});

document.addEventListener('input', (e) => {
  const el = e.target;
  if (el.id === 'oa-table-find') { S.tableFind = el.value; document.getElementById('oa-catalogue').innerHTML = catalogue(); }
  if (el.id === 'oa-col-find') {
    S.colFind = el.value;
    const box = document.querySelector('.oa-card-cols');
    const tmp = document.createElement('div'); tmp.innerHTML = tableCard();
    box.innerHTML = tmp.querySelector('.oa-card-cols').innerHTML;
  }
});
