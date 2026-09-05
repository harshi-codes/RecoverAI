"""
RecoverAI – ML Feature Engineering.

Queries the database and builds the feature matrix used for both
training and inference. All feature logic lives here so training
and prediction use exactly the same transformations.

Features (10 total):
  Numeric (8):
    amount                        – payment amount in INR
    customer_previous_success_rate – 0.0–1.0
    num_previous_failures         – derived from success_rate × estimated total
    retry_count                   – number of retries before giving up
    customer_lifetime_value       – total historical spend
    time_since_failure_hours      – hours since payment failed
    is_subscription               – 1/0 bool
    checkout_duration_sec         – seconds from page load to attempt

  Categorical (2, one-hot encoded):
    payment_method    – card | upi | netbanking | wallet
    failure_code      – 8 Razorpay failure codes

Target:
    recovered – 1 if recovery_case.status = 'recovered', else 0.
    (We predict whether a failed payment will ultimately be recovered.
     The 24h window is used for urgency scoring in the agent layer,
     not as the ML label — the within-24h rate is only 6.5% making it
     too sparse for reliable GBM training.)
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

# ── Column definitions ────────────────────────────────────────────────────────
NUMERIC_FEATURES = [
    "amount",
    "customer_previous_success_rate",
    "num_previous_failures",
    "retry_count",
    "customer_lifetime_value",
    "time_since_failure_hours",
    "is_subscription",
    "checkout_duration_sec",
]

CATEGORICAL_FEATURES = [
    "payment_method",
    "failure_code",
]

ALL_FEATURE_COLS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET_COL = "recovered"


def get_encoded_feature_names(enc) -> list[str]:
    """Return full ordered list of feature names after one-hot encoding.
    Numeric features first (in NUMERIC_FEATURES order), then OHE cat features.
    """
    cat_names = list(enc.get_feature_names_out(CATEGORICAL_FEATURES))
    return NUMERIC_FEATURES + cat_names


@dataclass
class RawFeatureRow:
    """One row of raw data before encoding."""
    # Numeric
    amount: float
    customer_previous_success_rate: float
    num_previous_failures: int
    retry_count: int
    customer_lifetime_value: float
    time_since_failure_hours: float
    is_subscription: int          # 0 or 1
    checkout_duration_sec: int
    # Categorical
    payment_method: str
    failure_code: str
    # Target (None during inference)
    recovered_within_24h: int | None = None


# ── SQL query ─────────────────────────────────────────────────────────────────
_FEATURE_SQL = """
SELECT
    p.id                            AS payment_id,
    p.amount,
    p.payment_method,
    p.failure_code,
    p.retry_count,
    p.checkout_duration_sec,
    p.subscription_id               IS NOT NULL AS is_subscription_raw,
    p.created_at                    AS payment_created_at,
    c.previous_success_rate         AS customer_previous_success_rate,
    c.lifetime_value                AS customer_lifetime_value,
    rc.status                       AS case_status,
    rc.opened_at,
    rc.closed_at,
    rc.recovery_probability         AS seeded_prob
FROM payments p
JOIN customers c ON c.id = p.customer_id
LEFT JOIN recovery_cases rc ON rc.payment_id = p.id
WHERE p.status = 'failed'
"""


async def _fetch_raw(db_url: str) -> pd.DataFrame:
    """Async fetch of all failed payments with joined customer + case data."""
    engine = create_async_engine(db_url, echo=False)
    async with engine.connect() as conn:
        result = await conn.execute(text(_FEATURE_SQL))
        rows = result.fetchall()
        columns = list(result.keys())
    await engine.dispose()
    return pd.DataFrame(rows, columns=columns)


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw query results into the final feature matrix.
    This function is called both during training and inference.
    """
    out = pd.DataFrame()

    # ── Numeric features ──────────────────────────────────────────────────────
    out["amount"] = df["amount"].astype(float)

    out["customer_previous_success_rate"] = (
        df["customer_previous_success_rate"].astype(float).clip(0.0, 1.0)
    )

    # num_previous_failures: estimated from success_rate
    # success_rate = successes / (successes + failures)
    # We approximate: if success_rate=0.8 and we assume ~10 total txns →
    # failures ≈ (1 - success_rate) × 10
    # Seeded data stores this implicitly; we derive it from success_rate
    out["num_previous_failures"] = (
        ((1.0 - df["customer_previous_success_rate"]) * 10).round().astype(int).clip(0, 20)
    )

    out["retry_count"] = df["retry_count"].fillna(0).astype(int).clip(0, 10)

    out["customer_lifetime_value"] = (
        df["customer_lifetime_value"].fillna(0.0).astype(float).clip(0, 500_000)
    )

    # time_since_failure_hours: hours between payment creation and now
    # We use opened_at if available, else payment_created_at
    now = pd.Timestamp.utcnow().tz_localize(None)

    def _to_hours(ts) -> float:
        if ts is None or pd.isna(ts):
            return 24.0
        try:
            t = pd.to_datetime(ts)
            if t.tzinfo is not None:
                t = t.tz_convert(None)
            delta = now - t
            return max(0.0, delta.total_seconds() / 3600)
        except Exception:
            return 24.0

    out["time_since_failure_hours"] = df["payment_created_at"].apply(_to_hours).clip(0, 720)

    out["is_subscription"] = df["is_subscription_raw"].fillna(0).astype(int)

    out["checkout_duration_sec"] = (
        df["checkout_duration_sec"].fillna(60).astype(int).clip(1, 3600)
    )

    # ── Categorical features ──────────────────────────────────────────────────
    out["payment_method"] = df["payment_method"].fillna("card").str.lower()
    out["failure_code"]   = df["failure_code"].fillna("PAYMENT_FAILED").str.upper()

    # ── Target variable ───────────────────────────────────────────────────────
    if "case_status" in df.columns and df["case_status"].notna().any():
        out[TARGET_COL] = (df["case_status"] == "recovered").astype(int)
    # else: no target (inference mode)

    # Keep payment_id for traceability
    out["payment_id"] = df["payment_id"].values

    return out


def build_training_dataframe(db_url: str) -> pd.DataFrame:
    """
    Synchronous wrapper: fetch + engineer features for training.
    Returns DataFrame with ALL_FEATURE_COLS + TARGET_COL + payment_id.
    """
    raw = asyncio.run(_fetch_raw(db_url))
    logger.info(f"Fetched {len(raw)} raw rows from database")
    df = _engineer_features(raw)
    # Drop rows with missing target
    df = df.dropna(subset=[TARGET_COL])
    df[TARGET_COL] = df[TARGET_COL].astype(int)
    logger.info(
        f"Feature matrix: {len(df)} rows, "
        f"positive={df[TARGET_COL].sum()}, "
        f"negative={(df[TARGET_COL]==0).sum()}"
    )
    return df


def build_inference_row(payment_data: dict, customer_data: dict) -> pd.DataFrame:
    """
    Build a single-row feature DataFrame for inference.
    payment_data and customer_data are dicts with the raw payment/customer fields.
    """
    import datetime as dt

    # Compute time_since_failure_hours from payment created_at
    created_at = payment_data.get("created_at")
    if created_at:
        if isinstance(created_at, str):
            created_at = pd.to_datetime(created_at)
        if hasattr(created_at, "tzinfo") and created_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=None)
        now = dt.datetime.utcnow()
        time_since = max(0.0, (now - created_at).total_seconds() / 3600)
    else:
        time_since = payment_data.get("time_since_failure_hours", 2.0)

    success_rate = float(customer_data.get("previous_success_rate", 0.7))
    row = {
        "amount":                        float(payment_data.get("amount", 0)),
        "customer_previous_success_rate": success_rate,
        "num_previous_failures":          int(round((1 - success_rate) * 10)),
        "retry_count":                    int(payment_data.get("retry_count", 0)),
        "customer_lifetime_value":        float(customer_data.get("lifetime_value", 0)),
        "time_since_failure_hours":       time_since,
        "is_subscription":                int(bool(payment_data.get("subscription_id"))),
        "checkout_duration_sec":          int(payment_data.get("checkout_duration_sec", 60)),
        "payment_method":                 str(payment_data.get("payment_method", "card")).lower(),
        "failure_code":                   str(payment_data.get("failure_code", "PAYMENT_FAILED")).upper(),
    }
    return pd.DataFrame([row])
