"""MLModelMetadata — records training run metadata for each saved model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MLModelMetadata(Base):
    __tablename__ = "ml_model_metadata"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    # Evaluation metrics (stored as floats for query support)
    roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON: list of feature names + importances
    feature_importances_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Path to serialized model artifact
    model_artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    encoder_artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<MLModelMetadata {self.model_name} v{self.model_version} auc={self.roc_auc}>"
