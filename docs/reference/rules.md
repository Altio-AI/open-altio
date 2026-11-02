# Rule files

For anyone reading, checking or changing how Open Altio treats the data.

Contract version 1.0: [Rules from other folders](#rules-from-other-folders) is part of Open Altio's [written contract](contract.md).

Every number and every policy Open Altio applies is a rule: one Markdown file in [`rules/`](https://github.com/Altio-AI/open-altio/tree/main/rules). The code reads each value from its file, so the words and the behaviour cannot drift apart, and a test fails if a rule's value is typed into the code instead.

## How to read one

A rule file has two parts: front matter, then text.

**The front matter** sits between the `---` lines at the top:

| Key | Meaning |
|---|---|
| `rule` | The rule's name, the file name without `.md`. `rules.toml` and the methods page use the same name. |
| `values` | The numbers and choices the code reads. |
| `line` | For a data rule: one plain sentence, shown under the rule's name on the methods page. |
| `settable` | For a data rule: the values `rules.toml` and the methods page let you change, each with a plain label. |
| `always_on` and `why_locked` | For a rule the pipeline cannot run without. It cannot be switched off, and `why_locked` says why. |
| `enforced_in` | The code that applies the rule and the tests that prove it. |
| `placeholder` | `true` for a rule whose values wait on their evidence: a starting point, not yet decided. Its text names the notebook that will decide them. |

**The text** has three parts:

1. The rule's name as its heading.
2. What it does and why, in plain words. The methods page shows this.
3. The exact rule, and why it is the rule, with the evidence.

`rules/steps.yaml` lists the steps a release is built in and the data rules that act in each, in order.

## Where to find them

- [`rules/README.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/README.md) lists every rule with one line each.
- [The methods page](https://open.altioai.com/methods) shows the data rules in pipeline order, each with what it moved on the release and the evidence behind it.

## Changing one

- For your own builds: [Change a rule](../customise/rules.md), with `rules.toml`. No code changes.
- For everyone: [propose a rule change](https://github.com/Altio-AI/open-altio/issues/new?template=rule.yml). A rule changes in one pull request holding the rule file, its test and the docs that describe it; [CONTRIBUTING.md](https://github.com/Altio-AI/open-altio/blob/main/CONTRIBUTING.md#how-a-rule-changes) says what each needs.

## Reading a value in code

```python
from open_altio.rulebook import value

per_page = value("explorer-page-size", "cases_per_page")
```

- **`open_altio.rulebook` is the only way code reads a rule.**
- **`is_on("deleted-cases")`** says whether a data rule acts in the build running.
- **An unknown rule or value raises an error,** so a typo fails loudly.

## Rules from other folders

A product built on Open Altio keeps its own numbers and policies as rule files too, in a folder of its own, and adds that folder once as it loads:

```python
from pathlib import Path

from open_altio import rulebook

rulebook.add_rules_dir(Path(__file__).parent / "rules", prefix="acme-")
```

- **Its rules are read like Open Altio's.** `rulebook.value("acme-review-days", "days")` reads one, after `rules/` is searched. A product's rule file has the same front matter (`rule`, `line`, `values`, `enforced_in`, `placeholder`) and the same text.
- **Every name carries the product's prefix.** In a folder added with a prefix, a rule whose file name does not start with it is refused, naming the file and the prefix, so a product's rule never takes a name Open Altio may use later.
- **A name lives in one folder.** A name in two folders is refused, so a product cannot replace one of Open Altio's rules with a copy of its own.
- **Tests change values with `open_altio.testing.rules.rules_with`,** which copies every folder, with its prefix, and changes only the values named.
