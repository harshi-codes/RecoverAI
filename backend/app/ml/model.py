"""
RecoverAI – ML Inference Service.

Loads the trained GradientBoostingClassifier and provides:
  - predict(payment_data, customer_data) → probability + risk category
  - model_info() → metadata from db

This is the ONLY place in the codebase that loads the model artifact.
FastAPI endpoints call this service; they never touch joblib directly.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.ml.features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    build_inference_row,
    get_encoded_feature_names,
)

logger = logging.getLogger(__name__)


# ── Risk categories (per implementation plan) ─────────────────────────────────
def _risk_category(prob: float) -> str:
    if prob >= 0.75:
        return "HIGH"
    if prob >= 0.50:
        return "MEDIUM"
    return "LOW"


# ── Model loader (singleton via lru_cache) ────────────────────────────────────
class RecoveryModel:
    """
    Thin wrapper around the trained sklearn model + encoder.
    Instantiate once at startup, reuse for all predictions.
    """

    def __init__(self, model_path: Path, encoder_path: Path, feature_names_path: Path):
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model artifact not found: {model_path}\n"
                "Run: cd backend && python3 scripts/train_model.py"
            )
        if not encoder_path.exists():
            raise FileNotFoundError(f"Encoder artifact not found: {encoder_path}")

        logger.info(f"Loading model from {model_path}")
        self._model   = joblib.load(model_path)
        self._encoder = joblib.load(encoder_path)
        self._feature_names: list[str] = get_encoded_feature_names(self._encoder)

        # Load feature names from JSON if available (for display)
        if feature_names_path.exists():
            saved = json.loads(feature_names_path.read_text())
            if saved:
                self._feature_names = saved

        self.model_path   = model_path
        self.encoder_path = encoder_path
        logger.info(
            f"Model loaded: {self._model.__class__.__name__}, "
            f"{len(self._feature_names)} features"
        )

    # ── Core prediction ───────────────────────────────────────────────────────
    def predict(
        self,
        payment_data: dict,
        customer_data: dict,
    ) -> dict[str, Any]:
        """
        Run inference for a single payment.

        Args:
            payment_data: dict with raw payment fields
            customer_data: dict with raw customer fields

        Returns:
            {
              recovery_probability: float,
              risk_category: str,
              feature_importances: list[{feature, importance}],
              model_version: str,
            }
        """
        df = build_inference_row(payment_data, customer_data)
        X  = self._encode(df)

        prob = float(self._model.predict_proba(X)[0, 1])
        prob = round(max(0.0, min(1.0, prob)), 4)

        # Per-prediction feature importances (global model weights, not SHAP)
        fi = self._feature_importances()

        return {
            "recovery_probability": prob,
            "risk_category":        _risk_category(prob),
            "feature_importances":  fi,
            "model_version":        "1.0.0",
        }

    # ── Batch prediction (for analytics) ─────────────────────────────────────
    def predict_batch(self, X_encoded: np.ndarray) -> np.ndarray:
        """Raw batch prediction on pre-encoded matrix. Returns prob array."""
        return self._model.predict_proba(X_encoded)[:, 1]

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _encode(self, df: pd.DataFrame) -> np.ndarray:
        numeric  = df[NUMERIC_FEATURES].astype(np.float32).values
        cat_enc  = self._encoder.transform(df[CATEGORICAL_FEATURES])
        return np.hstack([numeric, cat_enc])

    def _feature_importances(self) -> list[dict]:
        raw = self._model.feature_importances_
        result = [
            {"feature": name, "importance": round(float(imp), 6)}
            for name, imp in zip(self._feature_names, raw)
        ]
        return sorted(result, key=lambda x: x["importance"], reverse=True)

    def model_summary(self) -> dict:
        """Return a summary dict for GET /api/v1/ml/model-info."""
        return {
            "algorithm":       self._model.__class__.__name__,
            "n_estimators":    int(getattr(self._model, "n_estimators_", self._model.n_estimators)),
            "n_features":      len(self._feature_names),
            "feature_names":   self._feature_names,
            "feature_importances": self._feature_importances(),
        }


# ── Module-level singleton ────────────────────────────────────────────────────
_model_instance: RecoveryModel | None = None


def load_model(artifacts_dir: Path) -> RecoveryModel:
    """Load (or return cached) RecoveryModel from artifacts_dir."""
    global _model_instance
    if _model_instance is None:
        _model_instance = RecoveryModel(
            model_path=artifacts_dir / "model.joblib",
            encoder_path=artifacts_dir / "encoder.joblib",
            feature_names_path=artifacts_dir / "feature_names.json",
        )
    return _model_instance


def get_model() -> RecoveryModel:
    """
    FastAPI dependency / convenience accessor.
    Raises RuntimeError if model hasn't been loaded yet.
    """
    if _model_instance is None:
        raise RuntimeError(
            "Model not loaded. Call load_model(artifacts_dir) at application startup."
        )
    return _model_instance
