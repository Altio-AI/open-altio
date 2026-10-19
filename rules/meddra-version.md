---
rule: meddra-version
line: Every term in a release is read in one edition of MedDRA, the drug-safety dictionary, the newest when it is built, so all its counts use the same terms.
values:
  used: the newest English version held when the release is built
  language: English
  release_dates: ["03-01", "09-01"]
enforced_in:
  - src/open_altio/faers/meddra/versions.py
  - src/open_altio/faers/meddra/licensed.py
  - src/open_altio/explorer/meddra.py
  - tests/faers/test_meddra_licensed.py
  - tests/explorer/test_meddra.py
---
# One MedDRA edition per release

Each release is read to one MedDRA version, the newest held when the release is built, and everything in it uses that version: the reading of FDA's terms to today's PTs (`rules/meddra-terms.md`) and the steps that build on it, such as label flags, statistics and SMQs. A new MedDRA version waits until just before the next data build, and is never taken up partway through a release, so every count in a release is in one version. There is no change-over date, and a release never holds two versions.

A release is built with `used`. MedDRA publishes version x.0 on the first of `release_dates` and x.1 on the second (29.1 on 1 September 2026); the licensed manifest records the version's release date. A build given MedDRA's files (`python -m open_altio.faers build --meddra <folder>`, or a host's newest held version) reads the release to them as it builds it. `python -m open_altio.faers meddra --release <release> --meddra <folder>` reads a release already built, replacing the version it held. Only the `language` release is taken.

A MedDRA file older than the data is refused, by the check in `rules/meddra-terms.md` that stops the build when a reaction text matches nothing. FAERS's reaction field holds only MedDRA terms, so a text that is no name in the file, nor in its history file, means the data is coded in a later version. On the 2026Q2 release, whose newest quarter is coded in 29.0, a 28.1 file would leave 5,994 of that quarter's reaction rows matching nothing.

**Why:** each FAERS quarterly file is coded in the MedDRA version current when FDA built it, and FDA never reissues one, so the older the quarter, the more of its terms are no longer current: up to 10.3% of an AERS quarter's reaction rows. Reading the whole release to one version, the newest, makes every quarter comparable and keeps every number in the release consistent; a version taken up partway through would move counts between two looks at the same release, and two versions in one release would give two answers to one question. 89 of the 90 quarters to 2026Q2 fit exactly one MedDRA version, and none is more than one version from its time; 2017Q1 fits none, by 2 rows. The evidence is `notebooks/faers/06_meddra_versions`, section 2.
