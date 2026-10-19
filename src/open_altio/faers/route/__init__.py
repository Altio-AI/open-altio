"""The route step: one cleaned route per drug record (rule drug-route).

    tables.py   the reviewed tables in mappings/faers/route/, read and checked
    clean.py    drug_route_T, built with the release

    from open_altio.faers.route import COLUMNS, TABLE, RouteTables, label_families

`drug_route_T` has one row per drug record (era_T, primaryid, quarter_T,
drug_seq): route_T, FDA's route as an E2B route code; route_source_T, which of
FDA's fields said something; route_families_T, every family the record could be
in; route_family_T, that family when there is exactly one. A label's families
come from its route names through the same table: `label_families(routes)`, or
`RouteTables.read().label_families(routes)` for many labels. A report matches a
label when their families overlap.
"""

from .clean import KEY, SOURCES, TABLE, build
from .tables import RouteTableError, RouteTables, families, key, label_families

COLUMNS = ("route_T", "route_source_T", "route_family_T", "route_families_T")

__all__ = [
    "COLUMNS",
    "KEY",
    "SOURCES",
    "TABLE",
    "RouteTableError",
    "RouteTables",
    "build",
    "families",
    "key",
    "label_families",
]
