"""Unit tests for the pure-math helpers in routes/research.py.

DB + auth wiring is not under test here — that's covered by manual UI smoke
testing in docs/test-backlog.md.
"""

import math

from maelstrom_api.routes.research import _pearson, _stddev


def test_stddev_basic() -> None:
    assert _stddev([1.0]) == 0.0
    assert _stddev([1.0, 1.0, 1.0]) == 0.0
    # Sample stddev of [1, 2, 3, 4, 5] is sqrt(2.5)
    assert math.isclose(_stddev([1.0, 2.0, 3.0, 4.0, 5.0]), math.sqrt(2.5))


def test_pearson_perfect_positive() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 20.0, 30.0, 40.0, 50.0]
    corr, n = _pearson(xs, ys)
    assert n == 5
    assert corr is not None
    assert math.isclose(corr, 1.0, abs_tol=1e-9)


def test_pearson_perfect_negative() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [5.0, 4.0, 3.0, 2.0, 1.0]
    corr, _ = _pearson(xs, ys)
    assert corr is not None
    assert math.isclose(corr, -1.0, abs_tol=1e-9)


def test_pearson_uncorrelated() -> None:
    # Symmetric pair around mean — correlation should be ~0
    xs = [1.0, -1.0, 1.0, -1.0]
    ys = [1.0, 1.0, -1.0, -1.0]
    corr, _ = _pearson(xs, ys)
    assert corr is not None
    assert abs(corr) < 1e-9


def test_pearson_short_series_returns_none() -> None:
    corr, n = _pearson([], [])
    assert corr is None
    assert n == 0

    corr, n = _pearson([1.0], [2.0])
    assert corr is None
    assert n == 1


def test_pearson_aligns_to_shorter() -> None:
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [1.0, 2.0, 3.0]
    _, n = _pearson(xs, ys)
    assert n == 3


def test_pearson_constant_series_returns_none() -> None:
    # Zero variance on one side → undefined correlation
    xs = [1.0, 1.0, 1.0, 1.0]
    ys = [1.0, 2.0, 3.0, 4.0]
    corr, _ = _pearson(xs, ys)
    assert corr is None


# --- correlation alignment (regression for the gap-handling bug) ---


def _build_correlation_inputs(
    symbols: list[str],
    snapshots: list[tuple[int, dict[str, float]]],
) -> tuple[dict[str, list[float]], dict[str, float]]:
    """Mirror the prev/snap loop in routes/research.py exactly so we test it
    in isolation without needing a DB."""
    import math
    from collections import defaultdict
    from datetime import UTC, datetime

    by_ts: dict[datetime, dict[str, float]] = defaultdict(dict)
    for ts_s, snap in snapshots:
        ts = datetime.fromtimestamp(ts_s, tz=UTC)
        for s, c in snap.items():
            by_ts[ts][s] = float(c)

    returns: dict[str, list[float]] = {s: [] for s in symbols}
    prev: dict[str, float] = {}
    for ts in sorted(by_ts):
        snap = by_ts[ts]
        if not all(s in snap for s in symbols):
            prev = {}
            continue
        if all(s in prev for s in symbols):
            for s in symbols:
                cur = snap[s]
                p = prev[s]
                if p > 0:
                    returns[s].append(math.log(cur / p))
        prev = {s: snap[s] for s in symbols}
    return returns, prev


def test_correlation_alignment_drops_gap_periods() -> None:
    """If a symbol misses a tick, neither neighbor should get a return for
    that tick — otherwise A's 1-period return is correlated with B's
    multi-period return, biasing the result.
    """
    syms = ["A", "B"]
    # ts 1: both. ts 2: both. ts 3: only A. ts 4: both. ts 5: both.
    snaps: list[tuple[int, dict[str, float]]] = [
        (1, {"A": 100.0, "B": 200.0}),
        (2, {"A": 101.0, "B": 202.0}),
        (3, {"A": 102.0}),  # B missing — must reset alignment
        (4, {"A": 103.0, "B": 206.0}),
        (5, {"A": 104.0, "B": 208.0}),
    ]
    returns, _ = _build_correlation_inputs(syms, snaps)
    # Expected returns per symbol:
    #   ts2 vs ts1 (both present)  → 1 sample
    #   ts3 dropped (B missing, prev cleared)
    #   ts4 prev=ts3 but A only, prev cleared → no return
    #   ts5 vs ts4 (both present) → 1 sample
    # Total: 2 returns per symbol, lengths equal.
    assert len(returns["A"]) == len(returns["B"]) == 2


def test_correlation_alignment_no_gaps() -> None:
    syms = ["A", "B"]
    snaps: list[tuple[int, dict[str, float]]] = [
        (1, {"A": 100.0, "B": 200.0}),
        (2, {"A": 101.0, "B": 202.0}),
        (3, {"A": 102.0, "B": 204.0}),
    ]
    returns, _ = _build_correlation_inputs(syms, snaps)
    assert len(returns["A"]) == len(returns["B"]) == 2
