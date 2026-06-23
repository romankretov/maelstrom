"""Source registry — single place to look up a MarketDataSource by name."""

from .base import MarketDataSource
from .binance import CCXTBinanceSource
from .hyperliquid import HyperliquidSource

_FACTORIES = {
    "binance": CCXTBinanceSource,
    "hyperliquid": HyperliquidSource,
}


def list_sources() -> list[str]:
    return sorted(_FACTORIES.keys())


def get_source(name: str) -> MarketDataSource:
    try:
        return _FACTORIES[name]()
    except KeyError as e:
        raise ValueError(f"Unknown source: {name}. Known: {list_sources()}") from e
