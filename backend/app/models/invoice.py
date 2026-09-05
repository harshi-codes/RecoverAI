"""Invoice model."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # status: draft | sent | overdue | paid | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", foreign_keys="Payment.invoice_id"
    )

    def __repr__(self) -> str:
        return f"<Invoice {self.id[:8]} ₹{self.amount} {self.status}>"
