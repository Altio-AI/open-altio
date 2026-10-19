"""What the notebooks share: one look for their charts, the events marked on every time axis,
titles that state each chart's point, and showing and saving the cards they compute.

    from open_altio.faers.insights.cards.notebook import mark_years, plot_card, setup, title
    setup()
    title(ax, "Most cases publish one version", "Each bar is ...", "How many versions ...?")
    for card in cards:
        plot_card(card)
    write_cards(cards, "01_volume_over_time")   # -> notebooks/out/cards/01_volume_over_time.json

The release build computes the same cards itself (src/open_altio/faers/insights/methods.py); the
files written here are for checking a notebook's cards by eye, never committed.
"""

from __future__ import annotations

import json
import os
import textwrap
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import TAG_LABELS

OUT_ENV = "OPEN_ALTIO_INSIGHTS_OUT"
DEFAULT_OUT = Path(__file__).resolve().parents[5] / "notebooks" / "out"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#7a7a72", "#c3c2b7"]
ERA = {"legacy": SERIES[1], "faers": SERIES[0]}  # legacy orange, FAERS blue, in every notebook
GUIDE, GUIDE_TEXT = "#7a7a72", "#3a3a38"

# Marked on every time axis, so a jump in a chart is put down to its cause on sight:
# (quarter, the same moment as a year, label).
EVENTS = [
    ("2012q4", 2012.75, "AERS to FAERS"),
    ("2014q3", 2014.5, "2014Q3 schema"),
    ("2015q3", 2015.4, "e-sub mandate"),
    ("2020q1", 2020.2, "COVID"),
    ("2025q3", 2025.5, "occp NULL surge"),
]


def setup(colwidth: int | None = None) -> None:
    """pandas' display options and matplotlib's look, the same in every notebook; `colwidth`
    widens the text columns of a notebook whose tables quote long values."""
    import matplotlib as mpl
    import pandas as pd
    from matplotlib.rcsetup import cycler

    pd.set_option("display.max_rows", 200)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 60)
    if colwidth is not None:
        pd.set_option("display.max_colwidth", colwidth)
    mpl.rcParams.update(
        {
            "axes.prop_cycle": cycler(color=SERIES),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "lines.linewidth": 2,
            "figure.dpi": 100,
            "axes.titlesize": 12,
        }
    )


def _guide(ax: Any, x: float, label: str) -> None:
    ax.axvline(x, color=GUIDE, lw=1, ls=":", zorder=5)
    ax.text(
        x,
        ax.get_ylim()[1],
        " " + label,
        rotation=90,
        va="top",
        ha="left",
        fontsize=8,
        color=GUIDE_TEXT,
        zorder=6,
    )


def mark_years(ax: Any) -> None:
    """The events as dotted guides on a numeric year axis."""
    lo, hi = ax.get_xlim()
    for _, x, label in EVENTS:
        if lo <= x <= hi:
            _guide(ax, x, label)


def mark_quarters(ax: Any, quarters: Iterable[str]) -> None:
    """The events as dotted guides on a categorical axis of `quarters`, in their order."""
    qs = list(quarters)
    for quarter, _, label in EVENTS:
        if quarter in qs:
            _guide(ax, qs.index(quarter) - 0.5, label)


def quarter_ticks(ax: Any, quarters: Iterable[str], every: int = 4) -> None:
    """Label every `every`th quarter of a categorical quarter axis, as FDA names it (2026Q2)."""
    qs = list(quarters)
    ax.set_xticks(range(0, len(qs), every))
    ax.set_xticklabels([q.upper() for q in qs[::every]], rotation=90, fontsize=8)


def label_bars(ax: Any, bars: Any, fmt: str = "{:,.0f}", horizontal: bool = False) -> None:
    """Each bar's value written at its end, also when it is stacked on another."""
    for b in bars:
        if horizontal:
            v = b.get_width()
            end = b.get_x() + v
            ax.text(
                end, b.get_y() + b.get_height() / 2, " " + fmt.format(v), va="center", fontsize=8
            )
        else:
            v = b.get_height()
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_y() + v,
                fmt.format(v),
                ha="center",
                va="bottom",
                fontsize=8,
            )


def title(
    ax: Any,
    claim: str,
    guide: str | None = None,
    question: str | None = None,
    backs: str | None = None,
    width: int | None = None,
    above: float = 0,
) -> None:
    """Title a chart with its point, in bold; the subtitle says how to read it, then what it
    asks, and on its own line the rule it backs. `width` is the subtitle's line length in
    characters (by default what fits over the axes); `above` leaves that many points between
    the axes and the subtitle for labels drawn above the axes."""
    width = width or max(60, int(ax.get_position().width * ax.figure.get_figwidth() * 14))
    sub = textwrap.fill(" ".join(x for x in (guide, question) if x), width)
    if backs:
        sub = f"{sub}\n{backs}" if sub else backs
    lines = sub.count("\n") + 1 if sub else 0
    ax.set_title(
        textwrap.fill(claim, int(width * 0.72)),
        loc="left",
        fontsize=12,
        fontweight="bold",
        pad=above + 11 + 11.5 * lines,
    )
    if sub:
        ax.annotate(
            sub,
            (0, 1),
            xycoords="axes fraction",
            xytext=(0, 5 + above),
            textcoords="offset points",
            fontsize=9,
            color="0.35",
            va="bottom",
        )


def header(fig: Any) -> Any:
    """A blank strip across a figure's panels, above everything already drawn (panel titles,
    legends), to carry the figure's title()."""
    fig.canvas.draw()
    top = fig.get_tightbbox(fig.canvas.get_renderer()).y1 / fig.get_figheight()
    boxes = [a.get_position() for a in fig.axes]
    left, right = min(b.x0 for b in boxes), max(b.x1 for b in boxes)
    ax = fig.add_axes([left, top + 0.05 / fig.get_figheight(), right - left, 1e-4])
    ax.axis("off")
    return ax


def heatmap(
    df: Any,
    claim: str,
    guide: str | None = None,
    question: str | None = None,
    cmap: str = "Blues",
    figsize: tuple[float, float] = (16, 5),
    vmin: float = 0,
    vmax: float = 100,
    cbar_label: str = "% of rows populated",
) -> None:
    """A single-hue map of `df` (rows are fields, columns are quarters in order) with the events
    marked, titled with its claim."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(df.values, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_yticks(range(len(df.index)))
    ax.set_yticklabels(df.index, fontsize=9)
    quarter_ticks(ax, df.columns)
    ax.grid(False)
    quarters = list(df.columns)
    for quarter, _, label in EVENTS:
        if quarter in quarters:
            i = quarters.index(quarter)
            ax.axvline(i - 0.5, color="#1a1a19", lw=1, ls=":")
            ax.text(i - 0.5, -0.7, label, rotation=90, va="bottom", ha="left", fontsize=8)
    title(ax, claim, guide, question, above=72)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01, label=cbar_label)
    plt.show()


def out_dir() -> Path:
    return Path(os.environ.get(OUT_ENV) or DEFAULT_OUT).expanduser()


def write_cards(cards: list[dict], name: str) -> Path:
    path = out_dir() / "cards" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cards, indent=2) + "\n", encoding="utf-8")
    return path


def plot_card(card: dict, ax: Any = None) -> None:
    """Draw a card's chart with matplotlib, titled with its claim, the question it answers and
    its tag, then print its two sentences."""
    import matplotlib.pyplot as plt

    chart = card["chart"]
    xs = chart["x"]["values"]
    pos = list(range(len(xs)))
    if ax is None:
        _, ax = plt.subplots(figsize=(14, 4))
    series = chart["series"]
    if chart["type"] == "line":
        for i, s in enumerate(series):
            values = [float("nan") if v is None else v for v in s["values"]]
            ax.plot(pos, values, label=s["name"], color=SERIES[i % len(SERIES)], marker="o", ms=3)
    elif chart["type"] == "stacked_area":
        ax.stackplot(
            pos,
            *[[v or 0 for v in s["values"]] for s in series],
            labels=[s["name"] for s in series],
            colors=SERIES[: len(series)],
        )
    else:
        bottom = [0.0] * len(xs)
        for i, s in enumerate(series):
            vals = [v or 0 for v in s["values"]]
            ax.bar(
                pos, vals, bottom=bottom, label=s["name"], color=SERIES[i % len(SERIES)], width=0.8
            )
            bottom = [b + v for b, v in zip(bottom, vals, strict=True)]
    step = max(1, len(xs) // 30)
    ax.set_xticks(pos[::step])
    ax.set_xticklabels([str(x) for x in xs[::step]], rotation=90, fontsize=8)
    ax.set_xlabel(chart["x"]["label"])
    ax.set_ylabel(chart["y"]["label"] + (" (%)" if chart["y"]["unit"] == "percent" else ""))
    if chart["y"]["unit"] == "percent":
        ax.set_ylim(0, 100)
    tag = card["tag"]
    tag_text = TAG_LABELS[tag["kind"]]
    if tag["kind"] == "changed_pipeline":
        tag_text += f": {tag['step']}"
    title(ax, card["title"], chart.get("question"), backs=f"[{tag_text}]")
    if series:
        ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
    plt.show()
    print(card["two_sentences"])
