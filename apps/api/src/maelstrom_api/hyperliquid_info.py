"""Read-only Hyperliquid info endpoint helpers.

The HL info API doesn't require signing — just the wallet address. We
use it to fetch account equity when credentials are first added, so the
user doesn't have to type a "starting capital" guess for live accounts.
"""

import httpx
import structlog

log = structlog.get_logger()

_MAINNET_URL = "https://api.hyperliquid.xyz/info"
_TESTNET_URL = "https://api.hyperliquid-testnet.xyz/info"


class HyperliquidInfoError(RuntimeError):
    """Network / HTTP / parse failure talking to the HL info endpoint.

    Distinct from "request succeeded but the wallet has $0 equity", which
    returns 0.0 — callers need to tell those apart so they don't silently
    swallow a connectivity issue as an empty wallet.
    """


async def fetch_account_equity(wallet_address: str, *, testnet: bool) -> float:
    """Return the user's total perp account value (USDC equity).

    Raises HyperliquidInfoError on any network / HTTP / parse failure.
    Returns 0.0 only when HL successfully responds but the wallet has no
    perp margin (new wallet or all-spot).
    """
    url = _TESTNET_URL if testnet else _MAINNET_URL
    short_wallet = wallet_address[:6] + "…" + wallet_address[-4:]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                json={"type": "clearinghouseState", "user": wallet_address},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("hl.info.equity_failed", wallet=short_wallet, testnet=testnet, error=str(e))
        raise HyperliquidInfoError(str(e)) from e

    equity = float((data.get("marginSummary") or {}).get("accountValue") or 0)
    log.info("hl.info.equity", wallet=short_wallet, testnet=testnet, equity=equity)
    return equity
