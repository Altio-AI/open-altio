/* Downloads: whole tables come from the object store through short signed links; the server never
   sends them. The filtered export and a SQL result are written by the server. A host may log each one. */

import { actions } from './events.js';
import { dialog, toast } from './overlays.js';
import { host } from './host.js';
import { api, post } from './server.js';
import { S } from './state.js';
import { esc, size } from './util.js';

// what can be downloaded here, and the limits (rule export-csv-row-cap, rule sql-result-download)
export const loadDownloads = () => api('/api/downloads').then((d) => { S.downloads = d; return d; });
// lines per CSV file, header included, as Excel counts them
export const csvCap = () => S.downloads?.csv_row_cap ?? Infinity;

export function saveFile(href, name = '') {
  const a = Object.assign(document.createElement('a'), { href, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// one table, a layer or every table: one click starts every file; the dialog lists them with their links
export async function takeDownload(what) {
  const d = await loadDownloads().catch(() => null);
  if (!d) return;
  if (!d.on) { toast(d.why); return; }
  const r = await post('/api/downloads', what);
  if (r.status === 401) { host.signedOut(); return; }
  if (!r.ok) { toast(r.problem); return; }
  r.files.forEach((f, i) => setTimeout(() => saveFile(f.url, f.file), i * 400));
  if (r.files.length === 1) { toast(`Downloading ${r.files[0].file}, ${size(r.files[0].bytes)}`); return; }
  const views = r.views.length ? `<p class="note-faint">${r.views.map((v) => `<code>${esc(v)}</code>`).join(', ')} ${r.views.length === 1 ? 'is a view' : 'are views'}: <code>views.sql</code> makes ${r.views.length === 1 ? 'it' : 'them'} from these tables. Open each Parquet file as a table of its name, then run <code>views.sql</code>.</p>` : '';
  dialog(`Downloading ${esc(r.what)}`, `<p class="oa-dialog-lead">${r.files.length} files, ${size(r.bytes)} in all, from Open Altio's store. If your browser asks, let it download several files. Each link below works for ${r.minutes} minutes.</p>
    ${views}
    <ul class="oa-plain-list oa-download-list">${r.files.map((f) => `<li><a class="oa-link" href="${esc(f.url)}" download="${esc(f.file)}">${esc(f.file)}</a> <span class="oa-faint">${size(f.bytes)}</span></li>`).join('')}</ul>`,
  '<button type="button" class="btn" data-act="close-dialog">Close</button>');
}

actions({
  download: (el) => takeDownload(el.dataset.what === 'all' ? { all: true } : { [el.dataset.what]: el.dataset.v }),
});
