"""The one coding question and its reasons for none, read from rule label-coding."""

from __future__ import annotations

from dataclasses import dataclass

from open_altio import rulebook

RULE = "label-coding"


@dataclass(frozen=True)
class Reason:
    key: str
    name: str
    definition: str
    examples: tuple[str, ...]
    needs_note: bool


def question() -> str:
    return str(rulebook.value(RULE, "question"))


def reasons() -> dict[str, Reason]:
    """Why a phrase states no reaction, in the rule's order (the page's number keys follow it)."""
    rule = rulebook.rule(RULE)  # one read of the file for both values
    needs_note = set(rule.value("needs_note"))
    return {
        key: Reason(
            key,
            raw["name"],
            raw["definition"],
            tuple(raw["examples"]),
            key in needs_note,
        )
        for key, raw in rule.value("none_reasons").items()
    }


def as_text() -> str:
    """The question and its rules in plain words, as the agent reads them and a person prints."""
    rule = rulebook.rule(RULE)
    out = [
        f"The question: {rule.value('question')}",
        "",
        " ".join(rule.value("stated").split()),
        "",
    ]
    out.append("Phrases that state reactions, and the preferred terms they state:")
    out.append("")
    for e in rule.value("stated_examples"):
        out.append(f'- "{e["label"]}": {"; ".join(e["pts"])}')
    out += ["", "When a phrase states no reaction, give one reason:", ""]
    for r in reasons().values():
        out.append(
            f"- `{r.key}`, {r.name}: {r.definition}" + (" Add a note." if r.needs_note else "")
        )
        out += [f'  - "{example}"' for example in r.examples]
    out += ["", str(rule.value("faers_line"))]
    return "\n".join(out) + "\n"


def as_markdown() -> str:
    """The same, as a short page to read before approving it."""
    return "# Coding the label phrases the rules leave uncertain\n\n" + as_text()
