"""RecoveryCase model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )
    # status: open | in_progress | recovered | failed | blocked
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    revenue_at_risk: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    # root_cause: ml_decline | insufficient_funds | bank_block | user_drop |
    #             expired_card | network_timeout
    root_cause: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # selected_action: retry | offer_discount | send_reminder |
    #                  escalate_human | no_action | request_card_update
    selected_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # policy_decision: approved | blocked | requires_human
    policy_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recovered_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    payment: Mapped["Payment"] = relationship(back_populates="recovery_case")
    recovery_actions: Mapped[list["RecoveryAction"]] = relationship(back_populates="case")
    agent_decisions: Mapped[list["AgentDecision"]] = relationship(back_populates="case")

    def __repr__(self) -> str:
        return f"<RecoveryCase {self.id[:8]} {self.status} prob={self.recovery_probability}>"
