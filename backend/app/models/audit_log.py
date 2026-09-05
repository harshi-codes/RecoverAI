"""AuditLog model — APPEND ONLY. Never UPDATE or DELETE rows here."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """
    Immutable audit trail. Application code must NEVER issue UPDATE or DELETE
    against this table. INSERT only. The database-level constraint is enforced
    via application policy (no update method exposed on repository layer).
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # entity_type: payment | case | action | customer
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # event name: case_opened | action_executed | policy_blocked | recovered | etc.
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # actor: agent name or "system" or "merchant"
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON metadata snapshot
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.event} on {self.entity_type}:{self.entity_id[:8]}>"
