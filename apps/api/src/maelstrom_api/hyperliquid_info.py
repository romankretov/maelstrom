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


async def fetch_account_equity(wallet_address: str, *, testnet: bool) -> float | None:
    """Returns the user's total perp account value (USDC equity).

    Returns None on any error — caller decides whether to leave
    starting_capital at 0 or surface a 502.
    """
    url = _TESTNET_URL if testnet else _MAINNET_URL
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                json={"type": "clearinghouseState", "user": wallet_address},
            )
            resp.raise_for_status()
            data = resp.json()
        # `marginSummary.accountValue` is the total equity (USDC).
        equity = float((data.get("marginSummary") or {}).get("accountValue") or 0)
        log.info(
            "hl.info.equity",
            wallet=wallet_address[:6] + "…" + wallet_address[-4:],
            testnet=testnet,
            equity=equity,
        )
    except Exception as e:
        log.warning(
            "hl.info.equity_failed",
            wallet=wallet_address[:6] + "…" + wallet_address[-4:],
            testnet=testnet,
            error=str(e),
        )
        return None
    return equity
