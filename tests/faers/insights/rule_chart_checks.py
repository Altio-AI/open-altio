"""The numbers of the rule charts (insights/cards/rule_charts.py), counted again a second way:
straight from the release folder's Parquet files and its manifest, read only, without the
cards' code or connection. Every count of cases is over the cases the release shows
(case_latest_T where dup_kept_T), and every count of their drug or therapy records over the
records of those cases, found here by joining each record to its case. The tests compare them on
the fake releases; the same function runs on a real release by hand
(`python tests/faers/insights/rule_chart_checks.py <release>`)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

FDA = ["demo_T", "drug_latest_T", "reac_latest_T", "outc_latest_T", "rpsr_latest_T"]
FDA += ["ther_latest_T", "indi_latest_T"]
CNS = "('COUNTRY NOT SPECIFIED', 'A1')"
GIVEN = "length(trim({})) > 0"
STATS = [("ebgm_spread", "ebgm_T", 2), ("prr_spread", "prr_T", 2), ("ror_spread", "ror_T", 2)]
STATS += [("rrr_spread", "rrr_T", 2), ("ic_spread", "ic_T", 1)]


def independent(release: str | Path, settings: str = "") -> dict[str, dict]:
    release = Path(release)
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    tables = manifest["tables"]
    con = duckdb.connect()
    if settings:
        con.execute(settings)

    def t(name: str) -> str:
        return f"read_parquet('{release / tables[name]['path']}')"

    def cols(name: str) -> list[str]:
        return [c for (c, *_) in con.execute(f"DESCRIBE SELECT * FROM {t(name)}").fetchall()]

    def nums(keys: str, sql: str) -> dict:
        return dict(zip(keys.split(), con.execute(sql).fetchone(), strict=True))

    def shown(name: str) -> str:
        """The records of `name` that belong to a shown case."""
        return (
            f"(SELECT x.* FROM {t(name)} x JOIN {t('case_latest_T')} k "
            "ON x.era_T = k.era_T AND x.primaryid = k.primaryid AND x.quarter_T = k.quarter_T "
            "WHERE k.dup_kept_T)"
        )

    out: dict[str, dict] = {}
    names = [c for name in FDA if name in tables for c in cols(name)]
    ours = sum(c.endswith("_T") for c in names)
    out["fda_columns_kept"] = {"fda_columns": len(names) - ours, "added_columns": ours}
    split = [x for e in manifest["inputs"] for x in e.get("overlong_lines") or []]
    split = [x for x in split if x["records"] > 1]
    saved = sum(x["records"] - 1 for x in split)
    out["run_on_lines_split"] = {"lines": len(split), "records_saved": saved}
    c = "(SELECT * FROM " + t("case_latest_T") + " WHERE dup_kept_T)"
    w = nums("given kg", f"SELECT count(*), count(wt_kg_T) FROM {c} WHERE wt IS NOT NULL")
    out["weights_read_in_kg"] = {
        "weights_given": w["given"],
        "read_in_kg": w["kg"],
        "no_weight": w["given"] - w["kg"],
    }
    out["cases_by_age_band"] = nums(
        "cases in_a_band", f"SELECT count(*), count(age_band_T) FROM {c}"
    )
    n = nums(
        "cases no_country",
        f"SELECT count(*), count(*) - count(country_T) FROM {c} WHERE "
        f"(upper(trim(occr_country)) IN {CNS} OR upper(trim(reporter_country)) IN {CNS})",
    )
    n["country_from_other_field"] = n["cases"] - n["no_country"]
    out["country_not_specified"] = n
    ev = nums(
        "event_dates",
        f"SELECT count(*) FROM {c} WHERE {GIVEN.format('event_dt')} AND event_dt_prec_T IS NULL",
    )
    th = nums(
        "therapy_dates",
        f"SELECT count(*) FROM {t('ther_latest_T')} x, {c} k WHERE x.era_T = k.era_T "
        "AND x.primaryid = k.primaryid AND x.quarter_T = k.quarter_T "
        f"AND (({GIVEN.format('x.start_dt')} AND x.start_dt_prec_T IS NULL) "
        f"OR ({GIVEN.format('x.end_dt')} AND x.end_dt_prec_T IS NULL))",
    )
    out["dates_without_a_clean_date"] = ev | th
    exact = "coalesce(start_dt_prec_T, 0) = 8 AND coalesce(end_dt_prec_T, 0) = 8"
    out["therapy_durations"] = nums(
        "therapy_lines from_dates from_fda_duration",
        f"SELECT count(*), count(dur_days_T) FILTER (WHERE {exact}), "
        f"count(dur_days_T) FILTER (WHERE NOT ({exact})) FROM {shown('ther_latest_T')}",
    )
    if "drug_route_T" in tables:
        out["route_found"] = nums(
            "drug_records with_a_route",
            "SELECT count(*), count(*) FILTER (WHERE route_source_T NOT IN ('none', 'disagree')) "
            f"FROM {shown('drug_route_T')}",
        )
    if "atc_drug_T" in tables:
        a = shown("atc_drug_T")
        out["drug_records_classed"] = nums(
            "drug_records classed",
            f"SELECT (SELECT count(*) FROM {shown('drug_latest_T')}), count(atc_code_T) FROM {a}",
        )
        out["classes_chosen"] = nums(
            "by_use group_class use_not_said",
            "SELECT count(*) FILTER (WHERE atc_chosen_by_T IN ('route', 'dose', 'indication')), "
            "count(*) FILTER (WHERE atc_chosen_by_T = 'group_class'), "
            f"count(*) FILTER (WHERE atc_chosen_by_T = 'cannot_tell') FROM {a}",
        )
    if "drug_rxnorm_T" in tables:
        out["rxnorm_codes"] = nums(
            "drug_records coded",
            "SELECT count(*), count(*) FILTER (WHERE matched_by_T <> 'none') "
            f"FROM {shown('drug_rxnorm_T')}",
        )
    if "atc_statistics_T" in tables:
        out["class_pairs_by_level"] = nums("pairs", "SELECT count(*) FROM " + t("atc_statistics_T"))
    if "statistics_T" in tables:
        s = t("statistics_T")
        out["pairs_by_cases"] = nums(
            "pairs one_or_two_cases",
            f"SELECT count(*), count(*) FILTER (WHERE cases_T <= 2) FROM {s}",
        )
        for card, col, at in STATS:
            out[card] = nums(
                "pairs at_or_above",
                f"SELECT count(*), count(*) FILTER (WHERE isfinite({col}) AND {col} >= {at}) "
                f"FROM {s}",
            )
    if "statistics_strata_T" in tables:
        out["ror_by_stratum"] = nums(
            "pair_strata lower_above_1",
            "SELECT count(*), count(*) FILTER (WHERE ror_lower_T > 1) "
            f"FROM {t('statistics_strata_T')}",
        )
    if "label_candidates_T" in tables:
        lc, have = t("label_candidates_T"), set(cols("label_candidates_T"))
        if "application_T" in have:
            out["labels_by_application"] = nums(
                "labels", f"SELECT count(DISTINCT setid_T) FROM {lc}"
            )
        if {"chosen_because_T", "keyed_by_T"} <= have:
            out["label_choice_reasons"] = nums(
                "chosen only_label",
                "SELECT count(*), count(*) FILTER (WHERE chosen_because_T LIKE '%: the only label' "
                f"OR chosen_because_T LIKE '%: the only label;%') FROM {lc}",
            )
            out["labels_keyed_by_ingredients"] = nums(
                "own_ingredients",
                f"SELECT count(*) FROM {lc} WHERE keyed_by_T = 'label_ingredients'",
            )
    if "label_sections_T" in tables:
        out["label_sections_read"] = nums(
            "labels table_rows",
            "SELECT count(DISTINCT setid_T), count(*) FILTER (WHERE is_table_row_T) "
            f"FROM {t('label_sections_T')}",
        )
    if "label_flags_T" in tables and "drug_route_T" in tables:
        out.update(_shown_pair_checks(con, t, tables))
    return out


def _shown_pair_checks(con, t, tables) -> dict[str, dict]:
    """The label cards' numbers, counted once, without parts: every pair (code, forms, reaction)
    a suspect, non-trial record of a shown case uses, joined to its flag."""
    other = ""
    code = "x.rxcui_T"
    if "label_other_drug_T" in tables:
        keys = "era_T, primaryid, quarter_T, drug_seq"
        other = (
            f"LEFT JOIN (SELECT DISTINCT {keys}, true AS o FROM {t('label_other_drug_T')}) o "
            f"USING ({keys})"
        )
        code = "CASE WHEN o.o THEN NULL ELSE x.rxcui_T END"
    k = "era_T, primaryid, quarter_T"
    sql = f"""
    SELECT f.outcome_T, f.decided_by_T, count(*) FROM (
      SELECT DISTINCT coalesce({code}, '') AS c, coalesce(ro.route_families_T, '') AS fam,
             r.pt AS pt
      FROM (SELECT DISTINCT {k}, drug_seq FROM {t("drug_latest_T")}
            WHERE role_cod IN ('PS', 'SS')) d
      SEMI JOIN (SELECT {k} FROM {t("case_latest_T")} WHERE dup_kept_T) USING ({k})
      JOIN {t("drug_substance_T")} s USING ({k}, drug_seq)
      LEFT JOIN {t("drug_rxnorm_T")} x USING ({k}, drug_seq)
      LEFT JOIN {t("drug_route_T")} ro USING ({k}, drug_seq)
      {other}
      JOIN {t("reac_latest_T")} r USING ({k})
      WHERE NOT coalesce(s.diana_trial_T, false) AND r.pt IS NOT NULL) u
    LEFT JOIN {t("label_flags_T")} f ON coalesce(f.rxcui_T, '') = u.c
      AND coalesce(f.route_families_T, '') = u.fam AND f.pt_T = u.pt
    GROUP BY ALL"""
    rows = con.execute(sql).fetchall()
    by = {}
    for outcome, _, n in rows:
        by[outcome] = by.get(outcome, 0) + n
    umbrella = sum(n for o, d, n in rows if o == "on_label" and d == "rule: umbrella")
    total = sum(by.values())
    aside = sum(by.get(o, 0) for o in ("treated_disease", "not_a_medical_event", "procedure"))
    return {
        "label_flags_given": {
            "pairs": total,
            "on_label": by.get("on_label", 0),
            "umbrella": umbrella,
            "set_aside": aside,
        },
        "label_treated_disease": {"pairs": by.get("treated_disease", 0)},
        "label_not_a_medical_event": {"pairs": by.get("not_a_medical_event", 0)},
        "label_procedure": {"pairs": by.get("procedure", 0)},
        "label_umbrella": {"pairs": umbrella},
        "label_dictionary": {"pairs": by.get("on_label", 0)},
    }


if __name__ == "__main__":
    print(json.dumps(independent(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""), indent=1))
