# How to help

For anyone who wants to report something, suggest a change or send code, rules, mappings, notebooks or docs.

This page covers issues, labels, pull requests, security and conduct.

## Open an issue

Every issue starts from a form on the [new issue page](https://github.com/Altio-AI/open-altio/issues/new/choose):

| Form | For |
|---|---|
| Bug | Something works differently from its docs, its rule or its help text |
| Something in the data looks wrong | A count, a value or a case that does not match FDA's files or the methods page |
| Propose a rule change | A rule should work differently, a value should change, or a rule is missing |
| Idea | Something Open Altio could do that it does not do yet |
| Docs | A page, a help text or a README that is wrong, unclear or missing |

Each form starts with your own words, then asks for the facts someone needs to act on it. If you ran the command, `open-altio report` fills in the bug form for you.

We aim to answer within a week. A maintainer replies on your issue with the next step:

- **Confirmed,** with a label.
- **A question.**
- **A no,** with the reason.

## Labels

| Label | Means |
|---|---|
| `type: bug`, `type: data`, `type: rule`, `type: feature`, `type: docs` | What kind of issue it is |
| `area: pipeline`, `area: rules`, `area: explorer`, `area: cli`, `area: docs` | Which part it touches |
| `status: needs-triage` | New: a maintainer has not replied yet |
| `status: ready` | Has acceptance criteria an agent can check: ready to work on |
| `status: blocked` | Waiting on something else, which the issue names |
| `good first issue` | Small and well described, good for a first contribution |
| `help wanted` | We would welcome someone taking it on |

Milestones follow the data releases, one per FDA quarter.

## Send a pull request

[CONTRIBUTING.md](https://github.com/Altio-AI/open-altio/blob/main/CONTRIBUTING.md) says how to set up, run the checks and change a rule. In short:

- Pick an issue marked `status: ready`, or open one first for anything bigger than a small fix.
- One change per pull request. A behaviour change carries its rule file, its test and its docs page.
- Fill in the template, including the "I ran this" tick.
- Contributions made with AI are welcome, openly. A person owns each one and answers the review. Agents start at [AGENTS.md](https://github.com/Altio-AI/open-altio/blob/main/AGENTS.md).
- There is no CLA and no DCO to sign.

## Security and conduct

- **Security:** report problems privately, never in an issue. See [SECURITY.md](https://github.com/Altio-AI/open-altio/blob/main/SECURITY.md).
