"""
Audit service — records tamper-evident events during a review run.

Phase 1: basic hash chaining (SHA-256 of prev_hash + event_type + payload).
Phase 2+: full tamper-evident chain with external verification.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditEvent

logger = logging.getLogger(__name__)

# Event type constants
EVT_REVIEW_STARTED = "review_started"
EVT_AGENT_STARTED = "agent_started"
EVT_AGENT_COMPLETED = "agent_completed"
EVT_RECEIPT_CREATED = "receipt_created"
EVT_VERDICT_CREATED = "verdict_created"


def _compute_hash(prev_hash: Optional[str], event_type: str, payload: str) -> str:
    """SHA-256 of concatenated prev_hash + event_type + payload."""
    data = f"{prev_hash or ''}:{event_type}:{payload}"
    return hashlib.sha256(data.encode()).hexdigest()


def _last_hash(db: Session, review_run_id: str) -> Optional[str]:
    """Return the integrity_hash of the most recent event for this run."""
    last = (
        db.query(AuditEvent)
        .filter(AuditEvent.review_run_id == review_run_id)
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    return last.integrity_hash if last else None


def record_event(
    db: Session,
    event_type: str,
    review_run_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> AuditEvent:
    """Create and persist an audit event."""
    payload_str = json.dumps(payload or {}, default=str)
    prev_hash = _last_hash(db, review_run_id) if review_run_id else None
    integrity_hash = _compute_hash(prev_hash, event_type, payload_str)

    event = AuditEvent(
        review_run_id=review_run_id,
        event_type=event_type,
        payload=payload_str,
        integrity_hash=integrity_hash,
        prev_hash=prev_hash,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info("audit_event type=%s run_id=%s hash=%s", event_type, review_run_id, integrity_hash[:12])
    return event
