"""Small, fake FDA quarterly files, faithful to FDA's real layouts.

`write_input(folder, as_zips=True)` writes six quarters into `folder` the way
FDA publishes them, and returns the folder. The quarters cover both eras and
each layout quirk the real files have:

- 2012q2  AERS, the 2004Q1 header (no REPORTER_COUNTRY), CRLF, every data row
          ending in a stray `$`
- 2012q3  AERS, the 2012Q3 header (REPORTER_COUNTRY), a DRUG file in Latin-1
- 2012q4  FAERS first quarter: lower-case names, `gndr_cod`, a header field
          written ` rept_dt`, `lot_nbr`, `outc_code`, a BOM on DRUG, no prod_ai
- 2018q1  FAERS with the demographics file named DEMO18Q1_new.txt, LF endings
- 2019q1  FAERS with `deleted/ADR19Q1DeletedCases.txt` and FDA's one-off
          whole-history list `deleted/AllDeletedCases.txt`
- 2026q2  FAERS today: `ASCII/` folder, `Deleted/DELETE26Q2.txt` opening with
          a lone space, LF demographics and CRLF drugs

The reports (STORY) carry several case versions, a re-published primaryid,
cases carried over from AERS into FAERS (one of them later deleted), legacy
country names and reaction terms as AERS wrote them, two DRUG lines published glued together and
a DEMO line with a stray `$` inside a value (both as in FDA's 2011 and 2012Q1
files), deleted cases, partial and impossible dates, ages in every unit and weights
in pounds, kilograms and grams, and (DUPLICATES) probable duplicates across
cases by the AEOLUS rule, within and across eras. Drug roles, outcomes,
reporter types (codes FDA does not list among them), senders, indications and reaction spellings
vary on a few latest versions so the explorer's filters have something to narrow, and a
rechallenge of D appears in, before and after the years FDA filled it in. The column names below
restate FDA's headers independently of the pipeline's own schema, so the tests check the
pipeline against FDA's layout and not against itself.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_altio import rulebook

# ---------------------------------------------------------------- headers
# FDA's real header lines per layout (copied from the published files).
AERS_2004 = {
    "demo": (
        "ISR$CASE$I_F_COD$FOLL_SEQ$IMAGE$EVENT_DT$MFR_DT$FDA_DT$REPT_COD$MFR_NUM$MFR_SNDR$AGE"
        "$AGE_COD$GNDR_COD$E_SUB$WT$WT_COD$REPT_DT$OCCP_COD$DEATH_DT$TO_MFR$CONFID"
    ),
    "drug": (
        "ISR$DRUG_SEQ$ROLE_COD$DRUGNAME$VAL_VBM$ROUTE$DOSE_VBM$DECHAL$RECHAL$LOT_NUM$EXP_DT$NDA_NUM"
    ),
    "reac": "ISR$PT",
    "outc": "ISR$OUTC_COD",
    "rpsr": "ISR$RPSR_COD",
    "ther": "ISR$DRUG_SEQ$START_DT$END_DT$DUR$DUR_COD",
    "indi": "ISR$DRUG_SEQ$INDI_PT",
}
AERS_2012 = {**AERS_2004, "demo": AERS_2004["demo"] + "$REPORTER_COUNTRY"}
FAERS_2012Q4 = {
    "demo": (
        "primaryid$caseid$caseversion$i_f_code$event_dt$mfr_dt$init_fda_dt$fda_dt$rept_cod$mfr_num"
        "$mfr_sndr$age$age_cod$gndr_cod$e_sub$wt$wt_cod$ rept_dt$to_mfr$occp_cod$reporter_country"
        "$occr_country"
    ),
    "drug": (
        "primaryid$caseid$drug_seq$role_cod$drugname$val_vbm$route$dose_vbm$cum_dose_chr"
        "$cum_dose_unit$dechal$rechal$lot_nbr$exp_dt$nda_num$dose_amt$dose_unit$dose_form$dose_freq"
    ),
    "reac": "primaryid$caseid$pt",
    "outc": "primaryid$caseid$outc_code",
    "rpsr": "primaryid$caseid$rpsr_cod",
    "ther": "primaryid$caseid$dsg_drug_seq$start_dt$end_dt$dur$dur_cod",
    "indi": "primaryid$caseid$indi_drug_seq$indi_pt",
}
FAERS_NOW = {
    "demo": (
        "primaryid$caseid$caseversion$i_f_code$event_dt$mfr_dt$init_fda_dt$fda_dt$rept_cod$auth_num"
        "$mfr_num$mfr_sndr$lit_ref$age$age_cod$age_grp$sex$e_sub$wt$wt_cod$rept_dt$to_mfr$occp_cod"
        "$reporter_country$occr_country"
    ),
    "drug": (
        "primaryid$caseid$drug_seq$role_cod$drugname$prod_ai$val_vbm$route$dose_vbm$cum_dose_chr"
        "$cum_dose_unit$dechal$rechal$lot_num$exp_dt$nda_num$dose_amt$dose_unit$dose_form$dose_freq"
    ),
    "reac": "primaryid$caseid$pt$drug_rec_act",
    "outc": "primaryid$caseid$outc_cod",
    "rpsr": "primaryid$caseid$rpsr_cod",
    "ther": "primaryid$caseid$dsg_drug_seq$start_dt$end_dt$dur$dur_cod",
    "indi": "primaryid$caseid$indi_drug_seq$indi_pt",
}

# The documented unification (src/open_altio/faers/README.md), restated as the oracle:
# header (trimmed, lower-cased) -> release column, per table.
EXPECTED_RENAMES = {
    "*": {"isr": "primaryid", "case": "caseid"},
    "demo": {"i_f_cod": "i_f_code", "gndr_cod": "sex"},
    "drug": {"lot_nbr": "lot_num"},
    "outc": {"outc_code": "outc_cod"},
    "ther": {"drug_seq": "dsg_drug_seq"},
    "indi": {"drug_seq": "indi_drug_seq"},
}


def release_column(table: str, header: str) -> str:
    name = header.replace("﻿", "").strip().lower()
    return EXPECTED_RENAMES.get(table, {}).get(name) or EXPECTED_RENAMES["*"].get(name, name)


# ---------------------------------------------------------------- reports
@dataclass
class Drug:
    name: str
    prod_ai: str = ""
    role: str = "PS"
    indication: str = "Pain"  # "": the report gives no indication for the drug
    rechal: str = "U"
    start_dt: str | None = None  # its therapy start as FDA writes it; None: the event's month
    end_dt: str = ""


@dataclass
class Report:
    quarter: str
    primaryid: str
    caseid: str  # '' = no CASE (legacy only)
    fda_dt: str
    caseversion: str = "1"
    init_fda_dt: str = ""
    event_dt: str = ""
    age: str = ""
    age_cod: str = ""
    age_grp: str = ""
    sex: str = "F"
    wt: str = ""
    wt_cod: str = ""
    country: str = "US"  # reporter_country, and occr_country unless that is given
    occr_country: str | None = None
    drugs: list[Drug] = field(default_factory=lambda: [Drug("ASPIRIN", "ASPIRIN")])
    reacs: list[str] = field(default_factory=lambda: ["Headache"])
    rec_acts: list[str] = field(default_factory=list)  # drug_rec_act on each reaction row, in order
    outcomes: list[str] = field(default_factory=lambda: ["OT"])
    occp_cod: str = "MD"  # reporter type
    sender: str = "ACME PHARMA, INC."  # mfr_sndr
    rept_cod: str = "EXP"  # report type; DIR: sent straight to FDA
    mfr_num: str = ""  # default US-ACME-<caseid>

    def fields(self, table: str) -> list[dict[str, str]]:
        """This report's rows of one table, keyed by release column name."""
        key = {"primaryid": self.primaryid, "caseid": self.caseid}
        if table == "demo":
            return [
                {
                    **key,
                    "caseversion": self.caseversion,
                    "i_f_code": "F" if self.caseversion != "1" else "I",
                    "foll_seq": "",
                    "image": f"{self.primaryid}-7",
                    "event_dt": self.event_dt,
                    "mfr_dt": self.fda_dt,
                    "init_fda_dt": self.init_fda_dt or self.fda_dt,
                    "fda_dt": self.fda_dt,
                    "rept_cod": self.rept_cod,
                    "auth_num": "",
                    "mfr_num": self.mfr_num or f"US-ACME-{self.caseid}",
                    "mfr_sndr": self.sender,
                    "lit_ref": "",
                    "age": self.age,
                    "age_cod": self.age_cod,
                    "age_grp": self.age_grp,
                    "sex": self.sex,
                    "e_sub": "Y",
                    "wt": self.wt,
                    "wt_cod": self.wt_cod,
                    "rept_dt": self.fda_dt,
                    "to_mfr": "",
                    "occp_cod": self.occp_cod,
                    "death_dt": "",
                    "confid": "",
                    # AERS, which ended with 2012Q3, wrote the country's name
                    "reporter_country": (
                        LEGACY_COUNTRY.get(self.country, self.country)
                        if self.quarter < "2012q4"
                        else self.country
                    ),
                    "occr_country": (
                        self.country if self.occr_country is None else self.occr_country
                    ),
                }
            ]
        if table == "drug":
            return [
                {
                    **key,
                    "drug_seq": str(i),
                    "role_cod": d.role,
                    "drugname": d.name,
                    "prod_ai": d.prod_ai,
                    "val_vbm": "1",
                    "route": "ORAL",
                    "dose_vbm": "100 MG, QD",
                    "cum_dose_chr": "",
                    "cum_dose_unit": "",
                    "dechal": "D",
                    "rechal": d.rechal,
                    "lot_num": f"L{i}",
                    "exp_dt": "",
                    "nda_num": "",
                    "dose_amt": "100",
                    "dose_unit": "MG",
                    "dose_form": "TABLET",
                    "dose_freq": "QD",
                }
                for i, d in enumerate(self.drugs, 1)
            ]
        if table == "reac":
            return [
                {**key, "pt": self._term(pt), "drug_rec_act": (self.rec_acts[i : i + 1] or [""])[0]}
                for i, pt in enumerate(self.reacs)
            ]
        if table == "outc":
            return [{**key, "outc_cod": o} for o in self.outcomes]
        if table == "rpsr":
            return [{**key, "rpsr_cod": "HP"}]
        if table == "ther":
            return [
                {
                    **key,
                    "dsg_drug_seq": str(i),
                    "start_dt": self.event_dt[:6] if d.start_dt is None else d.start_dt,
                    "end_dt": d.end_dt,
                    "dur": "",
                    "dur_cod": "",
                }
                for i, d in enumerate(self.drugs, 1)
            ]
        if table == "indi":
            return [
                {**key, "indi_drug_seq": str(i), "indi_pt": self._term(d.indication)}
                for i, d in enumerate(self.drugs, 1)
                if d.indication
            ]
        raise KeyError(table)

    def _term(self, text: str) -> str:
        """A MedDRA term as the era writes it: AERS, which ended with 2012Q3, in capitals
        (ARRHYTHMIA); FAERS as MedDRA spells it."""
        return text.upper() if self.quarter < "2012q4" else text


# Legacy AERS writes the reporter's country in full (UNITED STATES); FAERS
# writes the ISO 3166-1 code (US). A report's `country` is the code; legacy
# files carry the name.
LEGACY_COUNTRY = {"US": "UNITED STATES", "CA": "CANADA"}

# Two FAERS spellings of one company in the reviewed sender mapping (rules/company-names.md):
# FAERS cases sent under either count under one company; a legacy case keeps its spelling.
LILLY = ("ELI LILLY AND CO", "ELI LILLY AND COMPANY")

# The reports are a table, one to a line or two, so the formatter leaves them as written.
R = Report
# fmt: off
STORY: list[Report] = [
    # AERS 2012q2: case 5100001 first version; a partial event year; a report with no CASE.
    R("2012q2", "4100001", "5100001", "20120415", caseversion="", event_dt="20120301",
      age="45", age_cod="YR", wt="154", wt_cod="LBS"),
    R("2012q2", "4100002", "5100002", "20120420", caseversion="", event_dt="2012",
      age="18", age_cod="MON", wt="70", wt_cod="KG", drugs=[Drug("ASPIRIN.", "")],
      sender=LILLY[0]),
    R("2012q2", "4100003", "", "20120501", caseversion="",
      drugs=[Drug("ASPIRIN", "ASPIRIN", rechal="D")]),
    # AERS 2012q3: a follow-up of 5100001; two versions of 5100005 on the same day; a legacy
    # case whose number is on a deleted list (taken out, as FAERS cases are).
    R("2012q3", "4100004", "5100001", "20120720", caseversion="", age="6", age_cod="DEC",
      wt="3500", wt_cod="GMS", drugs=[Drug("CAFÉ  TABLETS", "")]),
    R("2012q3", "4100005", "5100005", "20120801", caseversion="", event_dt="201207"),
    R("2012q3", "4100006", "5100005", "20120801", caseversion="",
      drugs=[Drug(" ibuprofen ", "")], occp_cod="LW"),
    R("2012q3", "4100007", "5100007", "20120805", caseversion=""),
    # FAERS 2012q4.
    R("2012q4", "90010011", "9001001", "20121120", event_dt="20121001", age="30", age_cod="YR",
      wt="80", wt_cod="KG"),
    R("2012q4", "90020021", "9002002", "20121125", age="104.36", age_cod="WK", sender=LILLY[0],
      drugs=[Drug("ASPIRIN", "ASPIRIN", rechal="D")]),
    # FAERS 2018q1: version 2 of 9001001; an impossible day.
    R("2018q1", "90010012", "9001001", "20180210", caseversion="2", init_fda_dt="20121120",
      wt="81", wt_cod="KGS"),
    R("2018q1", "90030031", "9003003", "20180115", event_dt="20180230", age="8766", age_cod="HR"),
    # FAERS 2019q1: a report sent straight to FDA, whose sender FAERS writes as FDA's intake.
    R("2019q1", "90040043", "9004004", "20190301", caseversion="3",
      drugs=[Drug("BAYER LOW DOSE", "ASPIRIN")], rept_cod="DIR", sender="FDA-CTU"),
    R("2019q1", "90050051", "9005005", "20190115", reacs=["Nausea"]),
    R("2019q1", "90060061", "9006006", "20190301", caseversion="2",
      drugs=[Drug("IBUPROFEN", "IBUPROFEN", role="SS"), Drug("ASPIRIN", "ASPIRIN", role="I")],
      occp_cod="OT"),
    R("2019q1", "90060069", "9006006", "20190201", caseversion="2"),
    R("2019q1", "90070071", "9007007", "20190110", rec_acts=["Head pain"]),
    R("2019q1", "90070079", "9007007", "20190110", reacs=["Hepatic enzyme INCREASED"],
      occp_cod="SALES"),
    R("2019q1", "90080081", "9008008", "20190120"),
    R("2019q1", "90090091", "9009009", "20190121"),
    R("2019q1", "90030032", "9003003", "20190105", caseversion="2", init_fda_dt="20180115",
      age="730.5", age_cod="DY", occp_cod="RN"),
    # drug_rec_act writes an apostrophe as ^
    R("2019q1", "90130131", "9013013", "20190320", outcomes=["DE"], occp_cod="HP",
      rec_acts=["Parkinson^s disease"]),
    # FAERS 2026q2: a lower version arriving late; primaryid 90050051 published again;
    # a case FDA deletes this quarter; values that are not numbers or have an unknown unit.
    R("2026q2", "90040042", "9004004", "20260501", caseversion="2"),
    R("2026q2", "90050051", "9005005", "20190115", reacs=["Vomiting"], outcomes=["HO", "OT"],
      drugs=[Drug("ASPIRIN", "ASPIRIN"),
             Drug("OMEPRAZOLE", "OMEPRAZOLE", role="C", indication="Dyspepsia")]),
    R("2026q2", "90100101", "9010010", "20260510",
      drugs=[Drug("ASPIRIN", "ASPIRIN", rechal="D")]),
    R("2026q2", "91100111", "9110011", "20260511", age="4O", age_cod="YR", wt="154", wt_cod="LBS",
      occp_cod="CN", sender="BETA LABS LTD"),
    R("2026q2", "91200121", "9120012", "20260512", age="40", age_cod="XX", occp_cod="",
      sender=LILLY[1]),
    # values that read Not given (rule not-given): a sex, an event country and a sender that say
    # unknown, and a filler age and weight; the reporter's country stands in for the event's.
    R("2026q2", "91300131", "9130013", "20260513", sex="NS", country="GB",
      occr_country="COUNTRY NOT SPECIFIED", age="999", age_cod="YR", wt="0", wt_cod="KG",
      sender="UNKNOWN MANUFACTURER"),
    # same version as 90130131, a later quarter but an earlier fda_dt: fda_dt decides first
    R("2026q2", "90130132", "9013013", "20190310"),
]
# fmt: on

# Probable duplicates across cases (AEOLUS): same event date, age, age unit, sex,
# country (occurrence, else reporter), normalised drug set and reaction set.
_A: dict[str, Any] = dict(
    event_dt="20190101",
    age="52",
    age_cod="YR",
    sex="F",
    country="US",
    reacs=["Haemorrhage", "Nausea"],
)
_B: dict[str, Any] = dict(
    event_dt="20181120",
    age="67",
    age_cod="YR",
    sex="M",
    country="GB",
    drugs=[Drug("METFORMIN", "METFORMIN")],
    reacs=["Lactic acidosis"],
)
_C: dict[str, Any] = dict(
    event_dt="20120601",
    age="70",
    age_cod="YR",
    sex="M",
    drugs=[Drug("DIGOXIN", "")],
    reacs=["Arrhythmia"],
)
# fmt: off
DUPLICATES: list[Report] = [
    # A, within FAERS: the same drug set however spelled, ordered or repeated; the
    # earlier received (9020020) is kept.
    R("2019q1", "90200201", "9020020", "20190210",
      drugs=[Drug("WARFARIN", ""), Drug("aspirin.", "")], **_A),
    R("2026q2", "90210211", "9021021", "20260515",
      drugs=[Drug("Aspirin", ""), Drug(" warfarin ", ""), Drug("WARFARIN.", "", indication="")],
      **_A),
    # A near-duplicate of A received earlier, but with no sex: never flagged.
    R("2019q1", "90260261", "9026026", "20190101",
      drugs=[Drug("WARFARIN", ""), Drug("ASPIRIN", "")], **{**_A, "sex": ""}),
    # B, a tie on received date (init_fda_dt) broken by the lower caseid, although
    # the lower caseid arrived in a later file.
    R("2019q1", "90230231", "9023023", "20190305", **_B),
    R("2026q2", "90220221", "9022022", "20260520", init_fda_dt="20190305", **_B),
    # C, across eras: legacy AERS has only a reporter country; FAERS's occurrence
    # country is used where given, the reporter country where not. Legacy is kept.
    R("2012q3", "4100008", "5100008", "20120810", caseversion="", country="CA", **_C),
    R("2012q4", "90240241", "9024024", "20121130", country="CA", occr_country="", **_C),
    R("2018q1", "90250251", "9025025", "20180120", country="US", occr_country="CA", **_C),
    # C again in the 2004Q1 layout, which has no country at all: never flagged.
    R("2012q2", "4100009", "5100009", "20120505", caseversion="", country="CA", **_C),
]
# fmt: on
STORY += DUPLICATES

# The duplicate rules of notebooks/faers/04_duplicates.ipynb, in a story of their own
# (DUP_STORY), built into a second fake release (the `dup_rel` fixture) so the main one
# stays small. FAERS only, quarters DUP_QUARTERS. Each case has no event
# date and its own manufacturer number unless said, so it matches nothing
# by default.
PADDED_SIZE = rulebook.value("dup-padded-event-dates", "min_group_size")
MAX_AGE_GAP = rulebook.value("dup-manufacturer-number", "max_age_gap_years")


def _sender(senders: tuple[str, ...], i: int) -> dict[str, Any]:
    return {"sender": senders[i % len(senders)]} if senders else {}


def _padded_group(
    first_caseid: int, size: int, event_dt: str, drug: str, senders: tuple[str, ...] = ()
) -> list[Report]:
    """`size` cases agreeing on every AEOLUS field, the shared event date
    `event_dt`, received a day apart; sent by ACME unless `senders` names
    the sender of each case in turn."""
    return [
        R(
            "2019q1",
            f"{first_caseid + i}1",
            str(first_caseid + i),
            f"201902{10 + i:02d}",
            event_dt=event_dt,
            age="70",
            age_cod="YR",
            sex="F",
            country="US",
            drugs=[Drug(drug, drug)],
            reacs=["Neoplasm"],
            **_sender(senders, i),
        )
        for i in range(size)
    ]


_CHAIN: dict[str, Any] = dict(
    age="60",
    age_cod="YR",
    sex="M",
    country="US",
    drugs=[Drug("LISINOPRIL", "LISINOPRIL")],
    reacs=["Cough"],
)
# fmt: off
DUP_STORY: list[Report] = [
    # N1, the same number from the same sender, written in another letter case: one group,
    # the later received shown, dated by the first.
    R("2019q1", "77010011", "7701001", "20190110", mfr_num="US-ACME-N1", age="50", age_cod="YR"),
    R("2026q2", "77010021", "7701002", "20260510", mfr_num="us-acme-n1", sender="Acme Pharma, Inc.",
      age="51", age_cod="YR"),
    # N1's number from another sender: not the same case.
    R("2026q2", "77060011", "7706001", "20260511", mfr_num="US-ACME-N1", sender="BETA LABS LTD"),
    # N2, sex guard: one female, one male.
    R("2019q1", "77020011", "7702001", "20190111", mfr_num="US-ACME-N2", sex="F"),
    R("2026q2", "77020021", "7702002", "20260512", mfr_num="US-ACME-N2", sex="M"),
    # N3, a sex other than M or F counts as empty.
    R("2019q1", "77030011", "7703001", "20190112", mfr_num="US-ACME-N3", sex="F"),
    R("2026q2", "77030021", "7703002", "20260513", mfr_num="US-ACME-N3", sex="UNK"),
    # N4, age guard: one year more than the gap allowed.
    R("2019q1", "77040011", "7704001", "20190113", mfr_num="US-ACME-N4", age="40", age_cod="YR"),
    R("2026q2", "77040021", "7704002", "20260514", mfr_num="US-ACME-N4",
      age=str(40 + MAX_AGE_GAP + 1), age_cod="YR"),
    # N5, ages compared in years by their units; an empty age never triggers the guard.
    R("2019q1", "77050011", "7705001", "20190114", mfr_num="US-ACME-N5", age="30", age_cod="YR"),
    R("2019q1", "77050021", "7705002", "20190115", mfr_num="US-ACME-N5", age="360", age_cod="MON"),
    R("2026q2", "77050031", "7705003", "20260515", mfr_num="US-ACME-N5"),
    # P1, one copy without its country code joins the coded number.
    R("2019q1", "77110011", "7711001", "20190116", mfr_num="ACME-P1"),
    R("2026q2", "77110021", "7711002", "20260516", mfr_num="US-ACME-P1"),
    # P2, a number without its code written by the sender with two codes: nothing matches.
    R("2019q1", "77120011", "7712001", "20190117", mfr_num="ACME-P2"),
    R("2026q2", "77120021", "7712002", "20260517", mfr_num="US-ACME-P2"),
    R("2026q2", "77120031", "7712003", "20260518", mfr_num="CA-ACME-P2"),
    # CH, a chain: 7721001 and 7721002 by the AEOLUS rule, 7721002 and 7721003 by the number.
    R("2019q1", "77210011", "7721001", "20190305", event_dt="20190301", **_CHAIN),
    R("2019q1", "77210021", "7721002", "20190320", event_dt="20190301", mfr_num="US-ACME-CH",
      **_CHAIN),
    R("2026q2", "77210031", "7721003", "20260501", mfr_num="US-ACME-CH", **_CHAIN),
    # S, reports with no usable drug or reaction, with and without a serious outcome; one with
    # FAERS's text for no country, one with the code of a country that no longer exists.
    R("2026q2", "77310011", "7731001", "20260520", reacs=["No adverse event"], outcomes=["DE"]),
    R("2026q2", "77310021", "7731002", "20260521", reacs=["No adverse event"], outcomes=[],
      country="COUNTRY NOT SPECIFIED", occr_country=""),
    R("2026q2", "77310031", "7731003", "20260522", drugs=[Drug("UNKNOWN", "")], reacs=["Rash"],
      outcomes=["HO"]),
    R("2026q2", "77310041", "7731004", "20260523", reacs=["Rash"], outcomes=["DE"], country="YU"),
]
# fmt: on
# PD, padded event dates: one case fewer than the guard's size on 1 January (a group);
# the guard's size on 1 January, on a year alone and on a month alone, all from one
# sender (no group); the guard's size on the 1st of March (a group); the guard's size
# on 1 January from two senders, and with one sender blank (groups: several companies
# reporting one case). Two cases of the one-sender 1 January group share a number, so
# the number rule still groups them.
PADDED_GROUPS = {
    "january_below": _padded_group(7800000, PADDED_SIZE - 1, "20180101", "RANITIDINE"),
    "january": _padded_group(7810000, PADDED_SIZE, "20170101", "ZANTAC"),
    "year": _padded_group(7820000, PADDED_SIZE, "2016", "FAMOTIDINE"),
    "month": _padded_group(7830000, PADDED_SIZE, "201605", "CIMETIDINE"),
    "first_of_march": _padded_group(7840000, PADDED_SIZE, "20150301", "NIZATIDINE"),
    "january_two_senders": _padded_group(
        7850000,
        PADDED_SIZE,
        "20140101",
        "PAROXETINE",
        senders=("ACME PHARMA, INC.", "BETA LABS LTD"),
    ),
    "january_blank_sender": _padded_group(
        7860000,
        PADDED_SIZE,
        "20130101",
        "SERTRALINE",
        senders=("ACME PHARMA, INC.",) * (PADDED_SIZE - 1) + ("",),
    ),
}
for _r in PADDED_GROUPS["january"][:2]:
    _r.mfr_num = "US-ACME-PD"
DUP_STORY += [r for group in PADDED_GROUPS.values() for r in group]
DUP_QUARTERS = ("2019q1", "2026q2")

# FDA's Convulsion, a lower level term of the PT Seizure in the invented MedDRA, beside Seizure
# itself: two reactions as FDA wrote them, one by today's MedDRA. Built on DUP_QUARTERS.
# fmt: off
SEIZURE_STORY: list[Report] = [
    R("2019q1", "78010011", "7801001", "20190110", event_dt="20190101", age="31", age_cod="YR",
      reacs=["Convulsion"]),
    R("2019q1", "78020011", "7802001", "20190111", event_dt="20190102", age="42", age_cod="YR",
      reacs=["CONVULSION"]),
    R("2026q2", "78030011", "7803001", "20260510", event_dt="20260501", age="53", age_cod="YR",
      sex="M", reacs=["Convulsion"]),
    R("2026q2", "78040011", "7804001", "20260511", event_dt="20260502", age="64", age_cod="YR",
      reacs=["Seizure"]),
    R("2026q2", "78050011", "7805001", "20260512", event_dt="20260503", age="25", age_cod="YR",
      sex="M", reacs=["Seizure", "Headache"]),
    R("2026q2", "78060011", "7806001", "20260513", event_dt="20260504", age="36", age_cod="YR",
      drugs=[Drug("IBUPROFEN", "IBUPROFEN")], reacs=["Headache"]),
]
# fmt: on


def _person(caseid: int, **values: Any) -> Report:
    """A one-version case received in 2026q2, its primaryid its caseid and a 1."""
    return R("2026q2", f"{caseid}1", str(caseid), "20260601", **values)


# Sex, age, weight, age band and country as the release reads them, one case for each thing
# checked, keyed by what it shows (rules sex-codes, age-in-years, weight-in-kg, age-bands,
# country-not-given, eu-member-state). Built on DUP_QUARTERS.
DEMOGRAPHICS: dict[str, Report] = {
    "sex F": _person(7901001, sex="F"),
    "sex m with spaces": _person(7901002, sex=" m "),
    "sex NS": _person(7901003, sex="NS"),
    "sex UNK": _person(7901004, sex="UNK"),
    "sex P": _person(7901005, sex="P"),
    "sex empty": _person(7901006, sex=""),
    "age with no unit": _person(7902001, age="45"),
    "age in minutes": _person(7902002, age="30", age_cod="MIN"),
    "age in seconds": _person(7902003, age="3600", age_cod="SEC"),
    "age negative": _person(7902004, age="-1", age_cod="YR"),
    "age at the top": _person(7902005, age="122", age_cod="YR"),
    "age over the top": _person(7902006, age="123", age_cod="YR"),
    "age in decades over the top": _person(7902007, age="13", age_cod="DEC"),
    "age .8": _person(7902008, age=".8", age_cod="YR"),
    "age 60.": _person(7902009, age="60.", age_cod="YR"),
    "age with spaces": _person(7902010, age=" 60 ", age_cod="YR"),
    "age not a number": _person(7902011, age="6O", age_cod="YR"),
    "age in an unknown unit": _person(7902012, age="40", age_cod="XX"),
    "weight in pounds": _person(7903001, wt="154", wt_cod="LBS"),
    "weight .9": _person(7903002, wt=".9", wt_cod="KG"),
    "weight zero": _person(7903003, wt="0", wt_cod="KG"),
    "weight at the top": _person(7903004, wt="635", wt_cod="KG"),
    "weight over the top": _person(7903005, wt="636", wt_cod="KG"),
    "weight in grams": _person(7903006, wt="3500", wt_cod="GMS"),
    "weight with no unit": _person(7903007, wt="70"),
    "weight in an unknown unit": _person(7903008, wt="70", wt_cod="XX"),
    "0 years, neonate": _person(7904001, age="0", age_cod="YR", age_grp="N"),
    "0 years, infant": _person(7904002, age="0", age_cod="YR", age_grp="I"),
    "0 years, no group": _person(7904003, age="0", age_cod="YR"),
    "0 decades, adult": _person(7904004, age="0", age_cod="DEC", age_grp="A"),
    "0 with no unit, neonate": _person(7904005, age="0", age_grp="n"),
    "0 days": _person(7904006, age="0", age_cod="DY", age_grp="I"),
    "27 days": _person(7904007, age="27", age_cod="DY"),
    "28 days": _person(7904008, age="28", age_cod="DY"),
    "4 weeks": _person(7904009, age="4", age_cod="WK"),
    "672 hours": _person(7904010, age="672", age_cod="HR"),
    "23 months": _person(7904011, age="23", age_cod="MON"),
    "24 months": _person(7904012, age="24", age_cod="MON"),
    "1.9 years": _person(7904013, age="1.9", age_cod="YR"),
    "85 years": _person(7904014, age="85", age_cod="YR"),
    "occurrence A1": _person(7905001, country="FR", occr_country="A1"),
    "country not specified": _person(7905002, country="COUNTRY NOT SPECIFIED", occr_country=""),
    "EU, earlier version DE": R(
        "2026q2", "79060012", "7906001", "20260602", caseversion="2", country="EU"
    ),
    "EU, earlier version not an ISO code": R(
        "2026q2", "79060022", "7906002", "20260603", caseversion="2", country="EU"
    ),
    "EU, two earlier versions": R(
        "2026q2", "79060033", "7906003", "20260604", caseversion="3", country="EU"
    ),
    "EU alone": _person(7906004, country="EU"),
}
# The earlier versions the EU cases read, received in 2019q1.
DEMOGRAPHICS_EARLIER = [
    R("2019q1", "79060011", "7906001", "20190201", country="DE"),
    R("2019q1", "79060021", "7906002", "20190202", country="XK"),
    R("2019q1", "79060031", "7906003", "20190203", country="FR"),
    R("2019q1", "79060032", "7906003", "20190204", caseversion="2", country="IT"),
]
# Two pairs the first duplicate rule compares: two cases whose only country is FDA's words for
# none (never matched), and two EU cases, one of which takes DE from an earlier version (still
# one group).
_PAIR: dict[str, Any] = dict(event_dt="20250901", age="50", age_cod="YR", sex="M")
DEMOGRAPHICS_PAIRS = {
    "no country": [
        _person(7907001, country="COUNTRY NOT SPECIFIED", occr_country="", **_PAIR),
        _person(7907002, country="COUNTRY NOT SPECIFIED", occr_country="", **_PAIR),
    ],
    "EU": [
        R("2026q2", "79080012", "7908001", "20260605", caseversion="2", country="EU", **_PAIR),
        _person(7908002, country="EU", **_PAIR),
    ],
}
DEMOGRAPHICS_STORY = (
    list(DEMOGRAPHICS.values())
    + DEMOGRAPHICS_EARLIER
    + [R("2019q1", "79080011", "7908001", "20190205", country="DE")]
    + [r for pair in DEMOGRAPHICS_PAIRS.values() for r in pair]
)

# Cases carried over from AERS into FAERS at the 2012 migration: the same case
# number, FAERS's caseversion counting on from the AERS versions. 5100010's
# AERS version has two drug lines FDA published glued together (GLUED);
# 5100011's AERS version has a `$` inside its mfr_num, and its FAERS version
# is later deleted.
# fmt: off
CARRIED_OVER: list[Report] = [
    R("2012q3", "4100010", "5100010", "20120815", caseversion="",
      drugs=[Drug("BLEOMYCIN SULFATE", ""), Drug("DOXORUBICIN", "", role="SS")]),
    R("2012q4", "51000102", "5100010", "20121201", caseversion="2", init_fda_dt="20120815",
      drugs=[Drug("BLEOMYCIN SULFATE", ""), Drug("DOXORUBICIN", "", role="SS")]),
    R("2012q3", "4100011", "5100011", "20120820", caseversion="", mfr_num="JP-ACME-$E2B0000000182"),
    R("2018q1", "51000112", "5100011", "20180105", caseversion="2", init_fda_dt="20120820"),
]
# fmt: on
STORY += CARRIED_OVER

# Drug names read to their ingredients (rule drug-names; the invented dictionary in fakediana),
# FAERS 2026q2: valsartan under two spellings, as each role, and in a combination; a spelling the
# dictionary does not know; one brand written two ways.
DRUG_NAMES: list[Report] = [
    R("2026q2", "92100011", "9210001", "20260601", drugs=[Drug("VALSARTAN", "VALSARTAN")]),
    R(
        "2026q2",
        "92100021",
        "9210002",
        "20260602",
        drugs=[Drug("DIOVAN", "VALSARTAN", role="SS"), Drug("LIPITOR", "ATORVASTATIN")],
    ),
    R(
        "2026q2",
        "92100031",
        "9210003",
        "20260603",
        drugs=[Drug("ENTRESTO", "SACUBITRIL\\VALSARTAN")],
    ),
    R(
        "2026q2",
        "92100041",
        "9210004",
        "20260604",
        drugs=[Drug("LIPITOR", "ATORVASTATIN"), Drug("DIOVAN", "VALSARTAN", role="C")],
    ),
    R(
        "2026q2",
        "92100051",
        "9210005",
        "20260605",
        drugs=[Drug("LIPITOR", "ATORVASTATIN"), Drug("VALSARTAN", "VALSARTAN", role="I")],
    ),
    R("2026q2", "92100061", "9210006", "20260606", drugs=[Drug("VALSARTAN TEVA", "")]),
    R("2026q2", "92100071", "9210007", "20260607", drugs=[Drug("HUMIRA", "ADALIMUMAB")]),
    R("2026q2", "92100081", "9210008", "20260608", drugs=[Drug("HUMIRA (ADALIMUMAB)", "")]),
]
STORY += DRUG_NAMES

# Lines FDA published with no line break after them, so the next record runs
# on in the same line (2011Q2, 2011Q3 and 2011Q4 DRUG): (quarter, table,
# primaryid) of the first of the two records.
GLUED = {("2012q3", "drug", "4100010")}

# FDA's deleted-case lists: (quarter, path inside the quarter, lines as written).
DELETED_LISTS = [
    ("2019q1", "deleted/ADR19Q1DeletedCases.txt", ["9008008", "9999998", "5100011"]),
    ("2019q1", "deleted/AllDeletedCases.txt", ["9009009", "9008008"]),
    ("2026q2", "Deleted/DELETE26Q2.txt", [" ", "9010010", "5100007", "9999999"]),
]


@dataclass(frozen=True)
class Layout:
    era: str
    headers: dict[str, str]
    zip_prefix: str
    folder: str  # the text files' folder inside the quarter
    names: dict[str, str]  # table -> file name
    encodings: dict[str, str]  # table -> encoding (default utf-8)
    eol: dict[str, str]  # table -> line ending (default CRLF)
    trailing_dollar: bool = False
    bom: tuple[str, ...] = ()
    extras: tuple[str, ...] = ()  # FDA's other files, which the loader must ignore


def _upper(q: str) -> dict[str, str]:
    yy, n = q[2:4], q[5]
    return {t: f"{t.upper()}{yy}Q{n}.TXT" for t in AERS_2004}


# fmt: off
LAYOUTS = {
    "2012q2": Layout("legacy", AERS_2004, "aers_ascii", "ascii", _upper("2012q2"), {}, {},
                     trailing_dollar=True,
                     extras=("ascii/STAT12Q2.TXT", "SIZE12Q2.TXT", "README.doc")),
    "2012q3": Layout("legacy", AERS_2012, "aers_ascii", "ascii", _upper("2012q3"),
                     {"drug": "latin-1"}, {}, trailing_dollar=True, extras=("ascii/Asc_nts.doc",)),
    "2012q4": Layout("faers", FAERS_2012Q4, "faers_ascii", "ascii",
                     {t: f"{t}12q4.txt" for t in AERS_2004}, {}, {}, bom=("drug",),
                     extras=("ascii/demo12q4.pdf", "FAQs.doc")),
    "2018q1": Layout("faers", FAERS_NOW, "faers_ascii", "ascii",
                     {**{t: f"{t.upper()}18Q1.txt" for t in AERS_2004}, "demo": "DEMO18Q1_new.txt"},
                     {}, {t: "\n" for t in AERS_2004}, extras=("ascii/demo18q1.pdf",)),
    "2019q1": Layout("faers", FAERS_NOW, "faers_ascii", "ascii",
                     {t: f"{t.upper()}19Q1.txt" for t in AERS_2004}, {}, {},
                     extras=("Readme.pdf",)),
    "2026q2": Layout("faers", FAERS_NOW, "faers_ascii", "ASCII",
                     {t: f"{t.upper()}26Q2.txt" for t in AERS_2004}, {},
                     {"demo": "\n", "reac": "\n", "outc": "\n"}, extras=("ASCII/DEMO26Q2.pdf",)),
}
# fmt: on
QUARTERS = tuple(LAYOUTS)
RELEASE = "2026Q2"


def text_file(
    quarter: str, table: str, *, glued: bool = True, story: list[Report] | None = None
) -> tuple[str, bytes]:
    """(path inside the quarter, bytes) of one table's file, as FDA writes it.
    With glued=False, the lines FDA ran together (GLUED) are written apart:
    the records as they really are. `story` replaces STORY (DUP_STORY)."""
    layout = LAYOUTS[quarter]
    header = layout.headers[table]
    names = [release_column(table, h) for h in header.split("$")]
    eol = layout.eol.get(table, "\r\n")
    text = header + eol
    for report in (r for r in (STORY if story is None else story) if r.quarter == quarter):
        for i, row in enumerate(report.fields(table)):
            line = "$".join(row[n] for n in names) + ("$" if layout.trailing_dollar else "")
            run_on = glued and i == 0 and (quarter, table, report.primaryid) in GLUED
            text += line + ("" if run_on else eol)
    data = text.encode(layout.encodings.get(table, "utf-8"))
    if table in layout.bom:
        data = b"\xef\xbb\xbf" + data
    return f"{layout.folder}/{layout.names[table]}", data


def quarter_files(quarter: str, story: list[Report] | None = None) -> dict[str, bytes]:
    """Every file of one quarter: path inside the quarter -> bytes."""
    layout = LAYOUTS[quarter]
    files = dict(text_file(quarter, t, story=story) for t in AERS_2004)
    for q, path, lines in DELETED_LISTS:
        if q == quarter:
            files[path] = (
                ("\r\n".join(lines) + "\r\n").encode()
                if "ADR" in path or "All" in path
                else ("\n".join(lines) + "\n").encode()
            )
    for extra in layout.extras:
        files[extra] = b"not a data file\r\n"
    return files


def write_input(
    folder: Path,
    *,
    as_zips: bool = True,
    quarters: tuple[str, ...] = QUARTERS,
    story: list[Report] | None = None,
) -> Path:
    """Write the fake quarters into `folder` as FDA zips or extracted folders.
    `story` replaces STORY: write_input(folder, quarters=DUP_QUARTERS, story=DUP_STORY)."""
    folder.mkdir(parents=True, exist_ok=True)
    for q in quarters:
        files = quarter_files(q, story)
        if as_zips:
            with zipfile.ZipFile(
                folder / f"{LAYOUTS[q].zip_prefix}_{q}.zip", "w", zipfile.ZIP_DEFLATED
            ) as z:
                for path, data in files.items():
                    z.writestr(path, data)
        else:
            for path, data in files.items():
                target = folder / q / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    return folder


def parsed_rows(quarter: str, table: str) -> list[dict[str, str | None]]:
    """Read one fake file back the plain way (split on `$`), keyed by release
    column name, empty fields as None: what the release must hold verbatim."""
    _, data = text_file(quarter, table, glued=False)
    text = data.decode(LAYOUTS[quarter].encodings.get(table, "utf-8"))
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line != ""]
    header = [release_column(table, h) for h in lines[0].split("$")]
    rows = []
    for line in lines[1:]:
        values = line.split("$")[: len(header)]
        # a short row leaves its last fields out
        rows.append({h: (v if v != "" else None) for h, v in zip(header, values, strict=False)})
    return rows


def header_columns(quarter: str, table: str) -> list[str]:
    """The release names of the columns one fake file publishes."""
    return [release_column(table, h) for h in LAYOUTS[quarter].headers[table].split("$")]
