/* The words of an opened finding and of a rule with no finding, in the methods page's Why shape:
   how to read the chart (Bars:, Lines:), why it matters and what we did. They hold no number of the
   release: what a chart shows is the finding's own two sentences, or the lines the release's cards
   bring, so every number on the page is the release's. */

// The drug names' line: FDA's spellings read to single ingredients and combinations, a combination
// counting under each of its own ingredients too. Wherever the page says it (the Drug names box, its
// card, the rule's Off line) it takes these words, so they change here alone.
export const DRUG_LINE = { spellings: 'FDA spellings', verb: 'read to', ingredients: 'single ingredients', combinations: 'combinations' };

// A rule that works inside another's chart says so in one line above it, in place of a chart of its own
const LABEL_CODING = 'This rule works inside the MedDRA coding of the labels, which is licensed, so it shares the label flags chart.';
export const SHARED_CHART = {
  'label-negation': LABEL_CODING,
  'label-population': LABEL_CODING,
  'atc-spelling-bridges': "WHO's spellings are joined to ours once, in a reviewed list, not record by record, so there is nothing of its own to count.",
  'dup-shown-copy': 'It only picks which copy of a duplicate you see, so it moves no total.',
};

// each finding of the release's methods, by its id
export const CARD_WORDS = {
  deleted_lists_name_aers_cases: { guide: "Bars: listed AERS cases by quarter published, direct electronic reports apart.", matters: "Followed for FAERS cases only, the listed AERS cases would stay in every count.", did: "Take every listed AERS case out too, as FDA's lists say." },
  one_case_two_numbers: { guide: "Bars: cases by year first received, set aside on the number or not matched.", matters: "Often a follow-up filed as a new case, which an exact match on every field misses.", did: "Set them aside on the number, except where the copies disagree on sex or on age." },
  padded_dates_join_different_patients: { guide: "Bars: share of groups dated 1 January, or a month or year only, by group size.", matters: "In large look-alike groups from one company, that date merges different patients.", did: "In large look-alike groups from one company such a date is no match, so their cases stay apart." },
  padding_puts_reactions_before_drug: { guide: "Lines: share of therapy lines with the event first, dated the 1st or another day.", matters: "A time to onset from a padded date would be wrong.", did: "Count it only from two dates known to the day; none when the event comes first." },
  brand_changes_ingredient: { guide: "Bars: cases naming Zantac by year, by the ingredient they carry.", matters: "Zantac 360, since ranitidine's 2020 withdrawal, is famotidine: a brand search mixes two medicines.", did: "Count each case by its ingredient, not the brand." },
  to_mfr_filler_on_company_reports: { guide: "Lines: share of report versions with to_mfr filled, direct and company reports.", matters: "to_mfr means something only on direct reports.", did: "Read to_mfr on a company report as Not given." },
  who_reported_lost_on_company_reports: { guide: "Lines: share of reports saying who reported, company and direct reports.", matters: "The fall is a change in FDA's files, not in who reports.", did: "Say so under the field's chart and filter." },
  completeness_depends_on_sender: { guide: "Bars: each large sender's cases, by how many of age, sex and event date they give.", matters: "A product's cases carry its companies' habits.", did: "Every chart says how many cases give its field; senders count by company." },
  rechal_filler: { guide: "Lines: share of drug rows with dechallenge, and rechallenge, filled per quarter.", matters: "Dechallenge is near empty in those years, and later versions drop the D: it is a filler.", did: "Read the D as a filler, not an answer swapped with dechallenge." },
  quarterly_files_keep_their_meddra_version: { guide: "Line: share of each quarter's reaction rows no longer a current MedDRA term.", matters: "FDA recodes its own database to each version but never reissues a published file.", did: "Read every quarter in the release's one MedDRA version, the newest at the build." },
  sender_names_unstable: { guide: "Lines: share of each company's cases under its long legal name, per quarter.", matters: "Counting cases by sender needs these spellings mapped.", did: "Document the spellings, as measured here." },
  rept_cod_combination_products: { guide: "Bars: 30-day and 5-day report cases by year, 30-day split by outcome.", matters: "30-day reports are device malfunctions with no adverse event; 5-day reports ask for remedial action.", did: "Keep FDA's report type; count neither as a 15-day expedited report, as DiAna does." },
  drug_seq_repeated: { guide: "Line: share of FAERS drug rows that share their drug number, per quarter.", matters: "Counting FDA's rows would count one drug several times.", did: "Count drugs by sequence number; time to onset takes each drug's earliest start." },
  country_empty_rising: { guide: "Lines: share of FAERS cases with no country, and from the US, by year.", matters: "Country filters miss these cases.", did: "Document the gap; no country is inferred." },
  european_union_for_member_state: { guide: "Bars: cases giving EU as country by quarter, member state found or not.", matters: "Counted by country, these cases fall out of their member state.", did: "Take the member state from an earlier version where one names it; the rest read European Union." },
  sex_not_specified_for_empty: { guide: "Lines: share of cases with sex empty, and written NS, per quarter.", matters: "A count of cases with no sex that leaves NS out misses them.", did: "Read NS, UNK and an empty field alike as not given, FDA's letter beside it." },
  duplicate_check_needs_fields: { guide: "Lines: share of cases that cannot be checked, event date or age blank, by year.", matters: "No exact rule can tell whether they repeat another case.", did: "Leave blanks unfilled: the duplicate flag finds only the copies it can check." },
  no_adverse_event_serious_outcome: { guide: "Bars: cases with no usable drug or reaction by year, serious outcome or not.", matters: "Some still record a serious outcome, such as a death or a hospital stay.", did: "Keep them all in view, and flag those with a serious outcome." },
  unknown_indication_placeholder: { guide: "Line: share of each quarter's indication rows that give no reason.", matters: "A count of what drugs were given for leaves them out, or counts them as one.", did: "Leave them as FDA wrote them." },
  two_use_drug_use_not_said: { guide: "Lines: share of two-use drug records whose use is not said, or whose route is.", matters: "A filter on exact classes would miss them.", did: "Give each the class its uses share, or can't tell, and keep every class it could be." },
  carried_cases_counted_twice: { guide: "Bars: cases with versions in both AERS and FAERS, by year first received.", matters: "Counted in each era, every one would count twice.", did: "Keep one latest version per case across both eras." },
  deleted_lists_unpublished: { guide: "Bars: case ids by the quarter whose list first named them.", matters: "Every published case on the lists would otherwise stay in every count.", did: "Take every published listed case out of the counts." },
  same_event_several_cases: { guide: "Bars: cases set aside as a copy, by year, by where the copy came from.", matters: "Each copy would count the same patient's event again.", did: "Show one copy per event, the latest; flag the rest." },
  one_medicine_many_spellings: { guide: "Bars: cases with adalimumab as a suspect, by what is searched.", matters: "A brand search misses other names and every biosimilar.", did: "Read every drug name to its ingredients." },
  eras_write_countries_and_terms_differently: { guide: "Lines: share written each way, per quarter published.", matters: "The same event in both eras could never match.", did: "Compare countries as codes and terms in capitals." },
  event_dates_padded: { guide: "Lines: share of full event dates on the 1st, and on the 15th.", matters: "A padded date gives a time to onset nobody reported.", did: "Read a date on the 1st as known to its month." },
  ages_without_a_unit: { guide: "Line: cases with an age but no unit, per quarter.", matters: "A count that needs the unit would leave them ageless.", did: "Read them as years, as other versions of the same cases say." },
  occupation_code_changes: { guide: "Lines: share of FAERS cases by reporter code, per quarter.", matters: "Counts by reporter type would show a false break when OT ended.", did: "Read OT and HP as one: other health professional." },
  unknown_written_two_ways: { guide: "Bars: share of drug rows by how the route is given, per quarter.", matters: "Counted apart, blank and unknown draw trends that are not real.", did: "Read every way of saying unknown as Not given." },
  background_drugs_counted_every_role: { guide: "Bars: cases per ingredient, as a suspect and in another role only.", matters: "Counting every role measures who takes it, not suspicion.", did: "Count a drug where it is the primary or secondary suspect." },
  aspirin_dose_tells_the_use: { guide: "Bars: aspirin records that state a dose, low dose against full dose.", matters: "One class per substance would file blood thinners as painkillers.", did: "Class aspirin by the dose its report states." },
  older_meddra_terms_missed: { guide: "Bars: cases per today's term, written as today's term or an older one.", matters: "A search on today's term would miss those cases.", did: "Count every reaction under today's preferred term." },
  no_outcome_not_non_serious: { guide: "Lines: share of each report type's cases with no outcome, per year.", matters: "Read as non-serious, serious cases would be undercounted.", did: "Never read a case with no outcome as non-serious." },
};

// a rule with no finding of its own: why it matters and what we did
export const RULE_WORDS = {
  'transformed-suffix-T': { matters: "So you can always tell FDA's data from ours.", did: "Keep every value as FDA wrote it; anything we work out sits beside it." },
  'overlong-lines': { matters: "A missing line break would lose the second report.", did: "Split the line back into two; only the line break is put back." },
  'sex-codes': { matters: "Every code but F and M means the sex is not known.", did: "The sex filter and statistics read sex_T; FDA's code stays in sex." },
  'age-in-years': { matters: "FDA gives ages in many units, and some with none.", did: "Read age in years, exact; no unit means years; a negative or impossible age is no age." },
  'weight-in-kg': { matters: "Weights come in several units, some with none or a filler.", did: "Read weight in kg; no unit, an unknown unit, zero or an impossible weight is no weight." },
  'age-bands': { matters: "The age filter and the statistics must read the same band.", did: "Place each case in one band; a child given as 0 years goes by the sender's age group." },
  'dup-shown-copy': { matters: "The copy FDA received last usually carries the most information.", did: "Show it, dated by when FDA first heard of the event; the others point to it." },
  'country-not-given': { matters: "Cases sharing only these words would match on country as duplicates.", did: "Read COUNTRY NOT SPECIFIED and A1 as no country; fall back to the reporter's." },
  'no-drug-or-reaction': { matters: "Some still record a death, a hospital stay or another serious outcome.", did: "Keep them in view rather than remove them, and mark those." },
  'company-names': { matters: "One company appears under several spellings, such as ELI LILLY AND CO.", did: "Read each spelling as its company's name, so one company counts together." },
  'drug-route': { matters: "The label flags read only labels whose route families overlap the report's.", did: "Read FDA's route, often Unknown, with the dose form and name words, for every family it could be." },
  'date-limits': { matters: "A time worked out from an impossible date would be wrong.", did: "Check the event, start and end dates; one after its file or long before birth gets no clean value." },
  'therapy-duration': { matters: "A duration longer than the patient could be treated is not real.", did: "Days from two dates known to the day, else FDA's duration; a missing date is never filled." },
  'atc-index': { matters: "Drugs count together by what they treat, the same in 2004 as in 2026.", did: "Give each drug record its WHO ATC class from one index year, in tables of its own." },
  'atc-spelling-bridges': { matters: "Where WHO and DiAna spell a substance differently, it would get no class.", did: "Join the two spellings through a reviewed list, such as ciclosporin and cyclosporine." },
  'atc-group-classes': { matters: "WHO codes each product, not a group such as insulin or iron.", did: "Give such a record WHO's class for the group, marked as a group class." },
  'rxnorm-ingredients': { matters: "The code joins a FAERS drug to its FDA label, never to another drug's.", did: "Take it from the drug name, else the active ingredient, else the ingredient; never guessed." },
  'legacy-term-spelling': { matters: "AERS wrote every term in capitals; FAERS writes them as MedDRA spells them.", did: "Show each legacy term in FAERS's spelling, FDA's capitals beside it; no MedDRA file needed." },
  'statistics-cases': { matters: "A pair's EBGM, PRR, ROR, RRR, IC, time to onset and strata stand side by side.", did: "Count the kept cases naming at least one suspect ingredient and one reaction." },
  ebgm: { matters: "Two or three cases cannot make a pair look alarming on their own.", did: "DuMouchel's Gamma-Poisson Shrinker; EB05 to EB95 holds the true ratio with 90% chance." },
  prr: { matters: "A PRR of 3: the reaction is three times as large a part of the ingredient's cases.", did: "Compare the reaction's share of the ingredient's cases with everyone else's, with chi-square." },
  ror: { matters: "An ROR of 3 means three times the odds among the ingredient's cases.", did: "Compare the odds with every other case's; a screen reads the 95% interval's lower bound." },
  rrr: { matters: "An RRR of 3 means three times as many cases as expected.", did: "Divide the cases with both by those expected if the two were unrelated." },
  ic: { matters: "An IC of 1 means twice the expected cases, 2 four times, 0 as expected.", did: "A doubling scale pulled to no difference when cases are few; a screen reads its lower bound." },
  'statistics-classes': { matters: "A reaction that stands out for a whole class can be told from one that stands out for one drug.", did: "Work the statistics out again with each drug's WHO class in place of its ingredient, at three levels of the class." },
  'ror-strata': { matters: "It shows a link that comes only from who takes the drug, such as older people.", did: "Work each pair's ROR out again within each age band and within each sex." },
  'label-source': { matters: "Only human prescription labels should ever be read.", did: "Read DailyMed's SPL XML and RxNorm link files, from its human prescription zips only." },
  'label-choice': { matters: "Every flag reads the same label, anyone can see why, and no label is a normal outcome.", did: "Reach a label by drug name, active ingredient, RxNorm ingredient, then label." },
  'label-sections': { matters: "A label from any company reads the same way.", did: "Find each safety and indications section by its LOINC code, never its heading." },
  'label-own-ingredients': { matters: "Some current labels, such as TECENTRIQ's, would show No label found.", did: "Key such a label by the active ingredients it lists, each matched to one RxNorm name." },
  'label-dictionary': { matters: "A reaction counts however the label spells it, never also as a broader one.", did: "Read each label's safety sections once, in MedDRA's words and synonyms." },
  'label-negation': { matters: "\"No cases of hepatitis were reported\" does not list hepatitis.", did: "A reaction the label rules out is not on it; an unsure sentence goes to a person." },
  'label-population': { matters: "\"Contraindicated in patients with renal failure\" names patients, not a reaction.", did: "Read such conditions, and all of contraindications, as not on the label." },
  'label-table-rows': { matters: "A reaction only the placebo or comparator group had is not the drug's.", did: "Leave it off the label; a row that cannot be lined up goes to a person." },
  'label-umbrella': { matters: "An injection site reaction covers pain or redness where the drug went in.", did: "Count the mild reactions under it as on the label, never a serious form." },
  'label-treated-disease': { matters: "Reports often name the disease the drug was given for.", did: "Flag it as the treated disease; a worse form, such as status asthmaticus, is judged." },
  'label-not-a-medical-event': { matters: "Not working, wrong or off-label use, a faulty product or exposure name no health effect.", did: "Set these aside; a real reaction in the report gets its own flag." },
  'label-procedure': { matters: "A procedure can be the only trace of serious harm.", did: "Flag terms such as liver transplant or dialysis as procedures, kept in view." },
  'label-flags': { matters: "A reaction not on the label is the first thing a safety reviewer asks about.", did: "Flag each drug and reaction by fixed rules anyone can rerun; the flags hold no MedDRA codes." },
};
