"""RxNorm's links from a product to its ingredients (rule label-choice).

DailyMed maps each label to product codes (SCD, SBD and packs). A label is
keyed by ingredient, so each product code is followed through RxNorm's own
relationships to its ingredients (IN), and a set of two or more ingredients
to RxNorm's code for that set (MIN).
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

_FILES = ("RXNCONSO.RRF", "RXNREL.RRF")
_READ = "read_csv('{path}', delim='|', header=false, all_varchar=true, quote='', escape='')"

# RRF columns by position (RxNorm's documentation, "RXNCONSO" and "RXNREL").
# A relationship row reads "RXCUI2 <rela> RXCUI1": a row with RXCUI1 an
# ingredient, RELA has_ingredient and RXCUI2 a component says the component
# has that ingredient.
_LOAD = """
CREATE TEMP TABLE conso AS
  SELECT DISTINCT column00 AS rxcui, column12 AS tty, column14 AS str
  FROM {conso} WHERE column11 = 'RXNORM' AND column16 = 'N';
CREATE TEMP TABLE rel AS
  SELECT DISTINCT column00 AS rxcui1, column04 AS rxcui2, column07 AS rela
  FROM {rel} WHERE column10 = 'RXNORM'
    AND column07 IN ('contains', 'consists_of', 'has_ingredient', 'has_ingredients');
"""

# A product's drugs: an SCD or SBD is its own drug; a pack (GPCK, BPCK)
# contains drugs. A drug consists of components, each with one ingredient.
_PRODUCT_INGREDIENTS = """
WITH drug AS (
  SELECT rxcui AS product, rxcui AS drug FROM conso WHERE tty IN ('SCD', 'SBD')
  UNION
  SELECT rxcui2, rxcui1 FROM rel WHERE rela = 'contains'
)
SELECT DISTINCT d.product, i.rxcui1
FROM drug d
JOIN rel c ON c.rela = 'consists_of' AND c.rxcui2 = d.drug
JOIN rel i ON i.rela = 'has_ingredient' AND i.rxcui2 = c.rxcui1
JOIN conso n ON n.rxcui = i.rxcui1 AND n.tty = 'IN'
"""

# A MIN is linked to the SCDs holding exactly its ingredients.
_MIN_DRUGS = (
    "SELECT DISTINCT rxcui1, rxcui2 FROM rel WHERE rela = 'has_ingredients' "
    "ORDER BY TRY_CAST(rxcui1 AS BIGINT), rxcui1"
)
_NAMES = "SELECT rxcui, min(str) FROM conso WHERE tty IN ('IN', 'MIN') GROUP BY rxcui"
# An ingredient's name, case-blind; a name two ingredients share names neither.
_INGREDIENT_NAMES = (
    "SELECT lower(str), min(rxcui) FROM conso WHERE tty = 'IN' "
    "GROUP BY 1 HAVING count(DISTINCT rxcui) = 1"
)


@dataclass(frozen=True)
class RxNorm:
    ingredients: dict[str, frozenset[str]]  # product code -> ingredient codes
    min_of: dict[frozenset[str], str]  # ingredient codes -> MIN code
    names: dict[str, str]  # IN or MIN code -> RxNorm's name
    named: dict[str, str]  # an ingredient's name, lower case -> its IN code

    def codes_named(self, names: list[str]) -> frozenset[str]:
        """The ingredient codes of RxNorm names, compared case-blind."""
        wanted = {n.lower() for n in names}
        return frozenset(c for c, n in self.names.items() if n.lower() in wanted)

    def key(
        self, products: list[str], set_aside: frozenset[str] = frozenset()
    ) -> tuple[str | None, str]:
        """The label's RxNorm key for its product codes, and how it was found:
        `IN`, `MIN`, `no_code` or `no_min`. Ingredients in `set_aside` (a
        kit's alcohol pad, a pack's placebo tablets) do not count while the
        label has any other."""
        found = [self.ingredients[p] for p in products if p in self.ingredients]
        if not found:
            return None, "no_code"
        together = frozenset().union(*found)
        together = together - set_aside or together
        return self._set(together)

    def _set(self, codes: frozenset[str]) -> tuple[str | None, str]:
        if len(codes) == 1:
            return next(iter(codes)), "IN"
        code = self.min_of.get(codes)
        return (code, "MIN") if code else (None, "no_min")

    def key_named(self, names: list[tuple[str, ...]]) -> tuple[str | None, str]:
        """A label's RxNorm key from its own active ingredients: each is a
        tuple of names to try in order, and the first that is exactly one
        RxNorm ingredient's name gives its code. `no_name` when one of them
        names no ingredient, else as `key`."""
        codes = set()
        for tried in names:
            code = next((self.named[n] for n in tried if n in self.named), None)
            if code is None:
                return None, "no_name"
            codes.add(code)
        return self._set(frozenset(codes)) if codes else (None, "no_name")


def read_rxnorm(zip_path: Path) -> RxNorm:
    """Read RxNorm's prescribable release zip as NLM ships it."""
    work = Path(tempfile.mkdtemp(prefix="open-altio-rxnorm-"))
    try:
        paths = {}
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                name = info.filename.rsplit("/", 1)[-1]
                if name in _FILES:
                    paths[name] = work / name
                    with z.open(info) as src, open(paths[name], "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
        missing = [f for f in _FILES if f not in paths]
        if missing:
            raise ValueError(f"{zip_path.name} lacks {', '.join(missing)}")
        con = duckdb.connect()
        con.execute(
            _LOAD.format(
                conso=_READ.format(path=paths["RXNCONSO.RRF"]),
                rel=_READ.format(path=paths["RXNREL.RRF"]),
            )
        )
        ingredients: dict[str, set[str]] = {}
        for product, ingredient in con.execute(_PRODUCT_INGREDIENTS).fetchall():
            ingredients.setdefault(product, set()).add(ingredient)
        frozen = {p: frozenset(s) for p, s in ingredients.items()}
        sets_of_min: dict[str, set[frozenset[str]]] = {}
        for min_code, drug in con.execute(_MIN_DRUGS).fetchall():
            if drug in frozen:
                sets_of_min.setdefault(min_code, set()).add(frozen[drug])
        # A MIN whose drugs disagree on the set would be a guess, so it is not
        # used; two MINs for one set (none today) give the lower code, read first.
        min_of: dict[frozenset[str], str] = {}
        for min_code, sets in sets_of_min.items():
            if len(sets) == 1:
                min_of.setdefault(next(iter(sets)), min_code)
        names = dict(con.execute(_NAMES).fetchall())
        named = dict(con.execute(_INGREDIENT_NAMES).fetchall())
        con.close()
        return RxNorm(frozen, min_of, names, named)
    finally:
        shutil.rmtree(work, ignore_errors=True)
