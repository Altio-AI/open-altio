"""The licensed MedDRA part of a release, for people who hold a MedDRA licence.

MedDRA codes, the LLT to PT mapping, everything above PT and SMQs are MSSO's licensed content,
shown only to a viewer the explorer's access hook allows. So they are never written into the
public part of a release (`parquet/`, `manifest.json`, `explorer.duckdb`) but into its own
`licensed/` folder, laid out as src/open_altio/faers/README.md says.

    from open_altio.faers.meddra import build_licensed
    build_licensed("releases/2026Q2", "~/Downloads/MedDRA_29_1_English_v2")

    python -m open_altio.faers meddra --release releases/2026Q2 --meddra <folder>
"""

from .files import (
    FILES,
    VERBATIM_TABLES,
    MeddraRefused,
    ascii_folder,
    check_ascii,
    read_release_file,
)
from .licensed import (
    DERIVED_TABLES,
    KEPT_ON_REBUILD,
    LABEL_CODINGS_FILE,
    LABEL_GROUPS_FILE,
    LABEL_REVIEW_FILES,
    LICENSED_DIR,
    LICENSED_MANIFEST,
    LICENSED_TABLES,
    MEDDRA_DIR,
    Source,
    add_held,
    build_licensed,
    held_versions,
    keep_person_files,
    licensed_dir,
    load,
    map_licensed,
    newest_held,
    older_part,
    older_words,
    read_licensed_manifest,
    report_lines,
    source,
    write_licensed,
    write_licensed_manifest,
)
from .terms import COLUMNS, key_sql, term_key
from .versions import newest, release_date

__all__ = [
    "COLUMNS",
    "DERIVED_TABLES",
    "FILES",
    "KEPT_ON_REBUILD",
    "LABEL_CODINGS_FILE",
    "LABEL_GROUPS_FILE",
    "LABEL_REVIEW_FILES",
    "LICENSED_DIR",
    "LICENSED_MANIFEST",
    "LICENSED_TABLES",
    "MEDDRA_DIR",
    "MeddraRefused",
    "Source",
    "VERBATIM_TABLES",
    "add_held",
    "ascii_folder",
    "build_licensed",
    "check_ascii",
    "held_versions",
    "keep_person_files",
    "key_sql",
    "licensed_dir",
    "load",
    "map_licensed",
    "newest",
    "newest_held",
    "older_part",
    "older_words",
    "read_licensed_manifest",
    "read_release_file",
    "release_date",
    "report_lines",
    "source",
    "term_key",
    "write_licensed",
    "write_licensed_manifest",
]
