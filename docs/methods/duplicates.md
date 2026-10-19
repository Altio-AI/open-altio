# Duplicates across cases

For anyone deciding whether to trust which FAERS cases Open Altio shows.

This page says what we measured about duplicate cases, and the rules that follow from it. The charts and every number are in the notebook `notebooks/faers/04_duplicates`. Numbers here are from the 2026Q2 data, after one latest version per case and FDA's deleted-case lists (20,588,529 cases).

## What we found

- **Most cases cannot be checked by an exact rule.** The AEOLUS rule compares two cases only when the event date, age, age unit, sex, country, drugs and reactions are all filled in. 12,673,308 cases (61.6%) leave at least one of them empty, mostly the event date or the age. 5.3 million miss exactly one, counting age and its unit as one field.
- **The manufacturer case number finds different duplicates.** The same company case number from the same sender groups cases the AEOLUS rule cannot compare, and the two rules overlap in only a few hundred cases. Most of these copies are from the AERS years (2004 to 2011): a follow-up FDA filed as a new case, a company sending a report twice, or the same report entered twice on one day.
- **One number can be two patients.** In 1.8% of number groups the cases disagree on sex, and in a few percent more their ages differ by more than 2 years. A company's own follow-ups switch sex far less often (about 12 in 10,000 versions now), so a clash between two case numbers means two patients much more often than a corrected error.
- **Ignoring the country code on numbers is mostly wrong.** Ignoring a leading `US-` or `DE-` in general groups one company's local numbers from different countries; sex differs in 23 to 28% of those groups. Where one copy simply lacks the code that the other has, the groups look like one patient.
- **Inside the AEOLUS groups the copies agree.** Where both copies have a weight, it agrees in 96% of groups; a different suspect drug almost always comes from a different sender naming its own product.
- **Padded event dates make large, doubtful groups when one company sent them.** Up to 7 cases, a group's shared event date falls on 1 January about as often as in FAERS overall (about 10%); from 8 cases it climbs to half and more. The 1st of other months does not climb. Of the 441 large padded groups, 373 come from one company, mostly its reports of one product over a few years. The other 68 come from several companies, often one published case that every maker reported: real duplicates.
- **The latest copy usually carries more.** In groups found by the number, the latest received copy has more reactions in 31% of groups (the earliest in 12%) and more patient fields in 23% (the earliest in 2%).
- **Reports with no usable drug or reaction are not empty.** Almost all of them report only "no adverse event", but they carry indications and outcome codes, including deaths and hospitalisations.
- **Matching an empty field to an empty field sets aside far too much.** Under DiAna's rule, where it does, a common drug and reaction pair becomes one group of thousands: 16% of all cases would be set aside.

## The rules that follow

| Rule | What it does | Rule file |
|---|---|---|
| Two duplicate rules | A case is a probable duplicate when the AEOLUS rule or the same manufacturer case number from the same sender groups it. A number group is skipped when its cases include both M and F, or ages more than 2 years apart. A number without its country code joins the one coded form its sender uses. Groups of the two rules that share a case are one group. | [dup-manufacturer-number](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-manufacturer-number.md), [dedup-default](https://github.com/Altio-AI/open-altio/blob/main/rules/dedup-default.md) |
| Empty fields are never compared | A field that reads Not given (blank, says unknown or a filler, such as sex `NS` or `COUNTRY NOT SPECIFIED`) is never compared. The release says how many cases the AEOLUS rule cannot check (`funnel.json`, `duplicates`, and the methods page). | [dedup-default](https://github.com/Altio-AI/open-altio/blob/main/rules/dedup-default.md), [not-given](https://github.com/Altio-AI/open-altio/blob/main/rules/not-given.md) |
| The latest received copy is shown | `dup_kept_T` marks it. The group is dated by its earliest receipt, `group_first_dt_T`, which received-date filters, sorting and exports use. | [dup-shown-copy](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-shown-copy.md) |
| A reason line per rule | `dup_rule_T`, `dup_shown_case_T` and `dup_other_cases_T` say which rules grouped a case and which copy is shown. The sentences are the rule's values. | [dup-shown-copy](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-shown-copy.md) |
| Reaction terms in capitals | Legacy and FAERS terms compare equal (see [case versions](case-versions.md)). | [reaction-term-case](https://github.com/Altio-AI/open-altio/blob/main/rules/reaction-term-case.md) |
| Reports with no usable drug or reaction stay visible | `no_drug_or_reaction_T`, and `serious_no_drug_or_reaction_T` for those with a serious outcome code. | [no-drug-or-reaction](https://github.com/Altio-AI/open-altio/blob/main/rules/no-drug-or-reaction.md) |
| Padded event dates in large one-company groups | In AEOLUS groups of 8 or more whose cases all come from one sender, and whose shared date is 1 January or a month or year only, the date does not count as a match, so nothing is set aside. Groups from several companies stay set aside. | [dup-padded-event-dates](https://github.com/Altio-AI/open-altio/blob/main/rules/dup-padded-event-dates.md) |

Not done yet, and open for contributions:

- matching on any version of a case rather than only its latest;
- a probability that two cases are one, which would weigh partial agreement and how precise each date is.

## The numbers

These are counted in the notebook apart from the release code, and are the same when the release code runs on that data:

| | Cases set aside |
|---|---|
| The AEOLUS rule alone | 291,896 |
| With the padded-date guard (373 one-company groups, 4,697 cases; the 68 groups from several companies stay) | 287,572 (4,324 fewer) |
| Plus the manufacturer number with its guards (79 groups skipped for sex, 110 for age) | 291,511 (3,939 more) |
| Plus a number without its country code (372 groups) | 291,876 (365 more) |

- **Groups.** The two rules together make 189,576 groups. 25 of them are linked across the two rules.
- **No usable drug or reaction.** 28,004 reports have none, and 2,405 of them carry a serious outcome code.
