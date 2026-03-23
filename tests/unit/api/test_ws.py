"""Tests for WebSocket progress bridges."""

from __future__ import annotations

from options_arena.api.ws import WebSocketProgressBridge
from options_arena.scan import ScanPhase


async def test_scan_bridge_progress_event() -> None:
    """WebSocketProgressBridge queues progress events."""
    bridge = WebSocketProgressBridge()
    bridge(ScanPhase.UNIVERSE, 10, 100)
    event = bridge.queue.get_nowait()
    assert event["type"] == "progress"
    assert event["phase"] == "universe"
    assert event["current"] == 10
    assert event["total"] == 100


async def test_scan_bridge_complete_event() -> None:
    """WebSocketProgressBridge queues complete event."""
    bridge = WebSocketProgressBridge()
    bridge.complete(42, cancelled=False)
    event = bridge.queue.get_nowait()
    assert event["type"] == "complete"
    assert event["scan_id"] == 42
    assert event["cancelled"] is False


async def test_scan_bridge_cancelled_event() -> None:
    """WebSocketProgressBridge complete with cancelled=True."""
    bridge = WebSocketProgressBridge()
    bridge.complete(42, cancelled=True)
    event = bridge.queue.get_nowait()
    assert event["cancelled"] is True


async def test_scan_bridge_error_event() -> None:
    """WebSocketProgressBridge queues error events."""
    bridge = WebSocketProgressBridge()
    bridge.error("Something went wrong")
    event = bridge.queue.get_nowait()
    assert event["type"] == "error"
    assert event["message"] == "Something went wrong"


async def test_scan_bridge_multiple_events() -> None:
    """WebSocketProgressBridge queues multiple events in order."""
    bridge = WebSocketProgressBridge()
    bridge(ScanPhase.UNIVERSE, 0, 100)
    bridge(ScanPhase.UNIVERSE, 50, 100)
    bridge(ScanPhase.SCORING, 0, 50)
    assert bridge.queue.qsize() == 3
    e1 = bridge.queue.get_nowait()
    assert e1["phase"] == "universe"
    assert e1["current"] == 0
    e2 = bridge.queue.get_nowait()
    assert e2["current"] == 50
    e3 = bridge.queue.get_nowait()
    assert e3["phase"] == "scoring"
