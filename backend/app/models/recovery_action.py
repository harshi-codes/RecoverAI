"""RecoveryAction model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recovery_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON string (SQLite compat) – use JSON type for PostgreSQL
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # result: success | failure | pending
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    razorpay_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Relationships
    case: Mapped["RecoveryCase"] = relationship(back_populates="recovery_actions")

    def __repr__(self) -> str:
        return f"<RecoveryAction {self.action_type} {self.result}>"
