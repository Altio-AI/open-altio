---
rule: company-names
line: One company sends under several spellings, such as ELI LILLY AND CO and ELI LILLY AND COMPANY; each spelling is read as its company, so the company counts together.
values:
  mapping: mappings/faers/senders/accepted.csv
  direct_reports: [DIR]
  fda_sender: FDA-CTU
enforced_in:
  - src/open_altio/faers/derive.py
  - src/open_altio/faers/companies.py
  - src/open_altio/faers/insights/cards/empty_fields.py
  - src/open_altio/explorer/filters.py
  - tests/faers/test_company_names.py
  - tests/faers/test_companies.py
  - tests/faers/test_user_rules.py
  - tests/explorer/test_filters.py
  - tests/explorer/test_page.py
---
# One name per company

FAERS names the company that sent a report in `mfr_sndr`, but one company appears under several spellings, such as `ELI LILLY AND CO` and `ELI LILLY AND COMPANY`. We read each spelling as its company's name, so one company counts together. FDA's own text is not changed.

`company_T` on each case is the company its sender spelling names in the reviewed mapping in `mapping`; a sender the mapping does not hold is FDA's sender, trimmed, as written. A sender that reads Not given (rule not-given) has no `company_T`: blank, only saying unknown (`UNKNOWN MANUFACTURER`), or naming no company, such as a regulator, a hospital, an ID number or only generic words (`HERBAL PRODUCTS MANUFACTURER`). A spelling is matched exactly, so it names the same company in either era: a legacy AERS case (2004 to 2012Q3) sent as `GLAXOSMITHKLINE` counts under GlaxoSmithKline, as a FAERS case does. AERS also used spellings and account codes FAERS never did, such as `PFIZERINC` and `AZPRODUW00`; the mapping holds the largest, and one it does not hold stays as written. The raw `mfr_sndr` is never changed, and the duplicate rules compare it, not `company_T`.

A case counts under the sender of its latest version (rule latest-version), as every field of a case is read from that version. When a later version came from another sender, the case counts under the later one: a case Janssen first sent and Johnson and Johnson sent again counts under Johnson and Johnson. Earlier versions keep their own `company_T` in `demo_T`.

A direct report, one whose `rept_cod` is in `direct_reports`, was sent straight to FDA by a patient or a health professional, not by a company, so it has no `company_T` whatever its sender says. FAERS writes `fda_sender`, FDA's own intake, as the sender of most direct reports and leaves the rest blank; legacy direct reports are blank. FDA's intake is no company, so a report of another type sent under `fda_sender` has no `company_T` either: its company reads Not given. The explorer shows the direct reports as one group, Sent straight to FDA, in its Companies chart and Company filter, counted as giving their sender; typing those words or `fda_sender` in the Company filter finds them, and the case window says so with FDA's sender beside. Switched off, `company_T` is every sender as written, a direct report's too.

A spelling counts under the company it names, never under the company that owns it: Genentech is not Roche. A firm's earlier or later name, the name taken at a merger included, is another company, even where FDA's account and the drugs are the same: Biogen Idec is not Biogen, and Aventis is not Sanofi Aventis. FDA's own FAERS name for a firm formed by a merger before FAERS began in 2012 names that firm, not one from before the merger: `DAIICHI` is Daiichi Sankyo, `KYOWA` is Kyowa Kirin, and `SWEDISH ORPHAN` and `BIOVITRUM` are Swedish Orphan Biovitrum, while an AERS name from before the merger, such as `SANKYO PHARMA INC.` or `BIOVITRUM AB.`, stays apart. Ownership and names change over time, so counting a firm across them needs dates.

**Why:** counted as written, one company is split across its spellings, and from 2024Q4 large senders split between a short name and a long legal name. The mapping's README in `mappings/faers/senders/` says how each row was made and reviewed; notebook `notebooks/faers/03_empty_fields` shows how complete a case is by who sent it, and `notebooks/faers/10_label_flags`, its closing section, shows why BIOVITRUM counts as Sobi from 2015Q4.
