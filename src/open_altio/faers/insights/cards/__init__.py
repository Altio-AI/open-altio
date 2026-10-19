"""The insight cards on the methods page, each computed from FAERS data with SQL.

    from open_altio.faers.insights.source import connect
    from open_altio.faers.insights.cards import compute_cards
    cards = compute_cards(connect(release))        # every card, in page order
    cards = compute_cards(con, ["deleted_lists_unpublished"])

A card function takes a DuckDB connection exposing the derived `_T` tables (a
release folder through `open_altio.faers.insights.source.connect`, or the release build's
own connection) and returns:

    {
      "id": "deleted_lists_unpublished",
      "title": "...",
      "two_sentences": "...",
      "chart": {"type": "line" | "stacked_area" | "stacked_bar",
                "x": {"label": "...", "kind": "quarter" | "year" | "category", "values": [...]},
                "y": {"label": "...", "unit": "percent" | "count"},
                "series": [{"name": "...", "values": [... one per x value, null where no data]}],
                "question": "...",                          # optional: what the chart answers
                "note": {"x": <an x value>, "text": "..."}},  # optional: the x value that matters
      "tag": {"kind": "changed_pipeline", "step": "<funnel step id>", "rules": ["<rule name>", ...]}
             | {"kind": "documented"},
      "notebook": "notebooks/faers/<notebook>.ipynb",
      "rules": ["<rule name>", ...],                     # the rules it is a chart for (RULES_OF)
      "numbers": {...},                                 # optional: the numbers its words quote
    }

A card whose columns or rows are missing from the data (a small or partial
release) returns its chart with empty values rather than failing.
"""

from __future__ import annotations

from collections.abc import Callable

import duckdb

from . import (
    dates_codes,
    demographics,
    drug_classes,
    drug_names,
    duplicates,
    empty_fields,
    meddra,
    publishing,
    rule_charts,
    versions,
)
from .common import MissingDataWarning

CardFn = Callable[[duckdb.DuckDBPyConnection], dict]

# Page order: the cards behind the funnel steps, in step order, then the documented ones.
# A new card is a function in a module here, added to this list.
CARDS: list[CardFn] = [
    versions.carried_cases_counted_twice,
    publishing.deleted_lists_unpublished,
    versions.deleted_lists_name_aers_cases,
    versions.eras_write_countries_and_terms_differently,
    duplicates.same_event_several_cases,
    duplicates.one_case_two_numbers,
    duplicates.padded_dates_join_different_patients,
    dates_codes.event_dates_padded,
    dates_codes.padding_puts_reactions_before_drug,
    dates_codes.occupation_code_changes,
    drug_names.one_medicine_many_spellings,
    drug_names.background_drugs_counted_every_role,
    drug_names.brand_changes_ingredient,
    empty_fields.unknown_written_two_ways,
    empty_fields.to_mfr_filler_on_company_reports,
    empty_fields.who_reported_lost_on_company_reports,
    empty_fields.completeness_depends_on_sender,
    publishing.rechal_filler,
    meddra.older_meddra_terms_missed,
    meddra.quarterly_files_keep_their_meddra_version,
    publishing.sender_names_unstable,
    dates_codes.rept_cod_combination_products,
    dates_codes.no_outcome_not_non_serious,
    dates_codes.drug_seq_repeated,
    publishing.country_empty_rising,
    demographics.european_union_for_member_state,
    demographics.sex_not_specified_for_empty,
    demographics.ages_without_a_unit,
    duplicates.duplicate_check_needs_fields,
    duplicates.no_adverse_event_serious_outcome,
    meddra.unknown_indication_placeholder,
    drug_classes.aspirin_dose_tells_the_use,
    drug_classes.two_use_drug_use_not_said,
    *rule_charts.CARDS,
]

# The rules each card is a chart for: a rule finds its cards here, and a card can serve several.
# Every rule of rules/steps.yaml has at least one (tests/faers/insights/test_rule_charts.py).
RULES_OF: dict[str, list[str]] = {
    "carried_cases_counted_twice": ["latest-version"],
    "deleted_lists_unpublished": ["deleted-cases"],
    "deleted_lists_name_aers_cases": ["deleted-cases"],
    "eras_write_countries_and_terms_differently": [
        "legacy-country",
        "reaction-term-case",
        "legacy-term-spelling",
    ],
    "same_event_several_cases": ["dedup-default", "dup-shown-copy"],
    "one_case_two_numbers": ["dup-manufacturer-number"],
    "padded_dates_join_different_patients": ["dup-padded-event-dates"],
    "event_dates_padded": ["event-date-precision"],
    "padding_puts_reactions_before_drug": ["time-to-onset"],
    "occupation_code_changes": ["reporter-type"],
    "one_medicine_many_spellings": ["drug-names"],
    "background_drugs_counted_every_role": ["drug-names"],
    "brand_changes_ingredient": ["drug-names"],
    "unknown_written_two_ways": ["not-given"],
    "to_mfr_filler_on_company_reports": ["not-given"],
    "who_reported_lost_on_company_reports": ["not-given", "explorer-field-notes"],
    "completeness_depends_on_sender": ["not-given"],
    "rechal_filler": ["not-given"],
    "older_meddra_terms_missed": ["meddra-terms"],
    "quarterly_files_keep_their_meddra_version": ["meddra-version", "meddra-terms"],
    "sender_names_unstable": ["company-names"],
    "european_union_for_member_state": ["eu-member-state"],
    "sex_not_specified_for_empty": ["sex-codes"],
    "ages_without_a_unit": ["age-in-years"],
    "duplicate_check_needs_fields": ["dedup-default"],
    "no_adverse_event_serious_outcome": ["no-drug-or-reaction"],
    "aspirin_dose_tells_the_use": ["atc-class-choice"],
    "two_use_drug_use_not_said": ["atc-class-choice"],
    "fda_columns_kept": ["transformed-suffix-T"],
    "run_on_lines_split": ["overlong-lines"],
    "weights_read_in_kg": ["weight-in-kg"],
    "cases_by_age_band": ["age-bands"],
    "country_not_specified": ["country-not-given"],
    "dates_without_a_clean_date": ["date-limits"],
    "therapy_durations": ["therapy-duration"],
    "route_found": ["drug-route"],
    "drug_records_classed": ["atc-index", "atc-spelling-bridges"],
    "classes_chosen": ["atc-group-classes", "atc-class-choice"],
    "rxnorm_codes": ["rxnorm-ingredients"],
    "pairs_by_cases": ["statistics-cases"],
    "class_pairs_by_level": ["statistics-classes"],
    "ebgm_spread": ["ebgm"],
    "prr_spread": ["prr"],
    "ror_spread": ["ror"],
    "rrr_spread": ["rrr"],
    "ic_spread": ["ic"],
    "ror_by_stratum": ["ror-strata"],
    "labels_by_application": ["label-source"],
    "label_choice_reasons": ["label-choice"],
    "label_sections_read": ["label-sections"],
    "labels_keyed_by_ingredients": ["label-own-ingredients"],
    "label_flags_given": ["label-flags", "label-negation", "label-population"],
    "label_treated_disease": ["label-treated-disease"],
    "label_not_a_medical_event": ["label-not-a-medical-event"],
    "label_procedure": ["label-procedure"],
    "label_umbrella": ["label-umbrella"],
    "label_dictionary": ["label-dictionary"],
    "label_table_rows": ["label-table-rows"],
}

# The cards that need MedDRA's licensed files: they go in the release's licensed part, never in
# the public methods.json (methods.refresh_cards).
LICENSED = frozenset(
    {"older_meddra_terms_missed", "quarterly_files_keep_their_meddra_version", "label_table_rows"}
)

TAG_LABELS = {
    "changed_pipeline": "Changed our pipeline",
    "documented": "Documented, not transformed",
}


def card_ids() -> list[str]:
    return [fn.__name__ for fn in CARDS]


def compute_cards(con: duckdb.DuckDBPyConnection, ids: list[str] | None = None) -> list[dict]:
    """Compute every card (or those named in `ids`), in page order."""
    wanted = set(ids) if ids is not None else None
    unknown = (wanted or set()) - set(card_ids())
    if unknown:
        raise KeyError(f"no insight card named {sorted(unknown)}; have {card_ids()}")
    out = []
    for fn in CARDS:
        if wanted is None or fn.__name__ in wanted:
            card = fn(con)
            card["rules"] = RULES_OF.get(card["id"], card["tag"].get("rules", []))
            out.append(card)
    return out


__all__ = [
    "CARDS",
    "LICENSED",
    "RULES_OF",
    "MissingDataWarning",
    "TAG_LABELS",
    "card_ids",
    "compute_cards",
]
