/* The release's tables in words: its four layers, what each table holds and is made from, and what
   each column is. The build itself is src/open_altio/faers/derive.py. */

import { S, eraSpan, eras } from './state.js';
import { day, num } from './util.js';

// a table's or a view's rows, as the release's manifest counts them
export const rowsIn = (m, name) => [...(m?.tables || []), ...(m?.views || [])].find((t) => t.name === name)?.rows;
export const quartersOf = (m) => (m ? `${m.quarters[0].toUpperCase()} to ${m.quarters[1].toUpperCase()}` : '');
// how to cite a release: its name, and when built and from which quarters where they are known
export const citeText = (name, m) => `Altio. Open Altio FAERS, release ${name}${m ? `, built ${day(m.built_at)} from the FDA Adverse Event Reporting System public quarterly files, ${quartersOf(m)}` : ''}. https://open.altioai.com`;

// the rows of one of the release's tables, less another's, as its manifest counts them
const releaseRows = (name, less) => {
  const n = rowsIn(S.manifest, name) - (less ? rowsIn(S.manifest, less) : 0);
  return Number.isFinite(n) ? num(n) : '';
};
// The release in four layers, from what Open Altio counts down to FDA's own files.
export const GROUP_WORDS = {
  start: ['Start here', () => `One row per case, ${releaseRows('case_dedup_T')} cases: each at its latest version, without the cases FDA deleted, and with probable duplicates set aside. What Open Altio counts.`],
  latest: ['Every case, duplicates flagged', () => `The same, ${releaseRows('case_latest_T')} cases, with the ${releaseRows('case_latest_T', 'case_dedup_T')} probable duplicates still in and flagged; and the tables the flags and deletions come from.`],
  versions: ['Every version of every report', () => `${releaseRows('demo_T')} report versions: FDA's demo file with Open Altio's columns beside it, and the latest version of each case.`],
  raw: ['As FDA published them', () => `FDA's quarterly files, stacked, every column verbatim. Only quarter_T and era_T are added: which file each row came from.`],
};
const CHILD_WORDS = { drug: 'drug', reac: 'reaction', outc: 'outcome', rpsr: 'report source', ther: 'therapy', indi: 'indication' };
// what each table is made from, in words; the build itself is derive.py
export function tableFrom(name) {
  const fixed = {
    case_dedup_T: `case_latest_T where dup_kept_T is true: the ${releaseRows('case_latest_T', 'case_dedup_T')} probable duplicates set aside, one case shown in each group (the latest received).`,
    case_latest_T: `demo_latest_T less the ${releaseRows('demo_latest_T', 'case_latest_T')} cases on FDA's deleted-case lists, with the duplicate flags from case_dup_T.`,
    case_dup_T: 'One row per case in case_latest_T: the two keys probable duplicates are found by, AEOLUS (event date, age, age unit, sex, country, drug set, reaction set) and the manufacturer case number with its sender, and the group they put the case in. Each group shows its latest received case and is dated by its earliest receipt.',
    deleted_cases_T: 'deleted: each caseid on any of FDA\'s deleted-case lists, once, with the first quarter that listed it.',
    quarters_T: 'demo: each FDA quarter in the release and its era.',
    demo_T: 'demo, every row, with Open Altio\'s columns added: dates as dates, age in years, weight in kg, the reporter type and the case key.',
    demo_latest_T: 'demo_T, one row per case: the highest caseversion, then the latest fda_dt, then the latest quarter, then the highest primaryid.',
    drug_onset_T: 'drug_latest_T, one row per drug record (era_T, primaryid, quarter_T, drug_seq), with the days from its first dose to the event, from ther_latest_T and the case\'s event date.',
    atc_index_T: "Our table of WHO's ATC codes by substance, mappings/faers/atc/classes.csv.",
    atc_drug_T: `The substance of each drug record, else FDA's own words or its group word, joined to atc_index_T; one class chosen by the record's dose, then its route, then its indication, else the class its possible codes share (rule atc-class-choice).`,
    atc_drug_codes_T: 'The same join, every code each record could have.',
  };
  if (fixed[name]) return fixed[name];
  const m = name.match(/^(drug|reac|outc|rpsr|ther|indi)_(dedup|latest)_T$/);
  if (m && m[2] === 'dedup') return `${m[1]}_latest_T, only the rows of the cases in case_dedup_T.`;
  if (m) return `FDA's ${CHILD_WORDS[m[1]]} rows of the cases in case_latest_T, matched on era_T, primaryid and quarter_T.${m[1] === 'drug' ? ' drugname_norm_T and prod_ai_norm_T are added for matching.' : m[1] === 'ther' ? ' The dates are added as dates where they can be true, with each therapy\'s duration in days.' : ' Every column is FDA\'s.'}`;
  if (name === 'deleted') return 'FDA\'s deleted-case lists, one line per caseid per list, as published.';
  return `FDA's ${name.toUpperCase()} files, one per quarter, stacked as published.`;
}
// the tables of WHO's classes, which carry WHO's short line
const CLASS_TABLES = new Set(['atc_index_T', 'atc_drug_T', 'atc_drug_codes_T']);
export const isClassTable = (name) => CLASS_TABLES.has(name);
export const isFdaColumn = (c) => !c.endsWith('_T');
export const TABLE_WORDS = {
  case_dedup_T: 'Cases: dates, patient, country, reporter, sender',
  drug_dedup_T: 'The drugs on each case and their role',
  reac_dedup_T: 'The reactions, as MedDRA preferred terms',
  outc_dedup_T: 'The serious outcomes',
  rpsr_dedup_T: 'Where each report came from',
  ther_dedup_T: 'When each drug was started and stopped',
  indi_dedup_T: 'What each drug was given for',
  case_latest_T: 'Every case once, at its latest version, deleted cases left out',
  drug_latest_T: 'Drugs of those cases, with names tidied for matching',
  drug_onset_T: 'Time to onset of each drug record',
  reac_latest_T: 'Reactions of those cases',
  outc_latest_T: 'Outcomes of those cases',
  rpsr_latest_T: 'Report sources of those cases',
  ther_latest_T: 'Therapy dates of those cases, with each therapy\'s duration',
  indi_latest_T: 'Indications of those cases',
  case_dup_T: 'The probable-duplicate flags and the keys they were found by',
  deleted_cases_T: 'Each case FDA asked to be deleted, once',
  quarters_T: 'One row per FDA quarter in the release',
  demo_T: 'Every report version, nothing removed',
  demo_latest_T: 'The latest version of each case, before deleted cases are taken out',
  demo: 'Patient, dates, reporter and country, per report version',
  drug: 'Drugs on each report',
  reac: 'Reactions on each report',
  outc: 'Outcomes on each report',
  rpsr: 'Report sources',
  ther: 'Therapy dates',
  indi: 'Indications',
  deleted: 'Every line of FDA\'s deleted-case lists',
  atc_index_T: 'WHO drug classes (ATC): every code, at every level, with WHO\'s name',
  atc_drug_T: 'Each drug record\'s one WHO class, and how it was chosen',
  atc_drug_codes_T: 'Every WHO class each drug record could have',
};
const COLUMN_WORDS = {
  primaryid: 'Report number (the case number plus its version); ISR in AERS',
  caseid: 'Case number, the same across a case\'s versions',
  caseversion: 'The case\'s version: 1, 2, ...',
  i_f_code: 'I for an initial report, F for a follow-up',
  event_dt: 'When the event happened: yyyymmdd, yyyymm or yyyy, as FDA gave it',
  mfr_dt: 'When the manufacturer first heard of it',
  init_fda_dt: 'When FDA first received the case',
  fda_dt: 'When FDA received this version',
  rept_cod: 'Report type: EXP expedited (15-day), PER periodic, DIR direct from the public or a health professional, 5DAY drug-device combination with remedial action, 30DAY device malfunction on a drug-device combination',
  auth_num: 'A regulator\'s own number for the case',
  mfr_num: 'The manufacturer\'s own number for the case',
  mfr_sndr: 'Who sent the report to FDA',
  lit_ref: 'Literature reference',
  age: 'Age, in the unit of age_cod',
  age_cod: 'Unit of age: YR, MON, WK, DY, HR, DEC',
  age_grp: 'Age group: N neonate, I infant, C child, T adolescent, A adult, E elderly',
  sex: 'FDA\'s code: F, M, NS, UNK, another code, or empty',
  e_sub: 'Y when the report came in electronically',
  wt: 'Weight, in the unit of wt_cod',
  wt_cod: 'Unit of weight: KG, LBS, GMS',
  rept_dt: 'When the report was sent',
  to_mfr: 'Y when the reporter also told the manufacturer',
  occp_cod: 'Who reported: MD physician, PH pharmacist, OT other health professional (HP from 2020), LW lawyer, CN consumer',
  reporter_country: 'The reporter\'s country',
  occr_country: 'The country where the event happened',
  foll_seq: 'AERS only: follow-up number',
  image: 'AERS only: FDA\'s image reference',
  death_dt: 'AERS only: date of death',
  confid: 'AERS only: confidential flag',
  drug_seq: 'The drug\'s number on the report',
  role_cod: 'PS primary suspect, SS secondary suspect, C concomitant, I interacting',
  drugname: 'The drug\'s name as reported',
  prod_ai: 'The active ingredient as FDA coded it',
  val_vbm: '1 when the name was checked against FDA\'s list, 2 when taken as written',
  route: 'How it was given',
  dose_vbm: 'The dose as written',
  cum_dose_chr: 'Cumulative dose', cum_dose_unit: 'Unit of the cumulative dose',
  dechal: 'Did the reaction stop when the drug stopped: Y, N, U unknown, D does not apply',
  rechal: 'Did it come back when the drug restarted: Y, N, U unknown, D does not apply',
  lot_num: 'Lot number', exp_dt: 'Expiry date', nda_num: 'FDA application number',
  dose_amt: 'Dose amount', dose_unit: 'Unit of the dose amount', dose_form: 'Dose form', dose_freq: 'How often, as FDA codes it, such as QD daily, BID twice a day, /wk per week, PRN as needed; the case window names each',
  pt: 'The reaction: a MedDRA preferred term, as FDA published it',
  drug_rec_act: 'A reaction that came back when the drug restarted',
  outc_cod: 'DE death, LT life-threatening, HO hospitalization, DS disability, CA congenital anomaly, RI required intervention, OT other serious',
  rpsr_cod: 'Report source, for example HP health professional, CSM consumer, LIT literature, SDY study, FGN foreign',
  dsg_drug_seq: 'The drug_seq this therapy belongs to',
  start_dt: 'Therapy start, as FDA gave it', end_dt: 'Therapy end, as FDA gave it',
  dur: 'Therapy duration', dur_cod: 'Unit of the duration',
  event_dt_T: 'event_dt as a date, where it is known to the day and can be true',
  event_dt_prec_T: 'How much of event_dt is known: 8 the day, 6 the month, 4 the year; empty when nothing, or when it cannot be true',
  start_dt_T: 'start_dt as a date, where FDA gave a full day that can be true', end_dt_T: 'end_dt as a date, where FDA gave a full day that can be true',
  start_dt_prec_T: 'How many digits FDA gave for start_dt: 8, 6 or 4; empty when it cannot be true', end_dt_prec_T: 'How many digits FDA gave for end_dt: 8, 6 or 4; empty when it cannot be true',
  dur_days_T: 'Therapy duration in days: from start_dt_T to end_dt_T, else from dur and dur_cod; empty when longer than the patient could have been treated',
  time_to_onset_T: 'Days from the drug\'s first dose (day 1) to the event, from two dates known to the day; empty when the event came first',
  indi_drug_seq: 'The drug_seq this indication belongs to',
  indi_pt: 'What the drug was given for: a MedDRA preferred term',
  qnum_T: 'The quarter as a sortable number, yyyyq',
  caseversion_T: 'caseversion as a number; empty in AERS',
  first_fda_dt_T: 'When FDA first received the case: init_fda_dt, else fda_dt',
  init_year_T: 'Year of first_fda_dt_T', fda_year_T: 'Year of fda_dt',
  age_years_T: 'Age in years, exact, from age and age_cod; no unit is years; empty over 122 or negative',
  age_band_T: 'The age band the explorer filters and the statistics count by; empty when no age is given',
  sex_T: 'F or M from sex; empty for every other code',
  wt_kg_T: 'Weight in kg from wt and wt_cod; empty with no unit, at zero or over 635 kg',
  country_source_T: 'Where country_T came from: as published, or earlier version for an EU case whose earlier version named the country',
  case_key_T: 'The case\'s key: caseid, or ISR:primaryid for an AERS report without one',
  company_T: 'The company that sent the report: a sender spelling, in either era, read as its company\'s name, else mfr_sndr as written; empty on a direct report (sent straight to FDA) and where the sender is blank or only says unknown',
  drugname_norm_T: 'drugname in capitals, spaces tidied, for matching',
  prod_ai_norm_T: 'prod_ai in capitals, spaces tidied: the product Open Altio groups by',
  reporter_type_T: 'Who reported, as E2B(R3) codes it: 1 physician, 2 pharmacist, 3 other health professional (FDA\'s OT, HP or RN), 4 lawyer, 5 consumer; empty for any other code',
  dup_key_T: 'The AEOLUS fields a probable duplicate is matched on, joined with |; empty when any is not given (blank, unknown or a filler)',
  dup_number_key_T: 'The sender and manufacturer case number the second rule matches on, joined with |; empty when either is missing',
  dup_padded_date_T: 'True for the cases of a large group from one sender left whole because its shared event date is padded',
  dup_group_T: 'A number shared by the cases of one group of probable duplicates, found by either rule',
  probable_duplicate_T: 'True for every case in a group of two or more, the shown one too',
  dup_kept_T: 'False only for a probable duplicate that is set aside',
  group_first_dt_T: 'When FDA first received any case of the group: the date the explorer sorts, counts and filters by',
  dup_rule_T: 'The rules that put the case in its group: aeolus, manufacturer_number, manufacturer_number_country_code',
  dup_shown_case_T: 'The case_key_T of the copy its group shows',
  dup_other_cases_T: 'On the shown copy: the case_key_T of the copies set aside, earliest received first',
  no_drug_or_reaction_T: 'True for a report with no usable drug or reaction: never a duplicate, never hidden',
  serious_no_drug_or_reaction_T: 'The same, with a serious outcome',
  first_listed_quarter_T: 'The first quarter whose deleted list named the case',
  n_listings_T: 'How many deleted lists named the case',
  in_all_history_list_T: 'True when FDA\'s whole-history deleted list names it',
  atc_code_T: 'WHO\'s ATC code; on atc_drug_T the record\'s one class, empty when it cannot tell',
  atc_level_T: 'The ATC level of the code, 1 (main group) to 5 (substance)',
  atc_name_T: 'WHO\'s name for the code, as WHO writes it',
  atc_index_year_T: 'The year of WHO\'s index the code comes from',
  atc_chosen_by_T: 'How the class was chosen: only_code, dose, route, indication, shared_class, group_class or cannot_tell',
  atc_possible_codes_T: 'How many WHO codes the record could have',
  atc_matched_on_T: 'What was matched: the substance, a combination\'s whole ingredient set or each ingredient; else FDA\'s drug name or active ingredient',
  atc_ingredient_T: 'The substance or ingredient set the code is for',
  atc_chosen_T: 'True for the code chosen as the record\'s class',
};
export function columnWords(c) {
  if (c === 'quarter_T') return `The FDA quarter whose file held the row, for example ${S.release?.quarters[1] || ''}`;
  if (c === 'era_T') return `legacy (AERS, ${eraSpan('AERS')}) or faers (${eras().FAERS[0].toUpperCase()} on)`;
  if (COLUMN_WORDS[c]) return COLUMN_WORDS[c];
  const date = c.match(/^(.*)_dt_T$/);
  if (date) return `${date[1]}_dt as a date, where FDA gave a full day`;
  const prec = c.match(/^(.*)_dt_prec_T$/);
  if (prec) return `How many digits FDA gave for ${prec[1]}_dt: 8, 6 or 4`;
  return '';
}
