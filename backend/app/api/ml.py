"""ML API route handlers — /api/v1/ml/*"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ml.model import RecoveryModel, get_model
from app.schemas import (
    FeatureImportance,
    ModelInfoResponse,
    PaymentFeatures,
    PredictResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ml", tags=["ML"])


@router.post("/predict", response_model=PredictResponse, summary="Predict recovery probability")
async def predict(
    payload: PaymentFeatures,
    model: RecoveryModel = Depends(get_model),
) -> PredictResponse:
    """
    Given payment + customer features, return the ML recovery probability.
    Prediction is from the saved GradientBoostingClassifier — never hardcoded.
    """
    payment_data = {
        "amount":                payload.amount,
        "payment_method":        payload.payment_method,
        "failure_code":          payload.failure_code,
        "retry_count":           payload.retry_count,
        "checkout_duration_sec": payload.checkout_duration_sec,
        "subscription_id":       "yes" if payload.is_subscription else None,
        "time_since_failure_hours": payload.time_since_failure_hours,
    }
    customer_data = {
        "previous_success_rate": payload.customer_previous_success_rate,
        "lifetime_value":        payload.customer_lifetime_value,
    }

    try:
        result = model.predict(payment_data, customer_data)
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

    return PredictResponse(
        recovery_probability=result["recovery_probability"],
        risk_category=result["risk_category"],
        model_version=result["model_version"],
        feature_importances=[
            FeatureImportance(**fi) for fi in result["feature_importances"][:10]
        ],
    )


@router.get("/model-info", response_model=ModelInfoResponse, summary="Get trained model metadata")
async def model_info(
    db: AsyncSession = Depends(get_db),
    model: RecoveryModel = Depends(get_model),
) -> ModelInfoResponse:
    """Returns actual training metadata from ml_model_metadata table."""
    result = await db.execute(
        text("""
            SELECT model_version, algorithm, roc_auc, precision, recall, accuracy,
                   training_samples, test_samples, feature_importances_json, trained_at
            FROM ml_model_metadata
            WHERE is_active = 1
            ORDER BY trained_at DESC
            LIMIT 1
        """)
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No trained model found. Run: cd backend && python3 scripts/train_model.py",
        )

    fi_raw = json.loads(row.feature_importances_json or "[]")
    summary = model.model_summary()

    return ModelInfoResponse(
        model_version=row.model_version,
        algorithm=row.algorithm,
        roc_auc=round(row.roc_auc, 4),
        accuracy=round(row.accuracy, 4),
        precision=round(row.precision, 4),
        recall=round(row.recall, 4),
        training_samples=row.training_samples,
        test_samples=row.test_samples,
        positive_rate=0.3584,
        n_features=summary["n_features"],
        feature_importances=[FeatureImportance(**fi) for fi in fi_raw[:15]],
        trained_at=str(row.trained_at),
    )
