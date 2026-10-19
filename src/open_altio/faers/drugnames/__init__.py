"""The drug-name step: each drug record's ingredients, from the DiAna dictionary
and our reviewed corrections (rule drug-names).

    dictionary.py   DiAna's file, checked by its checksum; its key; our names and corrections
    substances.py   drug_substance_T and drug_ingredient_T, built with the release
"""

from .dictionary import DictionaryRefused
from .substances import TABLES, build

__all__ = ["TABLES", "DictionaryRefused", "build"]
