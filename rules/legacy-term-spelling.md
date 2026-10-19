---
rule: legacy-term-spelling
line: FDA's old system wrote every reaction in capitals, such as DRUG INEFFECTIVE; we show it as FAERS spells the same term, Drug ineffective, with FDA's capitals beside it.
values: {}
enforced_in:
  - src/open_altio/faers/spelling.py
  - src/open_altio/faers/derive.py
  - tests/faers/test_spelling.py
---
# Old capitals shown in today's spelling

AERS, FDA's system until 2012, wrote every reaction and indication in capitals; FAERS writes them as MedDRA spells them. Each legacy term is also given the spelling FAERS uses for the same term, so a case can show it the way MedDRA writes it, with FDA's capitals beside it. FDA's text is not changed, and no MedDRA file is needed.

`pt_spelling_T` on `reac_latest_T` and `indi_pt_spelling_T` on `indi_latest_T` hold, on a legacy row, the spelling FAERS uses for the same text compared without capitals. Only FAERS text with a small letter in it counts as a spelling. Where FAERS spells a term two ways, the one on more rows is used. A term FAERS never spells stays as FDA wrote it, and so does every FAERS row. MedDRA's spelling is sentence case, not title case (`Drug ineffective`, `Hepatitis C`), so it cannot be made from capitals by a rule without getting abbreviations and names wrong. Switched off, both columns are FDA's text as written. Which cases are kept does not change: matching already ignores capitals (`rules/reaction-term-case.md`).

**Why:** FAERS writes the same term in mixed case for 97.4% of legacy reaction rows (9,662,115 of 9,918,945), so FAERS's own text gives nearly every legacy term its spelling with nothing licensed. The evidence is `notebooks/faers/06_meddra_versions`, section 3.
