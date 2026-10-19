"""The methods page's /api ("How we clean FAERS"). Anyone who may view the explorer reads the
rules: each in plain words with its values, the build's steps, the release's methods (its counts,
numbers and evidence), and the choices the release was built with. WHO's drug classes are a
section of their own, with one switch, left out wherever the host hides the classes or the
release carries none. Where the access hook lets the rules be edited (a person's own copy), they
also save their choices beside the release and rebuild it with them.

A choice set travels in the shape a release records it: {"off": [rule, ...], "changed":
[{"rule", "key", "value", "standard"}, ...]}.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from open_altio.faers.insights.cards import drug_classes as class_cards
from open_altio.faers.insights.methods import card_lines
from open_altio.faers.labels.build import as_of as labels_as_of
from open_altio.rulebook import (
    RuleInfo,
    UserRules,
    UserRulesError,
    catalogue,
    check_user_rules,
    differences,
    from_differences,
    load_user_rules,
    rule,
    save_user_rules,
    steps,
)

from .access import Viewer
from .answers import answer, json_body, problem
from .classes import layer_of
from .context import Explorer, explorer, viewer
from .rebuild import (
    CannotRebuild,
    built_with,
    methods_of,
    needs,
    rules_file,
    standard_methods,
)
from .release import NotLive, OpenRelease

# Who may read the rules, or change them here, is the access hook's to say.
router = APIRouter(prefix="/api/rules", dependencies=[Depends(viewer)])
NOT_HERE = "Rules are changed in your own copy of Open Altio, not here."
CLASSES = "drug_classes"  # the step of rules/steps.yaml whose rules give WHO's drug classes
# rules the methods page names where they act, beside the data rules: how a drug's cases are
# counted, the one MedDRA version, and how the label flags' uncertain phrases and groups are read
NAMED = ("explorer-drug-counts", "meddra-version", "label-coding", "label-groups")


def _code(name: str) -> str | None:
    """The code a rule is enforced in, the first source file its rule file names."""
    return next((f for f in rule(name).enforced_in if f.startswith("src/")), None)


def _rule(info: RuleInfo) -> dict[str, Any]:
    return {
        "name": info.name,
        "title": info.title,
        "line": info.line,
        "text": info.text,
        "step": {
            "id": info.step.id,
            "title": info.step.title,
            "sentence": info.step.sentence,
            "switch": info.step.switch,
        },
        "always_on": info.always_on,
        "why_locked": info.why_locked or "",
        "values": [
            {
                "key": v.key,
                "label": v.label,
                "standard": v.standard,
                "type": v.type,
                "options": [[value, words] for value, words in v.options],
                "minimum": v.minimum,
            }
            for v in info.values
        ],
        "file": info.file,
        "code": _code(info.name),
    }


def _named(name: str) -> dict[str, Any]:
    """A rule the page names that is not a step of the build: its words, file and code."""
    found = rule(name)
    return {
        "name": name,
        "title": found.title,
        "line": found.extra.get("line", ""),
        "text": found.text,
        "file": f"rules/{found.path.name}",
        "code": _code(name),
    }


def _release(opened: OpenRelease) -> dict[str, Any]:
    """What the page says about the release besides its methods: its quarters, when it was
    built, the day its labels are as of, the lines of FDA's files split back into two reports,
    and what its statistics count."""
    m = opened.manifest
    split = [
        {"table": i["table"], "quarter": i["quarter"]}
        for i in m.get("inputs", [])
        for line in i.get("overlong_lines", [])
        if line["records"] > 1
    ]
    return {
        "name": opened.name,
        "quarters": [m["quarters"][0], m["quarters"][-1]],
        "built_at": m.get("built_at"),
        # the DailyMed day its labels are as of, when it holds them (rule label-refresh)
        "labels_as_of": labels_as_of(m),
        "split_lines": split,
        # what the statistics count: cases, ingredients, reactions and pairs
        "statistics": (m.get("statistics") or {}).get("counted"),
    }


def _meddra(ex: Explorer) -> dict[str, Any] | None:
    """The MedDRA version the release counts its reactions in, and how many indication texts and
    rows matched no MedDRA name and are shown as FDA wrote them; None without MedDRA. Counts and
    a version only, nothing of MedDRA's content."""
    served = ex.meddra.served()
    if served is None:
        return None
    unmatched = served.report["columns"]["indi_pt"]["unmapped"]
    return {
        "version": served.version,
        "free_text_indications": {"texts": unmatched["texts"], "rows": unmatched["rows"]},
        # the methods page's counts that need MedDRA: terms reached and cases on an older term
        "numbers": served.numbers,
    }


def _read(opened: OpenRelease) -> UserRules | str | None:
    """The choices saved beside the release, None with no file, or why it cannot be read."""
    path = rules_file(opened)
    if not path.is_file():
        return None
    try:
        return load_user_rules(path)
    except (OSError, UserRulesError) as exc:
        return f"Your {path.name} beside the release could not be read: {exc}"


def _saved(opened: OpenRelease, built: dict[str, list]) -> dict[str, Any]:
    """The choices saved beside the release (what the switches show), and the file's text."""
    found = _read(opened)
    if found is None:
        return {"saved": built, "file": None}
    if isinstance(found, str):
        return {"saved": built, "file": None, "problem": found}
    return {"saved": differences(found), "file": rules_file(opened).read_text(encoding="utf-8")}


def _with_lines(card: dict[str, Any]) -> dict[str, Any]:
    """A card with its opened words (Shows, Why it matters, What we did) from the package as it
    is now, filled with the card's numbers from the release."""
    lines = card_lines(card)
    return {**card, "lines": lines} if lines else card


def _of_classes(card: dict[str, Any]) -> bool:
    """Whether an evidence card is the drug classes': the cards of their notebook."""
    return card["notebook"] == class_cards.NB09


def _classes(
    opened: OpenRelease, methods: dict[str, Any], built: dict[str, list], who: bool
) -> dict[str, Any] | None:
    """The drug classes' section of the page. None where the host hides WHO's classes, and where
    the release neither carries them nor was built with them switched off (then the section
    stays, so its switch can turn them on again). Their evidence cards are tagged documented in
    the release; the section names the rule they are evidence for."""
    switch = next(s.switch for s in steps() if s.id == CLASSES)
    carried = layer_of(opened.manifest) is not None
    if not who or not (carried or switch in built["off"]):
        return None
    entry = opened.manifest["classes"] if carried else {}
    return {
        "step": CLASSES,
        "present": carried,
        "index_year": entry.get("index_year"),
        "citation": entry.get("citation"),
        "cases": entry.get("cases"),
        "evidence": {class_cards.RULE: [c["id"] for c in methods["insights"] if _of_classes(c)]},
    }


def rules_answer(ex: Explorer, *, who: bool) -> dict[str, Any]:
    """What the methods page shows: the rules and the release's methods, nothing licensed but
    counts and nothing about people, so a host may give it to people who are not signed in
    (rules_page). `who` is whether the host shows WHO's drug classes: where it does not, the page
    holds nothing of them, neither their rules nor their evidence."""
    opened = ex.release.current()
    methods = methods_of(opened)
    built = built_with(methods)
    infos = catalogue()
    classes = _classes(opened, methods, built, who)
    if classes is None:
        infos = [info for info in infos if info.step.id != CLASSES]
        methods = {
            **methods,
            "insights": [c for c in methods["insights"] if not _of_classes(c)],
            "numbers": {k: v for k, v in methods.get("numbers", {}).items() if k != "classes"},
        }
    said: dict[str, Any] = {
        "editable": ex.access.edits_rules,
        "release": _release(opened),
        "meddra": _meddra(ex),
        "methods": {**methods, "insights": [_with_lines(c) for c in methods["insights"]]},
        "standard": standard_methods(opened) if any(built.values()) else None,
        "rules": [_rule(info) for info in infos],
        "steps": [
            {"id": s.id, "title": s.title, "sentence": s.sentence}
            for s in steps()
            if classes is not None or s.id != CLASSES
        ],
        "named": [_named(name) for name in NAMED],
        "built": built,
        "classes": classes,
    }
    if ex.access.edits_rules:
        # what a rebuild needs of this machine, said before it starts (rule machine-needs)
        said |= _saved(opened, built) | {"rebuild": ex.rebuild.state(), "needs": needs(opened)}
    return said


def _open(ex: Explorer) -> OpenRelease | Response:
    if not ex.access.edits_rules:
        return problem(403, NOT_HERE)
    return ex.release.current()


def _choices(asked: dict[str, Any]) -> UserRules | None:
    off, changed = asked.get("off", []), asked.get("changed", [])
    if not (
        isinstance(off, list)
        and all(isinstance(n, str) for n in off)
        and isinstance(changed, list)
        and all(isinstance(c, dict) and {"rule", "key", "value"} <= c.keys() for c in changed)
    ):
        return None
    return from_differences(asked)


Ex = Depends(explorer)


def rules_page(ex: Explorer, *, who: bool) -> Response:
    """The methods page's answer, for this app's route and for a host that serves it itself;
    `who` is whether the host shows WHO's drug classes."""
    try:
        return answer(rules_answer(ex, who=who))
    except NotLive as exc:
        return problem(503, str(exc))


@router.get("")
def rules(ex: Explorer = Ex, v: Viewer = Depends(viewer)) -> Response:
    return rules_page(ex, who=v.who)


@router.put("")
async def save(request: Request, ex: Explorer = Ex) -> Response:
    opened = _open(ex)
    if isinstance(opened, Response):
        return opened
    asked = await json_body(request)
    if isinstance(asked, Response):
        return asked
    chosen = _choices(asked)
    if chosen is None:
        return problem(
            400, 'Send the rules as {"off": [...], "changed": [{"rule", "key", "value"}]}.'
        )
    problems = check_user_rules(chosen)
    if problems:
        return answer({"problem": " ".join(problems), "problems": problems}, 400)
    save_user_rules(rules_file(opened), chosen)
    return answer(_saved(opened, built_with(methods_of(opened))))


@router.post("/rebuild")
async def start_rebuild(request: Request, ex: Explorer = Ex) -> Response:
    opened = _open(ex)
    if isinstance(opened, Response):
        return opened
    asked = await json_body(request)  # JSON only: a form on another site cannot start a rebuild
    if isinstance(asked, Response):
        return asked
    found = _read(opened)
    if isinstance(found, str):
        return problem(400, found)
    chosen = found or UserRules()
    problems = check_user_rules(chosen)
    if problems:
        return answer({"problem": " ".join(problems), "problems": problems}, 400)
    try:
        return answer(ex.rebuild.start(opened, chosen), 202)
    except CannotRebuild as exc:
        return problem(409, str(exc))


@router.get("/rebuild")
def rebuild_state(ex: Explorer = Ex) -> Response:
    if not ex.access.edits_rules:
        return problem(403, NOT_HERE)
    return answer(ex.rebuild.state())


__all__ = ["NOT_HERE", "router", "rules_answer", "rules_page"]
