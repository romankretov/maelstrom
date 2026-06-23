"""Source registry — single place to look up a MarketDataSource by name."""

from collections.abc import Callable
from typing import cast

from .base import MarketDataSource
from .binance import CCXTBinanceSource
from .hyperliquid import HyperliquidSource

# Concrete classes are structural subtypes of MarketDataSource (Protocol).
# mypy doesn't always infer that, so we widen the value type and cast on use.
_FACTORIES: dict[str, Callable[[], object]] = {
    "binance": CCXTBinanceSource,
    "hyperliquid": HyperliquidSource,
}


def list_sources() -> list[str]:
    return sorted(_FACTORIES.keys())


def get_source(name: str) -> MarketDataSource:
    try:
        instance = _FACTORIES[name]()
    except KeyError as e:
        raise ValueError(f"Unknown source: {name}. Known: {list_sources()}") from e
    return cast(MarketDataSource, instance)
