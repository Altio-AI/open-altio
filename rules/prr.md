---
rule: prr
line: Compares the share of an ingredient's cases that report a reaction with the same share among every other case; a PRR of 3 means three times as large a share.
values:
  presets:
    - id: evans-2001
      label: PRR at least 2, chi-square at least 4, at least 3 cases
      source: Evans, Waller and Davis 2001
      default: true
      when:
        - {column: prr, at_least: 2}
        - {column: chi_square_yates, at_least: 4}
        - {column: cases, at_least: 3}
always_on: true
why_locked: The statistics take no case out of the release; the thresholds you read them against are set on the Statistics tab.
enforced_in:
  - src/open_altio/stats/disproportionality.py
  - tests/stats/test_disproportionality.py
  - tests/stats/test_screen.py
---
# PRR: share of an ingredient's cases

Of all the cases that name this ingredient, the share that report this reaction, against the same share among the cases that do not name it. A PRR of 3 means the reaction makes up three times as large a part of the ingredient's cases as of everyone else's. The chi-square says how far the table is from what chance alone would give.

**Formula**, on the table of cases (`statistics-cases` says which cases):

|  | the reaction | any other reaction |
|---|---|---|
| the ingredient | a | b |
| any other ingredient | c | d |

    PRR = (a / (a + b)) / (c / (c + d))
    chi-square = N (ad - bc)^2 / ((a + b)(c + d)(a + c)(b + d)),   N = a + b + c + d
    chi-square with Yates' correction = N (max(|ad - bc| - N/2, 0))^2 / ((a + b)(c + d)(a + c)(b + d))

Both chi-squares are given, Pearson's (`chi_square`) and Yates' (`chi_square_yates`): one degree of freedom, the same as summing (O - E)^2 / E over the four cells without the correction and (|O - E| - 0.5)^2 / E with it.

**When it is empty:** PRR is left empty when c is 0 (no other ingredient's case reports the reaction, so the ratio has no comparator), never shown as infinity. The chi-squares are empty when a row or a column of the table is empty.

**Presets** (`presets`; change any number on the Statistics tab, or set your own):
- **Evans 2001** (the default): PRR at least 2, chi-square at least 4 and at least 3 cases, the criteria Evans, Waller and Davis (2001) proposed for the UK Yellow Card scheme. The paper states the three numbers but not which chi-square; later papers read it both ways. The preset reads Yates' corrected chi-square, the stricter of the two, named by the column of its second condition: `chi_square` there would read Pearson's instead.

**Source:** Evans SJW, Waller PC, Davis S. Use of proportional reporting ratios (PRRs) for signal generation from spontaneous adverse drug reaction reports. Pharmacoepidemiology and Drug Safety 2001;10:483-486. The table's layout: CIOMS Working Group VIII, Practical aspects of signal detection in pharmacovigilance (2010).

**A statistic of disproportionate reporting is not a signal and not evidence of cause.** It says which ingredient and reaction pairs are reported together more often than the rest of the release would lead one to expect; people judge what that means. Code: `src/open_altio/stats/disproportionality.py`.
