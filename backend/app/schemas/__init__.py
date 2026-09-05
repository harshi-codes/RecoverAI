"""Pydantic schemas for ML API endpoints."""
from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────────────
class PaymentFeatures(BaseModel):
    """
    Payment and customer features for recovery probability prediction.
    All fields match the ML feature set defined in features.py.
    """
    # Payment fields
    amount: float = Field(..., gt=0, description="Payment amount in INR")
    payment_method: str = Field(..., description="card | upi | netbanking | wallet")
    failure_code: str = Field(..., description="Razorpay failure code")
    retry_count: int = Field(0, ge=0, le=20, description="Number of retries attempted")
    checkout_duration_sec: int = Field(60, ge=1, le=3600, description="Checkout session length in seconds")
    is_subscription: bool = Field(False, description="True if this is a subscription payment")
    time_since_failure_hours: float = Field(
        2.0, ge=0, description="Hours since the payment failed (default: 2h)"
    )

    # Customer fields
    customer_previous_success_rate: float = Field(
        0.75, ge=0.0, le=1.0, description="Historical payment success rate (0–1)"
    )
    customer_lifetime_value: float = Field(
        0.0, ge=0, description="Total historical spend by this customer in INR"
    )
    num_previous_failures: int = Field(
        0, ge=0, description="Number of previous payment failures (derived if not provided)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "amount": 8499.0,
                "payment_method": "card",
                "failure_code": "PAYMENT_FAILED",
                "retry_count": 0,
                "checkout_duration_sec": 180,
                "is_subscription": False,
                "time_since_failure_hours": 2.0,
                "customer_previous_success_rate": 0.72,
                "customer_lifetime_value": 45000.0,
                "num_previous_failures": 2,
            }
        }


# ── Response ──────────────────────────────────────────────────────────────────
class FeatureImportance(BaseModel):
    feature: str
    importance: float


class PredictResponse(BaseModel):
    recovery_probability: float = Field(..., description="Probability [0,1] the payment will be recovered")
    risk_category: str = Field(..., description="HIGH (>=0.75) | MEDIUM (>=0.50) | LOW (<0.50)")
    model_version: str
    feature_importances: list[FeatureImportance]


class ModelInfoResponse(BaseModel):
    model_version: str
    algorithm: str
    roc_auc: float
    accuracy: float
    precision: float
    recall: float
    training_samples: int
    test_samples: int
    positive_rate: float
    n_features: int
    feature_importances: list[FeatureImportance]
    trained_at: str
