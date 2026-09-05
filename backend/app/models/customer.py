"""Customer model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lifetime_value: Mapped[float] = mapped_column(Float, default=0.0)
    previous_success_rate: Mapped[float] = mapped_column(Float, default=1.0)
    contact_count: Mapped[int] = mapped_column(Integer, default=0)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    # Relationships
    payments: Mapped[list["Payment"]] = relationship(back_populates="customer")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer {self.name} ({self.email})>"
