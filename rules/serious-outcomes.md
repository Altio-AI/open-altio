---
rule: serious-outcomes
line: A case is serious, fatal or life-threatening by FDA's own outcome codes; one with no outcome is none of them.
values:
  serious: [DE, LT, HO, DS, CA, RI, OT]
  death: DE
  life_threatening: LT
enforced_in:
  - src/open_altio/explorer/eventlist.py
  - src/open_altio/explorer/breakdowns/fields.py
  - src/open_altio/explorer/breakdowns/lines.py
  - src/open_altio/explorer/casecolumns.py
  - src/open_altio/faers/insights/cards/rule_charts.py
  - tests/explorer/test_eventlist.py
  - tests/explorer/test_counting.py
  - tests/explorer/test_breakdowns.py
  - tests/explorer/test_casecolumns.py
---
# Serious, fatal and life-threatening cases

A drug's events count, for each event or group of reactions counted as one, the cases that were serious, the cases that ended in death, the cases that were life-threatening and the cases that did either, read from the outcomes FDA gives the case. A case counts in each list one of its outcome codes is in, and in none of them when FDA gives it no outcome. An event's breakdowns count serious cases the same way on their Seriousness line (rule `breakdown-lines`).

- `serious`: FDA's outcome codes (`outc_cod`, as published, gathered in `explorer_case_T.outcomes_T`) that make a case serious: death (`DE`), life-threatening (`LT`), hospitalization, initial or prolonged (`HO`), disability (`DS`), congenital anomaly (`CA`), required intervention to prevent permanent impairment or damage (`RI`) and other serious, an important medical event (`OT`).
- `death`: the code of a case that ended in death.
- `life_threatening`: the code of a case that was life-threatening.
- A case with either code counts once among the cases that ended in death or were life-threatening (`death_or_life_threatening`), so that count is at least each of the two and at most both together.
- A share is the count over the event's cases, both counted in distinct cases.
- The case list sorted by seriousness puts first the cases whose most serious outcome comes earliest in `serious`, death first, and a case with no outcome last.

**Why:** FDA's outcome codes are the seriousness criteria of ICH E2A, one code for each criterion the report meets. So every code makes the case serious, and a case with no outcome row meets none of them by FDA's codes. Counting from FDA's own codes, as published, keeps each count checkable against FDA's files.
