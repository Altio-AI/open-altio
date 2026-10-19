/* Talking to the server: /api answers, each asked once and kept, and JSON sent to it. */

import { host } from './host.js';

// JSON sent with a POST, or the method named; the server's message comes back as `problem`
export async function post(path, body = {}, method = 'POST') {
  try {
    const r = await fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const said = await r.json().catch(() => ({}));
    return { ...said, ok: r.ok, status: r.status, problem: said.problem || (r.ok ? '' : `The server answered ${r.status}. Try again.`) };
  } catch {
    return { ok: false, status: 0, problem: 'The server did not answer. Try again in a moment.' };
  }
}

const cache = new Map();
export function api(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then(async (r) => {
      if (r.status === 401) { cache.delete(path); host.signedOut(); throw new Error('Sign in again.'); }
      const body = await r.json();
      if (!r.ok || body.problem) { cache.delete(path); throw new Error(body.problem || r.statusText); }
      return body;
    }));
  }
  return cache.get(path);
}
