"""Server WebSocket locale. Verso i client: stato, livello voce, sottotitoli. Dai client: comandi (wake, stop, mute, voice...)."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from .state import Hub

log = logging.getLogger("aria.display")


async def serve_display(hub: Hub, host: str = "127.0.0.1", port: int = 8765, fps: int = 30):
    from websockets.asyncio.server import serve

    async def reader(ws):
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(msg, dict) and "cmd" in msg:
                    hub.dispatch_command(msg)
        except Exception:                                           # noqa: BLE001
            pass

    async def handler(ws):
        sub = hub.subscribe()
        rd = asyncio.ensure_future(reader(ws))
        last = 0.0
        try:
            await ws.send(json.dumps(hub.snapshot()))
            while not rd.done():
                get = asyncio.ensure_future(sub.get())
                done, _ = await asyncio.wait({get, rd}, return_when=asyncio.FIRST_COMPLETED)
                if rd in done:                                      # il client e' andato via
                    get.cancel()
                    break
                msg = get.result()
                if msg.get("type") == "level":                      # i livelli al massimo a `fps` al secondo
                    wait = 1.0 / fps - (time.monotonic() - last)
                    if wait > 0:
                        await asyncio.sleep(wait)
                        try:
                            msg = sub.get_nowait() if sub._level is not None and not sub._events else msg
                        except asyncio.QueueEmpty:
                            pass
                await ws.send(json.dumps(msg))
                last = time.monotonic()
        except Exception:                                           # noqa: BLE001
            pass
        finally:
            rd.cancel()
            hub.unsubscribe(sub)

    server = await serve(handler, host, port)
    log.info("display WebSocket su ws://%s:%d", host, port)
    return server
