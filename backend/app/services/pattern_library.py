"""
Pattern Library service — Phase 3.

CRUD and search operations for PatternLibraryEntry.
Patterns are accumulated from completed immunity pipelines and represent
recurring bug signatures that can be detected proactively.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import PatternLibraryEntry

logger = logging.getLogger(__name__)


def create_pattern(
    db: Session,
    pattern_signature: str,
    description: str,
    source_pipeline_id: Optional[str] = None,
    regression_test_ref: Optional[str] = None,
    affected_area: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> PatternLibraryEntry:
    """Create a new pattern library entry."""
    entry = PatternLibraryEntry(
        pattern_signature=pattern_signature,
        description=description,
        source_pipeline_id=source_pipeline_id,
        regression_test_ref=regression_test_ref,
        affected_area=affected_area,
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info("pattern_library: created pattern id=%s sig=%s", entry.id, pattern_signature[:60])
    return entry


def get_pattern(db: Session, pattern_id: str) -> Optional[PatternLibraryEntry]:
    """Get a single pattern by ID."""
    return db.query(PatternLibraryEntry).filter(PatternLibraryEntry.id == pattern_id).first()


def list_patterns(
    db: Session,
    affected_area: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PatternLibraryEntry]:
    """List patterns, optionally filtered by affected area."""
    q = db.query(PatternLibraryEntry)
    if affected_area:
        q = q.filter(PatternLibraryEntry.affected_area == affected_area)
    return q.order_by(PatternLibraryEntry.created_at.desc()).offset(offset).limit(limit).all()


def search_patterns(
    db: Session,
    query: str,
    limit: int = 20,
) -> list[PatternLibraryEntry]:
    """
    Search patterns by text match against signature, description, or affected_area.
    Phase 3: simple SQL LIKE search. Phase 4+ can add embedding-based search.
    """
    like = f"%{query}%"
    results = (
        db.query(PatternLibraryEntry)
        .filter(
            or_(
                PatternLibraryEntry.pattern_signature.ilike(like),
                PatternLibraryEntry.description.ilike(like),
                PatternLibraryEntry.affected_area.ilike(like),
            )
        )
        .order_by(PatternLibraryEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    return results


def count_patterns(db: Session) -> int:
    return db.query(PatternLibraryEntry).count()
