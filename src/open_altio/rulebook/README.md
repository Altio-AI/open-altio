# Rulebook

Reads the rules in `rules/`: the values in each file's front-matter, the data rules as people see them, and a person's own choices in a `rules.toml`. It is the only way code reads a number or a policy, so a rule file and the behaviour it describes cannot drift apart.

```python
from open_altio.rulebook import value

timeout = value("sql-limits", "timeout_seconds")
```

- `loader.py`: `value(rule, key)` gives one value, `rule(name)` the whole rule, `all_rules()` every rule, and `is_on(rule)` whether a data rule acts in the build running. An unknown rule or key raises `UnknownRule` or `UnknownValue`, so a typo fails loudly. The rules folder is `rules/` at the top of a checkout, or inside the installed package (`data_root()`).
- `catalogue.py`: `catalogue()` lists the data rules in the order the build applies them, each with its plain title and line, its step, whether it is always on and why, and the values a person may set with their plain labels; `steps()` lists the build's steps (`rules/steps.yaml`). A step may name one of its rules as its `switch`: that rule's switch turns the whole step on and off, and its other rules cannot be switched off alone.
- `choices.py`: a person's own rules. `load_user_rules(path)` reads a `rules.toml` (Altio's standard when there is none), `check_user_rules(rules)` says in plain sentences why a build would refuse them, `save_user_rules(path, rules)` writes them with every rule and Altio's standard as comments, and `differences(rules)` is what a release built with them records. A build runs under them with `use_user_rules(rules)`.
- Tests run code under a changed copy of the rules with `open_altio.testing.rules.rules_with`; `use_rules_dir(path)` and `OPEN_ALTIO_RULES_DIR` point the loader elsewhere.

Not here: the rules themselves. They live in `rules/`, and `rules/README.md` says how to read, set or change one. This package only reads; it never decides.
