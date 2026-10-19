---
rule: deleted-cases
line: FDA lists the cases it has withdrawn but never fixes its old files; we take every listed case out of the counts and keep it in the release.
values:
  eras: [legacy, faers]
settable:
  eras:
    label: Take listed cases out of
    options:
      - [[legacy, faers], Both systems]
      - [[faers], FAERS only]
enforced_in:
  - src/open_altio/faers/derive.py
  - tests/faers/test_derive.py
---
# Cases FDA withdrew taken out

FDA publishes lists of cases it has withdrawn, but never corrects its old files. We take every listed case out of the cases you see, in both of FDA's systems. They stay in the release, so nothing is lost.

FDA publishes lists of the case numbers it deleted: one each quarter from 2019Q1, and a one-off list of every deletion before then. A case whose number is on any list is left out of `case_latest_T` and the child tables joined to it, when its latest version is in one of the eras in `eras`. It stays in `demo_T` and `demo_latest_T`; nothing is deleted from the record. A legacy report with no case number is never matched to a list. `eras: [faers]` takes out only FAERS cases and keeps the legacy AERS cases whose number is listed. Switched off, no listed case is taken out.

**Why:** the listed numbers in the legacy AERS range are AERS cases. AERS and FAERS share one case numbering, and FAERS never gave a new case a number in the AERS range. Of the 6,574 listed numbers in that range, 6,303 are on FDA's whole-history list of deletions from before 2019. DiAna and AEOLUS remove these cases too. Notebook `notebooks/faers/02_case_versions`, section 5, shows the evidence. It also shows the largest batch: from 1 July to 24 October 2011, FDA deleted 86% of the direct reports that reached it electronically. The deleted reports look ordinary, and FDA has not said why it removed them; we follow FDA's lists as they are. With one latest version per case across eras (`rules/latest-version.md`), taking out the listed legacy cases too removes 6,074 more cases than taking out FAERS cases alone.
