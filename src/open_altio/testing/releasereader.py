"""Read a release folder only through its files: Parquet, JSON and its views file.

rel = ReleaseReader(release)
rel.rows("SELECT count(*) FROM case_latest_T WHERE dup_kept_T")
rel.case_keys("c.sex = 'M'")       # {"faers/9001001", ...}: the kept cases it matches
rel.case_join("d")                   # the condition tying drug_latest_T d to its case c
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from open_altio.faers.reader import quoted


class ReleaseReader:
    """A release folder opened the way a downstream consumer would."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        self.funnel = json.loads((path / "funnel.json").read_text(encoding="utf-8"))
        self.con = duckdb.connect()
        for table, entry in self.manifest["tables"].items():
            parquet = quoted(str(path / entry["path"]))
            self.con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet({parquet})")
        # the release's own views (the deduplicated set), written against table names
        self.con.execute((path / self.manifest["views"]["file"]).read_text(encoding="utf-8"))

    def rows(self, sql: str, *params: object) -> list[tuple]:
        return self.con.execute(sql, params).fetchall()

    def dicts(self, sql: str, *params: object) -> list[dict]:
        cur = self.con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    def columns(self, table: str) -> list[str]:
        return [r[0] for r in self.con.execute(f"DESCRIBE {table}").fetchall()]

    def step(self, step_id: str) -> dict:
        return next(s for s in self.funnel["steps"] if s["id"] == step_id)

    def case_keys(
        self,
        where: str = "TRUE",
        *params: object,
        duplicates: bool = False,
        eras: tuple[str, ...] = ("legacy", "faers"),
    ) -> set[str]:
        """The cases of `eras` that `where` matches over case_latest_T c, as era/case_key (how
        the explorer addresses a case): the kept ones, or with `duplicates` every one."""
        if not eras:
            return set()
        kept = "TRUE" if duplicates else "c.dup_kept_T"
        marks = ", ".join("?" for _ in eras)
        got = self.rows(
            f"SELECT era_T, case_key_T FROM case_latest_T c WHERE {kept} "
            f"AND era_T IN ({marks}) AND ({where})",
            *eras,
            *params,
        )
        return {f"{era}/{key}" for era, key in got}

    @staticmethod
    def case_join(child: str) -> str:
        """The condition tying row `child` of a child table (drug_latest_T, reac_latest_T, ...)
        to its case, case_latest_T c."""
        return " AND ".join(f"{child}.{k} = c.{k}" for k in ("era_T", "primaryid", "quarter_T"))
