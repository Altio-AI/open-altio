/* Thresholds read as screens: a statistic's conditions, as /api/statistics/quarters takes them,
   whether a row's values meet them, and the conditions in words. */

export const WORDS = {
  cases: 'Cases', expected: 'Expected', ebgm: 'EBGM', eb05: 'EB05', eb95: 'EB95', prr: 'PRR',
  chi_square: 'Chi-square', chi_square_yates: 'Chi-square, Yates', ror: 'ROR', ror_lower: 'ROR lower bound',
  ror_upper: 'ROR upper bound', rrr: 'RRR', ic: 'IC', ic025: 'IC025',
};
export const COMPARE = { at_least: 'at least', above: 'above', at_most: 'at most', below: 'below' };
const TESTS = { at_least: (v, t) => v >= t, above: (v, t) => v > t, at_most: (v, t) => v <= t, below: (v, t) => v < t };

export const opOf = (cond) => Object.keys(cond).find((k) => k !== 'column');

// whether a pair's values meet every condition of a screen; an empty value meets no condition
export const meets = (when, pair) => when.every((c) => pair[c.column] != null && TESTS[opOf(c)](pair[c.column], c[opOf(c)]));

export const conditionWords = (when) => when.map((c) => `${WORDS[c.column]} ${COMPARE[opOf(c)]} ${c[opOf(c)]}`).join(', ');
