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


async def _post_info(client: httpx.AsyncClient, url: str, payload: dict) -> dict:
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


async def fetch_account_equity(wallet_address: str, *, testnet: bool) -> float:
    """Return the user's total USDC equity (perp + spot USDC).

    HL splits funds across two wallets — perp (`clearinghouseState`) and
    spot (`spotClearinghouseState`). New users coming off the faucet
    often have all their USDC in spot, so reading perp alone returned 0
    when the wallet was clearly funded. We sum both.

    Raises HyperliquidInfoError on any network / HTTP / parse failure.
    Returns 0.0 only when HL responds successfully but neither wallet
    holds anything.
    """
    url = _TESTNET_URL if testnet else _MAINNET_URL
    short_wallet = wallet_address[:6] + "…" + wallet_address[-4:]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            perp = await _post_info(
                client,
                url,
                {"type": "clearinghouseState", "user": wallet_address},
            )
            spot = await _post_info(
                client,
                url,
                {"type": "spotClearinghouseState", "user": wallet_address},
            )
    except Exception as e:
        log.warning("hl.info.equity_failed", wallet=short_wallet, testnet=testnet, error=str(e))
        raise HyperliquidInfoError(str(e)) from e

    perp_equity = float((perp.get("marginSummary") or {}).get("accountValue") or 0)
    spot_usdc = 0.0
    for bal in spot.get("balances") or []:
        if (bal.get("coin") or "").upper() == "USDC":
            spot_usdc = float(bal.get("total") or 0)
            break

    total = perp_equity + spot_usdc

    # If we'd otherwise report $0, log what HL actually returned (key
    # names only, no full payload) so the user can debug whether the
    # wallet they pasted is the right one.
    if total == 0:
        log.info(
            "hl.info.equity.zero",
            wallet=short_wallet,
            testnet=testnet,
            perp_keys=list(perp.keys()),
            perp_margin_summary=perp.get("marginSummary"),
            spot_balances=spot.get("balances"),
        )
    else:
        log.info(
            "hl.info.equity",
            wallet=short_wallet,
            testnet=testnet,
            perp=perp_equity,
            spot_usdc=spot_usdc,
            total=total,
        )
    return total
