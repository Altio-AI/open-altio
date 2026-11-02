---
rule: medical-event-lists
line: Reaction terms that EMA lists as designated or important medical events are marked from the list files you give the build.
values:
  lists:
  - dme
  - ime
enforced_in:
- src/open_altio/faers/medical_events.py
- src/open_altio/faers/release.py
- src/open_altio/explorer/eventlist.py
- src/open_altio/faers/insights/cards/rule_charts.py
- tests/faers/test_medical_events.py
- tests/explorer/test_eventlist.py
---
# EMA's medical event lists

The European Medicines Agency publishes two lists of reaction terms that deserve a closer look whenever they are reported: the Designated Medical Event (DME) list and the Important Medical Event (IME) list. The release holds each list you give it, as the table `medical_events_T`, and a drug's events say whether each is on a list. Nothing is taken out of the counts.

- `lists`: the two lists, `dme` and `ime`. A list is read from a file you name when you build, and is never part of the program. Neither is licensed to us, so we ship neither.
- The table holds one row for each term of each list: `list_T` is `dme` or `ime`, and `pt_T` is the preferred term as MedDRA writes it.
- The DME file is EMA's workbook, its terms in the first column under the heading PTs. The IME file is EMA's workbook for one MedDRA version, naming each term by code and by name.
- A release built with MedDRA reads the IME file's codes to the preferred terms of its own version and names each as that version does; a code that is no preferred term of the version is left out and counted in the manifest. A release built without MedDRA marks by the names the file gives.
- A list that was not given, or could not be read, has no rows. Its entry in the manifest says so and why, and every event's mark for it is Not available, never "no". A term is marked "no" only where the release holds the list and the term is not on it.

**Why:** a regulator reading a drug's events looks first at the ones EMA has named, and a mark that says "not on the list" where the list was never loaded would be wrong.
