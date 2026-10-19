"""The insight cards of notebook 09 (drug classes): what FDA's reports say, and do not say,
about which of a drug's uses its WHO class should follow, measured on the release with its drug
classes.

Each function is one card; its name is the card id. A drug record's class is `atc_drug_T`
(rule atc-class-choice), its doses are FDA's own, on `drug_latest_T`, and its route is the one the
route step reads, on `drug_route_T` (rule drug-route); only the
drug records of the default case set (`case_latest_T` where `dup_kept_T`) count. A release built
without the classes has no such table: each card then says so plainly, with no data.

Both cards are the evidence for rule atc-class-choice, but the drug classes are a layer of their
own, not a step of the funnel, so they are tagged "Documented, not transformed". The methods page
shows them under that rule, by their notebook (explorer/rules_api.py). Should the classes become
a funnel step, their tags change to it in the same change.
"""

from __future__ import annotations

import duckdb

from open_altio import rulebook
from open_altio.faers.reader import quoted

from ...route import TABLE as ROUTES
from ...route import RouteTables
from . import common

NB09 = "notebooks/faers/09_drug_classes.ipynb"
RULE = "atc-class-choice"  # the rule these cards are the evidence for
ASPIRIN = "acetylsalicylic acid"  # a drug whose dose tells its use
TWO_USES = ("methotrexate", "prednisone")  # two drugs WHO codes for two uses, named as examples
FAERS_FROM = 2013  # the first whole year of FAERS, after the change from AERS
_KEY = "era_T, primaryid, quarter_T, drug_seq"
_AMOUNT = "regexp_full_match(d.dose_amt, '[0-9]*\\.?[0-9]+')"  # a dose the layer reads as one


def _built(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether the release carries the drug classes."""
    [(have,)] = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'atc_drug_T'"
    ).fetchall()
    return bool(have)


def _absent(card_id: str, shows: str) -> dict:
    """The card of a release built without the drug classes: no data, and why."""
    return common.card(
        card_id,
        "This release does not give drugs their WHO class",
        "It was built without the drug classes, so no drug record has a class. Built with them, "
        f"this card shows {shows}.",
        common.chart("stacked_bar", "", "category", [], "", "count", []),
        common.DOCUMENTED,
        NB09,
    )


def aspirin_dose_tells_the_use(con: duckdb.DuckDBPyConnection) -> dict:
    """WHO classes aspirin by its use: a low dose is an antithrombotic, a full dose a painkiller.
    Most FAERS reports that state a dose give the low one, so a low stated dose chooses aspirin's
    class; a larger one decides nothing (rules/atc-class-choice.md)."""
    if not _built(con):
        return _absent("aspirin_dose_tells_the_use", "the doses aspirin reports state")
    low = next(d for d in rulebook.value(RULE, "dose_rules") if d["substance"] == ASPIRIN)
    unit = low["unit"].lower()
    bands = (f"{low['at_most']:g} {unit} or less", "More: decides nothing")
    rows = common.query(
        con,
        f"""
        WITH d AS (
          SELECT {_KEY}, bool_and(upper(trim(d.dose_unit)) = ?) AS in_unit_T,
                 max(CAST(d.dose_amt AS DOUBLE)) AS most_T
          FROM drug_substance_T s JOIN drug_latest_T d USING ({_KEY})
          SEMI JOIN case_latest_T c ON c.era_T = d.era_T AND c.primaryid = d.primaryid
                                   AND c.quarter_T = d.quarter_T AND c.dup_kept_T
          WHERE s.substance_T = ? AND {_AMOUNT}
          GROUP BY ALL)
        SELECT CASE WHEN most_T <= ? THEN {quoted(bands[0])} ELSE {quoted(bands[1])} END,
               count(*)
        FROM d WHERE in_unit_T GROUP BY 1""",
        [low["unit"], ASPIRIN, low["at_most"]],
    )
    got = dict(rows)
    dosed, lows = sum(got.values()), got.get(bands[0], 0)
    xs = list(bands)
    chart = common.chart(
        "stacked_bar",
        f"The dose the report states ({unit})",
        "category",
        xs,
        "Aspirin drug records",
        "count",
        common.zeros(common.series([(x, "Records", got.get(x)) for x in xs], xs, ["Records"])),
        question="Which dose do the aspirin reports that state one give?",
        note=(bands[0], f"{common.pct(lows, dosed)}: the blood thinner, {low['code']}"),
    )
    return common.card(
        "aspirin_dose_tells_the_use",
        f"{common.pct(lows, dosed)} of aspirin reports that state a dose give the low dose of a "
        "blood thinner, not a painkiller's",
        f"WHO classes aspirin by its use: {bands[0]} is an antithrombotic ({low['code']}) and "
        "a full dose a painkiller, and of the "
        f"{common.plural(dosed, 'aspirin record')} that state their dose in {unit}, "
        f"{common.pct(lows, dosed)} give the low dose. One fixed class per substance would put "
        "one use under the other's class, so Open Altio classes aspirin by the dose its report "
        "states, and a filter on antithrombotics finds the low-dose reports.",
        chart,
        common.DOCUMENTED,
        NB09,
    )


def two_use_drug_use_not_said(con: duckdb.DuckDBPyConnection) -> dict:
    """WHO gives a substance one code per use, and a report says which use only through its
    dose, its route or the indication it gives. More and more FAERS reports state none of them, so
    such a record gets the class its uses share, or "can't tell", never a guess
    (rules/atc-class-choice.md)."""
    if not _built(con):
        return _absent("two_use_drug_use_not_said", "how often a report says which use it was")
    # a route the class choice reads: one of the route step's drug-class groups
    routes = ", ".join(quoted(c) for c in sorted(RouteTables.read().atc_groups))
    unsaid, stated = (
        "Use not said: the class its uses share, or can't tell",
        "A route the rule reads is stated",
    )
    rows = common.query(
        con,
        f"""
        WITH r AS (
          SELECT a.era_T, a.primaryid, a.quarter_T, a.drug_seq,
                 a.atc_chosen_by_T IN ('cannot_tell', 'shared_class') AS unsaid_T,
                 coalesce(x.route_T IN ({routes}), false) AS stated_T
          FROM atc_drug_T a LEFT JOIN {ROUTES} x USING ({_KEY})
          SEMI JOIN case_latest_T c ON c.era_T = a.era_T AND c.primaryid = a.primaryid
                                   AND c.quarter_T = a.quarter_T AND c.dup_kept_T
          WHERE a.atc_possible_codes_T > 1
            AND a.atc_matched_on_T NOT IN ('each_ingredient', 'each_active_ingredient'))
        SELECT quarter_T, count(*), count(*) FILTER (WHERE unsaid_T),
               count(*) FILTER (WHERE stated_T)
        FROM r GROUP BY 1""",
    )
    by_q = {q: (n, u, s) for q, n, u, s in rows}
    xs = [q for q in common.quarters(con) if q in by_q]

    def share(q: str, i: int) -> float:
        return round(100.0 * by_q[q][i] / by_q[q][0], 1)

    lines = common.series(
        [(q, unsaid, share(q, 1)) for q in xs] + [(q, stated, share(q, 2)) for q in xs],
        xs,
        [unsaid, stated],
    )
    total = sum(n for n, _, _ in by_q.values())
    unsaid_all = sum(u for _, u, _ in by_q.values())
    # the year from which the share rises: its lowest whole year since FAERS began
    years: dict[int, list[int]] = {}
    for q, (n, u, _) in by_q.items():
        years.setdefault(int(q[:4]), [0, 0])
        years[int(q[:4])][0] += n
        years[int(q[:4])][1] += u
    since = {y: u / n for y, (n, u) in years.items() if y >= FAERS_FROM}
    low = min(since, key=lambda y: since[y]) if since else None
    last = xs[-1] if xs else None
    chart = common.chart(
        "line",
        "Quarter of the case's latest version",
        "quarter",
        xs,
        "Share of drug records of substances WHO codes for two or more uses",
        "percent",
        lines,
        question="How often does a report say which use a two-use drug had?",
        note=(last, f"{share(last, 1):.0f}% not said") if last else None,
    )
    rise = (
        f", up from {100.0 * since[low]:.0f}% in {low} to {share(last, 1):.0f}% in "
        f"{common.quarter_label(last)} as fewer reports state a route"
        if low is not None and last is not None and share(last, 1) > 100.0 * since[low]
        else ""
    )
    return common.card(
        "two_use_drug_use_not_said",
        f"FAERS does not say which use a two-use drug had in {common.pct(unsaid_all, total)} "
        "of its records",
        f"WHO gives a substance like {TWO_USES[0]} or {TWO_USES[1]} one code per use, and a "
        f"report says which only through its dose, its route or the indication it gives: of the "
        f"{common.plural(total, 'drug record')} of such substances, "
        f"{common.pct(unsaid_all, total)} say none of them{rise}. A filter that counts only "
        "records whose exact class is known would miss them, so Open Altio gives each the class "
        "its uses share, or says it cannot tell, and keeps every class it could be.",
        chart,
        common.DOCUMENTED,
        NB09,
    )
