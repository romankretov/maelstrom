"""Backtest <-> live SDK parity tests.

The two engines have separate code paths (BacktestEngine in
engine/runner.py and LiveContext in live/runner.py), but they MUST
present an identical Strategy SDK surface — same method signatures,
same return shapes, same ordering. These tests assert that.

Scope:
- history(symbol, n) returns the same list (oldest-first) in both
- position(symbol) for an unknown symbol returns a zero-Position in both
- A canned strategy run through both observes identical bar sequences
  via self.history during on_bar

We don't compare fills directly here — fills go through different
brokers (PaperBroker / HyperliquidBroker / ShadowBroker) with their
own slippage + fee models, and those are exercised by their own
tests. This file is about the SDK contract.
"""

from datetime import UTC, datetime, timedelta

import pytest

from maelstrom_worker.engine.runner import BacktestEngine
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar
from maelstrom_worker.live.runner import LiveContext


def _bars(n: int, symbol: str = "BTC-PERP") -> list[EngineBar]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        EngineBar(
            source="binance",
            symbol=symbol,
            ts=base + timedelta(hours=i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000.0,
        )
        for i in range(n)
    ]


def _make_live_ctx() -> LiveContext:
    # session_maker / broker / id strings are never touched by the SDK
    # surface methods we test (history, position, submit_order shape).
    # Pass placeholders so we don't pull in DB/Redis dependencies.
    return LiveContext(
        live_strategy_id="00000000-0000-0000-0000-000000000000",
        account_id="00000000-0000-0000-0000-000000000001",
        source="binance",
        broker=None,  # type: ignore[arg-type]
        session_maker=None,  # type: ignore[arg-type]
    )


def test_history_returns_chronological_in_both_engines() -> None:
    bt = BacktestEngine(initial_capital=10_000)
    live = _make_live_ctx()
    bars = _bars(10)
    for b in bars:
        bt.history_per_symbol[b.symbol].append(b)
        live.history_per_symbol[b.symbol].append(b)

    bt_h = bt.history("BTC-PERP", n=5)
    live_h = live.history("BTC-PERP", n=5)

    assert [x.ts for x in bt_h] == [x.ts for x in live_h]
    # Last item should be the most recent bar (newest at end).
    assert bt_h[-1].ts == bars[-1].ts
    assert live_h[-1].ts == bars[-1].ts
    # First item should be 5 bars before the most recent.
    assert bt_h[0].ts == bars[-5].ts


def test_history_capped_at_n_in_both_engines() -> None:
    bt = BacktestEngine(initial_capital=10_000)
    live = _make_live_ctx()
    for b in _bars(20):
        bt.history_per_symbol[b.symbol].append(b)
        live.history_per_symbol[b.symbol].append(b)

    # Even with 20 bars stored, history(n=3) returns at most 3.
    assert len(bt.history("BTC-PERP", n=3)) == 3
    assert len(live.history("BTC-PERP", n=3)) == 3


def test_history_shorter_than_n_before_fill() -> None:
    bt = BacktestEngine(initial_capital=10_000)
    live = _make_live_ctx()
    for b in _bars(2):  # only 2 bars seen so far
        bt.history_per_symbol[b.symbol].append(b)
        live.history_per_symbol[b.symbol].append(b)

    assert len(bt.history("BTC-PERP", n=10)) == 2
    assert len(live.history("BTC-PERP", n=10)) == 2


def test_position_returns_zero_for_unknown_symbol() -> None:
    bt = BacktestEngine(initial_capital=10_000)
    live = _make_live_ctx()
    assert bt.position("BTC-PERP").qty == 0
    assert live.position("BTC-PERP").qty == 0


def test_strategy_sees_identical_history_in_both_engines() -> None:
    """Run the same Recorder strategy against both engines' SDK surface
    on identical bars; assert it observes identical history slices.

    We drive the per-bar plumbing directly (last_prices set + history
    appended) the way each engine's bar loop does it, then call
    on_bar. This matches what BacktestEngine.run() and LiveRunner do
    internally without dragging in the async glue.
    """

    class Recorder(Strategy):
        symbols = ("BTC-PERP",)
        timeframe = "1h"

        def on_init(self) -> None:
            self.observations: list[tuple[str, int, str]] = []

        def on_bar(self, bar: EngineBar) -> None:
            h = self.history(bar.symbol, n=3)
            newest_close = f"{h[-1].close:.4f}" if h else ""
            self.observations.append((bar.symbol, len(h), newest_close))

    bars = _bars(10)

    # ---- drive Recorder against BacktestEngine
    bt = BacktestEngine(initial_capital=10_000)
    bt_rec = Recorder()
    bt_rec._ctx = bt  # type: ignore[assignment]
    bt_rec._params = {}
    bt_rec.on_init()
    for b in bars:
        bt._current_ts = b.ts
        bt.last_prices[b.symbol] = b.close
        bt.history_per_symbol[b.symbol].append(b)
        bt_rec.on_bar(b)

    # ---- drive Recorder against LiveContext
    live = _make_live_ctx()
    live_rec = Recorder()
    live_rec._ctx = live  # type: ignore[assignment]
    live_rec._params = {}
    live_rec.on_init()
    for b in bars:
        live.last_prices[b.symbol] = b.close
        live.history_per_symbol[b.symbol].append(b)
        live_rec.on_bar(b)

    assert bt_rec.observations == live_rec.observations
    # Sanity: history should grow monotonically up to the cap (n=3), and
    # the newest close should be the current bar's close on every call.
    assert bt_rec.observations[0] == ("BTC-PERP", 1, "100.5000")
    assert bt_rec.observations[2][1] == 3  # capped at n=3 from bar 3 onward
    assert bt_rec.observations[-1] == ("BTC-PERP", 3, "109.5000")
