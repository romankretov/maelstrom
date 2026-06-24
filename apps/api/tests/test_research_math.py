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
