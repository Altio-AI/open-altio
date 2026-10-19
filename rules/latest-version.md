---
rule: latest-version
line: FDA republishes a case each time news arrives; we count only its newest version, once, even for cases moved from FDA's old system (AERS) to the new one (FAERS) in 2012.
always_on: true
why_locked: Without it, every version of a case would count as a case of its own.
values:
  across_eras: true
settable:
  across_eras:
    label: Count a case once across AERS and FAERS
enforced_in:
  - src/open_altio/faers/derive.py
  - tests/faers/test_eras.py
---
# Newest version of each case

FDA publishes a case again each time new information arrives, so one case can have many versions. We keep only the newest version of each case, and count it once even when FDA moved it from its old system, AERS, to its new one, FAERS, in 2012. Older versions stay in the release.

A case is identified by its case number (`caseid`, legacy AERS's CASE). Its latest version is chosen from every version FDA published, in either era: the highest `caseversion`, then the latest `fda_dt`, then the latest quarter, then the highest `primaryid`. Legacy AERS has no `caseversion`, so a case FDA carried into FAERS keeps its FAERS version. A legacy row with no CASE number is its own case. With `across_eras: false` the latest version is chosen in each era on its own, so a carried case counts once in each.

The explorer's FDA system is the system of each case's latest version, so a carried case is a FAERS case though first received in AERS; the filter's note and the case window say so and point to the received-date filter for the cases first reported before FAERS.

**Why:** in 2012 FDA carried AERS cases into FAERS under the same case number, with `caseversion` counting on from the AERS versions. Chosen per era, 82,342 such cases were counted twice, once in each era. Notebook `notebooks/faers/02_case_versions` shows they are the same cases.
