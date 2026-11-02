---
rule: counted-question
line: A question's cases are counted by one field at a time, each case once under each value it gives, and each value comes with the question that lists exactly its cases.
values:
  by: [year, quarter, month, event, outcome, sex, age, country, reporter, route, dose_form, lot]
enforced_in:
  - src/open_altio/explorer/counted.py
  - tests/explorer/test_counted.py
---
# A counted question

Any product built on Open Altio may ask how many cases a question holds, counted by one field: a drug in the roles it is counted in (rule `explorer-drug-counts`) under the explorer's filters, by year, by event or by sex, say. Each count is of distinct cases, never of FDA's rows, and each value comes with the case list's question for exactly its cases, so anyone can open the cases behind a number.

- `by`: the fields a question may be counted by. Any other is refused, with these choices named.

What each case gives, field by field:

- **Year**, **quarter** and **month:** the year, quarter or month of the day a case is dated by (rule `received-day`), written `2026`, `2026q2` and `2026-04`, listed in time order. A case with no such day counts in a row of its own, its value null, and since no filter picks it, its question is null too.
- **Event:** each reaction the case names, under today's preferred term where the release holds MedDRA (rule `meddra-terms`). A case counts once under each event it names, so the events' counts can add up to more than the question's cases. A case naming no reaction counts in a row of its own, its value and its question null.
- **Outcome:** each of FDA's outcome codes the case gives (rule `serious-outcomes`), `_none` for a case with none. A case can give several, so a count by outcome is refused under an outcome filter: no question could list the cases giving both.
- **Route**, **dose form** and **lot:** each value the drug records the question counts give (the product's own, in the roles it is counted in, or every record with no product), as its filter reads it: in capitals, runs of spaces made one, `_none` for a case whose records give none. A case's records can give several, so these counts are refused under the same field's filter, as a count by outcome is.
- **Sex**, **age**, **country** and **reporter:** the case's own field, as its filter reads it (rules `sex-codes`, `age-bands`, `legacy-country` and `reporter-type`), `_none` for Not given (rule `not-given`).

Each value is the one its field's filter takes, so the question for a value's cases is the counted question with that value as the filter, and for a time, the days of it the question takes in. The values other than times are listed by their cases, most first, then by value. A filter value that is not one of its choices is left out of the count, and the answer says so in plain words.

**Why:** a number a person or a product reads should be checkable. Counting distinct cases by the fields the filters already read keeps one reading of each field: the case list lists a value's cases through the same filter the count was made with, so the two cannot disagree.
