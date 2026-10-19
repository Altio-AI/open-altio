"""The label dictionary: each FDA label coded into MedDRA once, by fixed rules, then
compared with FAERS reactions (rules label-dictionary and label-flags).

    from open_altio.faers.labeldict import build_label_terms, build_label_flags, build_release_flags
    build_label_terms("releases/2026Q2")                 # into licensed/meddra/<version>/
    build_label_flags("releases/2026Q2", [("1234", "by_mouth", "Nausea")])
    build_release_flags("releases/2026Q2")              # the pairs from its drug records

See README.md in this folder.
"""

from .build import TERMS, UNCERTAIN_FILE, build_label_terms
from .coding import ITEM_FIELDS, TERM_COLUMNS, Coded, LabelCoder, SectionRow, item_id
from .codings import CODINGS_FILE, apply_codings, read_codings
from .flagbuild import FLAGS, GROUPS_FILE, build_label_flags, build_release_flags
from .flags import FLAG_COLUMNS, Comparison, Label, Meddra, compare, resolve
from .ime import read_ime
from .release_io import CANDIDATES, LABELS, SECTIONS, LabelRefused, col
from .terms import Term

__all__ = [
    "CANDIDATES",
    "CODINGS_FILE",
    "FLAGS",
    "FLAG_COLUMNS",
    "GROUPS_FILE",
    "ITEM_FIELDS",
    "LABELS",
    "SECTIONS",
    "TERMS",
    "TERM_COLUMNS",
    "UNCERTAIN_FILE",
    "Coded",
    "Comparison",
    "Label",
    "LabelCoder",
    "LabelRefused",
    "Meddra",
    "SectionRow",
    "Term",
    "apply_codings",
    "build_label_flags",
    "build_label_terms",
    "build_release_flags",
    "col",
    "compare",
    "item_id",
    "read_codings",
    "read_ime",
    "resolve",
]
