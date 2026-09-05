"""
RecoverAI – Audit Log Service.

APPEND ONLY. This module only exposes write operations.
No UPDATE or DELETE methods exist here.

Event names (immutable vocabulary):
  PAYMENT_DETECTED       – revenue detection agent found a failed payment
  ML_SCORED              – ML model returned recovery probability
  ROOT_CAUSE_IDENTIFIED  – RCA agent identified failure reason
  ACTION_RECOMMENDED     – decision engine selected recovery action
  POLICY_EVALUATED       – policy guard evaluated the action
  POLICY_APPROVED        – policy guard approved
  POLICY_BLOCKED         – policy guard blocked
  POLICY_REQUIRES_HUMAN  – policy guard escalated to human
  ACTION_EXECUTED        – recovery action executed (simulated)
  OUTCOME_RECORDED       – final outcome (recovered/failed/blocked)
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


VALID_EVENTS = {
    "PAYMENT_DETECTED",
    "ML_SCORED",
    "ROOT_CAUSE_IDENTIFIED",
    "ACTION_RECOMMENDED",
    "POLICY_EVALUATED",
    "POLICY_APPROVED",
    "POLICY_BLOCKED",
    "POLICY_REQUIRES_HUMAN",
    "ACTION_EXECUTED",
    "OUTCOME_RECORDED",
}


async def append_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    event: str,
    actor: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Write one immutable audit log entry.

    Args:
        db:          AsyncSession
        entity_type: "payment" | "case" | "action"
        entity_id:   UUID of the entity
        event:       event name from VALID_EVENTS
        actor:       "revenue_detection_agent" | "ml_service" | "rca_agent" |
                     "decision_engine" | "policy_guard" | "action_executor" |
                     "outcome_agent" | "system"
        metadata:    arbitrary dict stored as JSON

    Returns:
        audit log entry ID (UUID string)
    """
    log_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO audit_logs
                (id, entity_type, entity_id, event, actor, metadata_json, created_at)
            VALUES
                (:id, :entity_type, :entity_id, :event, :actor, :metadata_json, :created_at)
        """),
        {
            "id":            log_id,
            "entity_type":   entity_type,
            "entity_id":     entity_id,
            "event":         event,
            "actor":         actor,
            "metadata_json": json.dumps(metadata or {}),
            "created_at":    datetime.now(timezone.utc),
        },
    )
    return log_id


async def get_audit_trail(
    db: AsyncSession,
    entity_id: str,
    entity_type: str | None = None,
) -> list[dict]:
    """Fetch all audit events for an entity, ordered chronologically."""
    if entity_type:
        result = await db.execute(
            text("""
                SELECT id, entity_type, entity_id, event, actor,
                       metadata_json, created_at
                FROM audit_logs
                WHERE entity_id = :entity_id AND entity_type = :entity_type
                ORDER BY created_at ASC
            """),
            {"entity_id": entity_id, "entity_type": entity_type},
        )
    else:
        result = await db.execute(
            text("""
                SELECT id, entity_type, entity_id, event, actor,
                       metadata_json, created_at
                FROM audit_logs
                WHERE entity_id = :entity_id
                ORDER BY created_at ASC
            """),
            {"entity_id": entity_id},
        )
    rows = result.fetchall()
    return [
        {
            "id":          row.id,
            "entity_type": row.entity_type,
            "entity_id":   row.entity_id,
            "event":       row.event,
            "actor":       row.actor,
            "metadata":    json.loads(row.metadata_json or "{}"),
            "timestamp":   str(row.created_at),
        }
        for row in rows
    ]
