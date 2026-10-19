# Case versions across AERS and FAERS

For anyone counting FAERS cases.

This page covers:

- how a case's versions reach FDA's files;
- five record-keeping faults Open Altio found in them, and what it does about each;
- the legacy cases on FDA's deleted lists.

The charts and every number are in the notebook `notebooks/faers/02_case_versions`. The methods page shows the evidence for each step on the release itself. Numbers here are from the 2026Q2 release.

## How versions reach the files

- **New versions.** A case gets a new version each time its sender adds information.
    - Legacy AERS (2004Q1 to 2012Q3) gave each version its own report number (ISR) under a CASE number.
    - FAERS numbers versions 1, 2, 3 under the case number (`caseid`).
- **One version per quarter.** Each quarterly file holds one version per case: the newest FDA had at the quarter's end. If versions 1 and 2 arrive in the same quarter, only version 2 is ever published. Of the versions FDA filed for cases first received from 2013, 23% never reached a published file for this reason.
- **Timing.** Most published follow-ups come 1 to 12 months after the version before. Only 2% come within 30 days.
- **Published twice.** 4,694 legacy ISRs and 707 FAERS primaryids were published in two quarters. The later record is kept, as FDA advises.

## What the pipeline does about it

| Finding | What the pipeline does | Rule |
|---|---|---|
| FDA carried 82,342 AERS cases into FAERS in 2012 under the same case number, with versions counting on. Choosing a latest version within each era counted each of them twice. The two versions share the manufacturer's case number in 99.9% of pairs, and FAERS's first-receipt date is the AERS one in 99.1%. | One latest version per case across both eras. A carried case keeps its FAERS version. | [latest-version](https://github.com/Altio-AI/open-altio/blob/main/rules/latest-version.md) |
| Legacy AERS writes countries as names (`UNITED STATES`), FAERS as ISO codes (`US`), so no duplicate group could span the eras and a country filter found one era only. | `country_T` reads legacy names as codes through a reviewed list of all 208 names. | [legacy-country](https://github.com/Altio-AI/open-altio/blob/main/rules/legacy-country.md), [`mappings/faers/countries/`](https://github.com/Altio-AI/open-altio/tree/main/mappings/faers/countries) |
| Three 2011 DRUG lines hold two records each with no line break between them, so the second drug was lost without a trace. | The header sets the columns. A line of whole records is split back into them, and any other long line is kept as read and recorded. | [overlong-lines](https://github.com/Altio-AI/open-altio/blob/main/rules/overlong-lines.md) |
| A 2012Q1 DEMO line has a `$` inside `mfr_num`, so one case's later values sit one column to the right. | Kept as read, and recorded in the manifest with the text past the last column. | [overlong-lines](https://github.com/Altio-AI/open-altio/blob/main/rules/overlong-lines.md) |
| Legacy AERS writes reaction terms in capitals (`DRUG INEFFECTIVE`), FAERS in MedDRA's mixed case (`Drug ineffective`), so reaction sets almost never matched across eras: even with countries as codes, only 11 duplicate groups spanned them. | `pt_norm_T` is `pt` in capitals and the duplicate rule compares it: 950 groups now span the eras, and 941 more cases are set aside. | [reaction-term-case](https://github.com/Altio-AI/open-altio/blob/main/rules/reaction-term-case.md) |

## Legacy cases on FDA's deleted lists

FDA's deleted-case lists name 6,074 legacy AERS cases that a FAERS-only reading of the lists would keep.

- **They are AERS cases.** The listed numbers in the AERS range are AERS cases, because AERS and FAERS share one case numbering. 6,303 of the 6,574 listed numbers in that range are on FDA's whole-history list.
- **Everyone removes them.** DiAna and AEOLUS remove them too, and so does Open Altio. Cases on the lists leave the case set in both eras, and stay in `demo_T` and `demo_latest_T` ([deleted-cases](https://github.com/Altio-AI/open-altio/blob/main/rules/deleted-cases.md)).

## The 2011 batch of deleted direct reports

The share of cases on a deleted list peaks in 2011Q3: 2.1% of the cases whose latest version is in that file, the highest of the 90 quarters, and 38% of its direct reports.

- **Electronic direct reports.** Direct reports flagged `e_sub = 'Y'` (sent to FDA electronically) first appear on 1 July 2011. Of the 3,593 received from then to 24 October 2011, 3,087 (86%) are on a list. Of about 6,900 received after, 7 are.
- **Paper direct reports** received in the same weeks: 2 of 5,205.
- **They look ordinary.** The deleted reports are not copies, and none lacks a drug or a reaction.
- **Effect on signals.** Removing them switches off about as many signals as removing a random batch of the same size.
- **Why is unknown.** FDA has not said why it deleted them. The pipeline follows its lists as they are.
