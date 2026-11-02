"""The `format` each JSON document of a release names itself by, so a reader knows what it holds,
and the sources and format versions of a release this version reads.

Releases built before the project took its one name carry earlier names. Readers take those as
today's (`with_current_name`), so a release built then still opens.
"""

from __future__ import annotations

RELEASE = "open-altio-release"  # manifest.json
LICENSED = "open-altio-licensed"  # licensed/manifest.json
METHODS = "open-altio-methods"  # methods.json
RELEASES = "open-altio-releases"  # the index of published releases

FAERS = "faers"
SOURCES = (FAERS,)  # the public databases a release is built from, by manifest `source`
# Version 1 names no `source`: it is FAERS. Version 2 names its source.
READABLE_VERSIONS = (1, 2)

EARLIER = {
    "altio-open-faers-release": RELEASE,
    "altio-open-faers-licensed": LICENSED,
    "altio-open-faers-methods": METHODS,
    "altio-open-faers-releases": RELEASES,
}


def with_current_name(doc: dict) -> dict:
    """The document, its format under today's name."""
    named = doc.get("format")
    return {**doc, "format": EARLIER[named]} if named in EARLIER else doc
