"""The plain facts about a drug and event pair's cases that a reviewer weighs, each read from
the release and each list or threshold a rule (age-groups, pregnancy-cases, not-a-medical-event,
treated-condition and indication-match).

    facts(data, query)    {"drug": {...}, "events": [{...}]} for the product, over the cases the
                          filters keep, for the events named (`event`, repeated) or its most
                          reported ones

A fact the release cannot give is null with a plain reason beside it in `why`, never 0 and never
false. The facts read from MedDRA's licensed part (pregnancy and the indication read to today's
term) are given only to a viewer with MedDRA. Not a medical event reads a public list of terms and
a licensed list of groups: without the licensed list, only a term on the public list is marked,
and the reason says so. A name MedDRA's version does not hold never refuses a person's page: that
one fact is null, with the reason, and the build says so loudly (faers.meddra.rulenames).
"""

from __future__ import annotations

from typing import Any

from open_altio.faers.meddra import term_key
from open_altio.faers.meddra.rulenames import words
from open_altio.rulebook import value

from . import labels
from .drugs import Unit
from .explore import Data, Problem, Query, list_length, scope
from .filters import age_bands
from .meddra import ServedMeddra

NO_AGE = "No case gives an age."
NO_LABELS = "This release holds no drug labels."
NO_GROUPS_LIST = "This release's licensed part holds no list of MedDRA groups (rule label-groups)."
NO_PREGNANCY_SMQ = (
    "This release's licensed part names no SMQ for rule pregnancy-cases (rule label-groups)."
)
PUBLIC_LIST_ONLY = (
    "Only the public list of terms was read, so a term on it is not a medical event and any "
    "other is not known either way."
)
# a label flag that does not settle whether the event is the treated condition, and why
UNSETTLED = {
    labels.NO_LABEL: "The drug has no label to read.",
    "forms_differ": "The drug's forms are read against labels that differ.",
    "uncertain": "The flag for this event is not settled yet.",
}


class NameNotHeld(Problem):
    """A rule names what this MedDRA version does not hold: the fact is null, the page stands."""

    def __init__(self, message: str) -> None:
        super().__init__(400, message)


def band_ids(rule: str, key: str) -> list[str]:
    """An age group of rule age-groups: the band ids of rule age-bands it names."""
    names = list(value(rule, key))
    held = {b["id"] for b in age_bands()}
    if missing := [n for n in names if n not in held]:
        raise Problem(
            400, f"Rule {rule} names age bands that rule age-bands does not hold: {missing}."
        )
    return names


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _counts(data: Data, sql: str, params: list, events: list[str] | None, top: int) -> list[dict]:
    """Each event's counted cases, the cases giving an age and those in the older and the
    children's bands; the event named, or the most reported ones."""
    older, children = band_ids("age-groups", "older"), band_ids("age-groups", "children")
    keyed, more = data.reactions.keyed(events)
    rows = data.rows(
        "SELECT r.k, count(DISTINCT r.case_id_T) AS cases, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE c.age_band_T IS NOT NULL) AS aged, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE list_contains(?::VARCHAR[], c.age_band_T)) "
        "AS older, "
        "count(DISTINCT r.case_id_T) FILTER (WHERE list_contains(?::VARCHAR[], c.age_band_T)) "
        f"AS children FROM {keyed} r JOIN explorer_case_T c USING (case_id_T) WHERE {sql} "
        "GROUP BY 1 ORDER BY cases DESC, r.k" + ("" if events else " LIMIT ?"),
        [older, children, *more, *params, *([] if events else [top])],
    )
    return rows


def _header(data: Data, sql: str, params: list) -> dict[str, Any]:
    older, children = band_ids("age-groups", "older"), band_ids("age-groups", "children")
    [row] = data.rows(
        "SELECT count(*) AS cases, count(*) FILTER (WHERE c.age_band_T IS NOT NULL) AS aged, "
        "count(*) FILTER (WHERE list_contains(?::VARCHAR[], c.age_band_T)) AS older, "
        "count(*) FILTER (WHERE list_contains(?::VARCHAR[], c.age_band_T)) AS children "
        f"FROM explorer_case_T c WHERE {sql}",
        [older, children, *params],
    )
    return _ages(row) | {"cases": row["cases"]}


def _ages(row: dict) -> dict[str, Any]:
    """The older and children shares of the cases giving an age, null where none does."""
    aged = row["aged"]
    got: dict[str, Any] = {
        "aged": aged,
        "older": _share(row["older"], aged),
        "children": _share(row["children"], aged),
    }
    if not aged:
        got["why"] = {"older": NO_AGE, "children": NO_AGE}
    return got


def pregnancy_terms(meddra: ServedMeddra) -> list[str]:
    """The PTs (lower case) of the SMQ the licensed groups file gives rule pregnancy-cases, in its
    scope and with its sub-SMQs folded in. Raises NameNotHeld when the file gives none or one this
    version does not hold; a scope or a folding no version can read refuses the question."""
    rule = "pregnancy-cases"
    scope_name = str(value(rule, "scope"))
    if scope_name not in ("narrow", "broad"):
        raise Problem(400, f"Rule {rule} gives a scope that is not narrow or broad.")
    if value(rule, "sub_smqs") != "folded":
        raise Problem(400, f"Rule {rule} gives sub-SMQs as something other than folded.")
    named = meddra.named_groups(str(value(rule, "smq_key")))
    if not named:
        raise NameNotHeld(NO_PREGNANCY_SMQ)
    by_name = {q["name"].lower(): q for q in meddra.smqs().values()}
    if missing := [n for n in named if n.lower() not in by_name]:
        raise NameNotHeld(words(rule, "smq", meddra.version, missing))
    return sorted({t for n in named for t in by_name[n.lower()][scope_name]})


def _pregnancy(data: Data, sql: str, params: list, keys: list[str], meddra: ServedMeddra) -> dict:
    """Each event key -> its counted cases that also name a term of the pregnancy SMQ."""
    terms = pregnancy_terms(meddra)
    if not terms or not keys:
        return {k: 0 for k in keys}
    events, e_more = data.reactions.keyed(keys)
    preg, p_more = data.reactions.keyed(terms)
    rows = data.rows(
        f"SELECT e.k, count(DISTINCT e.case_id_T) AS n FROM {events} e "
        f"JOIN {preg} p ON p.case_id_T = e.case_id_T "
        f"JOIN explorer_case_T c ON c.case_id_T = e.case_id_T WHERE {sql} GROUP BY 1",
        [*e_more, *p_more, *params],
    )
    counted = {r["k"]: r["n"] for r in rows}
    return {k: counted.get(k, 0) for k in keys}


def _public_list() -> set[str]:
    return {str(n).lower() for n in value("not-a-medical-event", "pts")}


def _set_aside(meddra: ServedMeddra) -> tuple[set[str] | None, set[str]]:
    """Rule not-a-medical-event's licensed groups, None where the release holds no such list, and
    its public terms, each checked against this MedDRA version. Raises NameNotHeld for a name it
    does not hold."""
    rule = "not-a-medical-event"
    pts = _public_list()
    if missing := sorted(pts - set(meddra.pt_names())):
        raise NameNotHeld(words(rule, "pts", meddra.version, missing))
    named = meddra.named_groups(str(value(rule, "groups_key")))
    if named is None:
        return None, pts
    groups = {n.lower() for n in named}
    held = {n.lower() for path in meddra.primary_paths().values() for n in path}
    if missing := sorted(groups - held):
        raise NameNotHeld(words(rule, "groups", meddra.version, missing))
    return groups, pts


def _not_medical(
    meddra: ServedMeddra | None, keys: list[str], why_no: str
) -> tuple[dict[str, bool | None], dict[str, str]]:
    """Each event key -> whether it is not a medical event, or None where that is not known, and
    the reason where only the public list could be read or the mark is None."""
    if meddra is None:
        pts, groups, only = _public_list(), None, why_no
    else:
        try:
            groups, pts = _set_aside(meddra)
        except NameNotHeld as lost:
            return dict.fromkeys(keys), dict.fromkeys(keys, str(lost))
        only = NO_GROUPS_LIST
    if groups is None:
        reason = f"{only} {PUBLIC_LIST_ONLY}"
        return {k: True if k in pts else None for k in keys}, dict.fromkeys(keys, reason)
    assert meddra is not None  # groups are read only from MedDRA's licensed part
    paths = meddra.primary_paths()
    marks: dict[str, bool | None] = {}
    why: dict[str, str] = {}
    for k in keys:
        path = paths.get(k)
        if path is None:
            marks[k], why[k] = None, "MedDRA does not hold this term."
        else:
            marks[k] = k in pts or any(n.lower() in groups for n in path)
    return marks, why


def _treated(data: Data, unit: Unit, keys: list[str]) -> dict[str, tuple[bool | None, str]]:
    """Each event key -> whether the label flag says it is the condition the drug treats, or
    None and why not."""
    rule = "treated-condition"
    if value(rule, "reads") != "label_flag":
        raise Problem(400, f"Rule {rule} reads something other than the label flag.")
    if not labels.held(data.opened):
        return dict.fromkeys(keys, (None, NO_LABELS))
    read = labels.product_flags(data, str(unit.substance), unit.exact).get("reactions", [])
    flags = {str(name).lower(): flag["outcome"] for name, flag in read}
    out: dict[str, tuple[bool | None, str]] = {}
    for k in keys:
        # the flags are by the reaction as FDA wrote it, so an event is read by every text of it
        found = [flags[t] for t in {k, *data.reactions.texts([k])} if t in flags]
        settled = [o for o in found if o not in UNSETTLED]
        if settled:
            out[k] = (value(rule, "outcome") in settled, "")
        elif found:
            out[k] = (None, UNSETTLED[found[0]])
        else:
            out[k] = (None, "The label flags hold no flag for this event.")
    return out


def _indications(
    data: Data, unit: Unit, sql: str, params: list, keys: list[str], meddra: ServedMeddra
) -> dict[str, tuple[int, int]]:
    """Each event key -> (cases whose record of the drug gives an indication, those whose
    indication read to today's term is the event), among its counted cases."""
    rule = "indication-match"
    if value(rule, "reads") != "indi_pt_current_pt" or value(rule, "equals") != "event_pt":
        raise Problem(400, f"Rule {rule} gives a comparison this release cannot make.")
    keyed, more = data.reactions.keyed(keys)
    record, record_params = unit.records()
    rows = data.rows(
        f"SELECT DISTINCT r.k, r.case_id_T, i.indi_pt FROM {keyed} r "
        "JOIN explorer_case_T c ON c.case_id_T = r.case_id_T "
        "JOIN explorer_drug_T d ON d.case_id_T = r.case_id_T "
        "JOIN explorer_indi_T i ON i.case_id_T = d.case_id_T AND i.indi_drug_seq = d.drug_seq "
        f"WHERE {sql} AND {record} AND nullif(trim(i.indi_pt), '') IS NOT NULL",
        [*more, *params, *record_params],
    )
    read = meddra.read("indi_pt")
    given: dict[str, set] = {k: set() for k in keys}
    matched: dict[str, set] = {k: set() for k in keys}
    for r in rows:
        given[r["k"]].add(r["case_id_T"])
        found = read.get(term_key("indi_pt", r["indi_pt"]) or "")
        if found and found[0].lower() == r["k"]:
            matched[r["k"]].add(r["case_id_T"])
    return {k: (len(given[k]), len(matched[k])) for k in keys}


def facts(data: Data, query: Query) -> dict[str, Any]:
    """The product's facts and each event's: older and children shares of the cases giving an
    age, pregnancy cases, whether the term is a medical event at all, whether the label says it
    is the condition the drug treats, and for such an event the share of cases whose reported
    indication is the event."""
    sc = scope(data, query)
    unit = sc.product
    if unit is None or not unit.substance:
        raise Problem(400, "Name a drug with its ingredient (product) to see its events' facts.")
    sql, params = sc.where()
    asked = sorted({k for k in map(data.reactions.key, query.get("event", [])) if k})
    counts = _counts(data, sql, params, asked or None, list_length("statistics_shown"))
    keys = [r["k"] for r in counts]
    meddra = data.meddra
    why_no = data.why_no_smqs
    no_pregnancy = None
    try:
        preg = _pregnancy(data, sql, params, keys, meddra) if meddra else {}
    except NameNotHeld as lost:
        preg, no_pregnancy = {}, str(lost)
    medical, why_medical = _not_medical(meddra, keys, why_no)
    treated = _treated(data, unit, keys)
    yes = [k for k in keys if treated[k][0]]
    indi = _indications(data, unit, sql, params, yes, meddra) if meddra and yes else {}
    events = []
    for row in counts:
        k = row["k"]
        event: dict[str, Any] = {"event": data.pt_name(k), "cases": row["cases"]}
        event |= _ages(row)
        why: dict[str, str] = dict(event.pop("why", {}))
        event["pregnancy"] = preg.get(k)
        event["not_medical"] = medical.get(k)
        if meddra is None:
            why["pregnancy"] = why_no
        elif no_pregnancy:
            why["pregnancy"] = no_pregnancy
        if k in why_medical:
            why["not_medical"] = why_medical[k]
        event["treated"], reason = treated[k]
        if reason:
            why["treated"] = reason
        given, matched = indi.get(k, (0, 0))
        event["indication_cases"] = given if k in indi else None
        event["indication_match"] = _share(matched, given)
        if treated[k][0] is None:
            why["indication_match"] = "Not compared: the treated condition could not be settled."
        elif not treated[k][0]:
            why["indication_match"] = "The event is not marked as the condition the drug treats."
        elif meddra is None:
            why["indication_match"] = why_no
        elif not given:
            why["indication_match"] = "No case gives an indication for the drug."
        event["why"] = why
        events.append(event)
    return {"drug": _header(data, sql, params), "events": events, "product": unit.substance}


__all__ = ["NameNotHeld", "band_ids", "facts", "pregnancy_terms"]
