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

    @property
    def named_by_meddra(self) -> bool:
        """Whether this viewer's reactions are named by the release's MedDRA version."""
        return self.meddra or self.todays_names


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
        """What the viewer did with the data, and its details: kind "search" (search, words,
        results), "export_started" (rows), "filtered_export" or "sql"."""
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


__all__ = ["LOCAL", "Access", "LocalAccess", "Viewer"]
