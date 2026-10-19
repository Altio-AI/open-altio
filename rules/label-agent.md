---
rule: label-agent
values:
  instructions_version: 1
  prompt: Follow INSTRUCTIONS.md in this folder.
  retries: 10
  first_wait_seconds: 30
  wait_factor: 2
  longest_wait_seconds: 1800
  attempt_timeout_minutes: 60
settable:
  retries:
    label: Retries for items left without an answer
    minimum: 0
  first_wait_seconds:
    label: Wait before the first retry (seconds)
    minimum: 0
  wait_factor:
    label: Each wait longer than the one before by (times)
    minimum: 1
  longest_wait_seconds:
    label: Longest wait (seconds)
    minimum: 0
enforced_in:
  - src/open_altio/labelreview/suggest.py
  - src/open_altio/labelreview/runner.py
  - src/open_altio/labelreview/__main__.py
  - tests/labelreview/test_suggest.py
  - tests/labelreview/test_runner.py
---
# Agent suggestions, file in and file out

For the label phrases in a review batch, an agent answers the coding question (rule label-coding): the MedDRA preferred terms each phrase states as a reaction, or a reason for none, with the words of the label it used as evidence and a short reason. Any agent works: Claude Code, Codex, Gemini CLI, a local model, or a person typing. Open Altio calls none of them and holds no key for any.

- `python -m open_altio.labelreview export` writes a folder for the current batch: `INSTRUCTIONS.md`, `items.jsonl`, `preferred_terms.txt` (the version's preferred terms, for exact spelling) and an empty `suggestions.jsonl`. `INSTRUCTIONS.md` is complete on its own: the instructions file named by `instructions_version` (`src/open_altio/labelreview/instructions/v<version>.md`), which says exactly what to read and what to write, followed by the coding question and its rules word for word.
- The person tells their agent to follow `INSTRUCTIONS.md` in that folder.
- `python -m open_altio.labelreview import --by "<agent and model>"` checks every line the agent wrote: an item of this export, every term a preferred term of the MedDRA version whose folder holds the review (`licensed/meddra/<version>/`, from the release's licensed part, as the label step reads it; the release's own version when the folder names none), evidence copied from the label phrase, terms or one known reason for none but not both, a note for "other". One bad line refuses the whole file, with the reason for each line, and nothing is kept. A good file is kept with who produced it, the instructions version and when.

`python -m open_altio.labelreview run --agent "<command>"` does all three with the person's own agent command line: `claude -p`, `codex exec`, `gemini -p`, or a local model's command. It starts the command in the batch folder with `prompt` as its last argument, imports what it wrote, then runs it again on only the items it left without an answer, up to `retries` more times. When a file cannot be imported, the reasons are left in the folder's `problems.txt` for the next try. Before each retry it waits, `first_wait_seconds` the first time and `wait_factor` times longer each time after, never more than `longest_wait_seconds`. An attempt that runs past `attempt_timeout_minutes` is stopped. Each attempt is logged in the batch folder's `attempts.jsonl`: when, which items, and the outcome.

There is no fallback model: the same agent is asked each time. An item the agent left out, or answered with neither terms nor a reason, is "no answer". After the last retry it is "refused". Either way it reaches the reviewer to decide, and counts as a disagreement for the agreement gate (rule label-review-gates). "Other" is only for a phrase that states no reaction for a reason the list does not give.

A change to the instructions is a new file with the next version number, so older suggestions can still be traced to the words that produced them. A change to the instructions or the coding rules makes every earlier suggestion stale, and the batch is exported again.

A suggestion is never a decision. The reviewer accepts or rejects each one on the review page (rule label-review), and only decided items become the frozen data a release build reads. A build never calls an agent.

**Why:** anyone can rerun a batch with the agent they have, read the exact words it was given, and send a better version of those words.
