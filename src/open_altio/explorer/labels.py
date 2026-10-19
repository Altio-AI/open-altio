"""The label flags the screens show: whether today's US prescription label of each suspect
drug lists a reaction (rule explorer-label-flags), read from the release's tables when it holds
them. A release without them shows no flags, and nothing here fails.

    held(opened)                          whether the release holds the tables the flags need
    screens(opened)                       what /api/release tells the page, or None
    narrowed(data, filters, product)      the filters, with the cases Label status keeps
    product_flags(data, drug, exact)      the labels read for a drug and each reaction's flag
    case_flags(data, era, key)            each suspect drug of one case, with its flag per reaction
                                          and the label read, named as labelnames.py names it
    label_counts(data, drug, sql, ps, exact)  cases with a reaction of each flag, under `sql`
    on_statistics(data, drug, query)      the Statistics tab's Label column, Label status and sort

A flag belongs to a suspect drug record and a reaction of its case, read as the label flags
step wrote it: the record's RxNorm code (`drug_rxnorm_T`, empty without one) and its candidate
route families (`drug_route_T`, sorted and joined with ";", empty when nothing is known) find
its row in `label_flags_T`, by the reaction as FDA published it. A record the drug names step
marks a trial product (`drug_substance_T`) gets none. A record whose code names another drug
than the one it is counted under (`label_other_drug_T`, written by the label flags step) finds
its flag as a record with no code does, never on the code's label. A drug page's flags follow
what it counts. Counting any product containing an ingredient, its records are every record
holding the ingredient, each read on the ingredient's own label: the ingredient's own code
(`ingredient_rxnorm_T`) finds the row, so a combination's reactions, and a record whose code
names another drug, are judged against the counted ingredient's label. Counting the product
alone, and on a combination's page, its records are those of exactly that product
(`substance_T`), each read by its own code. A release without `ingredient_rxnorm_T` reads every
page the second way. A record's key repeats on the drug rows, one per dose, so everything here
counts cases or distinct records, never joined rows. Each label read is named by its product,
its ingredients and, where the labels read for the page differ by form, its forms (rule
explorer-label-names), and each flag read on one carries it as `label`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.compute as pc

from open_altio.faers.drugnames.dictionary import SEPARATOR
from open_altio.faers.explorer_db import reaction_term
from open_altio.faers.labels.build import as_of as labels_as_of
from open_altio.rulebook import value

from . import labelnames
from .filters import Filters, parse
from .release import OpenRelease

if TYPE_CHECKING:
    from .drugs import Unit
    from .explore import Data, Query

RULE = "explorer-label-flags"
WORDS = "explorer-label-words"  # each flag's word on the screens
REFRESH = "label-refresh"  # when the labels are checked against DailyMed each day
STEP = "label-flags"  # the label flags step's own rule, which says which records it flags
FLAGS, RXNORM, ROUTE, SUBSTANCE, OTHER_DRUG, INGREDIENTS = (
    "label_flags_T",
    "drug_rxnorm_T",
    "drug_route_T",
    "drug_substance_T",
    "label_other_drug_T",
    "ingredient_rxnorm_T",
)
# without drug_route_T no record's form is known; label_candidates_T names the labels read
NEEDED = (FLAGS, RXNORM, SUBSTANCE, labelnames.CANDIDATES)
NO_LABEL = "no_label"
SORT = "label"  # the Statistics tab's sort by Label
# a flag as the page reads it: what the label says, the record's candidate route families
# (forms), the family label or labels that decided (judged_on), and each family's outcome
FLAG_FIELDS = (
    "outcome",
    "section",
    "setid",
    "date",
    "decided_by",
    "forms",
    "judged_on",
    "families",
)


def held(opened: OpenRelease) -> bool:
    return all(t in opened.manifest["tables"] for t in NEEDED)


def screens(opened: OpenRelease) -> dict | None:
    """The flags' order, Unexpected only's ticks, the address's word for none ticked, each
    flag's word and, for one not compared with the label, its reason (rule
    explorer-label-words), and the time each day the labels are checked against DailyMed and the
    day they are as of (rule label-refresh), for the page; None without the tables."""
    if not held(opened):
        return None
    shown = {k: value(RULE, k) for k in ("outcomes", "unexpected_only", "nothing_ticked")}
    words = {k: value(WORDS, k) for k in ("words", "reasons")}
    checked = value(REFRESH, "checked_at_utc")
    return shown | words | {"checked_at_utc": checked, "as_of": labels_as_of(opened.manifest)}


def _route(opened: OpenRelease) -> str | None:
    tables = opened.manifest["tables"]
    return str(opened.folder / tables[ROUTE]["path"]) if ROUTE in tables else None


def _other(opened: OpenRelease) -> str | None:
    tables = opened.manifest["tables"]
    return str(opened.folder / tables[OTHER_DRUG]["path"]) if OTHER_DRUG in tables else None


def _paths(opened: OpenRelease) -> list[str]:
    tables = opened.manifest["tables"]
    return [str(opened.folder / tables[t]["path"]) for t in (RXNORM, SUBSTANCE, FLAGS)]


@dataclass(frozen=True)
class OwnLabel:
    """An ingredient's own label, which a page counting any product containing it reads every
    record on: the ingredient, its own RxNorm code (None without one) and term type, and whether
    that code finds a label in any form. Without one, a record of the ingredient alone keeps its
    own code."""

    drug: str
    rxcui: str | None
    tty: str | None
    labelled: bool


def _own_label(opened: OpenRelease, drug: str, exact: bool) -> OwnLabel | None:
    """The ingredient's own label when the page counts any product containing it; None when it
    reads each record by its own code: the product alone, a combination, or a release without
    each ingredient's own code."""
    tables = opened.manifest["tables"]
    if exact or SEPARATOR in drug or INGREDIENTS not in tables:
        return None
    found = opened.rows(
        "SELECT rxcui_T, tty_T, coalesce(rxcui_T IN (SELECT rxcui_T FROM read_parquet(?)), FALSE)"
        " AS labelled FROM read_parquet(?) WHERE ingredient_T = ?",
        [str(opened.folder / tables[t]["path"]) for t in (labelnames.CANDIDATES, INGREDIENTS)]
        + [drug],
    )
    if not found:
        return OwnLabel(drug, None, None, False)
    return OwnLabel(drug, found[0]["rxcui_T"], found[0]["tty_T"], bool(found[0]["labelled"]))


RECORDS = "label_records_T"  # the records one question picks, in a cursor's own temporary table


def _records(chosen: str) -> str:
    """Each suspect drug record the `chosen` condition picks (over explorer_drug_T d), once.
    Its parameters: the roles, then `chosen`'s."""
    return f"""
    SELECT DISTINCT d.case_id_T, c.era_T, c.primaryid, c.quarter_T, d.drug_seq, d.drugname,
      d.substance_T
    FROM explorer_drug_T d JOIN explorer_case_T c USING (case_id_T)
    WHERE d.role_cod IN (SELECT unnest(?::VARCHAR[])) AND {chosen}"""


def _pairs(route: bool, by_ingredient: bool, other: bool = False) -> str:
    """Each non-trial record of RECORDS with every reaction of its case and the flag
    label_flags_T gives it, by the record's own code, or by the ingredient's own (`by_ingredient`:
    its code and term type, then whether a record of the ingredient alone keeps its own code and
    the ingredient, as parameters). A record with no RxNorm code keeps its flag (No label found);
    without drug_route_T every record's families are empty, as the step read them; by its own
    code, a record whose code names another drug (`other`, label_other_drug_T) is read as one
    with no code. Its parameters: drug_substance_T's file, the ingredient's (when
    `by_ingredient`), drug_rxnorm_T's file and label_other_drug_T's (when `other`),
    drug_route_T's, the decisions shown as Uncertain and the flags' file. The records are a table
    of their own, so DuckDB knows how few they are and keeps them, never a release table, in
    memory for each join; a release table is read only for the records' cases."""
    key = "USING (era_T, primaryid, quarter_T, drug_seq)"
    families = "coalesce(ro.route_families_T, '')"  # sorted and joined with ";" by its step
    # a record's own code is read only where it names the drug the record is counted under
    named = "od.drug_seq IS NULL" if other else "TRUE"
    listed = f" LEFT JOIN read_parquet(?) od {key}" if other else ""
    if by_ingredient:
        coded = f"""SELECT kept.*,
          CASE WHEN NOT alone THEN ?::VARCHAR WHEN {named} THEN r.rxcui_T END AS rxcui_T,
          CASE WHEN NOT alone THEN ?::VARCHAR WHEN {named} THEN r.tty_T END AS tty_T
        FROM (SELECT *, ?::BOOLEAN AND substance_T = ? AS alone FROM kept) kept
        LEFT JOIN read_parquet(?) r {key}{listed}"""
    elif other:
        coded = (
            "SELECT kept.*, CASE WHEN od.drug_seq IS NULL THEN r.rxcui_T END AS rxcui_T, "
            "CASE WHEN od.drug_seq IS NULL THEN r.tty_T END AS tty_T FROM kept "
            f"LEFT JOIN read_parquet(?) r {key} LEFT JOIN read_parquet(?) od {key}"
        )
    else:
        coded = f"SELECT kept.*, r.rxcui_T, r.tty_T FROM kept LEFT JOIN read_parquet(?) r {key}"
    # only the records' own routes, so the join keeps those, never all of drug_route_T, in memory
    routes = f"(SELECT ro.* FROM read_parquet(?) ro SEMI JOIN {RECORDS} rec {key}) ro"
    routed = (
        f"SELECT coded.*, {families} AS families_T FROM coded LEFT JOIN {routes} {key}"
        if route
        else "SELECT coded.*, '' AS families_T FROM coded"
    )
    return f"""
    WITH kept AS (
      SELECT rec.* FROM {RECORDS} rec JOIN read_parquet(?) s {key}
      WHERE NOT coalesce(s.diana_trial_T, FALSE)),
    coded AS ({coded}),
    routed AS ({routed}),
    reac AS (
      SELECT routed.*, x.pt FROM routed JOIN (
        SELECT case_id_T, pt FROM explorer_reac_T
        WHERE pt IS NOT NULL AND case_id_T IN (SELECT case_id_T FROM {RECORDS})) x
      USING (case_id_T))
    SELECT reac.case_id_T, reac.drug_seq, reac.drugname, reac.rxcui_T AS rxcui,
      reac.tty_T AS tty, reac.families_T AS forms, reac.pt,
      CASE WHEN suggested THEN 'uncertain' ELSE f.outcome_T END AS outcome,
      CASE WHEN suggested THEN 'unexpected' ELSE f.expectedness_T END AS expectedness,
      CASE WHEN suggested THEN NULL ELSE f.section_T END AS section, f.setid_T AS setid,
      f.label_date_T AS date, f.decided_by_T AS decided_by, f.family_outcomes_T AS families,
      f.judged_on_T AS judged_on
    FROM reac JOIN (SELECT *, decided_by_T IN (SELECT unnest(?::VARCHAR[])) AS suggested
                    FROM read_parquet(?)) f
      ON f.rxcui_T IS NOT DISTINCT FROM reac.rxcui_T AND f.route_families_T = reac.families_T
        AND f.pt_T = reac.pt"""


def _read(
    opened: OpenRelease,
    chosen: str,
    params: list[Any],
    ask: str,
    ingredient: OwnLabel | None = None,
) -> pa.Table:
    """`ask` (SELECT ... FROM pairs ...) over the pairs of the records `chosen` picks, read with
    `chosen`'s parameters on a cursor of its own, whose temporary table goes with it; each record
    by its own code, or on the ingredient's own label (`ingredient`)."""
    rx, substance, flags = _paths(opened)
    route, other = _route(opened), _other(opened)
    coded: list[Any] = [rx, *([other] if other else [])]
    if ingredient is not None:  # a record of it alone keeps its own code where it has no label
        own = [ingredient.rxcui, ingredient.tty, not ingredient.labelled, ingredient.drug]
        coded = [*own, *coded]
    cur = opened.cursor()
    try:
        roles = list(value(STEP, "suspect_roles"))  # the records the step flagged
        cur.execute(f"CREATE TEMP TABLE {RECORDS} AS {_records(chosen)}", [roles, *params])
        shown = list(value(RULE, "shown_as_uncertain"))
        args = [substance, *coded, *([route] if route else []), shown]
        pairs = f"({_pairs(route is not None, ingredient is not None, other is not None)}) pairs"
        return cur.execute(ask.format(pairs=pairs), [*args, flags]).to_arrow_table()
    finally:
        cur.close()


def _split(text: str | None, sep: str = ";") -> list[str]:
    return [p.strip() for p in (text or "").split(sep) if p.strip()]


def _families(flag: dict) -> list[list[str]]:
    """Each form's outcome, from label_flags_T's "by_mouth: on_label; skin: not_on_label"."""
    return [[p.strip() for p in part.split(":", 1)] for part in _split(flag.get("families"))]


def _shown(flag: dict) -> dict:
    return {k: flag.get(k) for k in FLAG_FIELDS} | {
        "forms": _split(flag.get("forms")),
        "families": _families(flag),
        "judged_on": _split(flag.get("judged_on")),
    }


def own_code(drug: str | None) -> str | None:
    """The RxNorm term type of the drug's own label (rule explorer-label-flags, own_label): a
    single ingredient's code for an ingredient, the combination's for a combination."""
    if not drug:
        return None
    return value(RULE, "own_label")["combination" if SEPARATOR in drug else "ingredient"]


def tiebreak(own: str | None) -> Callable[[dict], tuple]:
    """The order among flags that agree, best first, in the order rule explorer-label-flags
    gives (label_tiebreak): the drug's own label (read for a record whose code is of term type
    `own`), the newest label, the lower set ID. A flag with no one label comes after those with
    one, so the label shown never depends on the order the flags were read in."""
    parts: dict[str, Callable[[dict], Any]] = {
        "own_label": lambda f: own is None or f.get("tty") != own,
        "newest_label": lambda f: -f["date"].toordinal() if f.get("date") else 1,
        "setid": lambda f: (f.get("setid") is None, f.get("setid") or ""),
    }
    order = [parts[name] for name in value(RULE, "label_tiebreak")]
    return lambda f: tuple(part(f) for part in order)


def product_flag(
    flags: list[dict],
    closest: list[str] | None = None,
    own: str | None = None,
    best: Callable[[dict], tuple] | None = None,
) -> dict:
    """One flag for a drug's reaction from those its reports give, resolved as the comparison
    resolves a record's forms (rule explorer-label-flags, a drug's row): a report that found no
    label decides only when none did; then the one they agree on; Forms differ, with each form's
    outcome, when they differ in expectedness; else the one closest to the label, with the other
    outcomes in `others`. Flags that agree are taken in the rule's tie-break order (`tiebreak`,
    `own` the term type of the drug's own label). `row` marks it as a drug's row, no one
    report's. `closest` and `best` are the rule's order closest to the label and its tie-break
    for `own`, read once by a caller resolving many reactions: each read parses the rule's file."""
    closest = closest or value(RULE, "closest_to_label")
    best = best or tiebreak(own)
    flags = [f for f in flags if f["outcome"] != NO_LABEL] or flags
    flags = sorted(flags, key=lambda f: (closest.index(f["outcome"]), *best(f), f["forms"] or ""))
    if len({f["expectedness"] for f in flags}) == 1:
        others = list(
            dict.fromkeys(f["outcome"] for f in flags[1:] if f["outcome"] != flags[0]["outcome"])
        )
        # the forms of the reports that gave it, so its tip names another form's label only
        # when none of them had a label of its own
        given = [f for f in flags if f["outcome"] == flags[0]["outcome"]]
        theirs = sorted({form for f in given for form in _split(f["forms"])})
        return _shown(flags[0]) | {"forms": theirs, "row": True, "others": others}
    forms: dict[str, str] = {}
    for f in flags:  # best first, so the best flag gives each form's outcome
        each = dict(_families(f)) or dict.fromkeys(_split(f["judged_on"]), f["outcome"])
        for form, outcome in each.items():
            forms.setdefault(form, outcome)
    return {k: None for k in FLAG_FIELDS} | {
        "outcome": "forms_differ",
        "decided_by": "rule",
        "forms": None,
        "row": True,
        "judged_on": sorted(forms),
        "families": sorted(map(list, forms.items())),
        "others": [],
    }


def _labelled(flags: Iterable[dict], names: dict[str, dict]) -> None:
    """Each flag read on one label carries it, named, as `label`."""
    for flag in flags:
        flag["label"] = names.get(flag.get("setid") or "")


@dataclass(frozen=True)
class ProductFlags:
    labels: list[dict]  # the labels read, named (labelnames.named), in the tie-break's order
    reactions: list[list]  # [reaction as shown, its flag], furthest from the label first
    pairs: pa.Table  # (case_id_T, outcome): which cases have a reaction of each flag


# what a drug's reaction flag is read from: its reports' flags, as they differ
ROW_FIELDS = [
    "tty",
    "forms",
    "pt",
    "outcome",
    "expectedness",
    "section",
    "setid",
    "date",
    "decided_by",
    "families",
    "judged_on",
]


# the records of any product containing an ingredient: those whose ingredients hold it
HOLDING = f"list_contains(string_split(d.substance_T, '{SEPARATOR}'), ?)"


def _product(data: Data, drug: str, ingredient: OwnLabel | None) -> ProductFlags:
    """The drug's pairs read once, then cut two ways: which cases have each flag, and each
    reaction's flags as its reports give them. With `ingredient`, every record holding the
    ingredient, read on its own label; otherwise the records of exactly that product."""
    ask = f"SELECT DISTINCT case_id_T, {', '.join(ROW_FIELDS)} FROM {{pairs}}"
    chosen = "d.substance_T = ?" if ingredient is None else HOLDING
    rows = _read(data.opened, chosen, [drug], ask, ingredient)
    pairs = rows.group_by(["case_id_T", "outcome"]).aggregate([])
    found = rows.select(ROW_FIELDS).group_by(ROW_FIELDS).aggregate([]).to_pylist()
    by_pt: dict[str, list[dict]] = {}
    for f in found:
        by_pt.setdefault(reaction_term(f["pt"]) or f["pt"], []).append(f)
    order, closest = value(RULE, "outcomes"), value(RULE, "closest_to_label")
    own = own_code(drug)
    best = tiebreak(own)
    shown = [
        (data.pt_name(fs[0]["pt"]) or k, product_flag(fs, closest, own, best))
        for k, fs in by_pt.items()
    ]
    shown.sort(key=lambda r: (order.index(r[1]["outcome"]), r[0].lower()))
    # a label's forms are those whose label it is: the families it decided for; it is the drug's
    # own when a record coded as the drug itself read it
    read: dict[str, dict] = {}
    for f in found:
        if f["setid"]:
            label = read.setdefault(
                f["setid"], {"setid": f["setid"], "date": f["date"], "forms": set(), "tty": None}
            )
            label["forms"].update(_split(f["judged_on"] or f["forms"]))
            if own is not None and f["tty"] == own:
                label["tty"] = own
    ranked = sorted(read.values(), key=lambda label: (sorted(label["forms"]), *best(label)))
    names = labelnames.named(data.opened, read)
    _labelled((flag for _, flag in shown), names)
    labels = [names[x["setid"]] for x in ranked]
    return ProductFlags(labels, [list(r) for r in shown], pairs)


def _of(data: Data, drug: str, exact: bool = False) -> ProductFlags:
    """The drug's flags as a page counting any product containing it, or the product alone
    (`exact`), reads them, its reactions named as the viewer's are."""
    unit = "exact" if exact else "any"
    named = data.reactions.version or "-"
    return data.facts.remember(
        f"labels|{drug}|{unit}|{named}",
        lambda: _product(data, drug, _own_label(data.opened, drug, exact)),
    )


def product_flags(data: Data, drug: str, exact: bool = False) -> dict:
    """The labels a drug's reports are read against, and each of its reactions' flag, as a page
    counting any product containing it, or the product alone (`exact`), reads them."""
    if not held(data.opened):
        return {}
    found = _of(data, drug, exact)
    return {"labels": found.labels, "reactions": found.reactions}


def narrowed(data: Data, filters: Filters, product: Unit | None) -> Filters:
    """`filters` with the cases Label status keeps, on a drug's page of a release with the
    flags; elsewhere Label status is dropped."""
    if filters.labels is None:
        return filters
    if product is None or not product.substance or not held(data.opened):
        return filters.with_(labels=None)
    pairs = _of(data, product.substance, product.exact).pairs
    ticked = pa.array(filters.labels, pa.string())
    kept = pairs.filter(pc.is_in(pairs.column("outcome"), value_set=ticked))
    return filters.with_(label_cases=tuple(pc.unique(kept.column("case_id_T")).to_pylist()))


def label_counts(
    data: Data, drug: str, sql: str, params: list, exact: bool = False
) -> dict[str, int]:
    """Cases with at least one reaction of each flag for `drug`, as its page counts it (any
    product containing it, or the product alone: `exact`), among the cases `sql` (over
    explorer_case_T c) picks."""
    if not held(data.opened):
        return {}
    cur = data.opened.cursor()
    try:
        cur.register("label_pairs_T", _of(data, drug, exact).pairs)
        got = cur.execute(
            "SELECT outcome, count(DISTINCT case_id_T) FROM label_pairs_T WHERE case_id_T IN "
            f"(SELECT c.case_id_T FROM explorer_case_T c WHERE {sql}) GROUP BY 1",
            params,
        )
        return dict(got.fetchall())
    finally:
        cur.close()


def case_flags(data: Data, era: str, key: str) -> dict:
    """Each suspect drug of one case that has a flag, in the order of its drugs, with its flag
    for each reaction (by the reaction as FDA published it) and the label read."""
    if not held(data.opened):
        return {}
    found = _read(
        data.opened,
        "d.case_id_T = (SELECT case_id_T FROM explorer_case_T WHERE era_T = ? AND case_key_T = ?)",
        [era, key],
        "SELECT * FROM {pairs} ORDER BY try_cast(drug_seq AS BIGINT), drug_seq, pt",
    ).to_pylist()
    drugs: dict[tuple, dict] = {}
    read: dict[tuple, list[dict]] = {}  # the labels each drug's flags were read on
    for f in found:
        name = (f["drugname"] or "").strip()
        drug = drugs.setdefault(
            (f["rxcui"] or name, f["forms"]),
            {
                "drug_seq": f["drug_seq"],
                "name": name,
                "coded": bool(f["rxcui"]),
                "label": None,
                "flags": {},
            },
        )
        drug["flags"][f["pt"]] = _shown(f)
        if f["setid"]:
            read.setdefault((f["rxcui"] or name, f["forms"]), []).append(f)
    names = labelnames.named(data.opened, (f["setid"] for fs in read.values() for f in fs))
    best = tiebreak(None)  # one drug, one code: the newest label, then the lower set ID
    for at, flags in read.items():
        drugs[at]["label"] = names[min(flags, key=best)["setid"]]
    for drug in drugs.values():
        _labelled(drug["flags"].values(), names)
    return {"drugs": list(drugs.values())}


@dataclass(frozen=True)
class OnStatistics:
    """What Label status and sorting by Label add to the Statistics tab's question over its
    pairs, for one drug: each reaction keyed as the tab keys it (lower case), with its flag,
    and the labels read."""

    flags: dict[str, dict]
    ticked: tuple[str, ...] | None  # None: every flag
    labels: list[dict]

    def where(self) -> tuple[str, list]:
        if self.ticked is None:
            return "TRUE", []
        keys = [k for k, f in self.flags.items() if f["outcome"] in self.ticked]
        return "lower(reaction_T) IN (SELECT unnest(?::VARCHAR[]))", [keys]

    def order(self, direction: str) -> tuple[str, list]:
        """Furthest from the label first when descending, then the highest EB05 in each flag."""
        order = value(RULE, "outcomes")
        keys = list(self.flags)
        ranks = [len(order) - order.index(f["outcome"]) for f in self.flags.values()]
        return (
            f"coalesce(list_extract(?::INTEGER[], list_position(?::VARCHAR[], lower(reaction_T))),"
            f" 0) {direction}, eb05_T DESC NULLS LAST",
            [ranks, keys],
        )

    def counts(self, data: Data, sql: str, params: list) -> dict[str, int]:
        """Reactions of each flag among the pairs `sql` (FROM ... WHERE ...) picks."""
        got: dict[str, int] = {}
        for row in data.rows(f"SELECT DISTINCT lower(reaction_T) AS k {sql}", params):
            if flag := self.flags.get(row["k"]):
                got[flag["outcome"]] = got.get(flag["outcome"], 0) + 1
        return got

    def flag(self, reaction: str) -> dict | None:
        return self.flags.get(reaction_term(reaction) or "")


def on_statistics(data: Data, drug: str, query: Query) -> OnStatistics | None:
    """Label status (`label`, as filters.py reads it) and sorting by Label on a drug's
    Statistics tab, where the release holds the flags; None elsewhere. The statistics count any
    product containing the ingredient, so its flags are read so."""
    if not drug or not held(data.opened):
        return None
    found = _of(data, drug)
    flags = {reaction_term(name) or name: flag for name, flag in found.reactions}
    return OnStatistics(flags, parse(query).labels, found.labels)


__all__ = [
    "NEEDED",
    "SORT",
    "OnStatistics",
    "case_flags",
    "held",
    "label_counts",
    "narrowed",
    "on_statistics",
    "own_code",
    "product_flag",
    "product_flags",
    "screens",
    "tiebreak",
]
