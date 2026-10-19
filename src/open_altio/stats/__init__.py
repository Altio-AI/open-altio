"""Statistics over counts of cases, whatever the data source: a source counts its cases, these
modules do the arithmetic. Nothing here reads a release, a file or the web.

    ebgm/                 DuMouchel's Gamma-Poisson Shrinker: EBGM, EB05 and EB95 for each pair
    disproportionality.py PRR with its two chi-squares, ROR with its interval, RRR, IC with IC025
    screen.py             thresholds: the presets on each statistic's rule, and a person's own

Every setting is a value of the statistic's rule (rules/ebgm.md, prr.md, ror.md, rrr.md, ic.md),
and each module names the papers it is written from.
"""
