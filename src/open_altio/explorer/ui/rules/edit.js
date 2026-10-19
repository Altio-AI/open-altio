/* Changing the rules on a person's own copy: a switch per rule (or one for a whole step, in its
   head), its values in the open row, and the bar that rebuilds the release with them. Each change
   is checked and saved beside the release at once (PUT /api/rules); the counts change only when
   the rebuild ends, and then the explorer opens on the new release and every page counts with it. */

import { saveFile } from '../downloads.js';
import { toast } from '../overlays.js';
import { post } from '../server.js';
import { esc, num } from '../util.js';
import { differing, isOn, same, tidy, toApi, valueIn } from './choices.js';
import { altioValue, choicesOf, stateWord } from './rows.js';

const REBUILT = 'open-altio.rules-rebuilt'; // kept over the reload that opens the new release
const SAVE_AFTER_MS = 400; // a typed value is saved once the typing pauses
const FOLLOW_EVERY_MS = 800;

// problem: why the last change was refused, and where (a rule and a value, or null for the bar)
const E = { problem: '', where: null, run: null, timer: 0 };
let getCtx = () => null;

// ---- the bar at the foot of the page ----
export function paintBar() {
  const ctx = getCtx();
  const slot = document.getElementById('oa-rebuild');
  if (!ctx || !slot) return;
  if (E.run) {
    const { step = '', done = 0, total = 1 } = E.run;
    slot.innerHTML = `<div class="panel oa-rebuild-bar" role="status" data-state="running">
      <div class="oa-rebuild-words"><strong>Rebuilding with your rules</strong><span class="oa-faint">Step ${num(Math.max(1, done))} of ${num(total)}: ${esc(step)}</span></div>
      <span class="oa-rebuild-track" aria-hidden="true"><i style="--share:${(done / total).toFixed(3)}"></i></span>
      <p class="oa-rebuild-note">You can keep using the explorer. It switches to the new counts when the build is done.</p>
    </div>`;
    return;
  }
  const n = differing(ctx.built, ctx.pending);
  const barProblem = E.problem && !E.where;
  if (!n && !barProblem) { slot.innerHTML = ''; return; }
  const line = barProblem ? `<span class="oa-rebuild-problem">${esc(E.problem)}</span>`
    : E.problem ? '<span class="oa-rebuild-problem">Fix the value marked above, then rebuild.</span>'
      : '<span class="oa-faint">The counts change when the release is rebuilt with them.</span>';
  // what a rebuild needs of this machine (rule machine-needs), and why it will not start when the
  // disk has less room than that
  const needs = ctx.data.needs;
  const short = needs?.refused || '';
  const need = needs ? `<p class="oa-rebuild-note${short ? ' oa-rebuild-problem' : ''}" data-needs>${esc(short || needs.says)}</p>` : '';
  slot.innerHTML = `<div class="panel oa-rebuild-bar" role="status">
      <div class="oa-rebuild-words"><strong>${n ? `You changed ${num(n)} rule${n === 1 ? '' : 's'}.` : 'Your rules were not saved.'}</strong>${line}</div>
      <div class="oa-rebuild-acts">${n ? '<button type="button" class="btn" data-act="rules-undo">Undo</button>' : ''}<button type="button" class="btn btn-primary" data-act="rules-rebuild" ${E.problem || !n || short ? 'disabled' : ''}>Rebuild with your rules</button></div>${need}
    </div>`;
}

// ---- one rule's row, brought up to date without moving anything around it ----
function paintRule(name) {
  const ctx = getCtx();
  const li = document.getElementById(`rule-${name}`);
  const rule = ctx.R.find((r) => r.name === name);
  if (!li || !rule) return;
  const on = String(isOn(ctx.pending, name));
  li.dataset.on = on;
  // a step's one switch sits in its head and turns every row of the step
  const step = rule.step.switch === name ? document.getElementById(`step-${rule.step.id}`) : null;
  if (step) { step.dataset.on = on; step.querySelectorAll('.oa-rule').forEach((row) => { row.dataset.on = on; }); }
  const sw = (step || li).querySelector(`.oa-rule-switch[data-rule="${name}"]`);
  if (sw) {
    sw.setAttribute('aria-checked', String(isOn(ctx.pending, name)));
    sw.querySelector('.oa-switch-word').textContent = stateWord(rule, ctx.pending);
  }
  for (const box of li.querySelectorAll('.oa-rule-value')) {
    const def = rule.values.find((v) => v.key === box.dataset.key);
    const v = valueIn(ctx.pending, rule, def.key);
    const changed = !same(v, def.standard);
    const note = box.querySelector('.oa-value-note');
    if (note) note.innerHTML = changed ? altioValue(def) : '';
    box.querySelector('.oa-value-box')?.setAttribute('data-state', changed ? 'changed' : '');
    const sw2 = box.querySelector('.oa-value-switch');
    if (sw2) {
      const parts = [...sw2.querySelectorAll('.slide-switch-part')];
      const at = Math.max(0, choicesOf(def).findIndex(([o]) => same(o, v)));
      sw2.dataset.state = ['first', 'second', 'third'][at];
      parts.forEach((b, i) => b.setAttribute('aria-checked', String(i === at)));
    }
    const said = box.querySelector('.oa-rule-value-problem');
    const here = E.problem && E.where?.rule === name && E.where?.key === def.key;
    said.hidden = !here;
    said.textContent = here ? E.problem : '';
    box.querySelector('.oa-value-input')?.toggleAttribute('aria-invalid', !!here);
  }
}

// ---- saving each change beside the release ----
function choose(next, where) {
  const ctx = getCtx();
  ctx.pending = tidy(next, ctx.R);
  E.where = where;
  clearTimeout(E.timer);
  E.timer = setTimeout(save, where?.key ? SAVE_AFTER_MS : 0);
  if (where) paintRule(where.rule);
  paintBar();
}

async function save() {
  const ctx = getCtx();
  const asked = toApi(ctx.pending);
  const said = await post('/api/rules', asked, 'PUT');
  if (JSON.stringify(toApi(getCtx().pending)) !== JSON.stringify(asked)) return; // a later change is on its way
  const where = E.where;
  E.problem = said.ok ? '' : said.problem;
  if (said.ok) { ctx.data.saved = said.saved; ctx.data.file = said.file; }
  if (where?.rule) paintRule(where.rule);
  paintBar();
}

function setValue(name, key, v) {
  const ctx = getCtx();
  const mine = ctx.pending[name] || {};
  choose({ ...ctx.pending, [name]: { ...mine, values: { ...(mine.values || {}), [key]: v } } }, { rule: name, key });
}

// ---- the rebuild, followed until it ends ----
async function follow() {
  const said = await fetch('/api/rules/rebuild', { cache: 'no-store' }).then((r) => r.json()).catch(() => null);
  if (!said || said.state === 'running') {
    if (said) E.run = said;
    paintBar();
    setTimeout(follow, FOLLOW_EVERY_MS);
    return;
  }
  E.run = null;
  if (said.state === 'done') {
    try { sessionStorage.setItem(REBUILT, '1'); } catch { /* storage is off in this window */ }
    location.reload();
    return;
  }
  E.problem = said.problem || '';
  E.where = null;
  paintBar();
}

// after the reload that opened the rebuilt release
export function sayRebuilt() {
  try {
    if (sessionStorage.getItem(REBUILT)) { sessionStorage.removeItem(REBUILT); toast('Rebuilt with your rules. Every page now counts with them.'); }
  } catch { /* storage is off in this window */ }
}

// where the page left off: a rebuild still running, or one that stopped
export function resume(ctx) {
  getCtx = () => ctx;
  const state = ctx.data.rebuild || {};
  if (state.state === 'running' && !E.run) { E.run = state; setTimeout(follow, FOLLOW_EVERY_MS); }
  if (!E.problem && ctx.data.problem) { E.problem = ctx.data.problem; E.where = null; }
  if (!E.problem && state.state === 'failed' && differing(ctx.built, ctx.pending)) { E.problem = state.problem; E.where = null; }
}

export const editActs = {
  'rule-switch': (el) => {
    const ctx = getCtx();
    const name = el.dataset.rule;
    const mine = ctx.pending[name] || {};
    choose({ ...ctx.pending, [name]: { ...mine, on: !isOn(ctx.pending, name) } }, { rule: name });
  },
  'rule-value': (el) => {
    const ctx = getCtx();
    const { rule: name, key } = el.dataset;
    const def = ctx.R.find((r) => r.name === name).values.find((v) => v.key === key);
    setValue(name, key, choicesOf(def)[Number(el.dataset.i)][0]);
  },
  'rules-undo': () => {
    const ctx = getCtx();
    E.problem = '';
    choose(structuredClone(ctx.built), null);
    document.querySelectorAll('.oa-rule[id^="rule-"]').forEach((li) => paintRule(li.id.slice('rule-'.length)));
  },
  'rules-rebuild': async (el) => {
    el.disabled = true;
    clearTimeout(E.timer);
    await save();
    if (E.problem) return;
    const said = await post('/api/rules/rebuild', {});
    if (!said.ok) { E.problem = said.problem; E.where = null; paintBar(); return; }
    E.run = said;
    paintBar();
    setTimeout(follow, FOLLOW_EVERY_MS);
  },
  'rules-download': () => {
    const url = URL.createObjectURL(new Blob([getCtx().data.file || ''], { type: 'application/toml' }));
    saveFile(url, 'rules.toml');
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

// a typed value is kept as typed; the row's state and the bar follow at once, and it is saved when
// the typing pauses. Something that is not a number goes as typed, and the check says why it is refused.
document.addEventListener('input', (e) => {
  const el = e.target;
  if (!el.matches?.('.oa-value-input[data-rule]') || !getCtx()) return;
  const text = el.value.trim();
  const v = text !== '' && Number.isFinite(Number(text)) ? Number(text) : text;
  setValue(el.dataset.rule, el.dataset.key, v);
});
