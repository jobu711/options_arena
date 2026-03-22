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

from options_arena.agents._context import DebatePhase
from options_arena.scan import ScanPhase

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

# Per-endpoint-type connection limits to prevent resource exhaustion (P1 security).
_MAX_WS_CONNECTIONS_PER_TYPE = 10
_scan_ws_count = 0
_debate_ws_count = 0
_batch_ws_count = 0
# Locks to make connection-limit reservation atomic (prevents TOCTOU race).
_scan_ws_lock = asyncio.Lock()
_debate_ws_lock = asyncio.Lock()
_batch_ws_lock = asyncio.Lock()


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

    def _safe_put(self, event: dict[str, object]) -> None:
        """Put event on queue, dropping oldest if full."""
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            logger.debug("WS queue full — dropped oldest event")
        self.queue.put_nowait(event)

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        self._safe_put(
            {"type": "progress", "phase": phase.value, "current": current, "total": total}
        )

    def complete(self, scan_id: int, *, cancelled: bool, outcomes_collected: int = 0) -> None:
        """Signal scan completion."""
        self._safe_put(
            {
                "type": "complete",
                "scan_id": scan_id,
                "cancelled": cancelled,
                "outcomes_collected": outcomes_collected,
            }
        )

    def error(self, message: str) -> None:
        """Signal an error event."""
        self._safe_put({"type": "error", "message": message})


# ---------------------------------------------------------------------------
# Debate progress bridge
# ---------------------------------------------------------------------------


class DebateProgressBridge:
    """Bridges ``DebateProgressCallback`` to ``asyncio.Queue`` for WebSocket."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)

    def _safe_put(self, event: dict[str, object]) -> None:
        """Put event on queue, dropping oldest if full."""
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            logger.debug("WS queue full — dropped oldest event")
        self.queue.put_nowait(event)

    def __call__(self, phase: DebatePhase, status: str, confidence: float | None) -> None:
        event: dict[str, object] = {
            "type": "agent",
            "name": phase.value,
            "status": status,
        }
        if confidence is not None:
            event["confidence"] = confidence
        self._safe_put(event)

    def complete(self, debate_id: int) -> None:
        """Signal debate completion."""
        self._safe_put({"type": "complete", "debate_id": debate_id})

    def error(self, message: str) -> None:
        """Signal an error event."""
        self._safe_put({"type": "error", "message": message})


# ---------------------------------------------------------------------------
# Recommendation progress bridge (#670)
# ---------------------------------------------------------------------------


class RecommendationProgressBridge:
    """Bridges ``RecommendationProgressCallback`` to ``asyncio.Queue`` for WebSocket.

    Emits desk progress (parallel) and synthesis step events for the new
    recommendation pipeline.
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)

    def _safe_put(self, event: dict[str, object]) -> None:
        """Put event on queue, dropping oldest if full."""
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            logger.debug("WS queue full — dropped oldest event")
        self.queue.put_nowait(event)

    def __call__(self, phase_name: str, current_step: int, total_steps: int) -> None:
        """Match ``RecommendationProgressCallback`` signature: (phase, current, total)."""
        self._safe_put(
            {
                "type": "progress",
                "phase": phase_name,
                "current": current_step,
                "total": total_steps,
            }
        )

    def complete(self, debate_id: int) -> None:
        """Signal recommendation completion."""
        self._safe_put({"type": "complete", "debate_id": debate_id})

    def error(self, message: str) -> None:
        """Signal an error event."""
        self._safe_put({"type": "error", "message": message})


# ---------------------------------------------------------------------------
# Batch progress bridge
# ---------------------------------------------------------------------------


class _BatchAgentBridge:
    """Per-ticker agent bridge that tags events with the ticker name."""

    def __init__(self, ticker: str, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._ticker = ticker
        self._queue = queue

    def _safe_put(self, event: dict[str, object]) -> None:
        """Put event on queue, dropping oldest if full."""
        if self._queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
        self._queue.put_nowait(event)

    def __call__(self, phase: DebatePhase, status: str, confidence: float | None) -> None:
        event: dict[str, object] = {
            "type": "agent",
            "ticker": self._ticker,
            "name": phase.value,
            "status": status,
        }
        if confidence is not None:
            event["confidence"] = confidence
        self._safe_put(event)

    def complete(self, debate_id: int) -> None:
        """No-op — batch bridge handles completion."""

    def error(self, message: str) -> None:
        """Forward error to batch queue."""
        self._safe_put({"type": "error", "ticker": self._ticker, "message": message})


class BatchProgressBridge:
    """Bridges batch debate progress to ``asyncio.Queue`` for WebSocket."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)

    def _safe_put(self, event: dict[str, object]) -> None:
        """Put event on queue, dropping oldest if full."""
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            logger.debug("WS queue full — dropped oldest event")
        self.queue.put_nowait(event)

    def agent_bridge(self, ticker: str) -> _BatchAgentBridge:
        """Create a per-ticker agent progress bridge."""
        return _BatchAgentBridge(ticker, self.queue)

    def batch_progress(self, ticker: str, index: int, total: int, status: str) -> None:
        """Signal per-ticker batch progress."""
        self._safe_put(
            {
                "type": "batch_progress",
                "ticker": ticker,
                "index": index,
                "total": total,
                "status": status,
            }
        )

    def batch_complete(self, results: Sequence[object]) -> None:
        """Signal batch completion with results."""
        from options_arena.api.schemas import BatchTickerResult  # noqa: PLC0415

        serialized = [r.model_dump() if isinstance(r, BatchTickerResult) else r for r in results]
        self._safe_put({"type": "batch_complete", "results": serialized})

    def error(self, message: str) -> None:
        """Signal an error event."""
        self._safe_put({"type": "error", "message": message})


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------


@router.websocket("/ws/scan/{scan_id}")
async def ws_scan(websocket: WebSocket, scan_id: int) -> None:
    """Stream scan progress events to the client."""
    global _scan_ws_count  # noqa: PLW0603
    origin = websocket.headers.get("origin", "")
    if not origin or not _is_loopback_origin(origin):
        with contextlib.suppress(Exception):
            await websocket.close(code=4003)
        return
    # Atomically reserve capacity before accepting the connection.
    reserved = False
    async with _scan_ws_lock:
        if _scan_ws_count >= _MAX_WS_CONNECTIONS_PER_TYPE:
            with contextlib.suppress(Exception):
                await websocket.close(code=4008)
            return
        _scan_ws_count += 1
        reserved = True

    try:
        await websocket.accept()
        scan_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            websocket.app.state, "scan_queues", {}
        )
        queue = scan_queues.get(scan_id)
        if queue is None:
            with contextlib.suppress(Exception):
                await websocket.close(code=4004)
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "complete":
                    break
            except TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        logger.debug("WebSocket scan/%d disconnected", scan_id)
    finally:
        if reserved:
            async with _scan_ws_lock:
                _scan_ws_count -= 1
        scan_queues.pop(scan_id, None)
        with contextlib.suppress(Exception):
            await websocket.close()


@router.websocket("/ws/debate/{debate_id}")
async def ws_debate(websocket: WebSocket, debate_id: int) -> None:
    """Stream debate progress events to the client."""
    global _debate_ws_count  # noqa: PLW0603
    origin = websocket.headers.get("origin", "")
    if not origin or not _is_loopback_origin(origin):
        with contextlib.suppress(Exception):
            await websocket.close(code=4003)
        return
    reserved = False
    async with _debate_ws_lock:
        if _debate_ws_count >= _MAX_WS_CONNECTIONS_PER_TYPE:
            with contextlib.suppress(Exception):
                await websocket.close(code=4008)
            return
        _debate_ws_count += 1
        reserved = True

    try:
        await websocket.accept()
        debate_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            websocket.app.state, "debate_queues", {}
        )
        queue = debate_queues.get(debate_id)
        if queue is None:
            with contextlib.suppress(Exception):
                await websocket.close(code=4004)
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "complete":
                    break
            except TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        logger.debug("WebSocket debate/%d disconnected", debate_id)
    finally:
        if reserved:
            async with _debate_ws_lock:
                _debate_ws_count -= 1
        debate_queues.pop(debate_id, None)
        with contextlib.suppress(Exception):
            await websocket.close()


@router.websocket("/ws/batch/{batch_id}")
async def ws_batch(websocket: WebSocket, batch_id: int) -> None:
    """Stream batch debate progress events to the client."""
    global _batch_ws_count  # noqa: PLW0603
    origin = websocket.headers.get("origin", "")
    if not origin or not _is_loopback_origin(origin):
        with contextlib.suppress(Exception):
            await websocket.close(code=4003)
        return
    reserved = False
    async with _batch_ws_lock:
        if _batch_ws_count >= _MAX_WS_CONNECTIONS_PER_TYPE:
            with contextlib.suppress(Exception):
                await websocket.close(code=4008)
            return
        _batch_ws_count += 1
        reserved = True

    try:
        await websocket.accept()
        batch_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            websocket.app.state, "batch_queues", {}
        )
        queue = batch_queues.get(batch_id)
        if queue is None:
            with contextlib.suppress(Exception):
                await websocket.close(code=4004)
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(event)
                if event.get("type") == "batch_complete":
                    break
            except TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        logger.debug("WebSocket batch/%d disconnected", batch_id)
    finally:
        if reserved:
            async with _batch_ws_lock:
                _batch_ws_count -= 1
        batch_queues.pop(batch_id, None)
        with contextlib.suppress(Exception):
            await websocket.close()
