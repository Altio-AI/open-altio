"""Who is viewing, and what they may see: the one question the explorer asks
about people. The explorer is handed an `Access`; it never decides itself.

    LocalAccess()        one person on their own machine, who sees everything the release holds
    a hosted service's   sign-in, approval, and its own policy for MedDRA and WHO's classes

The Viewer it names also says, in its own words, why someone who asks for an
SMQ is shown none, and whether reactions are named by the release's MedDRA
version or as FDA wrote them. An Access also names the page modules a host adds to the
page (its own screens), the terms a filtered export is made under, and whether
the rules can be changed and the release rebuilt here, and hears what each
viewer did with the data, for a host that keeps a usage log.

What it hears is a closed list, part of Open Altio's written contract
(docs/reference/access-hook.md): the kinds the server announces (`RECORDED`, through
`Explorer.announce`) and the kinds the page reports to a host's page modules (`REPORTED`, the
same list as ui/host.js). A product announces kinds of its own from its own code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import Request


@dataclass(frozen=True)
class Viewer:
    id: str  # who, as the usage log and the one-query-at-a-time SQL slot know them
    meddra: bool  # MedDRA's licensed part (SMQs, lower-level terms), where the release has one
    who: bool  # WHO's drug classes on the pages: the class filter and each drug's class
    sql: bool = True  # read-only SQL, and its whole result as a file
    exports: bool = True  # the filtered export
    statistics: bool = True  # the Statistics tab: EBGM, PRR, ROR, RRR and IC per pair
    # WHO's drug classes in files: the class tables in SQL and the Tables page, and each drug's
    # class in a filtered export. A host may give it apart from `who`, as a licence asks.
    who_files: bool = False
    # reactions named and counted by the release's MedDRA version, each under its current PT,
    # for a viewer without `meddra` too; False: as FDA wrote them, as in a release without MedDRA
    todays_names: bool = True
    # the line the pages show where reactions are listed, for a viewer shown FDA's text in a
    # release that holds MedDRA
    fda_text_line: str = ""
    # why they are shown no SMQs, for when they ask for one (a link with an SMQ in it)
    why_no_smqs: str = "SMQs come from MedDRA's licensed part, which is not open to you here."
    # why they are shown no drug classes, for when they ask for one, in a release that holds them
    why_no_classes: str = "WHO's drug classes are not open to you here."

    @property
    def named_by_meddra(self) -> bool:
        """Whether this viewer's reactions are named by the release's MedDRA version."""
        return self.meddra or self.todays_names


# What the explorer announces to the access hook's `record`: each kind with its fields.
RECORDED: dict[str, tuple[str, ...]] = {
    "search": ("search", "words", "results"),  # which search, the words typed, results shown
    "export_started": ("rows",),  # the export dialog opened, with the rows it would write
    # a filtered export written: the release, its query and the filters in words, the format,
    # its rows and the moment it was made
    "filtered_export": ("release", "query", "described", "format", "rows", "at"),
    # a SQL query: its text, how it ended, its rows and seconds, and the format of a whole result
    # downloaded
    "sql": ("sql", "outcome", "rows", "seconds", "download"),
}
# the fields a kind carries only sometimes
OPTIONAL: dict[str, tuple[str, ...]] = {"sql": ("download",)}

# What the page tells a host's page modules (ui/host.js `REPORTED`, `host.report`), each kind
# with the fields of its detail: what the person did that the server cannot see.
REPORTED: dict[str, tuple[str, ...]] = {
    "screen": ("screen", "tab", "product"),  # a screen or a tab opened
    "rule": ("rule",),  # a rule read on How we clean FAERS
    # a search's result picked: an open name as `picked`, a licensed level or a class by its
    # `level` and `code`
    "pick": ("search", "words", "picked", "level", "code"),
    "improve_opened": ("page",),  # Improve this opened, on that page
}


class ContractError(Exception):
    """A name used that the written contract does not list."""


class Access(Protocol):
    @property
    def modules(self) -> Sequence[str]:
        """Page modules loaded after the explorer's own, by their address."""
        ...

    @property
    def terms(self) -> Mapping[str, Any]:
        """What a filtered export's manifest says about the terms it is used under."""
        ...

    @property
    def edits_rules(self) -> bool:
        """Whether the methods page saves choices beside the release and rebuilds it."""
        ...

    def viewer(self, request: Request) -> Viewer:
        """The person asking, or an HTTPException (401 or 403) when nobody may view."""
        ...

    def about(self, request: Request, viewer: Viewer) -> dict[str, Any]:
        """What /api/me adds about the viewer for the host's own screens."""
        ...

    def record(self, viewer: Viewer, kind: str, **event: Any) -> None:
        """What the viewer did with the data: one of the kinds in `RECORDED`, with its fields."""
        ...


# They may see everything, so they lack SMQs only when the release holds no MedDRA.
LOCAL = Viewer(
    id="local",
    meddra=True,
    who=True,
    who_files=True,
    why_no_smqs=(
        "SMQs come from MedDRA, and this release holds none. If your organisation subscribes to "
        "MedDRA, start the explorer with your own MedDRA files to see them: "
        "open-altio serve --meddra <folder>."
    ),
)


class LocalAccess:
    """One person, on the machine the explorer runs on. They see the release's
    licensed MedDRA part when they built one from their own MedDRA files, and
    WHO's drug classes when the release carries them. They change the rules of
    their own copy and rebuild it. Nothing they do is recorded or sent anywhere."""

    modules: Sequence[str] = ()
    terms: Mapping[str, Any] = {}
    edits_rules: bool = True

    def viewer(self, request: Request) -> Viewer:
        return LOCAL

    def about(self, request: Request, viewer: Viewer) -> dict[str, Any]:
        return {}

    def record(self, viewer: Viewer, kind: str, **event: Any) -> None:
        pass


__all__ = [
    "LOCAL",
    "OPTIONAL",
    "RECORDED",
    "REPORTED",
    "Access",
    "ContractError",
    "LocalAccess",
    "Viewer",
]
