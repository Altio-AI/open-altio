# Security

Please do not report security problems in public issues.

Report them privately through GitHub's private vulnerability reporting: on this repository's **Security** tab, choose **Report a vulnerability** ([direct link](https://github.com/Altio-AI/open-altio/security/advisories/new)). Only the maintainers see your report. We aim to reply within a week, and we tell you what we will do and when. We credit you in the advisory unless you ask us not to.

## What is in scope

- The local explorer: anything that makes it reachable from another machine, lets a page send data anywhere other than the one Improve this note a person chooses to send, or lets read-only SQL write, read files or escape its limits.
- The `open-altio` command: downloads from FDA, the files it writes, the issue links `open-altio report` builds.
- The pipeline: an FDA file, a `rules.toml` or a mapping that makes a build run code or write outside its folders.
- The hosted service at open.altioai.com, including anything that could show MedDRA content to someone whose subscription is not verified, or one person's data or usage to another. Report it the same way; it reaches the same people.

Out of scope: the content of FAERS itself, which FDA publishes.

## Supported versions

Security fixes go into the latest release. Upgrade with `uv tool upgrade open-altio` (or `pipx upgrade open-altio`).
