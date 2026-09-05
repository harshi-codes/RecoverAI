"""
RecoverAI – SQLAlchemy declarative base + all model imports.

Import order matters: tables with no foreign-key dependencies come first
so SQLAlchemy can resolve relationships correctly.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ── Import all models so Alembic autogenerate sees them ──────────────────────
from app.models.customer import Customer           # noqa: E402, F401
from app.models.subscription import Subscription   # noqa: E402, F401
from app.models.invoice import Invoice             # noqa: E402, F401
from app.models.payment import Payment             # noqa: E402, F401
from app.models.recovery_case import RecoveryCase  # noqa: E402, F401
from app.models.recovery_action import RecoveryAction  # noqa: E402, F401
from app.models.agent_decision import AgentDecision    # noqa: E402, F401
from app.models.audit_log import AuditLog          # noqa: E402, F401
from app.models.ml_model_metadata import MLModelMetadata  # noqa: E402, F401

__all__ = [
    "Base",
    "Customer",
    "Subscription",
    "Invoice",
    "Payment",
    "RecoveryCase",
    "RecoveryAction",
    "AgentDecision",
    "AuditLog",
    "MLModelMetadata",
]
