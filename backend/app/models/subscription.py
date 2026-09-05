"""Subscription model."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # status: active | paused | cancelled | expired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    billing_cycle: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="subscriptions")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="subscription", foreign_keys="Payment.subscription_id"
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.plan_name} {self.status}>"
