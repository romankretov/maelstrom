"""WebSocket endpoint that bridges Redis pub/sub bar streams to browsers.

URL: /ws/markets/{source}/{symbol}/{timeframe}
The worker (streams.StreamManager) publishes to channel
"bars:{source}:{symbol}:{timeframe}"; this endpoint subscribes and forwards
each message verbatim to the client.

Auth deferred: WebSocket connections are unauthenticated for now (market
data is non-sensitive). Phase 6 will add a query-token check.
"""

import asyncio
import contextlib

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from maelstrom_api.config import get_settings

log = structlog.get_logger()
router = APIRouter()


_redis_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(str(get_settings().redis_url))
    return _redis_client


@router.websocket("/ws/markets/{source}/{symbol}/{timeframe}")
async def ws_bars(
    websocket: WebSocket,
    source: str,
    symbol: str,
    timeframe: str,
) -> None:
    await websocket.accept()
    channel = f"bars:{source}:{symbol}:{timeframe}"
    pubsub = _redis().pubsub()
    try:
        await pubsub.subscribe(channel)
        log.info("ws.subscribe", channel=channel)
        # Tell client we're connected so it can show a "live" indicator.
        await websocket.send_json({"type": "subscribed", "channel": channel})

        # Concurrently pump pubsub messages and watch for client disconnect.
        async def reader() -> None:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                data = msg["data"]
                if isinstance(data, bytes):
                    await websocket.send_bytes(data)
                else:
                    await websocket.send_text(str(data))

        async def keepalive() -> None:
            # Receive (and discard) anything from the client; surfaces disconnects.
            while True:
                await websocket.receive_text()

        await asyncio.gather(reader(), keepalive())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("ws.error", channel=channel, error=str(e))
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        log.info("ws.unsubscribe", channel=channel)
