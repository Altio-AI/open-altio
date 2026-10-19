"""Read the rules, list the data rules, and keep a person's own choices.

`value` is the only way code reads a rule's values, so the rule file and the behaviour cannot
drift apart:

    from open_altio.rulebook import value
    timeout = value("sql-limits", "timeout_seconds")

The rules folder is `rules/`, inside the installed package or at the top of a checkout. A
package that brings rules of its own adds its folder with `add_rules_dir(path)`; rules are then
looked up in `rules/` first and in each added folder after it, and a name may be in only one of
them. Tests point the loader elsewhere with `use_rules_dir(path)` (in place of `rules/`),
`use_rules_dirs(paths)` (in place of every folder) or the `OPEN_ALTIO_RULES_DIR` environment
variable.

A build runs under a person's choices (`load_user_rules`, `use_user_rules`): `value` then gives
their value where they changed one, and `is_on` says whether a data rule acts.
"""

from .catalogue import NotADataRule, RuleInfo, RuleValue, Step, catalogue, data_rule, steps
from .choices import (
    FILE_NAME,
    UserRules,
    UserRulesError,
    check_user_rules,
    differences,
    from_differences,
    load_user_rules,
    rules_toml,
    save_user_rules,
)
from .loader import (
    ENV_VAR,
    NOT_YET_BUILT,
    REQUIRED_KEYS,
    Rule,
    RuleError,
    UnknownRule,
    UnknownValue,
    add_rules_dir,
    all_rules,
    data_root,
    is_on,
    parse_rule_file,
    rule,
    rule_names,
    rules_dir,
    rules_dirs,
    use_rules_dir,
    use_rules_dirs,
    use_user_rules,
    value,
)

__all__ = [
    "ENV_VAR",
    "FILE_NAME",
    "NOT_YET_BUILT",
    "REQUIRED_KEYS",
    "NotADataRule",
    "Rule",
    "RuleError",
    "RuleInfo",
    "RuleValue",
    "Step",
    "UnknownRule",
    "UnknownValue",
    "UserRules",
    "UserRulesError",
    "add_rules_dir",
    "all_rules",
    "catalogue",
    "check_user_rules",
    "data_root",
    "data_rule",
    "differences",
    "from_differences",
    "is_on",
    "load_user_rules",
    "parse_rule_file",
    "rule",
    "rule_names",
    "rules_dir",
    "rules_dirs",
    "rules_toml",
    "save_user_rules",
    "steps",
    "use_rules_dir",
    "use_rules_dirs",
    "use_user_rules",
    "value",
]
