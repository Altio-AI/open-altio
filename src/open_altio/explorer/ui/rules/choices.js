/* A set of rule choices: { rule: { on: false } | { values: { key: value } } }, holding only what
   differs from Altio's standard. The API sends and takes the shape a release records them in:
   { off: [rule], changed: [{ rule, key, value, standard }] }. */

export const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function fromApi({ off = [], changed = [] } = {}) {
  const out = {};
  for (const name of off) out[name] = { on: false };
  for (const { rule, key, value } of changed) {
    out[rule] = { ...(out[rule] || {}), values: { ...(out[rule]?.values || {}), [key]: value } };
  }
  return out;
}

export function toApi(choices) {
  return {
    off: Object.keys(choices).filter((name) => choices[name].on === false),
    changed: Object.entries(choices).flatMap(([rule, c]) => Object.entries(c.values || {}).map(([key, value]) => ({ rule, key, value }))),
  };
}

export const isOn = (choices, name) => choices[name]?.on !== false;
const standardOf = (rule, key) => rule.values.find((v) => v.key === key)?.standard;
export const valueIn = (choices, rule, key) => {
  const mine = choices[rule.name]?.values;
  return mine && key in mine ? mine[key] : standardOf(rule, key);
};

// the choices with every value back at Altio's dropped, and a rule that differs in nothing gone
export function tidy(choices, rules) {
  const out = {};
  for (const [name, c] of Object.entries(choices)) {
    const rule = rules.find((r) => r.name === name);
    if (!rule) continue;
    const values = Object.fromEntries(Object.entries(c.values || {}).filter(([k, v]) => !same(v, standardOf(rule, k))));
    const kept = Object.keys(values).length ? { values } : {};
    if (c.on === false) out[name] = { on: false, ...kept };
    else if (Object.keys(values).length) out[name] = kept;
  }
  return out;
}

// how many rules two sets of choices treat differently
export function differing(a, b) {
  const names = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...names].filter((name) => !same(a[name] || {}, b[name] || {})).length;
}

export function summary(choices) {
  const all = Object.values(choices);
  const off = all.filter((c) => c.on === false).length;
  const changed = all.length - off;
  return `Your rules: ${[off && `${off} off`, changed && `${changed} changed`].filter(Boolean).join(', ')}`;
}

export const anyChoice = (choices) => Object.keys(choices).length > 0;
