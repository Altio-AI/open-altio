---
rule: reporter-type
line: In 2020 FDA replaced the code OT, other health professional, with HP, health professional; we read both as one type, so charts of who reported do not break that year.
values:
  mapping: mappings/faers/reporter_types/accepted.csv
enforced_in:
  - src/open_altio/faers/derive.py
  - tests/faers/test_derive.py
  - tests/faers/test_user_rules.py
  - tests/explorer/test_filters.py
---
# Who reported, read one way

In 2020 FDA stopped writing OT, other health professional, and started writing HP, so a chart of who reported breaks in that year. We read FDA's reporter code as the reporter's qualification in ICH E2B(R3), the international standard for safety reports, where both are one type. FDA's own code is not changed.

`reporter_type_T` holds the E2B(R3) reporter qualification (C.2.r.4, code list 6) of FDA's `occp_cod`, read through the reviewed mapping in `mapping`: MD is 1 Physician, PH 2 Pharmacist, OT, HP and RN 3 Other health professional, LW 4 Lawyer, CN 5 Consumer or other non health professional. Any other code, and an empty one, is empty. The explorer's reporter filter and chart use `reporter_type_T`, and the case window shows the type with FDA's code beside it. Switched off, `reporter_type_T` is `occp_cod` as FDA wrote it.

HP and RN are not in FDA's README. Reading HP as other health professional is ours, from the pattern below; RN, a registered nurse, is a health professional who is neither physician nor pharmacist.

**Why:** notebook `notebooks/faers/08_dates_and_codes`. OT is about 20% of FAERS cases each year to 2019 and none from 2020; HP is 22% from 2020; MD and PH stay flat across the change. So HP took OT's place, and only the type counts across 2020.
