"""Invented reports enough for the statistics to fit: a story of its own (STORY), built into a
release apart from the main fake one (fixtures.py `stats_release`) so that one stays small.

    write_input(folder)    # one FAERS quarter of STORY, as FDA's zip

Each case names one or two drugs the invented DiAna dictionary knows (fakediana), as primary and
then secondary suspect, and one to three reactions. How often a drug's cases report a reaction
is drawn from DuMouchel's two-gamma model itself, so the prior fits; a few pairs (SIGNALS) are
reported far more often than the rest. Every case has its own manufacturer number and an event
date of its own, or none, so none is a duplicate of another.

The dates follow the case's number (`_dates`), so the time to onset has every outcome: the
primary suspect started a few days before the event, known to the day, except that every
NO_EVENT_DATE-th case gives no event date, every BEFORE-th starts after the event and every
MONTH_ONLY-th gives its start to the month alone; an event on the 1st reads as padded. The
secondary suspect's start is the event's month, as FDA often writes it.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from . import fakefda
from .fakefda import Drug, Report

QUARTER = "2026q2"
CASES = 2400
DRUGS = (
    "ASPIRIN",
    "IBUPROFEN",
    "WARFARIN",
    "OMEPRAZOLE",
    "METFORMIN",
    "DIGOXIN",
    "LISINOPRIL",
    "HUMIRA",
    "NEORAL",
    "TECFIDERA",
    "TRAMETINIB",
    "VALSARTAN",
)
REACTIONS = (
    "Nausea",
    "Headache",
    "Dizziness",
    "Fatigue",
    "Rash",
    "Vomiting",
    "Diarrhoea",
    "Pruritus",
    "Dyspnoea",
    "Arthralgia",
    "Pyrexia",
    "Cough",
    "Insomnia",
    "Back pain",
    "Constipation",
    "Oedema peripheral",
    "Hypertension",
    "Anxiety",
    "Abdominal pain",
    "Palpitations",
    "Haemorrhage",
    "Myalgia",
    "Alopecia",
    "Tremor",
    "Syncope",
    "Hypoglycaemia",
    "Urticaria",
    "Somnolence",
    "Chest pain",
    "Weight increased",
)
# (drug, reaction) reported many times more often than its drug's other reactions
SIGNALS = {
    ("WARFARIN", "Haemorrhage"): 12.0,
    ("METFORMIN", "Hypoglycaemia"): 10.0,
    ("HUMIRA", "Rash"): 6.0,
    ("DIGOXIN", "Palpitations"): 8.0,
}


NO_EVENT_DATE, BEFORE, MONTH_ONLY = 23, 13, 17


def _dates(i: int) -> tuple[str, str, str]:
    """Case i's event date, its primary suspect's start and end, as FDA writes them."""
    event = date(2019, 1, 1) + timedelta(days=i)
    start = event + timedelta(days=2) if i % BEFORE == 0 else event - timedelta(days=i % 45)
    end = start + timedelta(days=i % 30)
    written = start.strftime("%Y%m") if i % MONTH_ONLY == 0 else start.strftime("%Y%m%d")
    return (
        ("" if i % NO_EVENT_DATE == 0 else event.strftime("%Y%m%d")),
        written,
        end.strftime("%Y%m%d"),
    )


def _story(seed: int = 7) -> list[Report]:
    rng = random.Random(seed)
    # each pair's reporting ratio, from a mixture of two gammas (shape, scale): mostly near 1
    ratio = {
        (d, r): SIGNALS.get((d, r))
        or (rng.gammavariate(2.0, 2.5) if rng.random() < 0.1 else rng.gammavariate(6.0, 1 / 6.0))
        for d in DRUGS
        for r in REACTIONS
    }
    weight = [1.0 / (i + 3) for i in range(len(REACTIONS))]
    story = []
    for i in range(CASES):
        drugs = rng.sample(DRUGS, rng.choice((1, 1, 2)))
        rates = [
            w * sum(ratio[(d, r)] for d in drugs) for w, r in zip(weight, REACTIONS, strict=True)
        ]
        reacs: list[str] = []
        wanted = rng.choice((1, 1, 2, 3))
        while len(reacs) < wanted:
            pick = rng.choices(REACTIONS, weights=rates)[0]
            if pick not in reacs:
                reacs.append(pick)
        year = rng.choice(("2023", "2024", "2025", "2026"))
        event, start, end = _dates(i)
        story.append(
            Report(
                QUARTER,
                f"77{i:05d}1",
                f"77{i:05d}",
                "20260415",
                init_fda_dt=f"{year}0301",
                event_dt=event,
                age=str(rng.randint(1, 90)),
                age_cod="YR",
                sex=rng.choice("FFM"),
                drugs=[
                    Drug(d, d, role="SS")
                    if n
                    else Drug(d, d, role="PS", start_dt=start, end_dt=end)
                    for n, d in enumerate(drugs)
                ],
                reacs=reacs,
            )
        )
    return story


STORY = _story()


def write_input(folder: Path) -> Path:
    return fakefda.write_input(folder, quarters=(QUARTER,), story=STORY)
