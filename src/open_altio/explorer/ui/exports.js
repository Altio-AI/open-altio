/* The filtered export: the dialog that names what it holds, whether each file fits Excel as a CSV,
   and the zip the server writes for the page's filters. */

import { csvCap, loadDownloads, saveFile } from './downloads.js';
import { actions } from './events.js';
import { filterWords, filtersFor, query, rolesWords } from './filters.js';
import { slot } from './host.js';
import { icon } from './icons.js';
import { dialog, showProblem, slideTo, toast } from './overlays.js';
import { scopeNow } from './scope.js';
import { api } from './server.js';
import { S, drugWords, productLabel } from './state.js';
import { esc, num, skeletonRows, tip } from './util.js';

// the product as its page counts it: which products, in which roles
function productWords(sc) {
  const unit = sc.info?.kind === 'spelling' ? '' : `, ${Object.fromEntries(drugWords().units)[sc.unit].toLowerCase()} it`;
  return `${productLabel(sc.product)}${unit}, as ${rolesWords(sc.roles)}`;
}

// rule export-csv-row-cap: CSV is offered only while the largest of the files fits
async function openExport(sc) {
  const s = sc.summary;
  if (!s) return;
  const lines = filtersFor(sc).map((d) => [d.label, filterWords(sc, d)]).filter(([, w]) => w);
  const dlg = dialog(`Export ${num(s.cases)} cases`, `
    <p>Three files, holding only these cases: the cases, their drugs and their reactions, and a note naming the release and the filters.</p>
    <div id="oa-export-files">${skeletonRows(3)}</div>
    <dl class="field-list oa-fields">
      <dt>Release</dt><dd>${esc(S.release?.release)}</dd>
      ${sc.product ? `<dt>Product</dt><dd>${esc(productWords(sc))}</dd>` : ''}
      ${lines.map(([k, w]) => `<dt>${k}</dt><dd>${esc(w)}</dd>`).join('')}
      <dt>Duplicates</dt><dd>${sc.f.dedup === 'all' ? 'Included, flagged' : 'Left out'}</dd>
    </dl>
    <div class="oa-export-format" id="oa-export-format"></div>
    ${slot('export-note')}`,
  `<button type="button" class="btn" data-act="close-dialog">Cancel</button><button type="button" class="btn btn-primary" data-act="export-go">${icon('download')}<span>Download</span></button>`);
  let size;
  try { [size] = await Promise.all([api(`/api/exportsize?${query(sc)}`), loadDownloads()]); } catch (err) { showProblem(err); return; }
  if (!dlg.isConnected) return;
  const CSV_CAP = csvCap();
  const files = [['Cases', 'cases.csv', size.cases], ['Drugs', 'drugs.csv', size.drugs], ['Reactions', 'reactions.csv', size.reactions]];
  const over = files.filter(([, , n]) => n + 1 > CSV_CAP);
  const csvOk = !over.length;
  // each file once: what it is, its rows, and whether Excel can open it as a CSV (rows plus the header line)
  dlg.querySelector('#oa-export-files').innerHTML = `<div class="dashboard-frame"><table class="dashboard-table oa-export-table oa-freeze">
    <colgroup><col><col style="width:130px"><col style="width:190px"></colgroup>
    <thead><tr><th>File</th><th class="oa-num">Rows</th><th>As a CSV in Excel</th></tr></thead>
    <tbody>${files.map(([what, f, n]) => {
      const extra = n + 1 - CSV_CAP;
      return `<tr><th scope="row">${what}<span class="oa-file">${f}</span></th><td class="oa-num">${num(n)}</td>
        <td>${extra > 0 ? `<span class="oa-chip oa-chip-aside" ${tip(`Excel opens ${num(CSV_CAP)} lines a file; with its header line this file has ${num(n + 1)}`)}>${num(extra)} too many</span>` : '<span class="oa-fits">Fits</span>'}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  dlg.querySelector('#oa-export-format').innerHTML = `<span class="field-label">Format</span>
    <div class="slide-switch" role="radiogroup" data-state="first"><button type="button" class="slide-switch-part" role="radio" aria-checked="true" data-act="format" data-v="parquet">Parquet</button><button type="button" class="slide-switch-part" role="radio" aria-checked="false" data-act="format" data-v="csv" ${csvOk ? '' : 'disabled'}>CSV</button></div>
    ${csvOk ? '' : `<span class="note-faint">${over.map(([what]) => what).join(' and ')} ${over.length === 1 ? 'is' : 'are'} too big for Excel, so this export comes as Parquet only.</span>`}`;
}

// the filtered export: the browser saves the zip the server writes for the page's filters
function exportNow(el) {
  const sc = scopeNow();
  const dlg = el.closest('dialog');
  if (!sc || !dlg) return;
  const fmt = dlg.querySelector('[data-act="format"][aria-checked="true"]')?.dataset.v || 'parquet';
  saveFile(`/api/export?${query(sc, { format: fmt })}`);
  dlg.close();
  toast(`Writing the ${fmt === 'csv' ? 'CSV' : 'Parquet'} files; your browser saves the zip when it is ready.`);
}

actions({
  export: () => { const sc = scopeNow(); if (sc) openExport(sc); },
  'export-go': (el) => exportNow(el),
  format: (el) => { if (!el.disabled) slideTo(el); },
});
