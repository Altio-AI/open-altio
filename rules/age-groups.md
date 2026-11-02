---
rule: age-groups
line: An event's facts give the share of its cases in the children's bands and in the older bands, of the cases that give an age.
placeholder: true
values:
  children: ["0-27d", "28d-1", "under-1", "2-11", "12-17"]
  older: ["65-74", "75-84", "85+"]
  share_of: given_age
enforced_in:
  - src/open_altio/explorer/eventfacts.py
  - src/open_altio/explorer/breakdowns/lines.py
  - src/open_altio/faers/insights/cards/rule_charts.py
  - tests/explorer/test_eventfacts.py
---
# The age groups an event's facts compare

An event's facts give two shares of its counted cases: the children and the older people. Each is a list of the ids of rule `age-bands`, so a band added or renamed there is named here by the same id. `eventfacts` refuses a list that names an id `age-bands` does not hold.

- `children`: the bands counted as children.
- `older`: the bands counted as older people.
- `share_of`: what a share is of. `given_age` means the cases that give an age (`age_band_T` is not empty), so a case with no age is in neither the top nor the bottom of the share. The number of those cases is given beside each share as `aged`. An event, or a drug, with no case that gives an age has no share: it is empty (null), never 0.

The same two shares are given for all the drug's counted cases, so an event's can be read against the drug's own.

**Not yet decided.** These lists were chosen before their evidence. Notebook `notebooks/faers/15_event_facts` will decide them, by checking which bands separate the events regulators have acted on from those they did not, on years it was not tuned on.

**Why:** an event concentrated in children or in older people than the drug's own cases are is a fact a reviewer weighs, and it is only fair to compare it with the people who report the drug, not with everyone in FAERS.
