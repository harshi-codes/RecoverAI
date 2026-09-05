"""
RecoverAI – ML Training Pipeline.

Trains a GradientBoostingClassifier on the seeded payment/recovery data.
Encodes categoricals, balances classes, evaluates, saves artifacts.

Usage (called by train_model.py script):
    from app.ml.train import run_training
    result = run_training(db_url, artifacts_dir)
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.ml.features import (
    ALL_FEATURE_COLS,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COL,
    build_training_dataframe,
    get_encoded_feature_names,
)

logger = logging.getLogger(__name__)

RANDOM_STATE = 42
MODEL_VERSION = "1.0.0"


# ── Training result dataclass ─────────────────────────────────────────────────
class TrainingResult:
    def __init__(
        self,
        roc_auc: float,
        accuracy: float,
        precision: float,
        recall: float,
        confusion: list[list[int]],
        classification_rep: str,
        feature_importances: list[dict],
        model_path: Path,
        encoder_path: Path,
        feature_names_path: Path,
        train_size: int,
        test_size: int,
        positive_rate: float,
        model_version: str,
    ):
        self.roc_auc = roc_auc
        self.accuracy = accuracy
        self.precision = precision
        self.recall = recall
        self.confusion = confusion
        self.classification_rep = classification_rep
        self.feature_importances = feature_importances
        self.model_path = model_path
        self.encoder_path = encoder_path
        self.feature_names_path = feature_names_path
        self.train_size = train_size
        self.test_size = test_size
        self.positive_rate = positive_rate
        self.model_version = model_version

    def to_dict(self) -> dict:
        return {
            "model_version": self.model_version,
            "roc_auc": round(self.roc_auc, 4),
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "train_size": self.train_size,
            "test_size": self.test_size,
            "positive_rate": round(self.positive_rate, 4),
            "confusion_matrix": self.confusion,
            "feature_importances": self.feature_importances,
        }


# ── Encoder ────────────────────────────────────────────────────────────────────
def _build_encoder(df: pd.DataFrame) -> OneHotEncoder:
    """Fit OneHotEncoder on categorical columns."""
    enc = OneHotEncoder(
        handle_unknown="ignore",   # unknown categories at inference → all zeros
        sparse_output=False,
        dtype=np.float32,
    )
    enc.fit(df[CATEGORICAL_FEATURES])
    return enc


def _apply_encoder(df: pd.DataFrame, enc: OneHotEncoder) -> np.ndarray:
    """
    Apply encoder + concatenate with numeric features.
    Returns numpy array in a stable column order.
    """
    numeric = df[NUMERIC_FEATURES].astype(np.float32).values
    cat_encoded = enc.transform(df[CATEGORICAL_FEATURES])
    return np.hstack([numeric, cat_encoded])



# ── Main training function ────────────────────────────────────────────────────
def run_training(db_url: str, artifacts_dir: Path) -> TrainingResult:
    """
    Full training pipeline:
    1. Fetch + engineer features from database
    2. Encode categoricals
    3. 80/20 stratified split
    4. Train GradientBoostingClassifier
    5. Evaluate on test set
    6. Save model + encoder + feature names
    7. Return TrainingResult
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load data ──────────────────────────────────────────────────────────
    logger.info("Loading training data from database...")
    df = build_training_dataframe(db_url)
    logger.info(f"Dataset: {len(df)} rows")

    if len(df) < 100:
        raise ValueError(f"Too few training rows: {len(df)}. Run seed_data.py first.")

    X_df = df[ALL_FEATURE_COLS].copy()
    y    = df[TARGET_COL].values

    positive_rate = y.mean()
    logger.info(f"Positive rate (recovered_within_24h=1): {positive_rate:.2%}")

    # ── 2. Encode ─────────────────────────────────────────────────────────────
    logger.info("Fitting encoder...")
    enc = _build_encoder(X_df)
    X   = _apply_encoder(X_df, enc)
    feature_names = get_encoded_feature_names(enc)
    logger.info(f"Feature matrix shape: {X.shape} ({len(feature_names)} features)")

    # ── 3. Split ──────────────────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=y,          # preserve class ratio in both splits
    )
    logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")

    # ── 4. Train ──────────────────────────────────────────────────────────────
    # Class weight ratio for imbalanced data (replaces SMOTE for GBM)
    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    scale = n_neg / max(n_pos, 1)
    logger.info(f"Class balance — neg: {n_neg}, pos: {n_pos}, scale: {scale:.2f}")

    logger.info("Training GradientBoostingClassifier...")
    model = GradientBoostingClassifier(
        n_estimators=200,
        learning_rate=0.08,
        max_depth=4,
        min_samples_split=20,
        min_samples_leaf=10,
        subsample=0.8,
        max_features="sqrt",
        random_state=RANDOM_STATE,
        validation_fraction=0.1,
        n_iter_no_change=15,     # early stopping
        tol=1e-4,
    )
    model.fit(X_train, y_train)
    logger.info(f"Training complete. n_estimators used: {model.n_estimators_}")

    # ── 5. Evaluate ───────────────────────────────────────────────────────────
    y_pred      = model.predict(X_test)
    y_prob      = model.predict_proba(X_test)[:, 1]

    roc_auc   = float(roc_auc_score(y_test, y_prob))
    accuracy  = float(accuracy_score(y_test, y_pred))
    precision = float(precision_score(y_test, y_pred, zero_division=0))
    recall    = float(recall_score(y_test, y_pred, zero_division=0))
    cm        = confusion_matrix(y_test, y_pred).tolist()
    cr        = classification_report(y_test, y_pred, target_names=["not_recovered", "recovered"])

    logger.info(f"ROC-AUC:   {roc_auc:.4f}")
    logger.info(f"Accuracy:  {accuracy:.4f}")
    logger.info(f"Precision: {precision:.4f}")
    logger.info(f"Recall:    {recall:.4f}")

    # ── 6. Feature importances ────────────────────────────────────────────────
    raw_importance = model.feature_importances_
    fi_list = sorted(
        [
            {"feature": name, "importance": round(float(imp), 6)}
            for name, imp in zip(feature_names, raw_importance)
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )

    # ── 7. Save artifacts ─────────────────────────────────────────────────────
    model_path        = artifacts_dir / "model.joblib"
    encoder_path      = artifacts_dir / "encoder.joblib"
    feature_names_path = artifacts_dir / "feature_names.json"

    joblib.dump(model, model_path)
    joblib.dump(enc, encoder_path)
    feature_names_path.write_text(json.dumps(feature_names, indent=2))

    logger.info(f"Saved model → {model_path}")
    logger.info(f"Saved encoder → {encoder_path}")
    logger.info(f"Saved feature_names → {feature_names_path}")

    return TrainingResult(
        roc_auc=roc_auc,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        confusion=cm,
        classification_rep=cr,
        feature_importances=fi_list,
        model_path=model_path,
        encoder_path=encoder_path,
        feature_names_path=feature_names_path,
        train_size=len(X_train),
        test_size=len(X_test),
        positive_rate=positive_rate,
        model_version=MODEL_VERSION,
    )


async def _store_metadata(db_url: str, result: TrainingResult) -> None:
    """Insert training result into ml_model_metadata table."""
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        # Mark old active model as inactive
        await conn.execute(
            text("UPDATE ml_model_metadata SET is_active = 0 WHERE is_active = 1")
        )
        # Insert new record
        await conn.execute(
            text("""
                INSERT INTO ml_model_metadata (
                    id, model_name, model_version, algorithm,
                    roc_auc, precision, recall, accuracy,
                    training_samples, test_samples,
                    feature_importances_json,
                    model_artifact_path, encoder_artifact_path,
                    is_active, trained_at
                ) VALUES (
                    :id, :model_name, :model_version, :algorithm,
                    :roc_auc, :precision, :recall, :accuracy,
                    :training_samples, :test_samples,
                    :feature_importances_json,
                    :model_artifact_path, :encoder_artifact_path,
                    :is_active, :trained_at
                )
            """),
            {
                "id": str(uuid.uuid4()),
                "model_name": "RecoverAI-GBM",
                "model_version": result.model_version,
                "algorithm": "GradientBoostingClassifier",
                "roc_auc": result.roc_auc,
                "precision": result.precision,
                "recall": result.recall,
                "accuracy": result.accuracy,
                "training_samples": result.train_size,
                "test_samples": result.test_size,
                "feature_importances_json": json.dumps(result.feature_importances),
                "model_artifact_path": str(result.model_path),
                "encoder_artifact_path": str(result.encoder_path),
                "is_active": 1,
                "trained_at": datetime.now(timezone.utc),
            },
        )
    await engine.dispose()


def run_training_and_store(db_url: str, artifacts_dir: Path) -> TrainingResult:
    """Train model and persist metadata to database."""
    result = run_training(db_url, artifacts_dir)
    asyncio.run(_store_metadata(db_url, result))
    logger.info("Model metadata stored in database.")
    return result
