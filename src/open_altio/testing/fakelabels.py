"""An invented labels folder, laid out as `labels-fetch` leaves the real one.

    from open_altio.testing.fakelabels import write_labels
    folder = write_labels(tmp_path / "labels")

Two parts of a prescription release (each label a zip of its own holding its
SPL XML and a picture), DailyMed's labels-to-RxNorm file and an RxNorm
release with only the rows the labels step reads; `daily_zip` makes one day's
update file, as DailyMed publishes the labels changed between releases. Every
drug, company and code is made up; codes, sections and dates come from the
rules, so the fake follows them when they change.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from open_altio import rulebook

# Invented RxNorm codes: ingredients, their combination, the products.
ZENTOPRINE, VALMOREX, QUORBITAL, ZEN_VAL = "9001", "9002", "9003", "9101"
ZEN_TAB, ZEN_EYE, ZENTORA_TAB, VAL_TAB, ZEN_VAL_TAB, ZEN_VAL_PACK, QUO_TAB = (
    "9201",
    "9202",
    "9203",
    "9204",
    "9205",
    "9206",
    "9207",
)
# A kit's alcohol pad: an ingredient rule label-choice does not count beside others.
PAD, PAD_PRODUCT = "9004", "9208"
# An injection sold as a kit with an ethanol pad, which RxNorm names ethanol and the label alcohol
TEDUVARIN, ETHANOL, TED_VIAL, ETHANOL_PAD = "9005", "9006", "9209", "9210"
# Ingredients whose only labels the mapping file misses, found by the labels' own ingredients
PLOVIZUMAB, LUMETRINE = "9007", "9008"
# Two ingredients sold in several forms, one label reaching many families through TOPICAL
LIDORINE, DICLORIN = "9009", "9010"
LID_PATCH, LID_EYE, LID_MOUTH, DIC_GEL, DIC_PATCH, DIC_EYE = (
    "9211",
    "9212",
    "9213",
    "9214",
    "9215",
    "9216",
)
NOT_IN_RXNORM = "9999"

_SPL_DOC = "34391-3"


def _code(name: str) -> str:
    """A section's LOINC code, by the name rule label-sections gives it."""
    return next(
        str(k) for k, v in rulebook.value("label-sections", "sections").items() if v == name
    )


def _category(name: str) -> str:
    return next(
        k for k, v in rulebook.value("label-choice", "marketing_categories").items() if v == name
    )


def _years_after_recent(years: int) -> date:
    """A date `years` from rule label-choice's cut-off; negative is before it."""
    recent = rulebook.value("label-choice", "recent_from")
    return recent.replace(year=recent.year + years)


def _section(code: str, title: str, body: str = "", inner: str = "") -> str:
    return (
        f'<component><section><code code="{code}"/><title>{title}</title>'
        f"<text>{body}</text>{inner}</section></component>"
    )


def rich_sections() -> str:
    """A label in FDA's current format, with every way of writing text."""
    return "".join(
        [
            _section(
                _code("boxed_warning"),
                "WARNING: SERIOUS LIVER INJURY",
                '<paragraph>Zentora can cause <content styleCode="bold">severe liver'
                "\n   injury</content>.</paragraph>",
            ),
            _section(
                _code("indications"),
                "1 INDICATIONS AND USAGE",
                "<paragraph>Zentora is indicated for chronic plaque fatigue.</paragraph>",
            ),
            _section(
                "34068-7",
                "2 DOSAGE AND ADMINISTRATION",
                "<paragraph>Not read.</paragraph>",
            ),
            _section(
                _code("contraindications"),
                "4 CONTRAINDICATIONS",
                "<list><item><caption>&#8226;</caption>Known hypersensitivity to zentoprine"
                "</item></list>",
            ),
            '<component><section><code code="' + _code("warnings_and_precautions") + '"/>'
            "<title>5 WARNINGS AND PRECAUTIONS</title><excerpt><highlight><text><paragraph>"
            "Highlights copy of the liver warning.</paragraph></text></highlight></excerpt>"
            + _section(
                str(rulebook.value("label-sections", "unclassified_section")),
                "5.1 Hepatotoxicity",
                "<paragraph>Monitor liver tests.<br/>Stop if jaundice.</paragraph>"
                '<renderMultiMedia referencedObject="fig1"/>',
            )
            + "</section></component>",
            _section(
                _code("adverse_reactions"),
                "6 ADVERSE REACTIONS",
                "<paragraph>Table 1 lists reactions.</paragraph><table>"
                "<caption>Table 1: Adverse reactions in 2% or more</caption>"
                "<thead><tr><th/><th>Zentora N=100</th><th>Placebo N=100</th></tr></thead>"
                "<tfoot><tr><td>* Includes nausea and vomiting</td></tr></tfoot>"
                "<tbody><tr><td>Nausea*</td><td>12%</td><td>3%</td></tr>"
                "<tr><td>Headache</td><td>8%</td><td>7%</td></tr></tbody></table>",
            ),
        ]
    )


def old_format_sections() -> str:
    """The older format: Warnings and Precautions apart, with a subsection of
    another wanted section inside Precautions."""
    inner = _section(
        "34073-7",
        "Drug Interactions",
        "<paragraph>Avoid strong inhibitors.</paragraph>",
    )
    inner += _section(
        _code("adverse_reactions"),
        "Adverse Reactions",
        "<paragraph>Dizziness.</paragraph>",
    )
    return _section(
        _code("warnings"), "WARNINGS", "<paragraph>May cause drowsiness.</paragraph>"
    ) + (
        _section(
            _code("precautions"),
            "PRECAUTIONS",
            "<paragraph>General care.</paragraph>",
            inner,
        )
    )


def unclassified_sections() -> str:
    """Sections filed as unclassified only, whatever their headings say."""
    code = str(rulebook.value("label-sections", "unclassified_section"))
    return _section(code, "WARNINGS", "<paragraph>Sedation.</paragraph>")


@dataclass(frozen=True)
class FakeLabel:
    set_id: str
    title: str
    category: str  # NDA, BLA, ANDA or a code rule label-choice does not name
    number: str  # one application, or a kit's several separated by spaces
    effective: date
    routes: tuple[str, ...]
    form: str
    products: tuple[str, ...]  # RxNorm product codes in the mapping file
    sections: str
    part: int
    pad_route: str = ""  # a kit's alcohol pad, as a part of its own given by this route
    pad_name: str = ""  # the pad's active ingredient as the label writes it, if not the rule's
    # the active ingredients the label lists, each as (substance, active moiety)
    actives: tuple[tuple[str, str], ...] = ()
    version: int = 3


def labels() -> list[FakeLabel]:
    s = "{:08d}-aaaa-4bbb-8ccc-{:012d}"
    return [
        FakeLabel(
            s.format(1, 1),
            "ZENTORA (zentoprine) tablets",
            "NDA",
            "NDA020001",
            _years_after_recent(4),
            ("ORAL",),
            "TABLET, FILM COATED",
            (ZENTORA_TAB, PAD_PRODUCT),
            rich_sections(),
            1,
            pad_route="TOPICAL",
        ),
        FakeLabel(
            s.format(2, 2),
            "Zentoprine tablets",
            "ANDA",
            "ANDA200001",
            _years_after_recent(5),
            ("ORAL",),
            "TABLET",
            (ZEN_TAB,),
            old_format_sections(),
            1,
        ),
        FakeLabel(
            s.format(3, 3),
            "ZENTORA EYE (zentoprine) solution",
            "NDA",
            "NDA013000",
            _years_after_recent(3),
            ("OPHTHALMIC",),
            "SOLUTION",
            (ZEN_EYE,),
            old_format_sections(),
            1,
        ),
        FakeLabel(
            s.format(4, 4),
            "Zentoprine tablets, repackaged",
            "NDA",
            "NDA019000",
            _years_after_recent(-5),
            ("ORAL",),
            "TABLET",
            (ZEN_TAB,),
            rich_sections(),
            1,
        ),
        FakeLabel(
            s.format(5, 5),
            "Valmorex tablets",
            "ANDA",
            "ANDA200500",
            _years_after_recent(2),
            ("ORAL",),
            "TABLET",
            (VAL_TAB,),
            old_format_sections(),
            2,
        ),
        FakeLabel(
            s.format(6, 6),
            "ZENVAL (zentoprine and valmorex) tablets",
            "NDA",
            "NDA021000",
            _years_after_recent(1),
            ("ORAL",),
            "TABLET",
            (ZEN_VAL_TAB,),
            old_format_sections(),
            2,
        ),
        FakeLabel(
            s.format(7, 7),
            "Quorbital tablets",
            "C00000",
            "",
            _years_after_recent(-8),
            ("ORAL",),
            "TABLET",
            (QUO_TAB,),
            unclassified_sections(),
            2,
        ),
        FakeLabel(
            s.format(8, 8),
            "Unmapped tablets",
            "ANDA",
            "ANDA209999",
            _years_after_recent(1),
            ("ORAL",),
            "TABLET",
            (NOT_IN_RXNORM,),
            rich_sections(),
            2,
        ),
        FakeLabel(
            s.format(9, 9),
            "ZENTOPRINE tablets, every section unclassified",
            "NDA",
            "NDA010000",
            _years_after_recent(4),
            ("ORAL",),
            "TABLET",
            (ZEN_TAB,),
            unclassified_sections(),
            2,
        ),
        FakeLabel(
            s.format(10, 10),
            "Zentoprine convenience kit, with swabs and another drug",
            "NDA",
            "NDA015000 ANDA200001",
            _years_after_recent(4),
            ("INTRAVENOUS", "ORAL", "TOPICAL"),
            rulebook.value("label-choice", "kit_form"),
            (ZEN_TAB,),
            rich_sections(),
            2,
            pad_route="TOPICAL",
        ),
        FakeLabel(
            s.format(11, 11),
            "VALMORA (valmorex) kit, the originator's only form",
            "NDA",
            "NDA010500",
            _years_after_recent(3),
            ("INTRAVENOUS", "ORAL"),
            rulebook.value("label-choice", "kit_form"),
            (VAL_TAB,),
            rich_sections(),
            2,
            pad_route="TOPICAL",
        ),
        FakeLabel(
            s.format(12, 12),
            "TEDURA (teduvarin) for injection, in a kit with an ethanol pad",
            "NDA",
            "NDA203000",
            _years_after_recent(5),
            ("SUBCUTANEOUS",),
            "INJECTION, POWDER, LYOPHILIZED, FOR SOLUTION",
            (TED_VIAL, ETHANOL_PAD),
            old_format_sections(),
            1,
            pad_route="TOPICAL",
            pad_name="ALCOHOL",
        ),
        FakeLabel(
            s.format(13, 13),
            "PLOVIRA (plovizumab) injection, missing from the mapping file",
            "BLA",
            "BLA761100",
            _years_after_recent(5),
            ("SUBCUTANEOUS",),
            "INJECTION, SOLUTION",
            (),
            old_format_sections(),
            1,
            actives=(("PLOVIZUMAB", "PLOVIZUMAB"),),
        ),
        FakeLabel(
            s.format(14, 14),
            "LUMETRA (lumetrine hydrochloride) tablets, mapped to a code RxNorm no longer holds",
            "NDA",
            "NDA020500",
            _years_after_recent(-6),
            ("ORAL",),
            "TABLET",
            (NOT_IN_RXNORM,),
            old_format_sections(),
            2,
            actives=(("LUMETRINE HYDROCHLORIDE", "LUMETRINE"),),
        ),
        FakeLabel(
            s.format(15, 15),
            "Zentoprine tablets, missing from the mapping file",
            "ANDA",
            "ANDA200100",
            _years_after_recent(5),
            ("ORAL",),
            "TABLET",
            (),
            old_format_sections(),
            2,
            actives=(("ZENTOPRINE", "ZENTOPRINE"),),
        ),
        FakeLabel(
            s.format(16, 16),
            "Zentoprin tablets, a name near an ingredient's",
            "NDA",
            "NDA020600",
            _years_after_recent(5),
            ("ORAL",),
            "TABLET",
            (),
            old_format_sections(),
            2,
            actives=(("ZENTOPRIN", ""),),
        ),
        FakeLabel(
            s.format(17, 17),
            "LIDODERMA (lidorine) patch, the originator's",
            "NDA",
            "NDA020100",
            _years_after_recent(3),
            ("TOPICAL",),
            "PATCH",
            (LID_PATCH,),
            old_format_sections(),
            1,
        ),
        FakeLabel(
            s.format(18, 18),
            "Lidorine ophthalmic gel",
            "ANDA",
            "ANDA201000",
            _years_after_recent(3),
            ("OPHTHALMIC",),
            "GEL",
            (LID_EYE,),
            old_format_sections(),
            1,
        ),
        FakeLabel(
            s.format(19, 19),
            "Lidorine viscous solution for the mouth and throat",
            "ANDA",
            "ANDA201100",
            _years_after_recent(3),
            ("OROPHARYNGEAL",),
            "SOLUTION",
            (LID_MOUTH,),
            old_format_sections(),
            2,
        ),
        FakeLabel(
            s.format(20, 20),
            "DICLORA (diclorin) gel",
            "NDA",
            "NDA022000",
            _years_after_recent(3),
            ("TOPICAL",),
            "GEL",
            (DIC_GEL,),
            rich_sections(),
            2,
        ),
        FakeLabel(
            s.format(21, 21),
            "DICLORA PATCH (diclorin) transdermal system",
            "NDA",
            "NDA022500",
            _years_after_recent(3),
            ("TRANSDERMAL",),
            "PATCH",
            (DIC_PATCH,),
            old_format_sections(),
            2,
        ),
        FakeLabel(
            s.format(22, 22),
            "Diclorin ophthalmic solution",
            "NDA",
            "NDA022800",
            _years_after_recent(3),
            ("OPHTHALMIC",),
            "SOLUTION",
            (DIC_EYE,),
            old_format_sections(),
            1,
        ),
    ]


def _approvals(label: FakeLabel) -> str:
    """One approval per application, its category read from its letters."""
    out = ""
    for ident in label.number.split() or [""]:
        name = ident.rstrip("0123456789") or label.category
        code = label.category if label.category.startswith("C0") else _category(name)
        out += f'<subjectOf><approval><id extension="{ident}"/><code code="{code}"/>'
        out += "</approval></subjectOf>"
    return out


def _pad(route: str, name: str = "") -> str:
    """An alcohol pad as a kit part: its active ingredient and its own route."""
    if not route:
        return ""
    alcohol = name or rulebook.value("label-choice", "not_counted_beside_others")[1].upper()
    return (
        '<part><partProduct><name>Alcohol pad</name><ingredient classCode="ACTIB">'
        f"<ingredientSubstance><name>{alcohol}</name></ingredientSubstance></ingredient>"
        f'</partProduct><consumedIn><substanceAdministration><routeCode displayName="{route}"/>'
        "</substanceAdministration></consumedIn></part>"
    )


def _actives(label: FakeLabel) -> str:
    out = ""
    for substance, moiety in label.actives:
        held = (
            f"<activeMoiety><activeMoiety><name>{moiety}</name></activeMoiety></activeMoiety>"
            if moiety
            else ""
        )
        out += (
            '<ingredient classCode="ACTIB"><ingredientSubstance>'
            f"<name>{substance}</name>{held}</ingredientSubstance></ingredient>"
        )
    return out


def spl_xml(label: FakeLabel) -> str:
    routes = "".join(
        f'<consumedIn><substanceAdministration><routeCode displayName="{r}"/>'
        "</substanceAdministration></consumedIn>"
        for r in label.routes
    )
    product = (
        "<subject><manufacturedProduct><manufacturedProduct><name>Product</name>"
        f'<formCode displayName="{label.form}"/>{_actives(label)}'
        "<asContent><containerPackagedProduct>"
        '<formCode displayName="BOTTLE"/></containerPackagedProduct></asContent>'
        f"{_pad(label.pad_route, label.pad_name)}</manufacturedProduct>{_approvals(label)}{routes}"
        "</manufacturedProduct></subject>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><document xmlns="urn:hl7-org:v3">'
        f'<code code="{_SPL_DOC}"/><title>{label.title}<br/>Initial approval</title>'
        f'<effectiveTime value="{label.effective:%Y%m%d}"/>'
        f'<setId root="{label.set_id.upper()}"/><versionNumber value="{label.version}"/>'
        "<component><structuredBody>"
        f'<component><section><code code="48780-1"/>{product}</section></component>'
        f"{label.sections}</structuredBody></component></document>"
    )


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()


def _rxnorm_rows() -> tuple[list[str], list[str]]:
    """RXNCONSO and RXNREL lines, every field in its RRF position."""
    names = {
        ZENTOPRINE: ("IN", "zentoprine"),
        VALMOREX: ("IN", "valmorex"),
        QUORBITAL: ("IN", "quorbital"),
        PAD: ("IN", rulebook.value("label-choice", "not_counted_beside_others")[1]),
        TEDUVARIN: ("IN", "teduvarin"),
        ETHANOL: ("IN", "ethanol"),
        PLOVIZUMAB: ("IN", "plovizumab"),
        LUMETRINE: ("IN", "lumetrine"),
        LIDORINE: ("IN", "lidorine"),
        DICLORIN: ("IN", "diclorin"),
        ZEN_VAL: ("MIN", "valmorex / zentoprine"),
    }
    conso = [f"{c}|ENG||||||||||RXNORM|{t}|{c}|{n}||N||" for c, (t, n) in names.items()]
    drugs = {
        ZEN_TAB: ("SCD", [ZENTOPRINE]),
        ZEN_EYE: ("SCD", [ZENTOPRINE]),
        ZENTORA_TAB: ("SBD", [ZENTOPRINE]),
        VAL_TAB: ("SCD", [VALMOREX]),
        ZEN_VAL_TAB: ("SCD", [ZENTOPRINE, VALMOREX]),
        QUO_TAB: ("SCD", [QUORBITAL]),
        PAD_PRODUCT: ("SCD", [PAD]),
        TED_VIAL: ("SCD", [TEDUVARIN]),
        ETHANOL_PAD: ("SCD", [ETHANOL]),
        **{c: ("SCD", [LIDORINE]) for c in (LID_PATCH, LID_EYE, LID_MOUTH)},
        **{c: ("SCD", [DICLORIN]) for c in (DIC_GEL, DIC_PATCH, DIC_EYE)},
    }
    conso += [f"{c}|ENG||||||||||RXNORM|{t}|{c}|product {c}||N||" for c, (t, _) in drugs.items()]
    conso.append(f"{ZEN_VAL_PACK}|ENG||||||||||RXNORM|GPCK|{ZEN_VAL_PACK}|pack||N||")

    def rel(one: str, rela: str, two: str) -> str:
        """`two` <rela> `one`, as RxNorm writes a relationship."""
        return f"{one}|||RO|{two}|||{rela}|||RXNORM||||||"

    rows = []
    for drug, (_, ingredients) in drugs.items():
        for ingredient in ingredients:
            component = f"8{drug}{ingredient}"
            rows += [
                rel(component, "consists_of", drug),
                rel(ingredient, "has_ingredient", component),
            ]
    rows += [rel(drug, "contains", ZEN_VAL_PACK) for drug in (ZEN_TAB, VAL_TAB)]
    rows.append(rel(ZEN_VAL, "has_ingredients", ZEN_VAL_TAB))
    return conso, rows


def _member(label: FakeLabel, folder: str = "") -> tuple[str, bytes]:
    """A label as DailyMed ships it: a zip of its SPL XML and a picture, named by its day and
    set ID, in the folder of its kind."""
    folder = folder or rulebook.value("label-source", "daily_label_folder")
    inner = _zip_bytes({f"{label.set_id}.xml": spl_xml(label).encode(), "figure.jpg": b"\xff\xd8"})
    return f"{folder}/{label.effective:%Y%m%d}_{label.set_id}.zip", inner


def mapping_zip(found: list[FakeLabel]) -> bytes:
    """DailyMed's labels-to-RxNorm file for these labels."""
    mapping = ["SETID|SPL_VERSION|RXCUI|RXSTRING|RXTTY"]
    for label in found:
        for code in label.products:
            mapping += [
                f"{label.set_id}|{label.version}|{code}|name one|PSN",
                f"{label.set_id}|{label.version}|{code}|name two|SY",
            ]
    mapping.append(f"{labels()[5].set_id}|3|{ZEN_VAL_PACK}|pack|GPCK")
    return _zip_bytes({"rxnorm_mappings.txt": ("\n".join(mapping) + "\n").encode()})


def daily_zip(
    changed: Sequence[FakeLabel],
    deleted: Sequence[FakeLabel] = (),
    over_the_counter: Sequence[FakeLabel] = (),
) -> bytes:
    """A daily update file: the prescription labels of the day, the labels of another kind in a
    folder of their own, and the list of the files the day takes out of the full release."""
    members = dict(_member(label) for label in changed)
    members |= dict(_member(label, "otc") for label in over_the_counter)
    gone = [_member(label)[0] for label in deleted]
    members["files_added.txt"] = "\n".join(members).encode()
    members[rulebook.value("label-source", "daily_deleted_list")] = "\n".join(gone).encode()
    return _zip_bytes(members)


def write_labels(folder: Path, broken_label: bool = True) -> Path:
    """Write the fake labels folder; `broken_label` adds a label whose XML
    does not parse, which the step counts and skips."""
    folder.mkdir(parents=True, exist_ok=True)
    pattern = rulebook.value("label-source", "release_file_pattern")
    parts: dict[int, dict[str, bytes]] = {1: {}, 2: {}}
    for label in labels():
        name, inner = _member(label)
        parts[label.part][name] = inner
    if broken_label:
        parts[2]["prescription/20250101_broken.zip"] = _zip_bytes(
            {"broken.xml": b"<document><title>"}
        )
    for n, members in parts.items():
        (folder / pattern.format(n=n)).write_bytes(_zip_bytes(members))
    (folder / rulebook.value("label-source", "mapping_file")).write_bytes(mapping_zip(labels()))
    conso, rel = _rxnorm_rows()
    rxnorm_name = rulebook.value("label-source", "rxnorm_file_glob").replace("*", "current")
    (folder / rxnorm_name).write_bytes(
        _zip_bytes(
            {
                "rrf/RXNCONSO.RRF": ("\n".join(conso) + "\n").encode(),
                "rrf/RXNREL.RRF": ("\n".join(rel) + "\n").encode(),
            }
        )
    )
    return folder
