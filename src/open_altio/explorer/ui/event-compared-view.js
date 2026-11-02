/* A drug pressed on the Compared tab (event-compared.js): the same event for that drug, in place
   of the comparison. Its row, as a drug's events table shows it, opens under it: the opened event
   (event.js) for that drug, starting with this event's window, counting date and filters, against
   the same host thresholds, with Back to the first drug's event at the right of its bar. Its own
   line changes only its own view. The drug is counted the standard way: any product containing it,
   in the event's roles. Its row has no host's column and its bar no host's next step; a host says
   what it says about another drug in the places under the bar and on the line, which are handed the
   view's `from`. */

import { openedEvent } from './event.js';
import { restack, stickY, sticks } from './event-stick.js';
import { eventsTable } from './eventstable.js';
import { api } from './server.js';
import { S } from './state.js';
import { esc } from './util.js';
import { inSentence, titleOf } from './event-compared-data.js';

// another drug's settings: the event's roles, products and duplicates, none of its own spellings
const SETTINGS = ['prole', 'unit', 'dedup'];
function settingsOf(ctx, drug) {
  const p = new URLSearchParams(ctx.query());
  const out = new URLSearchParams({ product: drug });
  SETTINGS.forEach((k) => p.getAll(k).forEach((v) => out.append(k, v)));
  return String(out);
}

// a group of reactions has no row in a drug's events: its row is the group's figures and statistics
async function groupRow(ctx, drug, query) {
  const terms = ctx.reaction.map((r) => `reaction=${encodeURIComponent(r)}`).join('&');
  const [figures, stats] = await Promise.all([
    api(`/api/events/group?${query}&${terms}`),
    S.me?.statistics === false ? Promise.resolve({ why: 'Statistics are not open to you here.' })
      : api(`/api/statistics/group?product=${encodeURIComponent(drug)}&${terms}`).then((got) => ({ got }), (err) => ({ why: err.message })),
  ]);
  const { cases, ...s } = stats.got || {};
  return { row: { ...s, ...figures, pt: ctx.row?.pt || ctx.reaction.join(', '), reactions: [...ctx.reaction], product: drug }, why: stats.why || null };
}

// the view's top under the layers that stay at the top, where they stick
function bringUp(pane) {
  const page = pane.closest('.frame-page') || document.scrollingElement;
  if (!sticks(pane)) { if (pane.getBoundingClientRect().top < 0) pane.scrollIntoView({ block: 'start' }); return; }
  const under = stickY(pane, 4);
  const at = pane.getBoundingClientRect().top;
  if (at < under) page.scrollTop += at - under;
}

function afterRestack(pane) {
  restack();
  requestAnimationFrame(() => requestAnimationFrame(() => { if (pane.isConnected) bringUp(pane); }));
}

// The view of `drug`, drawn in place of the comparison; drawn again when the first event's dates or
// filters change, so it starts from them again.
export function openView(cmp, drug) {
  closeView(cmp);
  const { ctx } = cmp;
  const main = cmp.pane.querySelector('.oa-cmp-main'), box = cmp.pane.querySelector('.oa-cmp-view');
  if (!main || !box) return;
  cmp.viewing = drug;
  main.hidden = true;
  box.hidden = false;
  // it takes the first event's place under that event's row: the line, the bar and a host's next step
  // there are that event's, and go until Back
  cmp.pane.closest('.oa-ev').dataset.viewing = 'true';
  box.innerHTML = `<p class="oa-cmp-viewtitle"><strong>${esc(titleOf(drug))}</strong>'s ${esc(cmp.event)}, read only</p><div class="oa-cmp-viewtable"></div>`;
  const place = box.querySelector('.oa-cmp-viewtable');
  const query = settingsOf(ctx, drug);
  const key = `${drug}|${ctx.reaction.join('|').toLowerCase()}`;
  const opened = {
    key,
    draw: (inner, row) => {
      openedEvent(inner, { drug, row, query, reaction: ctx.reaction, screens: ctx.screens, classes: ctx.classes, from: ctx, back: () => { closeView(cmp); afterRestack(cmp.pane); } });
    },
  };
  const common = { find: false, open: () => {}, rowKey: () => key, opened };
  if (ctx.reaction.length === 1) {
    const pt = ctx.reaction[0].toLowerCase();
    cmp.table = eventsTable(place, { ...common, drug, query, only: (r) => r.pt.toLowerCase() === pt });
  } else {
    cmp.table = eventsTable(place, { ...common, rows: null });
    groupRow(ctx, drug, query).then(({ row, why }) => {
      if (cmp.viewing === drug) cmp.table.update({ rows: [row], noStatistics: why });
    });
  }
  afterRestack(cmp.pane);
}

// back to the comparison: the view's event is closed, so its panes are told
export function closeView(cmp) {
  if (!cmp.viewing) return;
  cmp.table?.update({ opened: null });
  cmp.viewing = null;
  cmp.table = null;
  const main = cmp.pane.querySelector('.oa-cmp-main'), box = cmp.pane.querySelector('.oa-cmp-view');
  if (box) { box.hidden = true; box.replaceChildren(); }
  if (main) main.hidden = false;
  delete cmp.pane.closest('.oa-ev')?.dataset.viewing;
  cmp.paintRows();
}
