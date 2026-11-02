/* Why two reports are likely the same patient, in words worked out from the two reports' own fields.
   Nothing here is typed in for a case: each field is compared and called same, close, differs or not
   given, and the words come from what agrees, in the order a person reads a case: who (age, sex,
   weight, country), what they took (the suspect drugs, the dose, how and when it was started, what
   for), what happened (when, the reactions, the outcome), how it reached FDA (the sender, the company
   case number, who reported it, when FDA got each). One sentence says what agrees; a second, short
   one, what clashes, or that nothing does. "Likely" when much agrees, "may be" when little does. Each
   phrase carries a tip with both reports' values.

   A pure module (no page, no fetching):
     sameness(kept, copy, { product, event, countryName, prev }) -> { likely, lead, parts: [{ words, tip }],
       path, link, clashes: [{ words, tip }], said: plain text, sig }
   `kept` and `copy` are /api/case answers; `product` the ingredient the event is counted for
   (valsartan); `event` the event's name; `prev` an earlier line's sig, so a second duplicate says
   "same woman, medicine and angioedema" rather than repeating it. */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// FDA's codes in plain words: who reported it (reporter_type_T, read from occp_cod), the outcomes as a clause
// about the patient, how often the dose was taken (in the sentence, and in a tip)
const REPORTER = { 1: 'a physician', 2: 'a pharmacist', 3: 'another health professional', 4: 'a lawyer', 5: 'a consumer' };
const OUTCOME = { DE: (p) => `${p} died`, LT: () => 'it was life-threatening', HO: (p) => `${p} was hospitalized`, DS: (p) => `${p} was left disabled`, CA: () => 'there was a birth defect', RI: (p) => `${p} needed treatment to prevent lasting harm`, OT: () => 'it was serious for another reason' };
const OUTCOME_TIP = { DE: 'died', LT: 'life-threatening', HO: 'hospitalized', DS: 'disabled', CA: 'birth defect', RI: 'needed treatment to prevent harm', OT: 'serious for another reason' };
const FREQ_SAID = { QD: 'daily', BID: 'twice a day', TID: '3 times a day', QID: '4 times a day', QOD: 'every other day', QW: 'weekly', QM: 'monthly', PRN: 'as needed', HS: 'at bedtime', '1X': 'once' };
const FREQ_TIP = { QD: 'once a day', BID: 'twice a day', TID: '3 times a day', QID: '4 times a day', QOD: 'every other day', QW: 'once a week', QM: 'once a month', PRN: 'as needed', HS: 'at bedtime', '1X': 'once' };
// codes that say the same thing
const FREQ_SAME = { Q24H: 'QD', Q12H: 'BID', Q8H: 'TID', Q6H: 'QID', Q1W: 'QW' };
const ROUTE_WORDS = { by_mouth: 'by mouth', under_tongue: 'under the tongue', injected: 'by injection', inhaled: 'inhaled', nasal: 'in the nose', rectal: 'rectally', vaginal: 'vaginally', transdermal: 'as a patch', skin: 'on the skin', eye: 'in the eye', ear: 'in the ear', other: 'another way' };
// an indication that says FDA was not told one
const NO_INDICATION = /^product used for unknown indication$/i;

const blank = (v) => v == null || String(v).trim() === '';
const notGiven = (row, name) => blank(row?.[name]) || (row?.not_given_T || []).includes(name);
const low = (s) => String(s).toLowerCase();
const title = (s) => String(s).toLowerCase().replace(/[.\s]+$/, '').replace(/(^|[\s\\/-])([a-z])/g, (m, a, b) => a + b.toUpperCase());
const andList = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);
const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
const plainDay = (iso) => { const [y, m, d] = String(iso).slice(0, 10).split('-'); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
// a date FDA gives as yyyymmdd, yyyymm or yyyy (its precision 8, 6 or 4), in words, with "in" or "on"
function fdaDate(raw, prec) {
  const r = String(raw || '');
  if (prec === 8 && r.length >= 8) return { at: 'on', words: `${+r.slice(6, 8)} ${MONTHS[+r.slice(4, 6) - 1]} ${r.slice(0, 4)}`, key: r.slice(0, 8), prec: 8 };
  if (prec >= 6 && r.length >= 6) return { at: 'in', words: `${MONTHS[+r.slice(4, 6) - 1]} ${r.slice(0, 4)}`, key: r.slice(0, 6), prec: 6 };
  if (r.length >= 4) return { at: 'in', words: r.slice(0, 4), key: r.slice(0, 4), prec: 4 };
  return null;
}
// two dates agree as far as both are given: same, differs, or not given
function dateCompare(a, b) {
  if (!a || !b) return 'none';
  const n = Math.min(a.key.length, b.key.length);
  return a.key.slice(0, n) === b.key.slice(0, n) ? 'same' : 'differs';
}

// ---- each report's facts ---------------------------------------------------------------------------------------
const SUSPECT = ['PS', 'SS', 'I'];
// a drug as a person writes it: an ingredient in lower case, a brand with its capital (Entresto)
const drugWord = (d) => { const n = String(d.drugname_norm_T || d.drugname || '').replace(/[.\s]+$/, ''); return d.substance_T && low(n) === d.substance_T ? low(n) : title(n); };
const ingredients = (d) => (d.substance_T ? d.substance_T.split(';') : [low(d.prod_ai_norm_T || d.drugname_norm_T || d.drugname || '')]);
function factsOf(c, product) {
  const suspects = (c.drug || []).filter((d) => SUSPECT.includes(d.role_T));
  const ours = suspects.find((d) => ingredients(d).includes(low(product))) || suspects.find((d) => d.role_T === 'PS') || suspects[0] || null;
  const ther = ours ? (c.ther || []).filter((t) => t.dsg_drug_seq === ours.drug_seq && !blank(t.start_dt)) : [];
  const start = ther.map((t) => fdaDate(t.start_dt, t.start_dt_prec_T)).filter(Boolean).sort((x, y) => x.key.localeCompare(y.key))[0] || null;
  const indications = ours ? (c.indi || []).filter((i) => i.indi_drug_seq === ours.drug_seq && !blank(i.indi_pt) && !NO_INDICATION.test(i.indi_pt)).map((i) => i.indi_pt_T || i.indi_pt) : [];
  const freq = ours && !notGiven(ours, 'dose_freq') ? String(ours.dose_freq).toUpperCase() : null;
  const dose = ours && !notGiven(ours, 'dose_amt') && !notGiven(ours, 'dose_unit') ? { amt: +ours.dose_amt, unit: low(ours.dose_unit) } : null;
  const routes = ours && ours.route_families_T?.length && ours.route_source_T !== 'disagree' ? [...ours.route_families_T] : [];
  return {
    key: c.case_key_T,
    age: c.age_years_T == null ? null : c.age_years_T,
    sex: c.sex_T || null,
    weight: c.wt_kg_T == null ? null : c.wt_kg_T,
    country: c.country_T || null,
    drug: ours ? drugWord(ours) : null,
    suspects: [...new Set(suspects.flatMap(ingredients))].sort(),
    otherSuspects: [...new Set(suspects.filter((d) => d !== ours).map(drugWord))],
    dose, freq: FREQ_SAME[freq] || freq,
    route: routes.length === 1 ? routes[0] : null,
    form: ours && !notGiven(ours, 'dose_form') && !/^unknown$/i.test(ours.dose_form) ? ours.dose_form : null,
    start,
    indications: indications.map(low).sort(),
    indicationWords: indications,
    eventDate: notGiven(c, 'event_dt') ? null : fdaDate(c.event_dt, c.event_dt_prec_T),
    reactions: (c.reac || []).map((r) => r.pt_T || r.pt),
    outcomes: [...(c.outcomes_T || [])].sort(),
    sender: c.direct_T ? 'sent straight to FDA' : c.company_T || null,
    number: blank(c.mfr_num) ? null : String(c.mfr_num).trim().toUpperCase(),
    reporter: c.reporter_type_T ? String(c.reporter_type_T) : null,
    received: c.first_fda_dt_T ? String(c.first_fda_dt_T).slice(0, 10) : null,
    // what rule dedup-default's first duplicate rule keys on, as FDA wrote it
    aeolus: [c.event_dt, c.age, c.age_cod, c.sex_T, c.country_T, [...new Set((c.drug || []).map((d) => d.drugname_norm_T))].sort().join('|'), [...new Set((c.reac || []).map((r) => String(r.pt).toUpperCase()))].sort().join('|')],
  };
}
// a company case number joins its coded form (country, company, number), as rule dup-manufacturer-number reads it
const bareNumber = (n) => (n ? n.replace(/^[A-Z]{2}-[^-]+-/, '') : null);

// ---- words ---------------------------------------------------------------------------------------------------
const ageWords = (y) => (y < 2 ? `${Math.round(y * 12)}-month-old` : `${Math.floor(y)}-year-old`);
const ageTip = (y) => (y == null ? 'age not given' : y < 2 ? `${Math.round(y * 12)} months` : `${Math.floor(y)} years`);
const noun = (sex, age) => (sex === 'F' ? (age != null && age < 18 ? 'girl' : 'woman') : sex === 'M' ? (age != null && age < 18 ? 'boy' : 'man') : 'patient');
const pronoun = (sex) => (sex === 'F' ? 'she' : sex === 'M' ? 'he' : 'the patient');
const possessive = (sex) => (sex === 'F' ? 'her' : sex === 'M' ? 'his' : "the patient's");
const num = (v) => String(Math.round(v * 10) / 10);
const doseWords = (f, words) => (f.dose ? `${num(f.dose.amt)} ${f.dose.unit}${f.freq ? ` ${(words[f.freq] || f.freq.toLowerCase())}` : ''}` : '');
const daysApart = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
function gapWords(d) {
  const n = Math.abs(d);
  if (n === 0) return 'the same day';
  if (n === 1) return 'a day apart';
  if (n <= 60) return `${n} days apart`;
  if (n < 730) return `${Math.round(n / 30.4)} months apart`;
  return `${Math.round(n / 365.25)} years apart`;
}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// a field compared: same, close, differs or none (not given in one or both)
function compare(a, b, { close = null } = {}) {
  if (a == null || b == null) return 'none';
  if (a === b) return 'same';
  if (close && close(a, b)) return 'close';
  return 'differs';
}

// both reports' values for a tip: "Both: x" where they read the same, else each with its case number
function both(kept, copy, words) {
  const a = words(kept), b = words(copy);
  return a === b ? `Both: ${a}.` : `Case ${kept.key}: ${a}. Case ${copy.key}: ${b}.`;
}

export function sameness(keptCase, copyCase, { product = '', event = '', countryName = (c) => c, prev = null } = {}) {
  const k = factsOf(keptCase, product), c = factsOf(copyCase, product);
  const country = (code) => (code ? countryName(code) : 'country not given');
  const eventWord = event ? event.charAt(0).toLowerCase() + event.slice(1) : 'the reaction';
  const he = pronoun(k.sex === c.sex ? k.sex : null);

  const f = {
    age: compare(k.age == null ? null : Math.floor(k.age), c.age == null ? null : Math.floor(c.age), { close: (x, y) => Math.abs(x - y) <= 1 }),
    sex: compare(k.sex, c.sex),
    weight: compare(k.weight, c.weight, { close: (x, y) => Math.abs(x - y) <= 2 }),
    country: compare(k.country, c.country),
    suspects: compare(k.suspects.join('|') || null, c.suspects.join('|') || null),
    dose: compare(k.dose ? `${k.dose.amt} ${k.dose.unit}` : null, c.dose ? `${c.dose.amt} ${c.dose.unit}` : null),
    freq: compare(k.freq, c.freq),
    route: compare(k.route, c.route),
    form: compare(k.form && low(k.form), c.form && low(c.form)),
    start: dateCompare(k.start, c.start),
    indication: k.indications.length && c.indications.length ? (sameSet(k.indications, c.indications) ? 'same' : 'differs') : 'none',
    eventDate: dateCompare(k.eventDate, c.eventDate),
    reactions: sameSet(k.reactions.map(low), c.reactions.map(low)) ? 'same' : 'differs',
    outcome: sameSet(k.outcomes, c.outcomes) ? 'same' : 'differs',
    sender: compare(k.sender, c.sender),
    number: compare(bareNumber(k.number), bareNumber(c.number)),
    reporter: compare(k.reporter, c.reporter),
  };
  const agrees = (x) => x === 'same' || x === 'close';

  // who
  const who = [];
  if (agrees(f.age)) who.push(ageWords(k.age));
  who.push(agrees(f.sex) ? noun(k.sex, k.age) : 'patient');
  if (agrees(f.weight)) who.push(`of ${num(k.weight)} kg`);
  if (agrees(f.country)) who.push(`in ${country(k.country)}`);
  const whoSaid = agrees(f.age) || agrees(f.sex) || agrees(f.country) ? who.join(' ') : '';
  const whoTip = both(k, c, (x) => [ageTip(x.age), x.sex === 'F' ? 'female' : x.sex === 'M' ? 'male' : 'sex not given', x.weight == null ? '' : `${num(x.weight)} kg`, country(x.country)].filter(Boolean).join(', '));

  // what they took: the event's drug, its dose when both agree, its start as far as both give it
  const med = k.drug ? [k.drug] : [];
  if (med.length && agrees(f.dose) && f.freq !== 'differs') med.push(doseWords(f.freq === 'same' ? k : { ...k, freq: null }, FREQ_SAID));
  if (med.length && f.start === 'same') { const s = (k.start.prec >= c.start.prec ? k : c).start; med.push(`from ${s.words}`); }
  if (med.length && agrees(f.suspects) && k.otherSuspects.length) med.push(`and ${andList(k.otherSuspects)}`);
  const medSaid = med.join(' ');
  const medTip = both(k, c, (x) => [x.drug || 'no suspect drug', x.otherSuspects.length ? `with ${andList(x.otherSuspects)}` : '', doseWords(x, FREQ_TIP), x.route ? ROUTE_WORDS[x.route] || x.route : '', x.form ? low(x.form) : '', x.indicationWords.length ? `for ${andList(x.indicationWords.map(low))}` : '', x.start ? `started ${x.start.words}` : ''].filter(Boolean).join(', '));

  // what happened
  const happened = [eventWord];
  if (f.eventDate === 'same') { const d = (k.eventDate.prec >= c.eventDate.prec ? k : c).eventDate; happened.push(`${d.at} ${d.words}`); }
  const happenedSaid = happened.join(' ');
  const happenedTip = both(k, c, (x) => `${andList(x.reactions.map(low))}${x.eventDate ? `, ${x.eventDate.at} ${x.eventDate.words}` : ', no date given'}; ${x.outcomes.length ? andList(x.outcomes.map((o) => OUTCOME_TIP[o] || o)) : 'no outcome given'}`);

  // how it reached FDA: the strongest two of what agrees, and how far apart FDA got them
  const from = f.sender === 'same' ? (k.sender === 'sent straight to FDA' ? 'both sent straight to FDA' : `both from ${k.sender}`) : '';
  const numbered = f.number === 'same' ? 'the same company case number' : '';
  const by = f.reporter === 'same' ? `reported by ${REPORTER[k.reporter] || 'the same kind of reporter'}` : '';
  const path = from ? `${from}${numbered ? ` with ${numbered}` : by ? `, ${by}` : ''}` : numbered ? `both with ${numbered}${by ? `, ${by}` : ''}` : by ? `both ${by}` : '';
  const gap = k.received && c.received ? gapWords(daysApart(k.received, c.received)) : '';
  const pathSaid = path ? [path, gap].filter(Boolean).join(', ') : gap ? `received ${gap}` : '';
  const pathTip = both(k, c, (x) => [x.sender || 'sender not given', x.number ? `company case number ${x.number}` : 'no company case number', x.reporter ? `reported by ${REPORTER[x.reporter] || 'another reporter'}` : 'reporter not given', x.received ? `received ${plainDay(x.received)}` : ''].filter(Boolean).join(', '));

  // a link through another report: neither of the release's two rules joins these two alone
  const direct = (k.aeolus.every((v, i) => v != null && v !== '' && v === c.aeolus[i])) || (f.number === 'same' && f.sender === 'same');
  const others = (keptCase.group || []).filter((g) => g.case_key_T !== c.key).map((g) => g.case_key_T);
  const link = !direct && others.length ? { words: `linked through ${others.length === 1 ? `case ${others[0]}` : `cases ${andList(others)}`}`, tip: `The release groups reports that agree with each other: these two each agree with ${others.length === 1 ? 'that report' : 'one of those reports'}, so they are one group` } : null;

  // likely or may be: how much of who, what and when agrees
  const strong = ['age', 'sex', 'country', 'weight', 'suspects', 'dose', 'start', 'eventDate', 'reactions', 'number'].filter((x) => f[x] === 'same' || f[x] === 'close').length;
  const likely = strong >= 5 || (f.number === 'same' && strong >= 3);

  // a later duplicate that agrees as the one before it says so in a word
  const sig = { who: whoSaid, med: medSaid, happened: happenedSaid, noun: whoSaid ? noun(k.sex, k.age) : '' };
  const parts = [];
  const sameAsBefore = prev ? ['who', 'med', 'happened'].filter((x) => sig[x] && sig[x] === prev[x]) : [];
  if (sameAsBefore.length >= 2) {
    const named = sameAsBefore.map((x) => (x === 'who' ? sig.noun : x === 'med' ? 'medicine' : eventWord));
    parts.push({ words: `same ${andList(named)}`, tip: [whoTip, medTip, happenedTip].filter((_, i) => sameAsBefore.includes(['who', 'med', 'happened'][i])).join(' ') });
    if (!sameAsBefore.includes('who') && whoSaid) parts.push({ words: whoSaid, tip: whoTip });
    if (!sameAsBefore.includes('med') && medSaid) parts.push({ words: medSaid, tip: medTip });
    if (!sameAsBefore.includes('happened')) parts.push({ words: happenedSaid, tip: happenedTip });
  } else {
    if (whoSaid) parts.push({ words: whoSaid, tip: whoTip });
    if (medSaid) parts.push({ words: medSaid, tip: medTip });
    parts.push({ words: happenedSaid, tip: happenedTip });
  }
  const pathPart = pathSaid ? { words: pathSaid, tip: pathTip, path: true } : null;

  // what clashes, the copy's word against the kept case's, patient first; how it reached FDA never clashes (a
  // report reaches FDA by several companies and reporters)
  const clashes = [];
  const clash = (words, tip) => clashes.push({ words, tip });
  const his = possessive(k.sex === c.sex ? k.sex : null);
  if (f.age === 'differs') clash(`it gives ${his} age as ${Math.floor(c.age)}`, both(k, c, (x) => ageTip(x.age)));
  if (f.sex === 'differs') clash(`it says ${c.sex === 'F' ? 'female' : 'male'}`, both(k, c, (x) => (x.sex === 'F' ? 'female' : 'male')));
  if (f.country === 'differs') clash(`it says ${country(c.country)}`, both(k, c, (x) => country(x.country)));
  if (f.weight === 'differs') clash(`it gives ${his} weight as ${num(c.weight)} kg`, both(k, c, (x) => `${num(x.weight)} kg`));
  if (f.suspects === 'differs') {
    const extra = c.suspects.filter((x) => !k.suspects.includes(x)), gone = k.suspects.filter((x) => !c.suspects.includes(x));
    clash(extra.length ? `only it names ${andList(extra)} as a suspect` : `only case ${k.key} names ${andList(gone)} as a suspect`, both(k, c, (x) => andList(x.suspects)));
  }
  if (f.dose === 'differs' || f.freq === 'differs') clash(`it gives the dose as ${doseWords(c, FREQ_TIP)}`, both(k, c, (x) => doseWords(x, FREQ_TIP) || 'no dose given'));
  if (f.start === 'differs') clash(`it has the drug started ${c.start.words}`, both(k, c, (x) => (x.start ? `started ${x.start.words}` : 'no start given')));
  if (f.route === 'differs') clash(`it says the drug was taken ${ROUTE_WORDS[c.route] || c.route}`, both(k, c, (x) => ROUTE_WORDS[x.route] || x.route));
  if (f.indication === 'differs') clash(`it says the drug was taken for ${andList(c.indicationWords.map(low))}`, both(k, c, (x) => andList(x.indicationWords.map(low))));
  if (f.eventDate === 'differs') clash(`it dates ${eventWord} ${c.eventDate.words}`, both(k, c, (x) => (x.eventDate ? x.eventDate.words : 'no date given')));
  if (f.reactions === 'differs') {
    const extra = c.reactions.filter((x) => !k.reactions.map(low).includes(low(x))), gone = k.reactions.filter((x) => !c.reactions.map(low).includes(low(x)));
    if (extra.length) clash(`only it reports ${andList(extra.map(low))}`, both(k, c, (x) => andList(x.reactions.map(low))));
    if (gone.length) clash(`only case ${k.key} reports ${andList(gone.map(low))}`, both(k, c, (x) => andList(x.reactions.map(low))));
  }
  if (f.outcome === 'differs') {
    const say = (codes) => andList(codes.map((o) => (OUTCOME[o] ? OUTCOME[o](he) : o)));
    const extra = c.outcomes.filter((x) => !k.outcomes.includes(x)), gone = k.outcomes.filter((x) => !c.outcomes.includes(x));
    const tipOut = both(k, c, (x) => (x.outcomes.length ? andList(x.outcomes.map((o) => OUTCOME_TIP[o] || o)) : 'no outcome given'));
    if (extra.length) clash(`only it says ${say(extra)}`, tipOut);
    if (gone.length) clash(`only case ${k.key} says ${say(gone)}`, tipOut);
  }

  const lead = likely ? 'Likely the same patient' : 'May be the same patient';
  const agreed = [parts.map((p) => p.words).join(', '), pathPart?.words, link?.words].filter(Boolean).join('; ');
  const differs = clashes.length ? `${cap(clashes.slice(0, 3).map((x) => x.words).join('; '))}.` : 'Nothing contradicts it.';
  return { likely, lead, parts, path: pathPart, link, clashes: clashes.slice(0, 3), sig, said: `${lead}: ${agreed}. ${differs}` };
}
