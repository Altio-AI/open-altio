# FAERS sender names as company names

For anyone counting FAERS reports by the company that sent them.

FAERS names the sender of each company report in `mfr_sndr`, but one company appears under several spellings: `ELI LILLY AND CO` and `ELI LILLY AND COMPANY`, `MERCK SHARP + DOHME LLC` beside `MERCK SHARP AND DOHME`, and from 2024Q4 long legal names beside short ones. Counted as written, one company is split into several. `accepted.csv` groups the spellings of one company under one name: 1,113 spellings in 475 companies, which together sent 99.1% of the FAERS and 98.2% of the AERS company reports kept in the 2026Q2 release. The release build reads it into `company_T` (`rules/company-names.md`) for AERS and FAERS cases alike: a spelling is matched exactly, so it names the same company in either era. The raw `mfr_sndr` is never changed.

## The file

| Column | What |
|---|---|
| `fda_value` | The sender exactly as FAERS wrote it, case and punctuation included |
| `company` | The company name it is counted under |
| `how` | `rule` (the same name once case, punctuation and legal-form words are set aside), `proposed` (a judgement, written in `evidence`, accepted at review) or `check` (kept as its own company, with the reason) |
| `evidence` | Why the spelling belongs to that company |
| `cases` | Cases with that spelling in the 2026Q2 release, at review: the latest version of each case, AERS and FAERS together |

## What counts as one company

Spellings of the same company's own name only. A company is never counted under its owner: Genentech is not Roche, Celgene is not Bristol Myers Squibb, Sandoz is not Novartis, and EMD Serono is not Merck KGaA. A renamed company is never counted under its new name, nor a new name under the old one: a firm's earlier or later name, the name taken at a merger included, is another company, even where FDA's account and the drugs are the same. Luitpold is not American Regent, Biogen Idec is not Biogen, Aventis and Sanofi are not Sanofi Aventis, and `BIOVITRUM AB.` in AERS is not Swedish Orphan Biovitrum. FDA's own FAERS name for a firm formed by a merger before FAERS began in 2012 is that firm under a short name, not a firm from before the merger: `DAIICHI` is Daiichi Sankyo, `KYOWA` is Kyowa Kirin, and `SWEDISH ORPHAN` and `BIOVITRUM` are Swedish Orphan Biovitrum, as their drugs show, while AERS names from before the merger (`SANKYO PHARMA INC.`) stay apart. Ownership and names change over time, so counting a firm across them needs dates; it is a later, separate step. Affiliates that carry the company's own name in another country or legal form (`NOVARTIS PHARMACEUTICALS CORP` and `NOVARTIS PHARMA AG`) are one company. The 33 `check` rows are names kept apart for these reasons, or because they may be two firms.

A sender name that only says unknown (`Unknown Manufacturer`, `UNKNOWN`) is not a company: it reads Not given (`rules/not-given.md`) and is not in this file. `GENERIC` is not such a word: `Generics [UK] Ltd` is a company.

## How it was made

- The most common FAERS spellings, which cover 99% of company reports (391 of the top 392; the other is `Unknown Manufacturer`), plus 225 smaller spellings that clearly belong to one of their companies.
- A fixed rule first: upper case, punctuation to spaces, legal-form words dropped from the end (`INC`, `LLC`, `CO`, `AND COMPANY`, `CORP`, `LTD`, `PLC`, `AG`, `GMBH`, `SA`, `PHARMACEUTICALS` and the like). 484 rows.
- A model proposed the rest (typos, word order, a parent's legal name such as `TEVA PHARMACEUTICALS INDUSTRIES LTD.`), each with its reason. 106 rows.
- The rename rule above, applied to every row: 12 spellings of a firm's earlier or later name, and Avadel CNS's parent, moved to companies of their own.
- FDA's FAERS names of three firms formed by a merger before 2012 (`DAIICHI`, `KYOWA`, `SWEDISH ORPHAN` and `BIOVITRUM`) then moved to those firms, with the merger's year and the firm's drugs in `evidence`.
- AERS spellings by the same method, largest first: the 350 most common AERS spellings the table did not yet hold, then smaller AERS spellings of companies already in it. Each is a spelling of one company's own name (`PFIZERINC`, `BIOGEN IDEC INC.`), or an AERS account code only where the drugs behind it leave no doubt, with those drugs in `evidence` (`AZPRODUW00` is AstraZeneca: Seroquel, Nexium, Crestor). Left out on purpose: service firms (`PPD PHARMACOVIGILANCE`), codes the drugs do not settle (`HPD PHARMACOVIGILANCE`, `GIMD`), generic words (`GLOBAL DEVELOPMENT`) and names of two firms. 497 rows: 324 `rule`, 165 `proposed`, 8 `check`.
- Notebook `notebooks/faers/03_empty_fields` shows why company names matter: how complete a case is depends heavily on who sent it.

## Review

Reviewed by a maintainer: every `rule` and `proposed` row accepted, every `check` row kept apart, and `SANOFI PASTEUR` (Sanofi's vaccine arm under its own name) moved from proposed to check. A later change to any row is its own reviewed change with its evidence.
