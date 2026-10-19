/* Where a person's custom MedDRA queries (CMQs) are kept, and how a list names them. On this machine
   they are kept in this browser and are all the person's own. A host may keep them in the person's
   account instead (host.queries), where the people of a group the person belongs to may share theirs:
   S.cmqs then holds both, each saying whether it is the person's own (`mine`), shared, who made it
   (`by`) and on what day (`made`), and whether the person may change it (`changes`). */

import { host } from './host.js';
import { S } from './state.js';
import { store } from './util.js';

// whether the queries are kept somewhere other than this browser
export const inAccount = () => !!host.queries;
// the group the person may share a query with, by its name; '' where there is none
export const shareGroup = () => host.queries?.group || '';
export const isMine = (q) => q.mine !== false;
export const mayChange = (q) => isMine(q) || !!q.changes;

// the grey line under a query's name: what it holds, and who made a colleague's
export function queryNote(q) {
  const terms = `${q.terms.length} ${q.terms.length === 1 ? 'term' : 'terms'}`;
  if (!isMine(q)) return `Made by ${q.by} · ${terms}`;
  return q.shared && shareGroup() ? `Shared with ${shareGroup()} · ${terms}` : terms;
}

// where a term added from another query came from, as its editor notes it
export const fromQuery = (q) => (isMine(q) ? `your query ${q.name}` : `${q.by}'s query ${q.name}`);
// where each of a query's terms came from, as this person reads it: a colleague's "your query" is theirs
export const notesOf = (q) => Object.fromEntries(Object.entries(q.src || {})
  .map(([t, note]) => [t, isMine(q) ? note : note.replace(/^from your query /, `from ${q.by}'s query `)]));

// queries under their headings: the person's own, then the group's, where they have one; `other` when
// they are the ones beside the query being edited
export function queryGroups(list, { other = false } = {}) {
  const own = other ? 'Your other' : 'Your';
  if (!shareGroup()) return list.length ? [[`${own} custom MedDRA queries (CMQs)`, list]] : [];
  return [[`${own} queries`, list.filter(isMine)], [`${shareGroup()}'s queries`, list.filter((q) => !isMine(q))]].filter(([, l]) => l.length);
}

// The query kept, new or changed: as it is kept now, or { problem }.
export async function keepQuery(q) {
  const kept = host.queries ? await host.queries.save(q) : { ...q, id: q.id || `q${Date.now()}` };
  if (kept.problem) return kept;
  // a colleague's query whose sharing an admin turned off is no longer theirs to see
  const gone = !isMine(kept) && !kept.shared;
  const at = S.cmqs.findIndex((x) => x.id === kept.id);
  if (gone) S.cmqs = S.cmqs.filter((x) => x.id !== kept.id);
  else if (at < 0) S.cmqs.push(kept); else S.cmqs[at] = kept;
  if (!host.queries) store.set('cmqs', S.cmqs);
  return kept;
}

// The query deleted: {} or { problem }.
export async function dropQuery(q) {
  const done = host.queries ? await host.queries.remove(q) : {};
  if (done.problem) return done;
  S.cmqs = S.cmqs.filter((x) => x.id !== q.id);
  if (!host.queries) store.set('cmqs', S.cmqs);
  return {};
}
