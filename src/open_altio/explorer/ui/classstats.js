/* The Statistics tab by WHO class, where the release holds the statistics of each class and the
   person may see the classes (/api/statistics/about's `classes`, rule statistics-classes): on All
   cases' tab the list is by ingredient or by class at one level; on a drug's tab, its class's EB05
   at the level chosen stands beside its own. One menu, from the button beside Thresholds, chooses
   both, and the choice is kept in this browser. statistics.js plugs these in. */

import { actions } from './events.js';
import { icon } from './icons.js';
import { choice, closeMenus, place, popMenu } from './overlays.js';
import { current } from './router.js';
import { S } from './state.js';
import { esc, store } from './util.js';

const KEPT = 'statistics-classes';
let held = null; // the release's class statistics, as /api/statistics/about says, or null
let kept = store.get(KEPT, {}); // { by: 'ingredient' or 'class', level }
let changed = () => {}; // the tab's reload, told the scope

export function useClasses(about, onChange) { held = about?.classes || null; changed = onChange; }

// known from the release (/api/release) before the tab's own answers come, so the toolbar is
// drawn whole at once
export const classesHeld = () => !!S.release?.class_statistics;
// the level chosen, the deepest the release holds until one is
export const classLevel = () => held?.levels.find((v) => v.level === kept.level) || held?.levels.at(-1);
// All cases' list, by class
export const byClass = (sc) => classesHeld() && !sc.product && kept.by === 'class';

// what /api/statistics reads of the choice
export function classParams(sc, p) {
  if (byClass(sc)) p.set('by', 'class');
  if (byClass(sc) || (sc.product && classesHeld())) p.set('level', String(classLevel().level));
}

const words = (sc) => (sc.product ? 'Class level' : byClass(sc) ? 'By class' : 'By ingredient');
export const classButton = (sc) => (classesHeld() ? `<button type="button" class="btn oa-classes-btn" data-act="stat-classes" aria-haspopup="menu" aria-label="${words(sc)}">${icon('bullets')}<span class="oa-btn-words">${words(sc)}</span></button>` : '');

// the drug's class beside its rows (/api/statistics's `class`), in the Class EB05 column's tip
export function classTip(sc) {
  const cls = sc.stat?.cls;
  const level = classLevel()?.name.toLowerCase();
  if (!cls) return `This drug has no WHO class at the ${level} level that the statistics count.`;
  return `EB05 of ${cls.name}, the drug's ${level} in WHO's classes, with the same reaction. Close to the drug's own, the reaction is reported for the whole class; far below it, for this drug more than for its class.`;
}

function menu(sc) {
  const level = classLevel().level;
  const levels = (on) => held.levels.map((v) => choice(on && v.level === level, v.name, null, `data-act="stat-by" data-v="class" data-level="${v.level}"`, { radio: true, note: `ATC level ${v.level}` })).join('');
  const how = `<a href="/rules?open=${encodeURIComponent(held.rule)}">How the class statistics are worked out</a>`;
  if (sc.product) return `<p class="menu-heading">Class EB05 at</p>${levels(true)}<p class="menu-footnote">The drug's class at this level, the one most of its cases name. ${how}</p>`;
  return `<p class="menu-heading">List by</p>${choice(!byClass(sc), 'Ingredient', null, 'data-act="stat-by" data-v="ingredient"', { radio: true })}
    <p class="menu-heading">WHO class</p>${levels(byClass(sc))}<p class="menu-footnote">${how}</p>`;
}

actions({
  'stat-classes': (el) => { if (held) place(popMenu(el, menu(current().scope), 'oa-classes-menu'), el); },
  'stat-by': (el) => {
    const sc = current().scope;
    const next = { by: sc.product ? kept.by : el.dataset.v, level: el.dataset.level ? +el.dataset.level : kept.level };
    // a list of another kind is sorted by its own columns again
    if (!sc.product && next.by !== kept.by && sc.stat) { sc.stat.sort = null; sc.stat.dir = null; }
    kept = next;
    store.set(KEPT, kept);
    closeMenus();
    changed(sc);
  },
});

// the class's name and code, in the first column of the list by class
export const classCell = (r) => `${esc(r.class_name)} <span class="oa-faint">${esc(r.class)}</span>`;
