# Writing these docs

For anyone changing a page on this site.

This page says how the site is built and the rules a page follows.

The site is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) from `docs/`, with `mkdocs.yml` at the root of the repository. Set up the repository as [CONTRIBUTING.md](https://github.com/Altio-AI/open-altio/blob/main/CONTRIBUTING.md#set-up-and-run-the-checks) says, then see your change as you write:

```sh
uv run mkdocs serve
```

- **`mkdocs build --strict` must pass** before a pull request merges. It fails on a broken link.
- **`scripts/check.py --all`** runs it with the other checks.

## How the site is organised

By reader, not by part of the code:

- **Use:** looking at the data, online or on your own machine.
- **Customise:** rebuilding from FDA's files and changing rules.
- **Contribute:** how to help, and how the code fits together.
- **Reference:** the command, the rule files and the data dictionary.
- **Methods:** the methods page and the background to it.

## Principles

- The first line of each page says who it is for.
- One fact, one place. Link to it instead of repeating it. A rule's values live in its rule file and its evidence on the methods page; a page here explains and links.
- Plain English, short sentences, no em dashes.
- Write for someone who has never seen the project: no internal names, no history of how a decision was reached. The CHANGELOG is the history.
- A behaviour change updates its rule, its test and the page that describes it in the same pull request.
- Delete a page nobody needs. Fewer, better pages.
