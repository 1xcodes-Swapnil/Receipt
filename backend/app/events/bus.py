"""
Event Bus — Phase 2.

A simple in-process async event bus used to:
  1. Broadcast review progress events to SSE subscribers.
  2. Persist events to the review_event table for replay.

Architecture:
  - asyncio.Queue per review_run_id
  - Queues are created on subscribe and removed on unsubscribe
  - Orchestrator publishes via emit() (thread-safe via run_coroutine_threadsafe)
  - SSE endpoint consumes via subscribe()

This is intentionally simple — no Redis, no pub/sub infrastructure in Phase 2.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# Event type constants
EVT_REVIEW_STARTED = "review.started"
EVT_AGENT_STARTED = "agent.started"
EVT_AGENT_PROGRESS = "agent.progress"
EVT_AGENT_COMPLETED = "agent.completed"
EVT_AGENT_FAILED = "agent.failed"
EVT_RECEIPT_CREATED = "receipt.created"
EVT_REVIEW_COMPLETED = "review.completed"

_SENTINEL = object()  # signals end-of-stream


class EventBus:
    """
    In-process event bus keyed by review_run_id.
    Thread-safe: orchestrator threads post events; SSE coroutines consume them.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Bind to the running event loop. Called at application startup."""
        self._loop = loop

    # ------------------------------------------------------------------
    # Producer side (called from sync orchestrator threads)
    # ------------------------------------------------------------------

    def emit(self, run_id: str, event_type: str, payload: dict | None = None):
        """
        Publish an event to all subscribers for run_id.
        Safe to call from a non-async context (e.g. ThreadPoolExecutor worker).
        """
        event = {
            "event_type": event_type,
            "review_run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            **(payload or {}),
        }
        with self._lock:
            queues = list(self._queues.get(run_id, []))

        if not queues:
            return  # no subscribers, drop event

        loop = self._loop
        if loop is None or not loop.is_running():
            return

        for q in queues:
            asyncio.run_coroutine_threadsafe(q.put(event), loop)

    def emit_done(self, run_id: str):
        """Signal end-of-stream to all subscribers."""
        with self._lock:
            queues = list(self._queues.get(run_id, []))
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        for q in queues:
            asyncio.run_coroutine_threadsafe(q.put(_SENTINEL), loop)

    # ------------------------------------------------------------------
    # Consumer side (called from async SSE endpoint)
    # ------------------------------------------------------------------

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        """Create and register a new queue for run_id."""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._queues.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue):
        with self._lock:
            subscribers = self._queues.get(run_id, [])
            try:
                subscribers.remove(q)
            except ValueError:
                pass
            if not subscribers:
                self._queues.pop(run_id, None)

    async def stream(self, run_id: str) -> AsyncGenerator[dict, None]:
        """Async generator that yields events until end-of-stream."""
        q = await self.subscribe(run_id)
        try:
            while True:
                item = await asyncio.wait_for(q.get(), timeout=30.0)
                if item is _SENTINEL:
                    break
                yield item
        except asyncio.TimeoutError:
            # Client connected but no events for 30s — send a keepalive
            yield {"event_type": "keepalive", "review_run_id": run_id}
        finally:
            self.unsubscribe(run_id, q)


# Module-level singleton
event_bus = EventBus()
