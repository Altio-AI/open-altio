/* WHO's drug classes (ATC), where the release carries them and the person may see them: the Drug
   class filter on All cases (a tree of classes at every level, searched or browsed, counted in the
   ticked roles, with one "could be" tick), and each drug's one class on the case list and in a case,
   with WHO's short line wherever a class shows (src/open_altio/explorer/classes.py). */

import { CHOSEN_BY } from './codes.js';
import { roleTicks, toggled } from './drugs.js';
import { actions } from './events.js';
import { query } from './filters.js';
import { menuState, otherFilters, paintRows } from './filtermenu.js';
import { picked } from './host.js';
import { icon } from './icons.js';
import { partTip, showProblem, tickMark } from './overlays.js';
import { refresh } from './scope.js';
import { api } from './server.js';
import { className, classLayer, learnClasses } from './state.js';
import { esc, num, skeletonRows, tip } from './util.js';

// WHO's short line, under whatever shows a class, as the MedDRA version shows under reactions; it
// opens the rule with WHO's full citation
export const whoLine = () => `<a class="oa-who-line" href="/methods?open=atc-index">Drug classes: WHO ATC ${esc(classLayer().index_year)}, WHO Collaborating Centre for Drug Statistics Methodology, Oslo</a>`;
const yearChip = () => `<span class="oa-atc-year" ${tip("The year of WHO's ATC index this release's classes come from")}>WHO ATC ${classLayer().index_year}</span>`;

export function classesPane(sc) {
  return `<div class="oa-pane-head oa-atc-head"><p class="menu-heading">Drug class (ATC)</p>${yearChip()}</div>
    <input class="field-input oa-menu-search" id="oa-class-find" type="search" autocomplete="off" spellcheck="false" aria-label="Find a class" placeholder="Type a class, a code or a substance" value="${esc(menuState.classQ || '')}">
    ${roleTicks(sc.f.aroles, 'arole')}
    <div class="oa-choices oa-atc-could" id="oa-class-could"></div>
    <div class="oa-term-results" id="oa-class-results"></div>
    <p class="menu-footnote">${otherFilters(sc, 'atc')}A case counts when a drug in a ticked role is in a ticked class. ${whoLine()}</p>`;
}

// what the counts depend on: every filter but the classes ticked, the roles, and what was typed
const unticked = (sc) => ({ ...sc, f: { ...sc.f, atc: [], atcOut: [], could: false } });
const classKey = (sc) => `${query(unticked(sc))}|${(menuState.classQ || '').trim().toLowerCase()}`;

// ---- the ticks: a tree ----------------------------------------------------------------------------
// A class is ticked when the nearest chosen (f.atc) or left-out (f.atcOut) class at or above it is a
// chosen one, and partly ticked (a dash) when one of either is under it. A press ticks or unticks the
// class and every class under it; a class whose classes all end ticked, or all unticked, ends so too,
// unless records are classed at it itself (a report naming only the class above, as "an ACE
// inhibitor" is classed at C09A): its classes are not all of it, so it stays partly ticked.

// the class a class is in: an ATC code is 1, 3, 4, 5 or 7 characters, by level
const UP = { 7: 5, 5: 4, 4: 3, 3: 1 };
const parentOf = (code) => code.slice(0, UP[code.length] || 0);
const marks = (f) => [...f.atc, ...f.atcOut];
function onAt(f, code) {
  const near = marks(f).filter((c) => code.startsWith(c)).sort((a, b) => b.length - a.length)[0];
  return !!near && f.atc.includes(near);
}
export const tickOf = (f, code) => (marks(f).some((c) => c !== code && c.startsWith(code)) ? 'mixed' : onAt(f, code));
function setTo(f, code, on) {
  const outside = (c) => !c.startsWith(code);
  f.atc = f.atc.filter(outside); f.atcOut = f.atcOut.filter(outside);
  if (on !== onAt(f, code)) (on ? f.atc : f.atcOut).push(code);
}
// the classes under each class, as /api lists them, and whether records are classed at each class
// itself: the release's tree, known as it is opened
const known = { kids: new Map(), own: new Map() };
export function press(f, code, tree = known) {
  setTo(f, code, tickOf(f, code) !== true);
  for (let up = parentOf(code); up; up = parentOf(up)) {
    const ticks = new Set((tree.kids.get(up) || []).map((k) => tickOf(f, k)));
    if (ticks.size !== 1 || ticks.has('mixed') || tree.own.get(up) !== false) return;
    setTo(f, up, ticks.has(true));
  }
}
// a class pressed in the Overview's chart takes the place of the classes above and under it, so the
// chart steps down; what is left out stays left out where a chosen class is still above it
export function stepTo(f, code) {
  f.atc = f.atc.includes(code) ? f.atc.filter((c) => c !== code) : [...f.atc.filter((c) => !code.startsWith(c) && !c.startsWith(code)), code];
  f.atcOut = f.atcOut.filter((o) => f.atc.some((c) => o !== c && o.startsWith(c)));
}

const typed = () => (menuState.classQ || '').trim().toLowerCase();
function marked(text) {
  const q = typed();
  const i = q ? String(text).toLowerCase().indexOf(q) : -1;
  return i < 0 ? esc(text) : `${esc(text.slice(0, i))}<mark class="search-mark">${esc(text.slice(i, i + q.length))}</mark>${esc(text.slice(i + q.length))}`;
}

function classChoice(sc, c) {
  const on = tickOf(sc.f, c.code);
  return `<button type="button" class="menu-item oa-choice" role="menuitemcheckbox" aria-checked="${on}" data-act="class-pick" data-code="${esc(c.code)}" data-cases="${c.cases}" ${c.cases === 0 && !on ? 'data-state="empty"' : ''}>
    <span class="oa-tick" aria-hidden="true" ${partTip(on, 'class')}>${tickMark(on)}</span>
    <span class="menu-choice-words"><span><span class="oa-atc-code">${marked(c.code)}</span>${marked(c.name || '')}</span></span>
    <span class="choice-count">${num(c.cases)}</span></button>`;
}

// a class and, opened, the classes under it: those found when something is typed, else all of them
function node(sc, c, listed) {
  if (!c.more) return classChoice(sc, c);
  const ms = menuState;
  const found = listed.filter((k) => k.level === c.level + 1 && k.code.startsWith(c.code));
  const searched = typed() && found.length;
  const open = ms.classOpen.has(c.code) || (searched && !ms.classShut.has(c.code));
  const under = searched && !ms.classOpen.has(c.code) ? found : ms.classKids[`${c.code}|${classKey(sc)}`];
  const btn = `<button type="button" class="icon-btn oa-expand" data-act="class-expand" data-code="${esc(c.code)}" aria-expanded="${!!open}" aria-label="${open ? 'Hide' : 'Show'} its classes" ${tip(open ? 'Hide its classes' : 'Show its classes')}>${icon('chevronDown')}</button>`;
  const inner = !open ? '' : `<div class="oa-group-terms">${under ? under.map((k) => node(sc, k, listed)).join('') : skeletonRows(2)}</div>`;
  return `<div class="oa-group" data-open="${!!open}"><div class="oa-group-row">${classChoice(sc, c)}${btn}</div>${inner}</div>`;
}

// the classes chosen and left out, as the pane opened or the search last changed: they keep their
// rows while ticks change, so nothing moves under the pointer
function pinned(ms) {
  const key = classKey(ms.sc);
  if (ms.classPin?.key !== key) ms.classPin = { key, chosen: [...ms.sc.f.atc], out: [...ms.sc.f.atcOut], known: {} };
  const r = ms.classResult;
  if (r?.key === key) [...r.chosen, ...r.left_out].forEach((c) => { ms.classPin.known[c.code] = c; });
  return ms.classPin;
}

export function paintClassResults() {
  const box = document.getElementById('oa-class-results');
  if (!box || !menuState) return;
  const { sc, classResult: r } = menuState;
  paintCould();
  if (!r || r.key !== classKey(sc)) { box.innerHTML = skeletonRows(3); return; }
  const parts = [];
  const pin = pinned(menuState);
  const rows = (codes) => codes.map((code) => pin.known[code]).filter(Boolean).map((c) => classChoice(sc, c)).join('');
  if (pin.chosen.length) parts.push(`<p class="menu-heading">Chosen</p><div class="oa-choices">${rows(pin.chosen)}</div>`);
  if (pin.out.length) parts.push(`<p class="menu-heading">Left out</p><div class="oa-choices">${rows(pin.out)}</div>`);
  const roots = r.classes.filter((c) => c.level === Math.min(...r.classes.map((k) => k.level)));
  if (roots.length) parts.push(`${pin.chosen.length || pin.out.length ? '<p class="menu-heading">Classes</p>' : ''}<div class="oa-choices">${roots.map((c) => node(sc, c, r.classes)).join('')}</div>`);
  else parts.push(`<p class="oa-pane-none">No class has "${esc(menuState.classQ.trim())}" in its code or name.</p>`);
  box.innerHTML = parts.join('');
}

// one tick for the drugs that could be a chosen class: the report does not say which of its classes;
// it keeps its row with no class chosen, offered once one is
function paintCould() {
  const box = document.getElementById('oa-class-could');
  if (!box || !menuState) return;
  const { sc, classResult: r } = menuState;
  const off = !sc.f.atc.length;
  const n = !off && r && r.key === classKey(sc) && r.atc === ticksKey(sc) ? r.could : null;
  box.innerHTML = `<button type="button" class="menu-item oa-choice" role="menuitemcheckbox" aria-checked="${sc.f.could}" data-act="class-could" data-cases="${n ?? ''}" ${off ? `aria-disabled="true" ${tip('Tick a class first')}` : tip("A drug whose report does not say which of its classes it was given as, and one of them is the chosen class")}>
    <span class="oa-tick" aria-hidden="true">${tickMark(sc.f.could)}</span>
    <span class="menu-choice-words">Also the drugs that could be in it</span>
    ${n == null ? '<span class="choice-count"></span>' : `<span class="choice-count">+${num(n)}</span>`}</button>`;
}
const ticksKey = (sc) => `${sc.f.atc.join()}|${sc.f.atcOut.join()}`;

let classTimer = 0;
export function searchClasses() {
  clearTimeout(classTimer);
  const ms = menuState;
  if (!ms) return;
  const key = classKey(ms.sc);
  if (ms.classResult?.key === key && ms.classResult.atc === ticksKey(ms.sc)) { paintClassResults(); return; }
  paintClassResults();
  classTimer = setTimeout(async () => {
    try {
      const q = (ms.classQ || '').trim();
      const r = await api(`/api/classes?${query(ms.sc, q ? { q } : {})}`);
      learnClasses([...r.classes, ...r.chosen].map((c) => [c.code, c.name]));
      learnOwn([...r.classes, ...r.chosen, ...r.left_out]);
      if (menuState === ms && classKey(ms.sc) === key) { ms.classResult = { ...r, key, atc: ticksKey(ms.sc) }; paintClassResults(); paintRows(); }
    } catch (err) { showProblem(err); }
  }, 110);
}

const learnTree = (code, kids) => known.kids.set(code, kids.map((c) => c.code));
const learnOwn = (list) => list.forEach((c) => known.own.set(c.code, !!c.own));

async function loadKids(code) {
  const ms = menuState;
  const id = `${code}|${classKey(ms.sc)}`;
  if (ms.classKids[id]) return;
  try {
    const r = await api(`/api/classes?${query(unticked(ms.sc), { parent: code })}`);
    learnClasses(r.classes.map((c) => [c.code, c.name]));
    learnTree(code, r.classes); learnOwn(r.classes);
    if (menuState === ms) { ms.classKids[id] = r.classes; paintClassResults(); }
  } catch (err) { showProblem(err); }
}

// a class found by a search may sit under classes not opened yet: learn what is under each, so a
// press can tick a whole class
async function learnAbove(code) {
  const missing = [];
  for (let up = parentOf(code); up; up = parentOf(up)) if (!known.kids.has(up)) missing.push(up);
  await Promise.all(missing.map(loadKids));
}

// ---- a drug's class on the case list and in a case -----------------------------------------------

// on the case list: the class's code, a quiet mark when it is a broader class, WHO's name on hover
export function classTag(cls) {
  if (!cls) return '';
  const [code, name, broader] = cls;
  const words = `${code}: ${name}${broader ? '. A broader class: the report does not say which class under it' : ''}`;
  return ` <span class="oa-class-tag" ${tip(words)}>${esc(code)}${broader ? '<span class="oa-class-broader"> broader</span>' : ''}</span>`;
}

// the code and WHO's name, the name free to start the next line
const codeName = ([code, name]) => `<span class="oa-atc-code">${esc(code)}</span><wbr>${esc(name || '')}`;

// in a case: the drug's one class (or that it can't tell), how it was chosen with its rule, and the
// classes it could be when the report does not say which
export function classCell(cls) {
  if (!cls) return '<span class="oa-faint">No class found</span>';
  const how = CHOSEN_BY[cls.chosen_by] || [cls.chosen_by, ''];
  const main = cls.code ? `${codeName([cls.code, cls.name])}${cls.broader ? ' <span class="oa-chip oa-chip-quiet">Broader class</span>' : ''}` : "<span>Can't tell</span>";
  const could = !cls.code || cls.broader ? cls.possible : [];
  return `<div class="oa-class-cell">${main}
    ${could.length ? `<p class="oa-class-could">Could be ${could.map(codeName).join('<span class="oa-faint">, </span>')}</p>` : ''}
    <p class="oa-class-how"><a class="oa-link" href="/methods?open=atc-class-choice" ${tip(how[1])}>${esc(how[0])}</a></p></div>`;
}

// ---- what a click does ----------------------------------------------------------------------------

// each class's cases as the pane lists them, under the other filters
function casesOf(ms) {
  const key = classKey(ms.sc);
  const r = ms.classResult?.key === key ? ms.classResult : { classes: [], chosen: [], left_out: [] };
  const kids = Object.entries(ms.classKids).filter(([id]) => id.endsWith(`|${key}`)).flatMap(([, list]) => list);
  return new Map([...r.classes, ...r.chosen, ...r.left_out, ...kids].map((c) => [c.code, c.cases]));
}
const sameSet = (a, b) => [...a].sort().join() === [...b].sort().join();

actions({
  'class-pick': async (el) => {
    const ms = menuState; const code = el.dataset.code;
    await learnAbove(code);
    if (menuState !== ms) return;
    const f = ms.sc.f;
    const was = { atc: [...f.atc], out: [...f.atcOut] };
    press(f, code);
    if (tickOf(f, code) === true) picked('classes', ms.classQ, { level: 'class', code });
    if (!f.atc.length) f.could = false;
    // classes of no cases left out of a chosen one, or put back, cannot change the cases
    const n = casesOf(ms);
    const moved = [...was.out, ...f.atcOut].filter((c) => was.out.includes(c) !== f.atcOut.includes(c));
    const same = !f.could && sameSet(was.atc, f.atc) && moved.every((c) => n.get(c) === 0);
    searchClasses(); paintRows(); refresh(ms.sc, { same });
  },
  'class-could': (el) => {
    const sc = menuState.sc;
    if (!sc.f.atc.length) return;
    sc.f.could = !sc.f.could; paintCould(); paintRows();
    refresh(sc, { same: el.dataset.cases === '0' });
  },
  'class-expand': (el) => {
    const ms = menuState; const code = el.dataset.code;
    const open = el.getAttribute('aria-expanded') === 'true';
    if (open) { ms.classOpen.delete(code); ms.classShut.add(code); } else { ms.classShut.delete(code); ms.classOpen.add(code); loadKids(code); }
    paintClassResults();
  },
  arole: (el) => {
    const sc = menuState.sc;
    const next = toggled(sc.f.aroles, el.dataset.v);
    if (next === sc.f.aroles) return;
    sc.f.aroles = next; el.closest('.oa-roles').outerHTML = roleTicks(next, 'arole');
    searchClasses(); paintRows(); refresh(sc);
  },
});

document.addEventListener('input', (e) => {
  if (e.target.id !== 'oa-class-find' || !menuState) return;
  menuState.classQ = e.target.value;
  menuState.classOpen.clear(); menuState.classShut.clear();
  searchClasses();
});
