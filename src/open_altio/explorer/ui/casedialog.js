/* The case dialog: one case in full, FDA's values under Open Altio's where they differ, why a
   probable duplicate is shown or set aside, each suspect's label flag under each reaction (labels.js),
   and the steps to the list's next and previous case. It reads in the order a safety reviewer reads
   a case: a line about it, what happened, the drugs (suspects first), the patient, and the report
   itself last. While it is open the address names the case (?case=), so a bookmark or a case number
   from an export opens it again, set aside or not. MedDRA terms are shown as meddra.js says. */

import { classCell } from './classes.js';
import { DECHAL, ERA, INGREDIENT_SOURCE, NO_ONSET, OUTCOME, RECHAL, REPORTER, REPT, ROLE, ROUTE_FAMILY, ROUTE_SOURCE, SEX, UNUSABLE_SERIOUS, freqWords, labelOf, noOutcome } from './codes.js';
import { EARLIER_VERSION, countryName, countryNote, countryNotGiven } from './countries.js';
import { actions } from './events.js';
import { host } from './host.js';
import { icon } from './icons.js';
import { labelSources, labelsOn, reactionLines } from './labels.js';
import { termShown } from './meddra.js';
import { layer, showProblem } from './overlays.js';
import { putAddress } from './router.js';
import { scopeNow } from './scope.js';
import { api } from './server.js';
import { ages, eras } from './state.js';
import { companyName, day, esc, fdaDay, fix, num, quarterStart, ruleTag, skeletonRows, tip } from './util.js';

let caseNav = null; // { sc, index }

function fda(clean, raw) {
  const c = clean == null || clean === '' ? '' : String(clean);
  const r = raw == null || raw === '' ? '' : String(raw);
  return `${esc(c || 'Not given')}${r && r !== c ? ` <span class="oa-fda" ${tip('As FDA published it')}>FDA: ${esc(r)}</span>` : ''}`;
}
// whether a field of a row reads Not given (rule not-given): empty, or named in its not_given_T
const notGiven = (row, name) => (row.not_given_T || []).includes(name) || row[name] == null;
// a field of a row: Not given, with FDA's value under it, where it reads so; else as shown
const field = (row, name, shown = row[name]) => (notGiven(row, name) ? fda('', row[name]) : esc(shown));

// a date as far as it is known (its _prec_T): the day, else the month or the year of FDA's text
function knownDay(clean, prec, raw) {
  const r = String(raw || '');
  if (prec === 8) return day(clean);
  if (prec === 6) return new Date(Date.UTC(+r.slice(0, 4), +r.slice(4, 6) - 1)).toLocaleString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  return prec === 4 ? r.slice(0, 4) : '';
}

// the address shown with a case named in it, or with none
function caseAddress(c) {
  const p = new URLSearchParams(location.search);
  p.delete('case'); p.delete('era');
  if (c) { p.set('case', c.key); if (c.era) p.set('era', c.era); }
  return `${location.pathname}${p.size ? `?${p}` : ''}`;
}

// a case by its number, in the system named, or in either when none is: a case number is the
// release's own (no two cases share one), and an export or a bookmark may give it alone
async function findCase(era, key) {
  let missing = null;
  for (const e of era ? [era] : Object.keys(ERA)) {
    try { return await api(`/api/case/${encodeURIComponent(e)}/${encodeURIComponent(key)}`); } catch (err) { missing = err; }
  }
  throw missing;
}

async function openCase(era, key, nav = null) {
  caseNav = nav;
  let dlg = document.getElementById('oa-case');
  if (!dlg) {
    dlg = document.createElement('dialog');
    dlg.className = 'dialog oa-case-dialog';
    dlg.id = 'oa-case';
    layer().appendChild(dlg);
    dlg.addEventListener('close', () => {
      dlg.remove(); caseNav = null;
      if (new URLSearchParams(location.search).get('case') === dlg.dataset.key) putAddress(caseAddress(null));
    });
    // a click on the backdrop closes it, and so does a link to another page, such as a rule's
    dlg.addEventListener('click', (e) => { if (e.target === dlg || e.target.closest('a[href]')) dlg.close(); });
  }
  dlg.dataset.key = key;
  putAddress(caseAddress({ era, key }));
  dlg.innerHTML = `<div class="dialog-head"><h2 class="dialog-title">Case ${esc(key)}</h2><button type="button" class="icon-btn" data-act="close-dialog" aria-label="Close">${icon('close')}</button></div>
    <div class="dialog-body">${skeletonRows(3)}</div>`;
  if (!dlg.open) dlg.showModal();
  try {
    const c = await findCase(era, key);
    // the flags come before the dialog is drawn, so nothing moves in it once it is
    const flags = labelsOn() ? await api(`/api/labels/case/${encodeURIComponent(c.era_T)}/${encodeURIComponent(c.case_key_T)}`) : null;
    if (document.getElementById('oa-case') === dlg) dlg.innerHTML = caseDialog(c, flags);
  } catch (err) {
    if (err.message !== 'not found') { showProblem(err); return; }
    if (document.getElementById('oa-case') === dlg) dlg.querySelector('.dialog-body').innerHTML = `<p class="oa-case-lead">There is no case ${esc(key)} in this release.</p>
      <p>A case FDA has deleted is taken out of the release. ${ruleTag('deleted-cases', 'Cases FDA deleted')}</p>`;
  }
}

const note = (words) => (words ? `<span class="oa-case-note">${words}</span>` : '');

// the case's country: its name beside the code, and FDA's own value with the rule where a rule read
// it (an AERS case's UNITED STATES; an EU case's member state, from an earlier version of the case);
// FDA's words for no country read as not given, with FDA's text kept
function countryCell(c) {
  const code = c.country_T, given = [c.occr_country, c.reporter_country].filter(Boolean);
  const raw = given.find((v) => !countryNotGiven(v)) || '';
  if (code == null || countryNotGiven(code)) {
    const said = code || given.find(countryNotGiven) || '';
    return `${fda('Not given', said)}${code == null && said ? note(ruleTag('country-not-given', 'fixed rule: country-not-given')) : ''}`;
  }
  const named = `${countryName(code)} (${code})`;
  if (c.country_source_T === EARLIER_VERSION) {
    return `${esc(named)} <span class="oa-fda" ${tip('As FDA published it')}>FDA: ${esc(raw)}</span>${note(`From an earlier version of this case ${ruleTag('eu-member-state', 'fixed rule: eu-member-state')}`)}`;
  }
  const read = raw && raw !== code ? ` <span class="oa-fda" ${tip('As FDA published it')}>FDA: ${esc(raw)}</span>${note(ruleTag('legacy-country', 'fixed rule: legacy-country'))}` : '';
  return `${esc(named)}${read}${note(esc(countryNote(code)))}`;
}
// a country field as FDA wrote it, Not given where it reads so (rules not-given and legacy-country)
const place = (row, name) => (notGiven(row, name) || countryNotGiven(row[name]) ? fda('', row[name]) : fda(countryName(row[name]), row[name]));

// a drug record's ingredients and where they came from, with FDA's active ingredient under them,
// always, as it is FDA's own field; FDA's alone where the release reads no drug names
function ingredient(d) {
  const theirs = `<span class="oa-fda" ${tip('As FDA published it')}>FDA: ${esc(d.prod_ai || 'Not given')}</span>`;
  if (d.substance_source_T == null) return theirs;
  if (d.substance_source_T === 'none') return `<span class="oa-faint">No ingredient</span>${theirs}`;
  return `${esc(d.ingredient_T)}${theirs}${note(ruleTag('drug-names', INGREDIENT_SOURCE[d.substance_source_T]))}`;
}

// a drug record's role as FDA codes it, its name on hover
const roleCell = (d) => (ROLE[d.role_T] ? `<span class="oa-has-tip" ${tip(ROLE[d.role_T])}>${esc(d.role_T)}</span>` : esc(d.role_T || d.role_cod || ''));

// a case's drugs in the order a reviewer weighs them: the suspects (primary, secondary, interacting),
// then the drugs taken alongside, then any role FDA's codes do not name; FDA's order within each
const RANK = { PS: 0, SS: 1, I: 2, C: 3 };
const byRole = (drugs) => [...drugs].sort((a, b) => (RANK[a.role_T] ?? 4) - (RANK[b.role_T] ?? 4));

// a drug record's dose as FDA wrote it, then how often in FDA's words, with FDA's code under it where it
// reads otherwise; FDA's filler for either reads Not given (rule not-given)
function doseCell(d) {
  const dose = notGiven(d, 'dose_vbm') ? '' : d.dose_vbm;
  const freqGiven = !notGiven(d, 'dose_freq');
  const words = freqGiven ? freqWords(d.dose_freq) : '';
  const often = words ? (dose ? words.toLowerCase() : words) : freqGiven ? d.dose_freq : '';
  const codes = [dose ? '' : d.dose_vbm, words || !freqGiven ? d.dose_freq : ''].filter(Boolean).join(', ');
  return fda([dose, often].filter(Boolean).join(', '), codes);
}

// whether the reaction abated when the drug was stopped and came back when it was restarted, each on
// a line of its own after its label
const challengeCell = (d) => [['Stopped', 'dechal', DECHAL], ['Restarted', 'rechal', RECHAL]]
  .map(([label, name, words]) => `<span class="oa-case-line"><span class="oa-faint">${label}</span> ${field(d, name, labelOf(words, d[name]))}</span>`).join('');

// a drug record's route families (rule drug-route) with FDA's route under it: its one family, or what
// it could be when its fields allow several, and which of FDA's fields said so; FDA's route alone
// where the release reads no routes or nothing is known
const joined = (words, and) => (words.length < 2 ? words.join('') : `${words.slice(0, -1).join(', ')} ${and} ${words[words.length - 1]}`);
function routeCell(d) {
  const families = (d.route_families_T || []).map((f) => ROUTE_FAMILY[f] || f);
  if (!families.length) return field(d, 'route');
  const shown = families.length === 1 ? families[0] : `Could be ${joined(families.map((f) => f.toLowerCase()), 'or')}`;
  const from = d.route_source_T === 'disagree' ? ROUTE_SOURCE.disagree : `From ${joined(String(d.route_source_T || '').split('+').map((s) => ROUTE_SOURCE[s] || s), 'and')}`;
  return `${fda(shown, d.route)}${note(ruleTag('drug-route', from))}`;
}

// a therapy's duration as the release works it out (dur_days_T), FDA's duration under it, with its rule
function duration(t) {
  const d = t.dur_days_T;
  const said = t.dur ? `${t.dur} ${t.dur_cod || ''}`.trim() : '';
  if (d == null) return said ? fda('', said) : '';
  const words = Number.isInteger(d) ? `${num(d)} ${d === 1 ? 'day' : 'days'}` : `${fix(d, d < 1 ? 2 : 1)} days`;
  return `${fda(words, said)}${note(ruleTag('therapy-duration', 'fixed rule: therapy-duration'))}`;
}

// a drug record's time to onset, the first dose being day 1, or why it has none (rule time-to-onset)
function onsetCell(d) {
  if (!d) return '';
  if (d.time_to_onset_T != null) return `Day ${num(d.time_to_onset_T)}${note(ruleTag('time-to-onset', 'fixed rule: time-to-onset'))}`;
  const why = NO_ONSET[d.time_to_onset_reason_T];
  return why ? `<span class="oa-faint oa-has-tip" ${tip(why[1])}>${why[0]}</span>` : '';
}

// the therapy lines, each drug's on rows together and in the drugs' order: the drug by the name it
// was reported under, its number beside where two drugs share that name, clean dates and duration
// beside FDA's, and the drug's one time to onset across its rows
function therapyRows(c, ordered) {
  const at = new Map(ordered.map((d, i) => [d.drug_seq, i]));
  const lines = [...(c.ther || [])].sort((a, b) => (at.get(a.dsg_drug_seq) ?? at.size) - (at.get(b.dsg_drug_seq) ?? at.size));
  const drugs = new Map(ordered.map((d) => [d.drug_seq, d]));
  const nameOf = (seq) => { const d = drugs.get(seq); return d && !notGiven(d, 'drugname') ? d.drugname : ''; };
  const shared = (name) => new Set(lines.filter((t) => nameOf(t.dsg_drug_seq) === name).map((t) => t.dsg_drug_seq)).size > 1;
  const drugCell = (seq) => {
    const name = nameOf(seq);
    if (!name) return `Drug ${esc(seq)}`;
    return shared(name) ? `${esc(name)} <span class="oa-faint oa-has-tip" ${tip("FDA's number for this drug on the report")}>(${esc(seq)})</span>` : esc(name);
  };
  return lines.map((t, i) => {
    const first = i === 0 || lines[i - 1].dsg_drug_seq !== t.dsg_drug_seq;
    let span = 1;
    while (first && lines[i + span]?.dsg_drug_seq === t.dsg_drug_seq) span += 1;
    const onset = first ? `<td${span > 1 ? ` rowspan="${span}"` : ''}>${onsetCell(drugs.get(t.dsg_drug_seq))}</td>` : '';
    return `<tr><td>${drugCell(t.dsg_drug_seq)}</td><td>${fda(knownDay(t.start_dt_T, t.start_dt_prec_T, t.start_dt), t.start_dt)}</td><td>${fda(knownDay(t.end_dt_T, t.end_dt_prec_T, t.end_dt), t.end_dt)}</td><td>${duration(t)}</td>${onset}</tr>`;
  }).join('');
}

// the case numbers in a line about its group, each a link to that copy
function withCaseLinks(line, group) {
  const era = new Map(group.map((g) => [g.case_key_T, g.era_T]));
  if (!era.size) return esc(line);
  const keys = [...era.keys()].sort((a, b) => b.length - a.length).map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return line.split(new RegExp(`(?<![\\w:])(${keys.join('|')})(?![\\w:])`)).map((part, i) => (i % 2
    ? `<button type="button" class="oa-link" data-act="case-jump" data-era="${esc(era.get(part))}" data-key="${esc(part)}">${esc(part)}</button>`
    : esc(part))).join('');
}

function caseDialog(c, flags) {
  const serious = (c.outcomes_T || []).length > 0;
  const faersFrom = eras().FAERS[0];
  const chips = [`<span class="oa-chip" ${tip(c.era_T === 'faers' ? `The system of the case's latest version: FAERS, FDA's since ${faersFrom}` : `The system of the case's latest version: AERS, FDA's before ${faersFrom}`)}>${ERA[c.era_T]}</span>`];
  if (serious) chips.push(`<span class="oa-chip oa-chip-serious" ${tip('The report gave at least one serious outcome')}>Serious</span>`);
  // why a probable duplicate is shown or set aside: the release's own sentences (/api/case), one a
  // line, each case number in them a link to that copy; and the flag on a report with no usable drug
  // or reaction that still gives a serious outcome
  const flag = c.serious_no_drug_or_reaction_T ? `<p class="oa-case-flag"><span class="oa-chip oa-chip-serious">${UNUSABLE_SERIOUS}</span>${note(ruleTag('no-drug-or-reaction', 'fixed rule: no-drug-or-reaction'))}</p>` : '';
  const lines = (c.reasons || []).map((line) => `<p>${withCaseLinks(line, c.group || [])}</p>`).join('');
  const why = flag || lines ? `<div class="oa-case-why" data-aside="${!c.dup_kept_T}">${flag}${lines}</div>` : '';
  // the system of the case's latest version: a case FDA carried from AERS into FAERS is a FAERS case,
  // though first received before FAERS began
  const carried = c.era_T === 'faers' && c.first_fda_dt_T && c.first_fda_dt_T < quarterStart(faersFrom);
  const system = `${ERA[c.era_T]}${note(`${carried ? `The system of its latest version. FDA first received it on ${day(c.first_fda_dt_T)}, in AERS, and carried it into FAERS; filter Received by FDA to find cases first reported before FAERS.` : 'The system of its latest version.'} ${ruleTag('latest-version', 'fixed rule: latest-version')}`)}`;
  const grouped = !!c.probable_duplicate_T;
  const ageYears = c.age_years_T == null ? '' : c.age_years_T < 2 ? `${Math.round(c.age_years_T * 12)} months` : `${Math.floor(c.age_years_T)} years`;
  const who = [ageYears && `${ageYears.replace(' years', '-year-old').replace(' months', '-month-old')}`, c.sex_T === 'F' ? 'female' : c.sex_T === 'M' ? 'male' : 'patient'].filter(Boolean).join(' ');
  const where = c.country_T && !countryNotGiven(c.country_T) ? ` in ${countryName(c.country_T)}` : '';
  const BY = { 1: 'a physician', 2: 'a pharmacist', 3: 'another health professional', 4: 'a lawyer', 5: 'a consumer' };
  const by = BY[c.reporter_type_T] ? `, reported by ${BY[c.reporter_type_T]}` : '';
  const outcomes = (c.outcomes_T || []).map((o) => labelOf(OUTCOME, o).toLowerCase());
  const lead = `${who.charAt(0).toUpperCase()}${who.slice(1)}${where}${by}. First received ${day(c.group_first_dt_T)}${grouped ? ' (any copy)' : ''}.${outcomes.length ? ` Serious: ${outcomes.join(', ')}.` : ''}`;
  const dl = (pairs) => `<dl class="field-list oa-fields">${pairs.filter(Boolean).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
  const weight = fda(c.wt_kg_T != null ? `${fix(c.wt_kg_T, 1)} kg` : 'Not given', c.wt ? `${c.wt} ${c.wt_cod || ''}`.trim() : '');
  const eventDay = knownDay(c.event_dt_T, c.event_dt_prec_T, c.event_dt);
  // each drug's WHO class, where the release carries them and this person may see them
  const classes = c.classes ? Object.fromEntries(c.classes.map((x) => [x.drug_seq, x])) : null;
  const classTd = (d) => (classes ? `<td>${classCell(classes[d.drug_seq])}</td>` : '');
  const v = c.meddra_version;
  // what each drug was given for, as this report says: FAERS's indications, by the drug's place on the report
  const usedFor = (d) => {
    // FDA's words for an unknown indication read Not given, FDA's words beside (rule not-given)
    const said = (c.indi || []).filter((i) => i.indi_drug_seq === d.drug_seq && i.indi_pt).map((i) => (notGiven(i, 'indi_pt') ? fda('', i.indi_pt) : termShown(i.indi_pt_T, i.indi_pt, i.current_pt_T, v)));
    return said.length ? said.map((x) => `<span class="oa-case-line">${x}</span>`).join('') : `<span class="oa-faint oa-has-tip" ${tip('FAERS gives no indication for this drug on this report')}>Not given</span>`;
  };
  const ordered = byRole(c.drug || []);
  const cols = 7 + !!classes;
  // a quiet row between the suspects and the drugs taken alongside them, where the case has both
  const alongside = ordered.findIndex((d) => d.role_T === 'C');
  const divider = `<tr class="oa-case-divider"><th colspan="${cols}" scope="rowgroup"><span>Taken alongside</span></th></tr>`;
  const drugs = ordered.map((d, i) => `${i > 0 && i === alongside ? divider : ''}<tr><td>${roleCell(d)}</td><td>${field(d, 'drugname')}</td><td>${ingredient(d)}</td><td>${usedFor(d)}</td>${classTd(d)}<td>${routeCell(d)}</td><td>${doseCell(d)}</td><td>${challengeCell(d)}</td></tr>`).join('');
  const flagged = !!flags?.drugs?.length;
  // the term in one piece, so the label lines go under it
  const reac = (c.reac || []).map((r) => `<li${flagged ? ' class="oa-reac-labelled"' : ''}><span>${termShown(r.pt_T, r.pt, r.current_pt_T, v)}</span>${r.soc_T ? `<span class="oa-fda" ${tip(`System organ class, in MedDRA ${v}`)}>System organ class: ${esc(r.soc_T)}</span>` : ''}${reactionLines(flags, r.pt)}</li>`).join('');
  // the reactions that came back when the drug was given again, as FDA wrote them (FAERS only)
  const back = (c.reac || []).filter((r) => r.drug_rec_act).map((r) => `<li>${termShown(r.drug_rec_act, r.drug_rec_act, r.rec_act_current_pt_T, v)}</li>`).join('');
  const outcome = (c.outcomes_T || []).map((o) => `<li>${fda(labelOf(OUTCOME, o), o)}</li>`).join('') || `<li class="oa-faint">${esc(noOutcome(c.rept_cod))}</li>`;
  const ther = therapyRows(c, ordered);
  const group = (c.group || []).map((g) => `<li><button type="button" class="oa-link" data-act="case-jump" data-era="${esc(g.era_T)}" data-key="${esc(g.case_key_T)}">Case ${esc(g.case_key_T)}</button> <span class="oa-faint">${ERA[g.era_T]}, received ${day(g.first_fda_dt_T)}</span> ${g.dup_kept_T ? '<span class="oa-chip">Kept</span>' : '<span class="oa-chip oa-chip-aside">Set aside</span>'}</li>`).join('');
  const nav = caseNav && caseNav.sc.cases ? `<span class="oa-faint">${num((caseNav.sc.cases.page - 1) * caseNav.sc.cases.size + caseNav.index + 1)} of ${num(caseNav.sc.summary?.cases)}</span>
      <button type="button" class="btn" data-act="case-step" data-v="-1" ${caseNav.index <= 0 ? 'disabled' : ''}>${icon('arrowLeft')}<span>Previous</span></button>
      <button type="button" class="btn" data-act="case-step" data-v="1" ${caseNav.index >= caseNav.sc.cases.cases.length - 1 ? 'disabled' : ''}><span>Next</span>${icon('arrowRight')}</button>` : '';
  const part = (name, body) => `<section class="oa-case-part"><h3 class="case-section">${name}</h3>${body}</section>`;
  return `<div class="dialog-head"><div class="oa-case-title"><h2 class="dialog-title">Case ${esc(c.case_key_T)} <span class="oa-chips">${chips.join('')}</span></h2>${why}</div>
      <button type="button" class="icon-btn" data-act="close-dialog" aria-label="Close">${icon('close')}</button></div>
    <div class="dialog-body oa-case-body">
      <p class="oa-case-lead">${esc(lead)}</p>
      <p class="oa-faint oa-case-narrative">FDA does not publish the reporter's narrative in its public files, so a case shows only the coded fields.</p>
      ${part('What happened', dl([
        [flagged ? 'Reactions, and each suspect\'s label' : 'Reactions', `<ul class="oa-list oa-reac-list">${reac || '<li>None recorded</li>'}</ul>${labelSources(flags)}`],
        back ? ['Came back when the drug was given again', `<ul class="oa-list">${back}</ul>`] : null,
        ['Outcomes', `<ul class="oa-list">${outcome}</ul>`],
        ['Event date', fda(eventDay, c.event_dt)],
      ]))}
      ${part('The drugs', `<div class="oa-case-scroll"><table class="case-table oa-case-drugs oa-freeze"><colgroup><col class="oa-cd-role"><col class="oa-cd-short"><col><col class="oa-cd-short">${classes ? '<col>' : ''}<col><col><col></colgroup><thead><tr><th>Role</th><th>As reported</th><th>Ingredient</th><th ${tip('What the drug was given for, as this report says')}>Used for</th>${classes ? '<th>WHO class (ATC)</th>' : ''}<th>Route</th><th>Dose</th><th ${tip('Whether the reaction abated when the drug was stopped, and came back when it was restarted')}>Stopped and restarted</th></tr></thead><tbody>${drugs || `<tr><td colspan="${cols}">None recorded</td></tr>`}</tbody></table></div>
        ${ther ? `<h4 class="oa-case-sub">Therapy dates</h4><div class="oa-case-scroll"><table class="case-table oa-case-therapy oa-freeze"><thead><tr><th>Drug</th><th>Start</th><th>End</th><th>Duration</th><th ${tip('Days from the first dose, day 1, to the event, from two dates known to the day')}>Time to onset</th></tr></thead><tbody>${ther}</tbody></table></div>` : ''}`)}
      <div class="oa-case-cols oa-case-pair">
      ${part('The patient', dl([
        ['Age', `${fda(ageYears || 'Not given', c.age ? `${c.age} ${c.age_cod || ''}`.trim() : '')}${c.age_band_T ? note(`${esc(ages()[c.age_band_T])} ${ruleTag('age-bands', 'fixed rule: age-bands')}`) : ''}`],
        ['Sex', fda(c.sex_T ? labelOf(SEX, c.sex_T) : 'Not given', c.sex)],
        ['Weight', weight],
        ['Country', countryCell(c)],
        ['Where it happened', place(c, 'occr_country')],
        ['Reporter\'s country', place(c, 'reporter_country')],
      ]))}
      ${part('About the report', dl([
        ['Case number', fda(c.caseid || 'None (an AERS report without one)', '')],
        ['Report', fda(c.primaryid, '')],
        c.caseversion ? ['Version', fda(c.caseversion, '')] : null,
        ['FDA quarter', fda(String(c.quarter_T || '').toUpperCase(), '')],
        ['FDA system', system],
        grouped ? ['First received (any copy)', fda(day(c.group_first_dt_T), '')] : null,
        [grouped ? 'First received (this copy)' : 'First received', fda(day(c.first_fda_dt_T), c.init_fda_dt)],
        ['This version received', fda(fdaDay(c.fda_dt), '')],
        ['Report type', fda(labelOf(REPT, c.rept_cod), c.rept_cod)],
        ['Who reported', fda(c.reporter_type_T ? labelOf(REPORTER, c.reporter_type_T) : '', c.occp_cod)],
        ['Company', fda(c.direct_T ? companyName('_direct') : c.company_T, c.mfr_sndr)],
        group ? ['Probable duplicates', `<ul class="oa-list">${group}</ul>`] : null,
      ]))}
      </div>
    </div>
    <div class="dialog-foot"><p class="dialog-note">Cleaned values, with FDA's own under them where they differ.</p>${nav}</div>`;
}

actions({
  case: (el) => { const sc = scopeNow(); const c = sc.cases.cases[+el.dataset.i]; openCase(c.era_T, c.case_key_T, { sc, index: +el.dataset.i }); },
  'case-step': (el) => { if (!caseNav) return; const i = caseNav.index + +el.dataset.v; const c = caseNav.sc.cases.cases[i]; if (c) openCase(c.era_T, c.case_key_T, { sc: caseNav.sc, index: i }); },
  'case-jump': (el) => openCase(el.dataset.era, el.dataset.key, null),
});

// an address that names a case opens it over the page it is on
host.after.push((r) => {
  const p = new URLSearchParams(location.search);
  if (r.page === 'scope' && p.get('case') && !document.getElementById('oa-case')) openCase(p.get('era') || '', p.get('case'));
});
