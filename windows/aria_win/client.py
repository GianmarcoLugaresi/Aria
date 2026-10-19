"""WebSocket verso il backend (127.0.0.1:8765): riceve stato, voce e sottotitoli, manda i comandi (wake, stop, mute, voice). Come BackendClient di Backend.swift."""
from __future__ import annotations

import json
import queue
import threading
import time

URL = "ws://127.0.0.1:8765"


def _default_connect(url: str):
    from websockets.sync.client import connect
    return connect(url, open_timeout=3, max_size=None)


class BackendClient:
    def __init__(self, url: str = URL, on_message=None, on_connection=None, connect=None, sleep=time.sleep):
        self.url, self.on_message, self.on_connection = url, on_message, on_connection
        self._connect = connect or _default_connect
        self._sleep = sleep
        self._out: queue.Queue = queue.Queue()
        self._closed = False
        self.connected = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send(self, cmd: dict) -> None:
        self._out.put(json.dumps(cmd))

    def close(self) -> None:
        self._closed = True

    def _set(self, ok: bool) -> None:
        if ok != self.connected:
            self.connected = ok
            if self.on_connection:
                self.on_connection(ok)

    def _run(self) -> None:
        while not self._closed:
            try:
                with self._connect(self.url) as ws:
                    self._set(True)
                    while not self._closed:
                        self._flush(ws)
                        try:
                            raw = ws.recv(timeout=0.2)
                        except TimeoutError:
                            continue
                        self._deliver(raw)
            except Exception:                                           # noqa: BLE001
                pass
            self._set(False)
            if not self._closed:
                self._sleep(1.0)

    def _flush(self, ws) -> None:
        while True:
            try:
                ws.send(self._out.get_nowait())
            except queue.Empty:
                return

    def _deliver(self, raw) -> None:
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            return
        if isinstance(obj, dict) and self.on_message:
            self.on_message(obj)
