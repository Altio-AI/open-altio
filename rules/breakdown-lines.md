---
rule: breakdown-lines
line: An event's cases are broken down one field at a time, each value's share among only the reports that give the field, in a window and before it.
placeholder: true
values:
  default_window_quarters: 1
  groups:
    - {group: clinical, name: Clinical picture}
    - {group: causality, name: Causality}
    - {group: quality, name: Data quality}
  fields:
    - {field: seriousness, name: Seriousness, group: clinical, pick: most_severe_rose}
    - {field: age, name: Age, group: clinical, pick: children_or_older_rose_else_most}
    - {field: sex, name: Sex, group: clinical, pick: rose_most}
    - {field: pregnancy, name: Pregnancy, group: clinical, pick: {value: "yes"}}
    - {field: indication, name: Taken for, group: clinical, pick: rose_most}
    - {field: onset, name: Time to onset, group: causality, pick: median_days}
    - {field: dechal, name: Dechallenge, group: causality, pick: {value: "Y"}}
    - {field: rechal, name: Rechallenge, group: causality, pick: {value: "Y"}}
    - {field: role, name: Drug role, group: causality, pick: {value: PS}}
    - {field: dose, name: Dose, group: causality, pick: highest_strength}
    - {field: other_drugs, name: Other drugs, group: causality, pick: rose_most}
    - {field: reporter, name: Reporter, group: quality, pick: health_professionals_or_lawyers_rose}
    - {field: literature, name: Literature, group: quality, pick: {value: cites}}
    - {field: country, name: Country, group: quality, pick: rose_most}
    - {field: report_type, name: Report type, group: quality, pick: rose_most}
    - {field: key_details, name: Key details, group: quality, pick: {all_given: [onset, dose, dechal, reporter]}}
    - {field: duplicates, name: Duplicates, group: quality, pick: copies_set_aside}
  health_professionals: ["1", "2", "3"]
  lawyers: ["4"]
  onset_bands:
    - {from: 1, to: 1, name: Same day}
    - {from: 2, to: 7, name: 2 to 7 days}
    - {from: 8, to: 30, name: 8 to 30 days}
    - {from: 31, to: 90, name: 31 to 90 days}
    - {from: 91, name: Over 90 days}
enforced_in:
  - src/open_altio/explorer/breakdowns/__init__.py
  - src/open_altio/explorer/breakdowns/periods.py
  - src/open_altio/explorer/breakdowns/fields.py
  - src/open_altio/explorer/breakdowns/lines.py
  - src/open_altio/explorer/recordfields.py
  - tests/explorer/test_breakdowns.py
---
# The breakdown lines of an event

An event's breakdowns show who its cases are and how they were reported, one field at a time, and how that changed: each value's share of the reports that give the field, in a window and in the time before it. A blank is never a value, so a field that FDA's files stop giving lowers how many reports give it and never moves its shares.

- `default_window_quarters`: when the question names no window, it is this many of the release's newest quarters, to the release's end. The window is the question's own received days (`received_from`, `received_to`); before it is `before_from` to `before_to`, by default every day before the window. Both are on the day a case is dated by (rule `received-day`), so a case is in one period at most, and a case with no such day is in neither. A before that does not end before the window starts is refused. A question that names its window by the day the event began (`event_from`, `event_to`) and no received day places each case by its full event date instead, as the event date filter reads it; a case with none is in neither period.
- `groups`: the groups the lines are shown in, in order, each with its name.
- `fields`: the lines, in order, each with its name, its group and its `pick`: the value the line shows, a value of the field or the way one is chosen.
- `health_professionals` and `lawyers`: the reporter qualifications of rule `reporter-type` the Reporter line's pick gathers: physicians, pharmacists and other health professionals, and lawyers.
- `onset_bands`: the bands the Time to onset line's days are also counted in, each from its first day to its last, both included (no `to`: no last day), with its name; day 1 is the day of the first dose (rule `time-to-onset`). Each band is a value of the onset filter (`2-7`, `91-`), and the filter names a range that is a band by the band's name.

What each case gives, field by field:

- **Seriousness:** each of FDA's outcome codes the case gives (rule `serious-outcomes`), and `serious`, any serious outcome, where one of them is a code of that rule's `serious`, the codes a drug's events count serious cases by. FDA writes outcome rows only for serious outcomes, so a case with none gives `_none`, no serious outcome given, and is not missing the field: every report gives it. As rule `serious-outcomes` holds all seven of FDA's codes, each report is either `serious` or `_none`.
- **Age:** its age band (rule `age-bands`).
- **Sex:** `sex_T` (rule `sex-codes`).
- **Pregnancy:** `yes` when the case also names a term of the pregnancy SMQ (rule `pregnancy-cases`), else `no`. FAERS has no pregnancy field, so the line has no Given in share. It reads MedDRA's licensed part, so for a viewer without MedDRA the line is Not available, with the reason.
- **Taken for:** each indication the product's drug records give (`indi_pt`, read through rule `not-given`), counted under today's preferred term where reactions are (rule `meddra-terms`).
- **Time to onset:** the days from the product's first dose to the event (rule `time-to-onset`).
- **Dechallenge** and **Rechallenge:** FDA's codes Y, N and D, read through rule `not-given` and rule `rechallenge-correction`.
- **Drug role:** the product's role in the case, the first in the order of rule `explorer-drug-counts`.
- **Dose:** each dose the product's records write (`dose_vbm`), its runs of spaces made one, in capitals.
- **Other drugs:** each other drug in the roles the product is counted in, by its ingredients or FDA's spelling with no ingredient; `_none` where the case names no other.
- **Reporter:** `reporter_type_T` (rule `reporter-type`). Most reports in FDA's files since 2025 Q3 give no reporter, which lowers the line's Given in share and never its shares.
- **Literature:** `cites` where the report cites an article in FDA's literature reference (`lit_ref`), else `_none`, no article cited (rule `literature-reference`). A report from FDA's files before they held the field does not give it. On a release whose explorer database was built without the field, the line is Not available, with the reason.
- **Country:** `country_T`.
- **Report type:** FDA's `rept_cod`.
- **Key details:** how many of the fields its pick names the case gives.
- **Duplicates:** whether the case is kept or set aside as a probable duplicate (rule `dedup-default`), over every case of the question, kept or set aside.

Each line shows one value (`shown`), chosen by its `pick`, with its share in each period, its change, its p-value and whether it rose (rule `breakdown-rose`), and the line says whether it is an alarm (rule `breakdown-alarm`). A pick is one of these:

- `most_severe_rose`: the first outcome of rule `serious-outcomes`' list, in its order from death, that rose; else death.
- `children_or_older_rose_else_most`: the children or the older bands of rule `age-groups`, whichever rose, the one up most where both did; else whichever of those two, and of each band in neither, rose most.
- `health_professionals_or_lawyers_rose`: the lawyers (`lawyers`) where they rose, else the health professionals (`health_professionals`).
- `rose_most`: the value that rose most of those that rose, else the one up most, else the commonest in the window, else before.
- `median_days`: the median of the days, with its change in days and the Mann-Whitney test of rule `chance-test`.
- `value`: the value the pick names, such as FDA's code Y.
- `highest_strength`: the doses that read to the highest strength (rule `dose-strength`).
- `all_given`: the reports giving every field the pick names.
- `copies_set_aside`: the copies set aside as probable duplicates.

A value of several gathered (any serious outcome, the children, the health professionals, the doses at one strength) counts each case once. A value with nothing to compare in a period has no change, p or rise there.

A field a drug record gives once (time to onset, dechallenge, rechallenge, drug role) takes the product's first record that gives it, by role and then by FDA's drug sequence. A share is null, never 0, in a period where no report gives the field, and so is its change in points; a period with no report has no Given in share either.

**Not yet decided.** These values were chosen before their evidence. Notebook `notebooks/faers/16_breakdowns` will decide them: which window, and which fields and picks, separate the changes regulators acted on from those they did not, on years it was not tuned on.

**Why:** a change in who an event's cases are, or in how they were reported, can show before the count does. Counting only the reports that give a field keeps a gap in FDA's files from reading as a change.
