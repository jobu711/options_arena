"""WebSocket handlers for scan and debate progress streaming.

Bridges sync callbacks (``ProgressCallback``, ``DebateProgressCallback``) to
``asyncio.Queue`` objects that WebSocket handlers drain in real time.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from options_arena.agents import DebatePhase
from options_arena.scan import ScanPhase

logger = logging.getLogger(__name__)

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
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def __call__(self, phase: ScanPhase, current: int, total: int) -> None:
        self.queue.put_nowait(
            {"type": "progress", "phase": phase.value, "current": current, "total": total}
        )

    def complete(self, scan_id: int, *, cancelled: bool) -> None:
        """Signal scan completion."""
        self.queue.put_nowait({"type": "complete", "scan_id": scan_id, "cancelled": cancelled})

    def error(self, message: str) -> None:
        """Signal an error event."""
        self.queue.put_nowait({"type": "error", "message": message})


# ---------------------------------------------------------------------------
# Debate progress bridge
# ---------------------------------------------------------------------------


class DebateProgressBridge:
    """Bridges ``DebateProgressCallback`` to ``asyncio.Queue`` for WebSocket."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def __call__(self, phase: DebatePhase, status: str, confidence: float | None) -> None:
        event: dict[str, object] = {
            "type": "agent",
            "name": phase.value,
            "status": status,
        }
        if confidence is not None:
            event["confidence"] = confidence
        self.queue.put_nowait(event)

    def complete(self, debate_id: int) -> None:
        """Signal debate completion."""
        self.queue.put_nowait({"type": "complete", "debate_id": debate_id})

    def error(self, message: str) -> None:
        """Signal an error event."""
        self.queue.put_nowait({"type": "error", "message": message})


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------


@router.websocket("/ws/scan/{scan_id}")
async def ws_scan(websocket: WebSocket, scan_id: int) -> None:
    """Stream scan progress events to the client."""
    await websocket.accept()
    scan_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
        websocket.app.state, "scan_queues", {}
    )
    queue = scan_queues.get(scan_id)
    if queue is None:
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
        await websocket.close()


@router.websocket("/ws/debate/{debate_id}")
async def ws_debate(websocket: WebSocket, debate_id: int) -> None:
    """Stream debate progress events to the client."""
    await websocket.accept()
    debate_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
        websocket.app.state, "debate_queues", {}
    )
    queue = debate_queues.get(debate_id)
    if queue is None:
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
        await websocket.close()
