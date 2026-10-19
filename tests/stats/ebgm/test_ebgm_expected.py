"""Expected counts within strata, the cells never seen, and squashing
(src/open_altio/stats/ebgm/expected.py), worked by hand."""

from __future__ import annotations

import pytest

from open_altio.stats import ebgm as g


def test_expected_count_sums_over_strata_by_hand():
    """Stratum A: 4 cases, 2 name X, 1 names Y. Stratum B: 2 cases, 1 names X, 2 name Y.
    E(X, Y) = 2*1/4 + 1*2/2 = 1.5. Z is only in A: E(X, Z) = 2*3/4 = 1.5."""
    out = g.expected_counts(
        pairs={"product": ["X", "X"], "event": ["Y", "Z"], "n": [2, 1]},
        product_strata={"product": ["X", "X"], "stratum": ["A", "B"], "n": [2, 1]},
        event_strata={"event": ["Y", "Y", "Z"], "stratum": ["A", "B", "A"], "n": [1, 2, 3]},
        strata={"stratum": ["A", "B"], "n": [4, 2]},
    )
    assert list(out["product"]) == ["X", "X"] and list(out["event"]) == ["Y", "Z"]
    assert list(out["N"]) == [2, 1]
    assert out["E"] == pytest.approx([1.5, 1.5], rel=1e-12)


def test_expected_counts_refuse_a_product_with_no_stratum_counts():
    with pytest.raises(ValueError, match="no stratum counts"):
        g.expected_counts(
            pairs={"product": ["X"], "event": ["Y"], "n": [1]},
            product_strata={"product": ["W"], "stratum": ["A"], "n": [1]},
            event_strata={"event": ["Y"], "stratum": ["A"], "n": [1]},
            strata={"stratum": ["A"], "n": [1]},
        )


def test_squash_merges_only_the_same_n_with_close_e():
    """At 50 bins a decade, 1.00 and 1.01 share a bin; 2.0 and N = 2 do not."""
    n, e, w = g.squash([1, 1, 1, 2], [1.0, 1.01, 2.0, 1.0], bins_per_decade=50)
    points = sorted(zip(n.tolist(), e.round(6).tolist(), w.tolist(), strict=False))
    assert points == [(1, 1.005, 2.0), (1, 2.0, 1.0), (2, 1.0, 1.0)]


def test_squash_weights_the_mean_e():
    n, e, w = g.squash([0, 0], [1.0, 1.01], bins_per_decade=50, w=[3.0, 1.0])
    assert n.tolist() == [0] and w.tolist() == [4.0]
    assert e[0] == pytest.approx((3 * 1.0 + 1.01) / 4)


@pytest.mark.parametrize("block", [1, 500])  # rule-literal-ok: block sizes
def test_unseen_cells_worked_by_hand(block):
    """As above, plus product V (one case, in B) and product W (one case, in A).
    Seen: X with Y. Never seen: X-Z 2*3/4 = 1.5, W-Y 1*1/4 = 0.25, W-Z 1*3/4 = 0.75,
    V-Y 1*2/2 = 1.0. V-Z has E = 0 (no stratum holds both) and is left out."""
    e, w = g.unseen_cells(
        pairs={"product": ["X"], "event": ["Y"], "n": [2]},
        product_strata={
            "product": ["X", "X", "W", "V"],
            "stratum": ["A", "B", "A", "B"],
            "n": [2, 1, 1, 1],
        },
        event_strata={"event": ["Y", "Y", "Z"], "stratum": ["A", "B", "A"], "n": [1, 2, 3]},
        strata={"stratum": ["A", "B"], "n": [4, 2]},
        bins_per_decade=50,
        block=block,
    )
    assert sorted(zip(e.round(12).tolist(), w.tolist(), strict=False)) == [
        (0.25, 1.0),
        (0.75, 1.0),
        (1.0, 1.0),
        (1.5, 1.0),
    ]
