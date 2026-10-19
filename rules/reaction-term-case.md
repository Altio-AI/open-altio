---
rule: reaction-term-case
line: FDA's old system wrote reactions in capitals and the new one does not; reactions are compared ignoring capitals, so the same reaction matches across both.
values: {}
enforced_in:
  - src/open_altio/faers/derive.py
  - tests/faers/test_eras.py
  - tests/faers/test_user_rules.py
  - tests/explorer/test_filters.py
---
# Capital letters ignored in reactions

FDA's old system wrote reactions in capitals; the new one does not. We compare reactions without regard to capitals, so the same reaction matches across both systems. FDA's own text is not changed.

Legacy AERS writes every reaction term in capitals (`DRUG INEFFECTIVE`); FAERS writes MedDRA's own spelling (`Drug ineffective`). `pt_norm_T` on `reac_latest_T` is `pt` in upper case, and the duplicate key compares the set of `pt_norm_T`, so a legacy case and a FAERS case with the same reactions can match. The raw `pt` is never changed. Switched off, `pt_norm_T` is `pt` as written.

Only letter case is ignored. A legacy term MedDRA has since renamed (`DRUG EXPOSURE DURING PREGNANCY`) still differs from its current name; that is a question of MedDRA versions, not of letter case.

**Why:** compared as FDA wrote them, the reaction sets of the two eras almost never agree, so duplicates across AERS and FAERS go unfound even with countries read as codes (`rules/legacy-country.md`). Notebook `notebooks/faers/02_case_versions`, section 6, counts it. FAERS's 2012Q4 to 2013Q2 files also hold some terms in capitals; those cases match the rest of FAERS too.
