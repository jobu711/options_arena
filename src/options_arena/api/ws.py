"""WebSocket handlers for scan and debate progress streaming.

Bridges sync callbacks (``ProgressCallback``, ``DebateProgressCallback``) to
``asyncio.Queue`` objects that WebSocket handlers drain in real time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import urllib.parse
from collections.abc import Sequence

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from options_arena.agents import DebatePhase
from options_arena.scan import ScanPhase

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def _is_loopback_origin(origin: str) -> bool:
    """Check whether *origin* refers to a loopback address.

    Accepts ``http://127.0.0.1:5173``, ``http://localhost:8000``,
    ``http://[::1]:5173``, etc.  Returns ``False`` for empty strings
    or non-loopback hosts.
    """
    if not origin:
        return False
    parsed = urllib.parse.urlparse(origin)
    hostname = (parsed.hostname or "").lower()
    return hostname in _LOOPBACK_HOSTS


router = APIRouter()


_SENTINEL_TYPES: frozenset[str] = frozenset({"complete", "batch_complete", "error"})


def _safe_put(queue: asyncio.Queue[dict[str, object]], event: dict[str, object]) -> None:
    """Put event on queue, dropping progress events if full (CWE-770 defense).

    Sentinel events (complete, batch_complete, error) are never dropped — if the
    queue is full, one progress event is evicted to make room.  Without this,
    a dropped sentinel would cause the WebSocket consumer loop to spin forever.
    """
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        if event.get("type") in _SENTINEL_TYPES:
            # Evict oldest event to make room for the sentinel
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.error("Failed to enqueue sentinel event type=%s", event.get("type"))
        else:
            logger.debug("WebSocket queue full — dropping event type=%s", event.get("type"))


# ---------------------------------------------------------------------------
# Scan progress bridge
# ---------------------------------------------------------------------------


class WebSocketProgressBridge:
    """Bridges sync ``ProgressCallback`` to ``asyncio.Queue`` for WebSocket.

    ``__call__`` uses ``put_nowait`` because the scan pipeline's
    ``ProgressCallback`` is sync (called from ``asyncio.to_thread`` context).
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        _safe_put(
            self.queue,
            {"type": "progress", "phase": phase.value, "current": current, "total": total},
        )

    def complete(self, scan_id: int, *, cancelled: bool, outcomes_collected: int = 0) -> None:
        """Signal scan completion."""
        _safe_put(
            self.queue,
            {
                "type": "complete",
                "scan_id": scan_id,
                "cancelled": cancelled,
                "outcomes_collected": outcomes_collected,
            },
        )

    def error(self, message: str) -> None:
        """Signal an error event."""
        _safe_put(self.queue, {"type": "error", "message": message})


# ---------------------------------------------------------------------------
# Debate progress bridge
# ---------------------------------------------------------------------------


class DebateProgressBridge:
    """Bridges ``DebateProgressCallback`` to ``asyncio.Queue`` for WebSocket."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)

    def __call__(self, phase: DebatePhase, status: str, confidence: float | None) -> None:
        event: dict[str, object] = {
            "type": "agent",
            "name": phase.value,
            "status": status,
        }
        if confidence is not None:
            event["confidence"] = confidence
        _safe_put(self.queue, event)

    def complete(self, debate_id: int) -> None:
        """Signal debate completion."""
        _safe_put(self.queue, {"type": "complete", "debate_id": debate_id})

    def error(self, message: str) -> None:
        """Signal an error event."""
        _safe_put(self.queue, {"type": "error", "message": message})


# ---------------------------------------------------------------------------
# Batch progress bridge
# ---------------------------------------------------------------------------


class _BatchAgentBridge:
    """Per-ticker agent bridge that tags events with the ticker name."""

    def __init__(self, ticker: str, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._ticker = ticker
        self._queue = queue

    def __call__(self, phase: DebatePhase, status: str, confidence: float | None) -> None:
        event: dict[str, object] = {
            "type": "agent",
            "ticker": self._ticker,
            "name": phase.value,
            "status": status,
        }
        if confidence is not None:
            event["confidence"] = confidence
        _safe_put(self._queue, event)

    def complete(self, debate_id: int) -> None:
        """No-op — batch bridge handles completion."""

    def error(self, message: str) -> None:
        """Forward error to batch queue."""
        _safe_put(self._queue, {"type": "error", "ticker": self._ticker, "message": message})


class BatchProgressBridge:
    """Bridges batch debate progress to ``asyncio.Queue`` for WebSocket."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)

    def agent_bridge(self, ticker: str) -> _BatchAgentBridge:
        """Create a per-ticker agent progress bridge."""
        return _BatchAgentBridge(ticker, self.queue)

    def batch_progress(self, ticker: str, index: int, total: int, status: str) -> None:
        """Signal per-ticker batch progress."""
        _safe_put(
            self.queue,
            {
                "type": "batch_progress",
                "ticker": ticker,
                "index": index,
                "total": total,
                "status": status,
            },
        )

    def batch_complete(self, results: Sequence[object]) -> None:
        """Signal batch completion with results."""
        from options_arena.api.schemas import BatchTickerResult  # noqa: PLC0415

        serialized = [r.model_dump() if isinstance(r, BatchTickerResult) else r for r in results]
        _safe_put(self.queue, {"type": "batch_complete", "results": serialized})

    def error(self, message: str) -> None:
        """Signal an error event."""
        _safe_put(self.queue, {"type": "error", "message": message})


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------


@router.websocket("/ws/scan/{scan_id}")
async def ws_scan(websocket: WebSocket, scan_id: int) -> None:
    """Stream scan progress events to the client."""
    origin = websocket.headers.get("origin", "")
    if not origin or not _is_loopback_origin(origin):
        with contextlib.suppress(Exception):
            await websocket.close(code=4003)
        return
    await websocket.accept()
    scan_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
        websocket.app.state, "scan_queues", {}
    )
    queue = scan_queues.get(scan_id)
    if queue is None:
        with contextlib.suppress(Exception):
            await websocket.close(code=4004)
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "complete":
                    break
            except TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.debug("WebSocket scan/%d disconnected", scan_id)
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()


@router.websocket("/ws/debate/{debate_id}")
async def ws_debate(websocket: WebSocket, debate_id: int) -> None:
    """Stream debate progress events to the client."""
    origin = websocket.headers.get("origin", "")
    if not origin or not _is_loopback_origin(origin):
        with contextlib.suppress(Exception):
            await websocket.close(code=4003)
        return
    await websocket.accept()
    debate_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
        websocket.app.state, "debate_queues", {}
    )
    queue = debate_queues.get(debate_id)
    if queue is None:
        with contextlib.suppress(Exception):
            await websocket.close(code=4004)
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "complete":
                    break
            except TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.debug("WebSocket debate/%d disconnected", debate_id)
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()


@router.websocket("/ws/batch/{batch_id}")
async def ws_batch(websocket: WebSocket, batch_id: int) -> None:
    """Stream batch debate progress events to the client."""
    origin = websocket.headers.get("origin", "")
    if not origin or not _is_loopback_origin(origin):
        with contextlib.suppress(Exception):
            await websocket.close(code=4003)
        return
    await websocket.accept()
    batch_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
        websocket.app.state, "batch_queues", {}
    )
    queue = batch_queues.get(batch_id)
    if queue is None:
        with contextlib.suppress(Exception):
            await websocket.close(code=4004)
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "batch_complete":
                    break
            except TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.debug("WebSocket batch/%d disconnected", batch_id)
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
