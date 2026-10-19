/* FDA's codes, and Open Altio's own, and what a person reads for each. A code that says unknown reads
   Not given, as an empty field does (rule not-given). The age bands are a rule's, sent with /api/release
   (state.js, ages). */

export const NONE = '_none';
export const OUTCOME = { DE: 'Death', LT: 'Life-threatening', HO: 'Hospitalization', DS: 'Disability', CA: 'Congenital anomaly', RI: 'Required intervention', OT: 'Other serious', [NONE]: 'No outcome given' };
// the E2B(R3) reporter qualification FDA's occp_cod is read as (reporter_type_T, rule reporter-type)
export const REPORTER = { 1: 'Physician', 2: 'Pharmacist', 3: 'Other health professional', 4: 'Lawyer', 5: 'Consumer or other non health professional', [NONE]: 'Not given' };
export const SEX = { F: 'Female', M: 'Male', [NONE]: 'Not given' };
export const ROLE = { PS: 'Primary suspect', SS: 'Secondary suspect', C: 'Concomitant', I: 'Interacting' };
// each route family a drug record could be in, in words (rule drug-route), and the fields of FDA's
// it was read from (route_source_T joins them with +)
export const ROUTE_FAMILY = { by_mouth: 'By mouth', under_tongue: 'Under the tongue', injected: 'Injected', inhaled: 'Inhaled', nasal: 'Nasal', rectal: 'Rectal', vaginal: 'Vaginal', transdermal: 'As a patch', skin: 'On the skin', eye: 'In the eye', ear: 'In the ear', other: 'Another way' };
export const ROUTE_SOURCE = { route: 'FDA\'s route', dose_form: 'the dose form', drugname: 'the drug name', disagree: 'Its route, dose form and name disagree' };
// FDA's report types as FDA's E2B(R3) rules name them: never regrouped, 30DAY and 5DAY are not EXP
export const REPT = { EXP: 'Expedited (15-day)', PER: 'Periodic', DIR: 'Direct from the public or a health professional', '5DAY': '5-day: drug-device combination, remedial action', '30DAY': '30-day: device malfunction on a drug-device combination' };
// A case with no outcome is never called non-serious; an expedited report is meant for serious reactions.
export const noOutcome = (rept) => (rept === 'EXP' ? 'Sent as an expedited report, which is for serious reactions, but FDA gives no seriousness criterion' : 'No serious outcome given');
// FDA's dose_freq codes in FDA's own words (its ASCII file description), and the codes it uses
// beyond that list; a code not here, such as 999 or UD, is shown as FDA wrote it.
export const FREQ = {
  '1X': 'Once or one time', BID: 'Twice a day', BIW: 'Twice a week', HS: 'At bedtime', PRN: 'As needed',
  Q2H: 'Every 2 hours', Q3H: 'Every 3 hours', Q4H: 'Every 4 hours', Q5H: 'Every 5 hours', Q6H: 'Every 6 hours', Q8H: 'Every 8 hours', Q12H: 'Every 12 hours',
  Q3W: 'Every 3 weeks', QD: 'Daily', QH: 'Every hour', QID: '4 times a day', QM: 'Monthly', QOD: 'Every other day', QOW: 'Every other week',
  TID: '3 times a day', TIW: '3 times a week', QW: 'Weekly',
  '/DAY': 'Per day', '/WK': 'Per week', '/MONTH': 'Per month', '/YR': 'Per year', '/CYCLE': 'Per cycle', '/HR': 'Per hour', '/MIN': 'Per minute', '/SEC': 'Per second',
};
// FDA writes its per-unit codes in either case (/wk and /WK)
export const freqWords = (code) => (code ? FREQ[String(code).toUpperCase()] || '' : '');
export const ERA = { faers: 'FAERS', legacy: 'AERS' };
// the flag on a report with no usable drug or reaction that still gives a serious outcome (rule no-drug-or-reaction)
export const UNUSABLE_SERIOUS = 'No usable drug or reaction recorded, serious outcome reported';
// where a drug record's ingredients came from (rule drug-names)
export const INGREDIENT_SOURCE = { diana_name: 'DiAna dictionary', diana_prod_ai: 'DiAna, via FDA\'s active ingredient', correction: 'Open Altio correction' };
export const DECHAL = { Y: 'Reaction abated when stopped', N: 'Did not abate when stopped', D: 'Does not apply' };
export const RECHAL = { Y: 'Recurred when restarted', N: 'Did not recur when restarted', D: 'Does not apply' };
// a code as a person reads it: a missing code is the map's Not given, an unknown one stays as it is
// why a drug has no time to onset (time_to_onset_reason_T, rule time-to-onset): a few words, then
// the sentence a tip gives
export const NO_ONSET = {
  padded_event_date: ['Padded event date', 'The event date is on the 1st, which FDA writes for a date known only to its month or year'],
  event_date_not_exact: ['No exact event date', 'The event date is not known to the day'],
  first_dose_not_exact: ['No exact first dose', 'No start of the drug is known to the day, or one known only to its month or year could be earlier'],
  event_before_first_dose: ['Event before first dose', 'The event date is before the first dose'],
};
export const labelOf = (map, code) => map[code ?? NONE] ?? code ?? map[NONE];
// How a drug record's one WHO class was chosen (rule atc-class-choice): the words, and what they mean
export const CHOSEN_BY = {
  only_code: ['Only one code', 'The drug has one WHO code.'],
  dose: ['Chosen by dose', 'The drug has a WHO code for each use, and the dose on the report says which.'],
  route: ['Chosen by route', 'The drug has a WHO code for each use, and the route on the report says which.'],
  indication: ['Chosen by indication', 'The drug has a WHO code for each use, and what the report says it was taken for says which.'],
  shared_class: ['Shared class', 'The report does not say which of its WHO codes; they share this broader class.'],
  cannot_tell: ["Can't tell", 'The report does not say which of its WHO codes, and they share no class but the main group.'],
  group_class: ['Group class', 'The report names only a group of drugs, such as insulin; this is WHO\'s class for the group.'],
};
