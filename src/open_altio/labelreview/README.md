# Label review

The part of the label coding that a person checks. Fixed rules code most of each label into MedDRA terms; what they leave uncertain (label phrases that read like reactions but match no term, and rule matches that may be wrong) comes here. For each phrase an agent answers one question, which MedDRA preferred terms the phrase states as a reaction to this drug, or none and why; one reviewer accepts or changes the answer; and decided codings are frozen so a release build codes the same and never runs an agent. The comparison rules, not this package, turn the codings into flags. A second queue checks a random sample of rule-made flags by hand, so the rules' accuracy can be published.

Rules: `label-coding`, `label-agent`, `label-review`, `label-review-gates`, `label-rule-check`.

## Running it

Every command takes `--folder`, the MedDRA version folder of a release's licensed part (`licensed/meddra/<version>/`) that holds `label_uncertain.jsonl` from the label step; the batch folders and the frozen codings go there too, and the label step reads the codings from there. It must sit inside a folder named `licensed` and outside anything git would publish; the command refuses anything else. Every term is checked against the preferred terms of that MedDRA version, read from the licensed part of the release that holds the folder, or of the release named with `--release`. A coding names the terms of one version.

```sh
F=<release>/licensed/meddra/29.1     # the MedDRA version folder the label step wrote its items into
python -m open_altio.labelreview definitions            # the coding question and its rules, to read
python -m open_altio.labelreview batch   --folder $F    # start the next batch (refused while a gate fails)
python -m open_altio.labelreview run     --folder $F --agent "claude -p"   # or export, your agent, import
python -m open_altio.labelreview review  --folder $F    # the page, on 127.0.0.1 (rule label-review)
python -m open_altio.labelreview status  --folder $F    # the gates, and the items decided as other
python -m open_altio.labelreview patterns --folder $F   # candidates for fixed rules
python -m open_altio.labelreview freeze  --folder $F    # what the label step reads
python -m open_altio.labelreview sample  --folder $F --flags <release>/parquet/label_flags_T.parquet
python -m open_altio.labelreview rates   --folder $F    # the rule check's error rates
python -m open_altio.labelreview redo start --folder $F # once, for the blind redo
```

## Any agent, file in and file out

Open Altio calls no model and needs no key. You use the agent you already have.

`export` writes the batch folder `$F/batch-<n>/`: `INSTRUCTIONS.md` (the published instructions and the coding question with its rules, all an agent needs), `items.jsonl` (the phrases to code), `preferred_terms.txt` (the version's preferred terms, so the agent can spell each exactly) and an empty `suggestions.jsonl`. When `run` finds a file it cannot import, it leaves the reasons in `problems.txt` for the agent's next try. Tell your agent to follow the instructions, in that folder, with whatever agent you use:

```sh
cd $F/batch-1
claude -p "Follow INSTRUCTIONS.md in this folder."    # or: codex exec "...", gemini -p "...", a local model
```

Then `import --folder $F --by "Claude Code, claude-opus-5-5"` checks every line the agent wrote, and every term against MedDRA's current preferred terms. One bad line refuses the whole file and says what is wrong on each line, so you fix it or ask again; nothing is kept from a refused file. A good file is kept with who produced it and the instructions version. An item the agent left out or left blank reaches the reviewer as "no answer".

`run --agent "<command>"` does the same with retries: it starts your command in the batch folder with the instruction above as its last argument, imports, and asks again for only the items left without an answer, waiting longer each time (rule label-agent). An item still without one after the last retry reaches the reviewer as "refused". Each attempt is logged in the batch folder's `attempts.jsonl`. Any command that works in its folder and takes the instruction as its last argument will do: `claude -p`, `codex exec`, `gemini -p`, or a local model's command line.

Altio runs its own batches with Claude Code, recording the model it used:

```sh
python -m open_altio.labelreview run --folder $F --agent "claude -p" --by "Claude Code, claude-opus-5-5"
```

With any other agent command line, the same:

```sh
python -m open_altio.labelreview run --folder $F --agent "<your agent's command>" --by "<agent, model>"
```

Either way the agent must be allowed to write files in the batch folder without stopping to ask. Each agent has its own option for that; see its help (for Claude Code, `claude --help`).

## The folder's files

| File | Written by | One line or object holds |
|---|---|---|
| `label_uncertain.jsonl` | the label step | `item_id`, `set_id`, `rxcui`, `section`, `sentence`, `candidate_pt` (may be empty), `why_uncertain`; and when it has them, `drug`, `label_date`, `rank` |
| `label_batches.jsonl` | `batch` | a batch: its number, item ids, its items as they were when it started, when |
| `batch-<n>/` | `export`, `run`, the agent | `INSTRUCTIONS.md`, `items.jsonl`, `suggestions.jsonl`, `export.json`, and `attempts.jsonl` from `run` |
| `label_suggestions.jsonl` | `import`, `run` | a suggestion: `pts`, `none_reason`, note, evidence, reason, `status` (`answered`, `no_answer` or `refused`), who produced it, instructions version |
| `label_decisions.jsonl` | the page | a decision (`kind` `phrase`) or a rule check mark (`kind` `rule_check`), with who and when; the newest per item counts |
| `label_codings_frozen.jsonl` | `freeze` | a decided item, for the label step: `item_id`, `set_id`, `section`, `sentence`, `pts` (empty for none), `none_reason`, `agent`, `instructions_version`, `reviewed_at` |
| `label_rule_check.json` | `sample` | the drawn sample of rule-decided flags |
| `label_redo_set.json`, `label_redo_answers.jsonl` | `redo start`, the page | the blind redo |

The label step reads `label_codings_frozen.jsonl` with its own reader (`open_altio.faers.labeldict.codings.read_codings`); the review only writes it. Only decided items are in it; a suggestion nobody reviewed never is. The file names the label step and the review share are named once, in `open_altio.faers.meddra` (`LABEL_CODINGS_FILE`, `LABEL_REVIEW_FILES`) and `open_altio.faers.labeldict` (`UNCERTAIN_FILE`), so building the MedDRA version again keeps the review's files (`KEPT_ON_REBUILD`). The `batch-<n>/` folders are the agent's working copies and are not kept; `export` writes them again.

## Modules

| Module | Job |
|---|---|
| `store.py` | The licensed folder: the check that it is not public, and reading and writing its files |
| `items.py` | The input items |
| `coding.py`, `terms.py` | The coding question and its reasons for none, from their rule; MedDRA's current preferred terms |
| `batches.py`, `gates.py` | Picking batches as a mix, and the gates before a bigger one |
| `suggest.py`, `instructions/` | The batch folder an agent works in, and checking and keeping what it wrote |
| `runner.py` | Running the person's agent command on the batch folder, with retries |
| `decisions.py`, `redo.py`, `patterns.py`, `freeze.py` | Decisions, the blind redo, repeated patterns, freezing |
| `rulecheck.py` | The random sample of rule-made flags and its error rates |
| `page.py`, `ui/` | The review page and its three queues |

A new reason for none: add it to `rules/label-coding.md` with a definition and examples. The agent reads the coding rules word for word, so every suggestion made before shows as not current and the batch is exported again. A change to the instructions themselves is a new file, `instructions/v<next>.md`, with `instructions_version` raised in `rules/label-agent.md`; older files stay, so each suggestion can be traced to the words that produced it.
