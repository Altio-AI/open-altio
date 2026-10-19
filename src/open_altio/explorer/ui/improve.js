/* Improve this: one text box, and a pointer to name the part of the page a note is about. Offered
   where a host takes the notes (host.improve); the note goes to the server, which says who sent it,
   unless a module sends it elsewhere (host.sendNote, outbox.js on someone's own machine) and adds its
   own lines to the dialog (the note-head and note-fields slots). */

import { actions } from './events.js';
import { host, report, slot } from './host.js';
import { icon } from './icons.js';
import { busy, dialog, toast } from './overlays.js';
import { current, here } from './router.js';
import { post } from './server.js';
import { esc, focusBox, hovered, tip } from './util.js';

let note = null; // { text, page, route, part, where }
let notePointing = null;
let noteOutlined = null;

// the page's title alone: a button in it, such as a drug's spellings, is not part of its name
function pageName() {
  if (current()?.page === 'home') return 'Home';
  const h = document.querySelector('#app h1')?.cloneNode(true);
  h?.querySelectorAll('button').forEach((b) => b.remove());
  return (h?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60) || 'this page';
}

const partOf = (el) => el.closest('button, a, [role], tr, li, label, h1, h2, h3, .oa-chart, .panel, section') || el;

function partName(el) {
  const t = partOf(el);
  // a control that names itself (data-part) is named so; one that shows its current choice after
  // its name ("Status: Not decided yet, Being made", "View as: Admin") is named by what it is,
  // never by today's choice, so a note and its thank-you email read "Status filter", not the choices
  const named = t.closest('[data-part]')?.dataset.part;
  if (named) return named.slice(0, 60);
  const shown = (t.getAttribute('aria-label') || t.innerText || '').trim().split('\n')[0];
  const label = shown.match(/^([^:]{2,40}):\s/)?.[1];
  if (label && t.matches('button, [role=button]')) return /-filter$/.test(t.dataset.act || '') ? `${label} filter` : label;
  let text = (t.getAttribute('aria-label') || t.innerText || t.textContent || '').trim().split('\n')[0];
  // a heading the page shows in capitals is named as it is written ("Products", not "PRODUCTS")
  const written = (t.textContent || '').replace(/\s+/g, ' ').trim();
  if (!t.getAttribute('aria-label') && text && text === text.toUpperCase() && written.toUpperCase().startsWith(text)) text = written.slice(0, text.length);
  return text.slice(0, 60) || t.tagName.toLowerCase();
}

// where a part is, to outline it again later: a path of tags and positions from the page
function partPath(el) {
  const steps = [];
  for (let n = el; n && n.id !== 'app' && n !== document.body; n = n.parentElement) {
    if (n.id) { steps.unshift(`#${CSS.escape(n.id)}`); break; }
    const same = [...(n.parentElement?.children || [])].filter((c) => c.tagName === n.tagName);
    steps.unshift(`${n.tagName.toLowerCase()}${same.length > 1 ? `:nth-of-type(${same.indexOf(n) + 1})` : ''}`);
  }
  return steps.join(' > ');
}

function improveDialog(keep = false) {
  if (!keep) note = { text: '', page: pageName(), route: here(), part: '', where: '' };
  const dlg = dialog('Improve this', `${slot('note-head')}<label class="oa-note-ask" for="oa-note-text">What was confusing, slow or missing here? <span class="oa-req" aria-hidden="true">*</span></label>
    <textarea class="field-input" id="oa-note-text" rows="4" required placeholder="For example: I could not tell which filters were on">${esc(note.text)}</textarea>
    <div class="oa-note-part">
      <button type="button" class="icon-btn oa-point" data-act="note-point" aria-pressed="false" aria-label="Point at something" ${tip('Point at something: pick the part of this page your note is about')}>${icon('pointer')}</button>
      ${note.part ? `<span class="oa-note-tag">About: <strong>${esc(note.part)}</strong><button type="button" class="oa-note-x" data-act="note-part-x" aria-label="Remove ${esc(note.part)}">×</button></span>` : '<span class="oa-faint">Point at the part of the page it is about <span class="oa-optional">optional</span></span>'}
    </div>${slot('note-fields')}`,
  '<button type="button" class="btn" data-act="close-dialog">Cancel</button><button type="button" class="btn btn-primary" data-act="noted">Submit improvement</button>');
  dlg.classList.add('oa-note-dialog');
  const t = dlg.querySelector('#oa-note-text');
  focusBox(t);
  t.setSelectionRange(t.value.length, t.value.length);
}

// A host that takes notes keeps them; who sent one is the server's to say.
async function keepNote(n) {
  const sent = await post('/api/notes', n);
  return sent.ok ? { said: 'Noted. It is kept for the developers.' } : { problem: sent.problem };
}

// the dialog steps aside, the next click names the part, and the dialog comes back with the text kept
function notePoint(on, el) {
  if (on) {
    note.text = document.getElementById('oa-note-text')?.value || '';
    notePointing = true;
    document.querySelector('.oa-note-dialog')?.close();
    document.documentElement.setAttribute('data-note-pointing', '');
    toast('Click the part of the page your note is about, or Esc to stop');
    return;
  }
  notePointing = null;
  document.documentElement.removeAttribute('data-note-pointing');
  if (noteOutlined) { noteOutlined.classList.remove('oa-outlined'); noteOutlined = null; }
  if (el) { note.part = partName(el); note.where = partPath(partOf(el)); }
  improveDialog(true);
}
addEventListener('pointerover', (e) => {
  if (!notePointing || !hovered(e)) return;
  if (noteOutlined) noteOutlined.classList.remove('oa-outlined');
  noteOutlined = e.target.closest('#oa-toasts') ? null : e.target;
  noteOutlined?.classList.add('oa-outlined');
}, true);
addEventListener('click', (e) => {
  if (!notePointing) return;
  e.preventDefault(); e.stopPropagation();
  notePoint(false, e.target);
}, true);
addEventListener('keydown', (e) => { if (notePointing && e.key === 'Escape') { e.preventDefault(); notePoint(false); } }, true);

actions({
  improve: () => { report('improve_opened', { page: pageName() }); improveDialog(false); },
  'request-label': (el) => {
    const drug = el.dataset.drug;
    note = { text: `Please add the FDA label for ${drug}. DailyMed link, if you have it: `, page: pageName(), route: here(), part: el.dataset.part, where: partPath(el) };
    report('improve_opened', { page: pageName() });
    improveDialog(true);
  },
  'note-point': () => notePoint(true),
  'note-part-x': () => { note.text = document.getElementById('oa-note-text')?.value || ''; note.part = ''; note.where = ''; document.querySelector('.oa-note-dialog')?.close(); improveDialog(true); },
  noted: async (el) => {
    const text = document.getElementById('oa-note-text').value.trim();
    if (!text) { document.getElementById('oa-note-text').focus(); return; }
    busy(el, true);
    const sent = await (host.sendNote || keepNote)({ page: note.page, route: note.route, part: note.part, where: note.where, text });
    busy(el, false);
    if (sent.problem) { toast(sent.problem); return; }
    el.closest('dialog').close();
    toast(sent.said);
    host.noted.forEach((done) => done());
  },
});
