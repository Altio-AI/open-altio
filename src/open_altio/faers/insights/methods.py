"""The methods-page data: `methods.json` in every release.

    from open_altio.faers.insights.methods import build_methods, validate
    doc = build_methods(con, funnel_doc, code_version="0.1.0")

The methods page draws the release's steps, counts and evidence only from this document. Its shape
is `methods.schema.json` beside this file. It is built from the release's funnel, the steps'
titles and lines in `rules/steps.yaml`, the step cards in `steps.yaml` here, the insight cards in
`cards/` computed on the release's own data, how the rules the release was built with differ
from Altio's standard. The numbers its story shows, the limits in `limits.yaml` filled with them,
and every rule's version are added once the release is written, from its own tables
(numbers.write).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import yaml

from open_altio import rulebook
from open_altio.faers import formats

from .cards import LICENSED, TAG_LABELS, compute_cards

FORMAT = formats.METHODS
FORMAT_VERSION = 1
REPOSITORY = "https://github.com/Altio-AI/open-altio"
CODE_REF_ENV = "OPEN_ALTIO_CODE_REF"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # the repository, in a checkout
SOURCE = HERE.parents[
    2
]  # the folder holding open_altio: src/ in a checkout, site-packages once installed
STEPS_FILE = HERE / "steps.yaml"
LIMITS_FILE = HERE / "limits.yaml"
LINES_FILE = HERE / "lines.yaml"
SCHEMA_FILE = HERE / "methods.schema.json"

EM_DASH = "\u2014"
SPILL_CAP_GB = 20  # the most a cards run given a temp directory may spill there
CHANGELOG_PLACEHOLDER = "Changelog entry to be written when this release is published."


class MethodsError(ValueError):
    """The methods page cannot be built from this release, said by name."""


def step_cards() -> dict:
    return yaml.safe_load(STEPS_FILE.read_text(encoding="utf-8")) or {}


def limits() -> list[dict]:
    return yaml.safe_load(LIMITS_FILE.read_text(encoding="utf-8")) or []


def card_lines(card: dict) -> dict[str, str] | None:
    """An opened card's Shows / Why it matters / What we did, read from `lines.yaml` now, not
    from the release, and filled with the card's own numbers; None for a card with no lines
    there, or whose numbers the release lacks (a card computed before it had them)."""
    words = (yaml.safe_load(LINES_FILE.read_text(encoding="utf-8")) or {}).get(card.get("id"))
    if not words:
        return None
    try:
        return {k: v.format(**(card.get("numbers") or {})) for k, v in words.items()}
    except (KeyError, ValueError):
        return None


def schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def code_ref(code_version: str) -> str:
    """The git ref the code links point at: $OPEN_ALTIO_CODE_REF, else the
    commit checked out in this repository, else the tag v<code_version>."""
    return os.environ.get(CODE_REF_ENV) or _git_head(ROOT) or f"v{code_version}"


def _git_head(root: Path) -> str | None:
    """The checked-out commit, read from .git without running git (a
    worktree's .git is a file naming its git folder)."""
    try:
        git = root / ".git"
        if git.is_file():
            git = (root / git.read_text().split("gitdir:", 1)[1].strip()).resolve()
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(":", 1)[1].strip()
        common = (
            (git / (git / "commondir").read_text().strip()).resolve()
            if (git / "commondir").is_file()
            else git
        )
        for folder in (git, common):
            if (folder / ref).is_file():
                return (folder / ref).read_text().strip()
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text().splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0]
    except (OSError, IndexError):
        return None
    return None


def code_link(path: str, anchor: str, ref: str) -> dict:
    """The GitHub link to the line of `path` (src/... in the repository) holding `anchor`,
    read from the installed code, which is the code the link points at."""
    file = SOURCE / path.removeprefix("src/")
    if not file.is_file():
        raise MethodsError(f"step card code path {path} does not exist")
    for n, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        if anchor in line:
            return {"path": path, "line": n, "url": f"{REPOSITORY}/blob/{ref}/{path}#L{n}"}
    raise MethodsError(f"step card anchor {anchor!r} is not in {path}")


class _RuleValues(dict):
    """rules[name][key] in a step card or limit text reads that rule's value as
    the release was built with it, so the methods page and the rule cannot
    drift apart."""

    def __missing__(self, name: str) -> dict[str, Any]:
        return {key: rulebook.value(name, key) for key in rulebook.rule(name).values}


def fill(text: str, **numbers: Any) -> str:
    """A step card or limit text with its {rules[...][...]} and number fields filled."""
    try:
        return text.format_map({"rules": _RuleValues(), **numbers})
    except (KeyError, IndexError, ValueError, rulebook.RuleError) as e:
        raise MethodsError(f"cannot fill {text[:60]!r}...: {e}") from None


def _plain(value: Any) -> Any:
    """A rule value as JSON holds it: a date as its ISO day."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def rule_hash(path: Path) -> str:
    """A short hash of a rule file's front-matter values and its text, so the next release can
    say which rules are new or changed. Read as values, not bytes: a reworded comment or a
    re-wrapped YAML list leaves it as it was."""
    lines = path.read_text(encoding="utf-8").splitlines()
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    front = yaml.safe_load("\n".join(lines[1:end])) or {}
    text = "\n".join(lines[end + 1 :]).strip()
    words = json.dumps([_plain(front), text], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(words.encode("utf-8")).hexdigest()[:12]


def rule_versions() -> dict[str, dict[str, Any]]:
    """Every rule's version: its file's hash and its values as the release was built with them
    (a person's own where they changed one)."""
    return {
        name: {
            "hash": rule_hash(rulebook.rule(name).path),
            "values": {
                key: _plain(rulebook.value(name, key)) for key in rulebook.rule(name).values
            },
        }
        for name in rulebook.rule_names()
    }


def _share(part: int, whole: int) -> float:
    return 100.0 * part / whole if whole else 0.0


def fill_limits(funnel_doc: dict, numbers: dict) -> list[dict]:
    """The limits filled with the funnel's duplicate counts and methods.json's `numbers`, so
    they count the cases the release shows; one that `needs` a part of the release the numbers
    lack is left out."""
    dup = funnel_doc.get("duplicates") or {}
    names, rx = numbers.get("drug_names") or {}, numbers.get("rxnorm") or {}
    values = {
        "duplicates": dup,
        "not_compared_share": _share(dup.get("not_compared_by_aeolus", 0), dup.get("cases", 0)),
        "unmapped_share": _share(names.get("unmapped_records", 0), names.get("drug_records", 0)),
        "coded_share": _share(rx.get("coded_records", 0), rx.get("suspect_records", 0)),
        **numbers,
    }
    return [
        {k: v for k, v in item.items() if k != "needs"} | {"text": fill(item["text"], **values)}
        for item in limits()
        if not item.get("needs") or item["needs"] in numbers
    ]


def build_methods(
    con: duckdb.DuckDBPyConnection,
    funnel_doc: dict,
    code_version: str,
    user_rules: dict | None = None,
    classes: dict | None = None,
) -> dict:
    """The methods-page document for a release, from its funnel and the
    release's own data on `con`; `user_rules` is how the rules it was built
    with differ from Altio's standard (rulebook.differences), and `classes` the
    manifest's entry for the drug classes layer, whose citation the page shows
    wherever it shows a class. Its limits are filled once the release is written
    (numbers.write), as they quote its numbers. Raises MethodsError
    when a funnel step has no step card, a code link cannot be found, or the
    result is invalid."""
    cards = step_cards()
    titles = {s.id: s for s in rulebook.steps()}
    missing = [
        s["id"] for s in funnel_doc["steps"] if s["id"] not in cards or s["id"] not in titles
    ]
    if missing:
        raise MethodsError(
            f"funnel step(s) {missing} need a step card in "
            "src/open_altio/faers/insights/steps.yaml and a title in rules/steps.yaml"
        )
    step_ids = [s["id"] for s in funnel_doc["steps"]]
    insights = _labelled([c for c in compute_cards(con) if c["id"] not in LICENSED], step_ids)

    ref = code_ref(code_version)
    steps = []
    previous = None
    for number, step in enumerate(funnel_doc["steps"], 1):
        text = cards[step["id"]]
        steps.append(
            {
                "id": step["id"],
                "number": number,
                "title": titles[step["id"]].title,
                "label": step["label"],
                "table": step["table"],
                "before": previous,
                "after": step["count"],
                "removed": step.get("removed"),
                "sentence": fill(titles[step["id"]].sentence),
                "rule": fill(text["rule"]),
                "code": code_link(text["code"]["path"], text["code"]["anchor"], ref),
                "insights": _step_insights(insights, step["id"]),
            }
        )
        previous = step["count"]

    doc = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "release": funnel_doc["release"],
        "code": {"repository": REPOSITORY, "version": code_version, "ref": ref},
        "funnel": {
            "eras": funnel_doc["eras"],
            "steps": [
                {"id": s["id"], "label": s["label"], "count": s["count"]}
                for s in funnel_doc["steps"]
            ],
            "deleted_lists": funnel_doc.get("deleted_lists"),
            **({"duplicates": funnel_doc["duplicates"]} if "duplicates" in funnel_doc else {}),
        },
        "steps": steps,
        "insights": insights,
        "limits": [],
        "changelog": {
            "release": funnel_doc["release"],
            "date": None,
            "entry": CHANGELOG_PLACEHOLDER,
            "placeholder": True,
        },
        "user_rules": user_rules or {"off": [], "changed": []},
    }
    if classes is not None:
        shown = ("present", "source", "index_year", "citation", "cases", "reason")
        doc["classes"] = {k: classes[k] for k in shown if k in classes}
    problems = validate(doc)
    if problems:
        raise MethodsError("; ".join(problems))
    return doc


def _labelled(cards: list[dict], step_ids: list[str] | None) -> list[dict]:
    """The cards with their tag's label, refusing one that names a step not in the funnel
    (`step_ids`; None for the licensed part's cards, whose step acts only with MedDRA, which
    may have been added after the build)."""
    out = []
    for card in cards:
        tag = dict(card["tag"])
        tag["label"] = TAG_LABELS[tag["kind"]]
        if (
            step_ids is not None
            and tag["kind"] == "changed_pipeline"
            and tag["step"] not in step_ids
        ):
            raise MethodsError(
                f"insight {card['id']} names step {tag['step']!r}, which is not in the funnel"
            )
        out.append({**card, "tag": tag})
    return out


def _step_insights(insights: list[dict], step_id: str) -> list[str]:
    return [
        c["id"]
        for c in insights
        if c["tag"]["kind"] == "changed_pipeline" and c["tag"]["step"] == step_id
    ]


def _release_connection(
    release: Path,
    memory_limit: str | None = None,
    threads: int | None = None,
    temp_directory: str | Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """The built release's own tables, as the cards read them: its tables and views
    (source.connect, with the lines of FDA's files its load split back apart), and its newest
    MedDRA version's licensed tables where it holds one."""
    from open_altio.faers.meddra.licensed import licensed_dir, read_licensed_manifest
    from open_altio.faers.reader import quoted

    from .source import connect

    con = connect(release)
    if memory_limit:
        con.execute(f"SET memory_limit = '{memory_limit}'")
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    if temp_directory:
        con.execute(f"SET temp_directory = {quoted(str(temp_directory))}")
        con.execute(f"SET max_temp_directory_size = '{SPILL_CAP_GB}GB'")
    version = _licensed_version(read_licensed_manifest(release))
    if version is not None:
        for table, entry in version["tables"].items():
            path = quoted(str(licensed_dir(release) / entry["path"]))
            con.execute(f'CREATE OR REPLACE VIEW "{table}" AS SELECT * FROM read_parquet({path})')
    return con


def _licensed_version(licensed: dict | None) -> dict | None:
    versions = ((licensed or {}).get("meddra") or {}).get("versions") or {}
    if not versions:
        return None
    newest = max(versions, key=lambda v: tuple(int(p) for p in v.split(".") if p.isdigit()))
    return versions[newest]


def refresh_cards(
    release_dir: str | Path,
    memory_limit: str | None = None,
    threads: int | None = None,
    temp_directory: str | Path | None = None,
) -> dict:
    """Compute the insight cards again on a built release's own tables and write them into its
    methods.json (the cards, each step's links to them and its code link, pointed at code_ref();
    nothing else changes), and the cards
    that need MedDRA into its licensed part, under the newest version, as `insights`. The release
    build ends with this and then the numbers (numbers.write), as `python -m open_altio.faers
    methods --release <folder>` does on a built release, so it gets new cards without a rebuild.
    Returns the new methods.json."""
    import shutil

    from open_altio.faers.meddra.licensed import read_licensed_manifest, write_licensed_manifest

    release = Path(release_dir)
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    path = release / manifest["methods"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    spill = Path(temp_directory) if temp_directory else release / ".cards.spill"
    con = _release_connection(release, memory_limit, threads, spill)
    built = rulebook.from_differences(manifest.get("user_rules") or {"off": [], "changed": []})
    try:
        with rulebook.use_user_rules(built):  # the rules it was built with, as the numbers are
            cards = compute_cards(con)
    finally:
        con.close()
        if not temp_directory:
            shutil.rmtree(spill, ignore_errors=True)
    step_ids = [s["id"] for s in doc["steps"]]
    doc["insights"] = _labelled([c for c in cards if c["id"] not in LICENSED], step_ids)
    ref = code_ref(doc["code"]["version"])
    doc["code"]["ref"] = ref
    texts = step_cards()
    for step in doc["steps"]:
        step["insights"] = _step_insights(doc["insights"], step["id"])
        code = texts[step["id"]]["code"]
        step["code"] = code_link(code["path"], code["anchor"], ref)
    # the numbers are checked when numbers.write replaces them, so a release built before a
    # number was added can still take new cards
    problems = validate({k: v for k, v in doc.items() if k != "numbers"})
    if problems:
        raise MethodsError("; ".join(problems))
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    licensed = read_licensed_manifest(release)
    version = _licensed_version(licensed)
    if licensed is not None and version is not None:
        version["insights"] = _labelled([c for c in cards if c["id"] in LICENSED], None)
        write_licensed_manifest(release, licensed)
    return doc


def validate(doc: dict) -> list[str]:
    """Every way `doc` breaks the methods-page contract, as plain sentences:
    the JSON schema, links between insights and steps, a card behind every
    step that removes cases, chart notes on their own x axis, and no em
    dashes."""
    import jsonschema

    doc = formats.with_current_name(doc)
    problems = [
        f"{'/'.join(map(str, e.absolute_path)) or 'document'}: {e.message}"
        for e in jsonschema.Draft202012Validator(schema()).iter_errors(doc)
    ]
    insight_ids = {c.get("id") for c in doc.get("insights", [])}
    rule_names = set(rulebook.rule_names())
    for card in doc.get("insights", []):
        tag = card.get("tag", {})
        if tag.get("kind") == "changed_pipeline":
            step = next((s for s in doc.get("steps", []) if s.get("id") == tag.get("step")), None)
            if step is None:
                problems.append(
                    f"insight {card.get('id')} names step {tag.get('step')!r}, "
                    "which has no step card"
                )
            elif card.get("id") not in step.get("insights", []):
                problems.append(f"step {step['id']} does not link back to insight {card.get('id')}")
        for name in dict.fromkeys([*tag.get("rules", []), *card.get("rules", [])]):
            if name not in rule_names:
                problems.append(
                    f"insight {card.get('id')} is evidence for rule {name!r}, "
                    "which has no rule file"
                )
        note = card.get("chart", {}).get("note")
        if note and note.get("x") not in card.get("chart", {}).get("x", {}).get("values", []):
            problems.append(
                f"insight {card.get('id')} has a chart note at {note.get('x')!r}, "
                "which is not on its x axis"
            )
    for step in doc.get("steps", []):
        for linked in step.get("insights", []):
            if linked not in insight_ids:
                problems.append(
                    f"step {step.get('id')} links to insight {linked!r}, which does not exist"
                )
        removed = step.get("removed")
        if isinstance(removed, dict):  # by era, with the total
            removed = removed.get("total")
        if removed and not step.get("insights"):
            problems.append(f"step {step.get('id')} removes cases but no insight card says why")
    if [s["id"] for s in doc.get("funnel", {}).get("steps", [])] != [
        s.get("id") for s in doc.get("steps", [])
    ]:
        problems.append("the step cards are not the funnel steps in order")
    # a rule's values are data, not words: a label table's empty cell may be an em dash
    for where, text in _texts({k: v for k, v in doc.items() if k != "rule_versions"}):
        if EM_DASH in text:
            problems.append(f"{where} contains an em dash")
    return problems


def _texts(value: object, where: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield where or "document", value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _texts(v, f"{where}.{k}" if where else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _texts(v, f"{where}[{i}]")


__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "MethodsError",
    "build_methods",
    "card_lines",
    "code_ref",
    "fill",
    "fill_limits",
    "limits",
    "refresh_cards",
    "rule_hash",
    "rule_versions",
    "schema",
    "step_cards",
    "validate",
]
