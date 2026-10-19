"""Pipeline: load FAERS as FDA published it, derive the `_T` objects, build a release.

    from open_altio.faers import build_release
    build_release("zips", "releases")  # -> releases/2026Q2

See src/open_altio/faers/README.md for its modules and the release folder's layout.
"""

from .explorer_db import EXPLORER_TABLES, build_explorer_db
from .reader import EXPLORER_FILE, open_explorer, open_release, read_manifest, register_release
from .release import (
    DERIVED_TABLES,
    DERIVED_VIEWS,
    FORMAT_VERSION,
    FUNNEL_FILE,
    MANIFEST_FILE,
    PARQUET_DIR,
    RAW_TABLES,
    VIEWS_FILE,
    ReleaseError,
    build_release,
)
from .schema import COLUMN_UNIFICATION, RAW_COLUMNS, unified_name
from .sources import SourceError

__all__ = [
    "COLUMN_UNIFICATION",
    "DERIVED_TABLES",
    "DERIVED_VIEWS",
    "EXPLORER_FILE",
    "EXPLORER_TABLES",
    "FORMAT_VERSION",
    "FUNNEL_FILE",
    "MANIFEST_FILE",
    "PARQUET_DIR",
    "RAW_COLUMNS",
    "RAW_TABLES",
    "ReleaseError",
    "SourceError",
    "VIEWS_FILE",
    "build_explorer_db",
    "build_release",
    "open_explorer",
    "open_release",
    "read_manifest",
    "register_release",
    "unified_name",
]
