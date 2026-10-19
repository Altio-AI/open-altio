# FDA's reporter codes as E2B(R3) reporter qualifications

For anyone checking how a case's reporter type is read across the years.

FDA writes who reported a case as a code in `occp_cod`. Its README lists five: MD physician, PH pharmacist, OT other health-professional, LW lawyer, CN consumer. From 2020 FDA writes HP where it used to write OT, and a few older cases say RN. `accepted.csv` reads each code as the reporter's qualification in ICH E2B(R3) (C.2.r.4, code list 6: 1 Physician, 2 Pharmacist, 3 Other health professional, 4 Lawyer, 5 Consumer or other non health professional), read by the release build into `reporter_type_T` (`rules/reporter-type.md`). The raw `occp_cod` is never changed, and a code the file does not hold gives an empty type.

## The file

| Column | What |
|---|---|
| `fda_value` | The code exactly as FDA writes it |
| `e2b_code` | The E2B(R3) reporter qualification it is read as |
| `evidence` | Why: FDA's README, or the pattern in the data for a code FDA does not list |

## Review

Reviewed row by row. The five codes in FDA's README map one to one onto the E2B(R3) list. HP and RN are not in FDA's README: HP is read as other health professional because it takes OT's place in 2020 (notebook `notebooks/faers/08_dates_and_codes`: OT about 20% of FAERS cases each year to 2019 and none from 2020, HP 22% from 2020, MD and PH flat), and RN, a registered nurse, is a health professional who is neither physician nor pharmacist. A later change to any row is its own reviewed change with its evidence.
