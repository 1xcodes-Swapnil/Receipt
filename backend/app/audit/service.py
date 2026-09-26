"""
Audit service — Phase 5 upgraded.

Hash chain: SHA256(prev_hash + ":" + event_type + ":" + canonical_payload)

Canonical payload: JSON with sorted keys and no extra whitespace, ensuring
the hash is deterministic regardless of dict insertion order.

Concurrency: a module-level threading.Lock serialises concurrent calls to
record_event().  This ensures the prev_hash lookup + insert is atomic from
the perspective of all threads in this process.

Ordering: each event is assigned a monotonically-increasing ``sequence``
number under the lock.  The hash chain uses ``sequence`` order, NOT
``created_at``, because parallel agent threads may commit rows with equal
timestamps.

Limitation: _audit_lock is a PROCESS-LOCAL lock only.  In a multi-process
deployment (e.g. multiple gunicorn workers) separate processes cannot share
this lock.  For distributed deployments a database-level serialisation
mechanism (e.g. SELECT ... FOR UPDATE, advisory locks, or an external queue)
would be needed.  The current deployment is single-process (uvicorn with
asyncio + thread-pool), so the process-local lock is sufficient.

Verification: detect modified payload, invalid hash, broken chain, missing event.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditEvent

logger = logging.getLogger(__name__)

# Module-level lock for serialising concurrent audit writes within this process.
# See module docstring for the distributed-deployment limitation.
_audit_lock = threading.Lock()

# Global sequence counter — increments under _audit_lock.
# This gives deterministic ordering even when created_at timestamps are equal.
_sequence_counter: int = 0

# Event type constants (preserved from Phase 1)
EVT_REVIEW_STARTED = "review_started"
EVT_AGENT_STARTED = "agent_started"
EVT_AGENT_COMPLETED = "agent_completed"
EVT_RECEIPT_CREATED = "receipt_created"
EVT_VERDICT_CREATED = "verdict_created"


def _canonical(payload: dict) -> str:
    """Produce a deterministic JSON string (sorted keys, no extra whitespace)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(prev_hash: Optional[str], event_type: str, canonical: str) -> str:
    """SHA256(prev_hash + ":" + event_type + ":" + canonical_payload)."""
    data = f"{prev_hash or ''}:{event_type}:{canonical}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _last_event(db: Session, review_run_id: str) -> Optional[AuditEvent]:
    """
    Return the last audit event for this run by sequence order.
    MUST be called while holding _audit_lock.
    """
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.review_run_id == review_run_id)
        .order_by(AuditEvent.sequence.desc().nullslast(), AuditEvent.id.desc())
        .first()
    )


def record_event(
    db: Session,
    event_type: str,
    review_run_id: Optional[str] = None,
    payload: Optional[dict] = None,
    entity_ref: Optional[str] = None,
) -> AuditEvent:
    """
    Create and persist an audit event with SHA-256 hash chain.

    The critical section (prev_hash lookup → hash compute → insert) is
    serialised by _audit_lock so concurrent callers from parallel agent
    threads cannot produce a non-deterministic prev_hash.

    A monotonically-increasing sequence number is assigned under the lock
    to give deterministic chain ordering regardless of timestamp collisions.

    canonical_payload is used for hashing; payload is stored as display copy.
    """
    global _sequence_counter

    payload = payload or {}
    canonical = _canonical(payload)
    payload_str = json.dumps(payload, default=str)

    with _audit_lock:
        # Advance the global sequence counter
        _sequence_counter += 1
        seq = _sequence_counter

        prev_hash: Optional[str] = None
        if review_run_id:
            # Expire the session cache so we see all previously committed rows
            # from other threads/sessions before reading the last event.
            db.expire_all()
            last = _last_event(db, review_run_id)
            prev_hash = last.integrity_hash if last else None

        integrity_hash = _compute_hash(prev_hash, event_type, canonical)

        event = AuditEvent(
            review_run_id=review_run_id,
            event_type=event_type,
            payload=payload_str,
            canonical_payload=canonical,
            integrity_hash=integrity_hash,
            prev_hash=prev_hash,
            entity_ref=entity_ref,
            sequence=seq,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

    logger.debug(
        "audit_event type=%s run_id=%s hash=%s seq=%d",
        event_type, review_run_id, integrity_hash[:12], seq,
    )
    return event


# ---------------------------------------------------------------------------
# Audit verification — Phase 5
# ---------------------------------------------------------------------------

class AuditVerificationResult:
    def __init__(self):
        self.valid = True
        self.total_events = 0
        self.errors: list[dict] = []

    def add_error(self, event_id: str, event_type: str, error: str):
        self.valid = False
        self.errors.append({"event_id": event_id, "event_type": event_type, "error": error})

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "total_events": self.total_events,
            "errors": self.errors,
            "error_count": len(self.errors),
        }


def verify_chain(db: Session, review_run_id: str) -> AuditVerificationResult:
    """
    Verify the hash chain for a review run.

    Events are ordered by sequence (the authoritative chain order) with
    created_at as a secondary sort for events that predate this column.

    Checks:
    1. Each event's integrity_hash matches SHA256(prev_hash:event_type:canonical_payload).
    2. Each event's prev_hash equals the previous event's integrity_hash.
    3. No gaps in the chain (every event except the first has a prev_hash).

    Returns AuditVerificationResult with valid=True if chain is intact.
    """
    result = AuditVerificationResult()

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.review_run_id == review_run_id)
        .order_by(
            AuditEvent.sequence.asc().nullsfirst(),
            AuditEvent.created_at.asc(),
            AuditEvent.id.asc(),
        )
        .all()
    )

    result.total_events = len(events)
    if not events:
        return result

    for i, ev in enumerate(events):
        # Check prev_hash linkage
        if i == 0:
            if ev.prev_hash is not None:
                result.add_error(ev.id, ev.event_type,
                                 f"First event should have prev_hash=None, got {ev.prev_hash[:12]}...")
        else:
            expected_prev = events[i - 1].integrity_hash
            if ev.prev_hash != expected_prev:
                result.add_error(ev.id, ev.event_type,
                                 f"Chain broken: prev_hash={ev.prev_hash[:12] if ev.prev_hash else None}... "
                                 f"expected={expected_prev[:12] if expected_prev else None}...")

        # Recompute integrity_hash from canonical_payload
        canonical = ev.canonical_payload
        if not canonical and ev.payload:
            try:
                canonical = _canonical(json.loads(ev.payload))
            except Exception:
                canonical = ev.payload or ""

        if canonical is None:
            canonical = ""

        expected_hash = _compute_hash(
            events[i - 1].integrity_hash if i > 0 else None,
            ev.event_type,
            canonical,
        )

        if ev.integrity_hash != expected_hash:
            result.add_error(ev.id, ev.event_type,
                             f"Hash mismatch: stored={ev.integrity_hash[:12]}... "
                             f"computed={expected_hash[:12]}...")

    return result
