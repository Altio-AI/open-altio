"""Each published question asked of the invented release, the way the contract tests and
scripts/contract_snapshot.py ask it.

    folder = invented_release(scratch)            # built as the `labelled_release` fixture is
    web = TestClient(create_app(folder))
    answered(web, "GET /api/summary")             # the response to ASKED's address for the route
    query_of("GET /api/summary")                  # the same question as its function takes it
    snapshot(web)                                 # {route: the answer's keys}
    renewed(old, snapshot(web), CONTRACT_VERSION) # the snapshot to write, or SnapshotRefused
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from fastapi.testclient import TestClient
from httpx import Response

from open_altio.faers import build_release
from open_altio.testing import fakediana, fakefda
from open_altio.testing.fakelabelflags import add_label_flags
from open_altio.testing.fakemeddra import write_meddra

PRODUCT = "product=acetylsalicylic+acid"
CASE = "faers/9004004"


@dataclass(frozen=True)
class Asked:
    address: str  # its query string included
    body: dict[str, Any] | None = None  # a POST's JSON


ASKED: dict[str, Asked] = {
    "GET /api/me": Asked("/api/me"),
    "GET /api/release": Asked("/api/release"),
    "GET /api/products": Asked("/api/products?q=acetyl"),
    "GET /api/product": Asked(f"/api/product?{PRODUCT}"),
    "GET /api/spellings": Asked(f"/api/spellings?{PRODUCT}"),
    "GET /api/summary": Asked(f"/api/summary?{PRODUCT}"),
    "GET /api/timeline": Asked(f"/api/timeline?{PRODUCT}"),
    "GET /api/events": Asked(f"/api/events?{PRODUCT}"),
    "GET /api/events/group": Asked(
        f"/api/events/group?{PRODUCT}&reaction=Headache&reaction=Nausea"
    ),
    "GET /api/events/prior-quarter": Asked(f"/api/events/prior-quarter?{PRODUCT}"),
    "GET /api/cases": Asked(f"/api/cases?{PRODUCT}"),
    "GET /api/count": Asked(f"/api/count?{PRODUCT}&by=sex"),
    "GET /api/case/{era}/{key}": Asked(f"/api/case/{CASE}"),
    "GET /api/terms": Asked("/api/terms?q=head"),
    "GET /api/smq": Asked("/api/smq?code=96000001"),
    "GET /api/termcounts": Asked("/api/termcounts?pt=headache&pt=nausea"),
    "GET /api/drugs": Asked("/api/drugs?q=acetyl"),
    "GET /api/classes": Asked("/api/classes"),
    "GET /api/exportsize": Asked(f"/api/exportsize?{PRODUCT}"),
    "GET /api/statistics/about": Asked("/api/statistics/about"),
    "GET /api/statistics": Asked("/api/statistics?ingredient=acetylsalicylic+acid"),
    "GET /api/statistics/strata": Asked(
        "/api/statistics/strata?ingredient=acetylsalicylic+acid&reaction=Headache"
    ),
    "GET /api/statistics/group": Asked(
        f"/api/statistics/group?{PRODUCT}&reaction=Headache&reaction=Nausea"
    ),
    "GET /api/statistics/quarters": Asked(
        f"/api/statistics/quarters?{PRODUCT}&screen=%5B%7B%22column%22%3A%22cases%22%2C"
        "%22at_least%22%3A2%7D%5D&rising=prr"
    ),
    "GET /api/events/statistics": Asked(f"/api/events/statistics?{PRODUCT}"),
    "GET /api/events/facts": Asked(f"/api/events/facts?{PRODUCT}"),
    "GET /api/breakdowns": Asked(f"/api/breakdowns?{PRODUCT}&reaction=Headache"),
    "GET /api/labels/product": Asked(f"/api/labels/product?{PRODUCT}"),
    "GET /api/labels/cases": Asked(f"/api/labels/cases?{PRODUCT}"),
    "GET /api/labels/query": Asked(f"/api/labels/query?{PRODUCT}&reaction=Headache"),
    "GET /api/labels/case/{era}/{key}": Asked(f"/api/labels/case/{CASE}"),
    "GET /api/schema": Asked("/api/schema"),
    "GET /api/manifest": Asked("/api/manifest"),
    "POST /api/sql": Asked("/api/sql", {"sql": "SELECT count(*) AS cases FROM case_dedup_T"}),
    "GET /api/downloads": Asked("/api/downloads"),
    "GET /api/export": Asked(f"/api/export?{PRODUCT}&format=csv"),
    "POST /api/sql/download": Asked(
        "/api/sql/download", {"sql": "SELECT count(*) AS cases FROM case_dedup_T", "format": "csv"}
    ),
}


def invented_release(folder: Path) -> Path:
    """The invented release the questions are asked of, built in `folder` as the fixtures build
    `labelled_release`: FDA's invented quarters, the invented DiAna dictionary and MedDRA 29.1,
    then the invented label flags."""
    zips = fakefda.write_input(folder / "zips")
    diana = fakediana.write_dictionary(folder / "diana" / "DiAna_dictionary.csv")
    meddra = write_meddra(folder / "meddra" / "29.1", "29.1")
    releases = folder / "releases"
    releases.mkdir()
    with fakediana.pinned(diana, releases):
        built = build_release(zips, releases, diana_dictionary=diana, meddra_dir=meddra)
    return add_label_flags(built)


def answered(web: TestClient, route: str) -> Response:
    """The response to the address ASKED gives `route`."""
    asked = ASKED[route]
    if route.startswith("POST "):
        return web.post(asked.address, json=asked.body)
    return web.get(asked.address)


def query_of(route: str) -> dict[str, list[str]]:
    """The question ASKED puts to `route` as the route's function takes it: the address's query,
    with its path parameters under their own names."""
    parts = urlsplit(ASKED[route].address)
    query = parse_qs(parts.query)
    template = route.split(" ", 1)[1]
    for name, given in zip(template.split("/"), parts.path.split("/"), strict=True):
        if name.startswith("{"):
            query[name.strip("{}")] = [unquote(given)]
    return query


def keys_of(got: Response) -> list[str]:
    """An answer's keys: a JSON object's own, or its items' for a list of them; none for a
    file."""
    if not got.headers.get("content-type", "").startswith("application/json"):
        return []
    found = got.json()
    if isinstance(found, list):
        return sorted({k for item in found if isinstance(item, dict) for k in item})
    return sorted(found)


def snapshot(web: TestClient) -> dict[str, list[str]]:
    """Every asked route's answer keys."""
    return {route: keys_of(answered(web, route)) for route in ASKED}


class SnapshotRefused(Exception):
    """A snapshot that drops a route or key while the contract's major version stays."""


def major(version: str) -> int:
    return int(version.split(".")[0])


def renewed(old: dict[str, Any] | None, routes: dict[str, list[str]], version: str) -> dict:
    """The snapshot to write: `routes` under contract `version`. Refused when it drops a route
    or a key `old` lists, unless `version`'s major is above `old`'s: a product may rely on
    every name a snapshot lists until the contract's major version changes."""
    if old:
        dropped = [r for r in old["routes"] if r not in routes] + [
            f"{r} {k}" for r, ks in old["routes"].items() for k in ks if k not in routes.get(r, ks)
        ]
        if dropped and major(version) <= major(old["version"]):
            raise SnapshotRefused(
                f"This drops {', '.join(dropped)} from contract {old['version']}. Keep them, or "
                "raise CONTRACT_VERSION's major and say so in the CHANGELOG."
            )
    return {"version": version, "routes": routes}


__all__ = [
    "ASKED",
    "Asked",
    "SnapshotRefused",
    "answered",
    "invented_release",
    "keys_of",
    "major",
    "query_of",
    "renewed",
    "snapshot",
]
