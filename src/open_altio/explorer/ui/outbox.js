/* Improve this on a copy run on someone's own machine (rule improve-this), on the page only where
   the copy has an outbox (src/open_altio/explorer/pages.py). A note is kept in the outbox first,
   then sent from this page straight to Altio's improvements board and crossed off. One that cannot
   go yet waits, and goes when a page opens or the browser is back online. Nothing else is sent. */

import { actions } from './events.js';
import { extend } from './host.js';
import { slideTo } from './overlays.js';
import { render } from './router.js';
import { post } from './server.js';
import { esc, store } from './util.js';

const PRIVACY = "We send only your words, the page you're on, the part you pointed at and your email if you give one. Nothing else.";
const OFFLINE = "You're offline. Your note waits on this computer and is sent when you're back online.";

const shown = () => store.get('improve', true);
// an email given once is filled in on later notes, in this browser only
let email = store.get('noteEmail', '');
document.addEventListener('input', (e) => { if (e.target.id === 'oa-note-email') email = e.target.value; });

const crossOff = (id) => fetch(`/api/notes/outbox/${id}`, { method: 'DELETE' }).catch(() => {});

// One note from the outbox to Altio: { sent }, { waiting } when it could not go and stays in the
// outbox, or { problem } when Altio refused it. A refused note can never go as it is, so it leaves the
// outbox; one refused for the day's cap waits for tomorrow, unless it is new and its words are still
// in the dialog to send again.
async function deliver(sendTo, note, { fresh }) {
  let answer;
  try {
    answer = await fetch(sendTo, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(note), credentials: 'omit' });
  } catch {
    return { waiting: true };
  }
  if (answer.status >= 500 || (answer.status === 429 && !fresh)) return { waiting: true };
  await crossOff(note.id);
  if (answer.ok) return { sent: true };
  return { problem: (await answer.json().catch(() => ({}))).problem || 'Altio did not take the note.' };
}

// Every note still waiting, oldest first, until one cannot go. One round at a time, so a page that
// opens as the browser comes back online sends each note once.
let round = null;
function sendWaiting() {
  round ||= (async () => {
    const box = await fetch('/api/notes/outbox').then((r) => r.json()).catch(() => null);
    for (const note of box?.notes || []) {
      if ((await deliver(box.send_to, note, { fresh: false })).waiting) break;
    }
  })().finally(() => { round = null; });
  return round;
}

async function sendNote(note) {
  const box = document.getElementById('oa-note-email');
  if (!box.checkValidity()) {
    box.setAttribute('aria-invalid', 'true');
    box.focus();
    return { problem: 'Check your email address, or leave it empty.' };
  }
  box.removeAttribute('aria-invalid');
  const given = box.value.trim();
  const kept = await post('/api/notes/outbox', { ...note, email: given });
  if (!kept.ok) return { problem: kept.problem };
  email = given;
  store.set('noteEmail', email);
  const went = await deliver(kept.send_to, kept.note, { fresh: true });
  if (went.waiting) return { said: navigator.onLine ? 'Queued. Altio did not answer, so it will send later.' : "Queued. It will send when you're back online." };
  if (went.problem) return went;
  sendWaiting();
  return { said: given ? "Noted. We'll email you once we've looked at it." : 'Noted. It is kept for the developers.' };
}

const showSwitch = () => `<div class="oa-setting-row"><div><p class="oa-setting-name">Improve this</p><p class="note-faint">The button at the top right of every page. Notes go to Altio's improvements board.</p></div>
  <div class="slide-switch" role="radiogroup" aria-label="Improve this" data-state="${shown() ? 'first' : 'second'}">
    <button type="button" class="slide-switch-part" role="radio" aria-checked="${shown()}" data-act="improve-button" data-v="show">Show</button>
    <button type="button" class="slide-switch-part" role="radio" aria-checked="${!shown()}" data-act="improve-button" data-v="hide">Hide</button></div></div>`;

extend({
  improve: shown(),
  sendNote,
  slots: {
    'note-head': () => (navigator.onLine ? '' : `<p class="banner oa-note-offline">${OFFLINE}</p>`),
    'note-fields': () => `<label class="field oa-note-email"><span class="field-label">Your email, if you want to hear back <span class="oa-optional">optional</span></span>
      <input class="field-input" id="oa-note-email" type="email" autocomplete="email" spellcheck="false" placeholder="name@example.org" value="${esc(email)}"></label>
      <p class="note-faint oa-note-privacy">${PRIVACY}</p>`,
    settings: showSwitch,
  },
});

actions({
  'improve-button': (el) => {
    const on = el.dataset.v === 'show';
    store.set('improve', on);
    extend({ improve: on });
    slideTo(el);
    render();
  },
});

sendWaiting();
addEventListener('online', sendWaiting);
