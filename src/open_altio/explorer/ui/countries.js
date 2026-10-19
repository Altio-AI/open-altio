/* Countries as a person reads them: the name for FDA's code, from the ISO 3166-1 list; a code that
   names no country of today with its own name and a note; and what FDA writes where no country was
   given, read as not given. The names and notes are rule legacy-country's, FDA's words for no country
   rule country-not-given's, sent with /api/release. */

import { S } from './state.js';

const regions = new Intl.DisplayNames(['en'], { type: 'region' });
const title = (s) => String(s).toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase());
const words = () => S.release?.countries || { noted: {}, not_given: [] };

// country_source_T for a country taken from an earlier version of the case (rule eu-member-state)
export const EARLIER_VERSION = 'earlier version';
// FDA's words for a country it was not given, such as COUNTRY NOT SPECIFIED
export const countryNotGiven = (code) => words().not_given.includes(code);
// what a code that names no country of today stands for, or ''
export const countryNote = (code) => words().noted[code]?.note || '';

export function countryName(code) {
  if (code == null || code === '_none') return 'Not given';
  if (countryNotGiven(code)) return `Not given (${code})`;
  if (words().noted[code]) return words().noted[code].name;
  if (/^[A-Z]{2}$/.test(code)) {
    try { const n = regions.of(code); if (n && n !== code) return n; } catch { /* not a region code */ }
    return code;
  }
  return title(code);
}
