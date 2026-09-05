"""Payment model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    razorpay_payment_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    # status: created | attempted | failed | captured | refunded
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created", index=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkout_duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="payments", foreign_keys=[subscription_id]
    )
    invoice: Mapped["Invoice | None"] = relationship(
        back_populates="payments", foreign_keys=[invoice_id]
    )
    recovery_case: Mapped["RecoveryCase | None"] = relationship(
        back_populates="payment", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Payment {self.id[:8]} ₹{self.amount} {self.status}>"
