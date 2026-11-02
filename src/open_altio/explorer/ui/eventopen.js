/* A drug's Events tab opens an event under its row. A press on a row opens Open Altio's opened event
   in the cell the events table keeps under it through every sort, narrowing and redraw while the row
   is listed; a press on the open row closes it, and one row is open at a time. The address keeps the
   row open as ?open=<event>, so a reload or a link opens it again, whatever the thresholds say. */

import { openedEvent } from './event.js';
import { putAddress } from './router.js';

const OPEN = 'open';
const named = () => new URLSearchParams(location.search).get(OPEN);

// the address with the row open now, or with none
function keepAddress(key) {
  const asked = new URLSearchParams(location.search);
  if (key) asked.set(OPEN, key); else asked.delete(OPEN);
  const search = asked.toString();
  putAddress(`${location.pathname}${search ? `?${search}` : ''}`);
}

// a drug's page lists each event once
const rowKey = (row) => row.pt.toLowerCase();

// The options that open `drug`'s rows, in terms of `table()`, its handle once drawn.
export const openOptions = (drug, table) => ({
  rowKey,
  beyond: (row) => rowKey(row) === named(),
  open: () => keepAddress(table().opened()),
  opened: { key: named(), draw: (box, row) => openedEvent(box, { drug, row }), gone: () => keepAddress(null) },
});
