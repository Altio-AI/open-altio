"""Every count of a counted question (/api/count) checked by a second count (recount.py), made
apart from filters.py and the explorer database over the release's own Parquet tables: the two
agree for every `by` and for the filters in combination, with and without MedDRA and under Label
status; a difference planted in either one is answered as a difference with both counts, never
as agreeing; and every parameter filters.py reads is one the second count reads, so a new filter
cannot slip past it. The count written as one query (`sql_of`) holds each value as a constant
that is exactly that value, and gives what the count with its values passed apart gives.

Run over the invented release (`release`), the same with MedDRA (`licensed_release`) and with
invented label flags (`labelled_release`).
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from open_altio.explorer import counted, explore, filters, recount
from open_altio.explorer.access import LOCAL
from open_altio.explorer.questions import open_release_data
from open_altio.testing.countedquestions import DRUG, QUESTIONS, REACTIONS, by_value

BY = counted.choices()


def agreed(got: dict[str, Any]) -> None:
    """The answer's check agrees with its counts, value for value, and holds cases."""
    check = got["check"]
    assert check["agrees"] is True and check["differences"] == [] and check["unread"] == []
    assert check["total"] == got["total"] > 0
    assert by_value(got["by"], check["counts"]) == by_value(got["by"], got["counts"])


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: "&".join(q) or "nothing")
def test_the_two_counts_agree_for_every_by_and_filters_in_combination(question, client, ask):
    for by in BY:
        if by in question or (by == "outcome" and "outcome" in question):
            continue  # refused: a case can give several outcomes
        agreed(ask(client, "/api/count", by=by, **question))


@pytest.mark.parametrize("question", REACTIONS, ids=lambda q: "&".join(q))
def test_with_meddra_the_two_counts_agree_by_todays_preferred_terms(question, licensed_client, ask):
    for by in BY:
        agreed(ask(licensed_client, "/api/count", by=by, **question))


def label_questions(client: TestClient, ask: Any) -> int:
    """Every flag ticked alone, none, and all, for each drug with flags and both units: each
    count agrees with the second; how many questions held cases."""
    held = 0
    ticks = [[t] for t in filters.label_outcomes()] + [[filters.nothing_ticked()]]
    for drug in (DRUG, "valsartan", "sacubitril;valsartan", "metformin", "digoxin"):
        for unit in ("any", "exact"):
            for ticked in [*ticks, filters.label_outcomes()]:
                question = {"product": drug, "unit": unit, "label": ticked, "dedup": "all"}
                for by in ("sex", "event"):
                    got = ask(client, "/api/count", by=by, **question)
                    assert got["check"]["agrees"] is True, (question, got["check"])
                    assert got["check"]["total"] == got["total"]
                    held += got["total"] > 0
    return held


def test_under_label_status_the_two_counts_agree(label_client, ask):
    assert label_questions(label_client, ask) > 0


def test_label_status_agrees_where_a_code_names_another_drug_and_an_ingredient_has_no_label(
    ask, explorer_app, labelled_release, tmp_path
):
    """Metformin's own code taken away, so a record of it alone keeps its own; one aspirin
    record listed as coded as another drug, so it is read as one with no code."""
    copy = tmp_path / labelled_release.name
    shutil.copytree(labelled_release, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    tables = manifest["tables"]
    path = copy / tables["ingredient_rxnorm_T"]["path"]
    sql = "SELECT * REPLACE (if(ingredient_T = 'metformin', NULL, rxcui_T) AS rxcui_T) FROM "
    pq.write_table(duckdb.sql(f"{sql} read_parquet('{path}')").to_arrow_table(), path)
    drugs = pq.read_table(copy / tables["drug_latest_T"]["path"]).to_pylist()
    names = ("era_T", "primaryid", "quarter_T", "drug_seq")
    key = next({k: d[k] for k in names} for d in drugs if d["drugname"] == "ASPIRIN")
    pq.write_table(pa.Table.from_pylist([key]), copy / "parquet" / "label_other_drug_T.parquet")
    tables["label_other_drug_T"] = {"path": "parquet/label_other_drug_T.parquet", "rows": 1}
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert label_questions(TestClient(explorer_app(copy)), ask) > 0


def sexes(release: Any, **more: list[str]) -> dict[str, int]:
    """The drug's cases by sex, as the first count gives them, asked in this process (the app
    keeps each answer it gave)."""
    asked = {"product": [DRUG], "by": ["sex"], **more}
    return {v: n for v, n, _ in counted.count(open_release_data(release, LOCAL), asked)["counts"]}


def test_a_difference_in_the_first_count_answers_both_counts_never_agreeing(
    client, ask, release, monkeypatch
):
    (value, n), *rest = sexes(release).items()
    real = counted._rows

    def one_more(*args: Any) -> list[list[Any]]:
        (v, cases, q), *others = real(*args)
        return [[v, cases + 1, q], *others]

    monkeypatch.setattr(counted, "_rows", one_more)
    check = ask(client, "/api/count", product=DRUG, by="sex")["check"]
    assert check["agrees"] is False and check["differences"] == [[value, n + 1, n]]


def test_a_difference_in_the_second_count_answers_both_counts_never_agreeing(
    client, ask, release, monkeypatch
):
    """The second count planted to count the probable duplicates set aside too."""
    kept, every = sexes(release, dedup=["kept_only"]), sexes(release, dedup=["all"])
    assert kept != every
    monkeypatch.setitem(recount.CASES, True, recount.CASES[False])
    check = ask(client, "/api/count", product=DRUG, by="sex", dedup="kept_only")["check"]
    assert check["agrees"] is False and check["total"] == sum(every.values())
    differ = [[v, kept.get(v, 0), n] for v, n in every.items() if kept.get(v, 0) != n]
    assert sorted(check["differences"]) == sorted(differ) != []


def test_totals_that_differ_never_agree_though_every_value_does(client, ask, monkeypatch):
    def more(self: recount.Statement) -> str:
        return f"{self.cases} SELECT count(*) + 1 AS cases FROM picked"

    monkeypatch.setattr(recount.Statement, "total", property(more))
    got = ask(client, "/api/count", product=DRUG, by="sex")
    assert got["check"]["differences"] == [] and got["check"]["agrees"] is False
    assert got["check"]["total"] == got["total"] + 1


class Recorded(dict):
    """A question that records every name read from it."""

    def __init__(self, given: dict[str, list[str]] | None = None) -> None:
        super().__init__(given or {})
        self.read: set[str] = set()

    def get(self, name: str, default: Any = None) -> Any:
        self.read.add(name)
        return super().get(name, default)


def test_every_parameter_filters_reads_is_read_by_the_second_count():
    """A filter added to filters.py fails here until the second count reads it too."""
    question = Recorded()
    filters.parse(question)
    assert question.read and question.read <= set(recount.READS)


def test_a_question_the_second_count_does_not_read_is_never_said_to_agree(
    client, ask, licensed_release
):
    """What a page's question reads beyond READS: MedDRA's SMQs and system organ classes and
    WHO's classes, which the second count leaves to the first; any of them, or any other name,
    leaves the counts unchecked and says which."""
    question = Recorded({"product": [DRUG], "dprod": ["valsartan"]})
    explore.scope(open_release_data(licensed_release, LOCAL), question)
    assert question.read - set(recount.READS) == {"smq", "soc", "atc", "atc_out"}
    check = ask(client, "/api/count", product=DRUG, by="sex", points="3")["check"]
    assert check == {
        "counts": None,
        "total": None,
        "agrees": None,
        "differences": None,
        "unread": ["points"],
    }


# the count as one query ----------------------------------------------------------------------

# values that would end a string, or read as SQL or as another value's name, were they not quoted
SNEAKY = [
    "it's",
    "x'); DELETE FROM case_latest_T; --",
    "' OR '1'='1",
    "''",
    "$v2",
    "$$ dollar $$",
    "back\\slash \\'",
    "a\0b",
    "line\nbreak /* comment",
    "É 名前 \u2028",
]


@pytest.mark.parametrize("given", [*SNEAKY, date(2012, 5, 3)], ids=repr)
def test_a_value_is_written_as_one_constant_that_is_exactly_itself(given):
    written = f"SELECT {recount.literal(given)}"
    (one,) = duckdb.extract_statements(written)
    assert one.type == duckdb.StatementType.SELECT
    assert duckdb.sql(written).fetchall() == [(given,)]


def test_the_query_gives_what_the_count_with_its_values_passed_apart_gives():
    """Eleven values, so $v1 is never read as the start of $v11, and one value that is another's
    name, so a value is never written in twice."""
    values = [*SNEAKY, "US"]
    con = duckdb.connect()
    con.execute("CREATE TABLE countries (sex_T VARCHAR, country_T VARCHAR)")
    con.executemany("INSERT INTO countries VALUES (?, ?)", [["F", v] for v in values[::2]])
    con.executemany("INSERT INTO countries VALUES (?, ?)", [["M", "US"], ["M", "FR"]])
    marks = recount.Values()
    picked = f"SELECT * FROM countries c WHERE {marks.among('c.country_T', values)}"
    made = recount.Statement("sex", f"WITH picked AS ({picked})", marks.params)
    assert len(made.params) == 11 and made.params["v1"] == "it's" and made.params["v5"] == "$v2"
    passed_apart = con.execute(made.counts, made.params).fetchall()
    assert passed_apart == [("F", 6), ("M", 1)]
    assert con.execute(recount.sql_of(made)).fetchall() == passed_apart
    assert "$v" not in recount.sql_of(made).replace("'$v2'", "")
