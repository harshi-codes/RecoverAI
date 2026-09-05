# RecoverAI — Architecture

## Overview

RecoverAI is an **agentic revenue recovery workflow** for merchants. It detects failed payments and revenue-risk events, scores recoverability using a trained ML model, diagnoses root causes through deterministic rule mapping, selects the safest recovery action, enforces policy constraints, executes a bounded simulated action, records the outcome, and produces an immutable audit trail.

> **Important:** RecoverAI is **not** a generic LLM chatbot. The LLM is not responsible for any recovery decision. All decisions are made by deterministic business logic and an ML model trained on real payment outcome data.

---

## System Architecture

```
Failed / Revenue-Risk Payment
        │
        ▼
┌─────────────────────┐
│  Revenue Detection  │  Loads payment + customer from DB.
│  (DetectionAgent)   │  Classifies: failed_payment | abandoned_checkout
└─────────┬───────────┘  │ subscription_failure | overdue_invoice
          │
          ▼
┌─────────────────────┐
│  ML Recovery Score  │  GradientBoostingClassifier (scikit-learn)
│  (MLScoringAgent)   │  Trained on seeded payment outcome data.
│                     │  Outputs: recovery_probability [0,1], risk_category
└─────────┬───────────┘  Feature importances returned per prediction.
          │
          ▼
┌─────────────────────┐
│  Root Cause         │  Pure deterministic rule engine.
│  Analysis (RCA)     │  Maps failure_code → root_cause + severity + auto_recoverable.
│  (RCAAgent)         │  No LLM involvement.
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Recovery Decision  │  Deterministic rule engine combining ML signal + RCA result.
│  (DecisionAgent)    │  Outputs: recommended_action, rationale, confidence.
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Policy Guard       │  ← THE SAFETY LAYER. Evaluated in priority order.
│  (Mandatory)        │
│  Rules evaluated:   │  1. payment_succeeded  → cancel (no duplicate charge)
│                     │  2. opted_out          → hard block (GDPR/preference)
│                     │  3. contact_limit      → block after 3 contacts
│                     │  4. low_probability    → block if prob < 0.60
│                     │  5. high_amount        → require human if amount > ₹50,000
│                     │  6. (pass)             → approved for execution
└─────────┬───────────┘
          │
    ┌─────┴──────┐
    │            │
    ▼            ▼
 BLOCKED     APPROVED / REQUIRES_HUMAN
    │            │
    │            ▼
    │  ┌─────────────────────┐
    │  │  Action Executor    │  SANDBOX: SimulatedRecoveryExecutor
    │  │  (Simulated)        │  No real Razorpay API calls.
    │  │                     │  All references prefixed: rzp_sim_*
    │  └─────────┬───────────┘
    │            │
    ▼            ▼
┌─────────────────────┐
│  Outcome Recording  │  Updates recovery_cases.status + recovered_amount.
│  + Audit Trail      │  audit_logs is append-only — no deletions permitted.
│  (AuditLogger)      │  All events timestamped + actor-tagged.
└─────────────────────┘
```

---

## Key Design Principles

### What the ML Model does
- Trained `GradientBoostingClassifier` on payment outcome data.
- Target: `recovered_within_24h` (binary).
- Features: amount, payment_method, failure_code, customer_previous_success_rate, num_previous_failures, retry_count, customer_lifetime_value, time_since_failure_hours, is_subscription, checkout_duration_sec.
- Outputs a probability score — it **never decides** which action to take.
- Verified ROC-AUC ≈ 0.857, Precision ≈ 0.704, Recall ≈ 0.461.

### What deterministic logic does
- **RCA**: Pure rule-based. `failure_code → (root_cause, severity, auto_recoverable)`.
- **Decision Engine**: Rule-based selector using (root_cause, auto_recoverable, ML probability).
- **Policy Guard**: Hard constraints in priority order. No ML involvement.

### What the LLM is NOT responsible for
- Deciding which payment to recover.
- Choosing the recovery action.
- Determining policy outcomes.
- Executing any action.
- Writing to the audit trail.

---

## Database Schema (SQLite / PostgreSQL-compatible)

| Table | Purpose |
|---|---|
| `customers` | Merchant customers with contact_count, opted_out, lifetime_value |
| `payments` | Payment records with failure_code, status, amount |
| `subscriptions` | Subscription info for recurring payment failures |
| `invoices` | Invoice records for overdue detection |
| `recovery_cases` | One recovery case per payment. Stores probability, RCA, decision, outcome |
| `recovery_actions` | Executed actions (simulated). append-only per case |
| `agent_decisions` | Step-by-step log of each pipeline agent's input/output/confidence |
| `audit_logs` | Immutable event log. No DELETE allowed by application code |
| `ml_model_metadata` | Trained model info: version, metrics, feature importances |

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/recovery/analyze/{payment_id}` | Run full pipeline (idempotent for terminal cases) |
| `GET` | `/api/v1/recovery/stats` | Dashboard metrics (real DB aggregates) |
| `GET` | `/api/v1/recovery/cases` | Paginated case list with filters |
| `GET` | `/api/v1/recovery/cases/{case_id}` | Full case detail with audit trail |
| `POST` | `/api/v1/recovery/cases/{case_id}/approve` | Human approval of high-value cases |
| `POST` | `/api/v1/recovery/cases/{case_id}/reject` | Human rejection |
| `POST` | `/api/v1/demo/reset` | Reset all demo scenario data (idempotent) |
| `GET` | `/api/v1/ml/model-info` | Model metadata and feature importances |
| `POST` | `/api/v1/ml/predict` | Raw ML prediction endpoint |
| `GET` | `/health` | Health check |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy (async), Alembic |
| ML | scikit-learn GradientBoostingClassifier, joblib |
| Database | SQLite (local dev), PostgreSQL-compatible schema |
| Frontend | React 18, Vite, TypeScript, Vanilla CSS (no Tailwind) |
| Testing | pytest, pytest-asyncio (51 tests, 100% pass) |

---

## Idempotency

The pipeline checks for existing terminal cases (`recovered`, `blocked`, `failed`, `rejected`) before processing. If one exists, it reconstructs the full result from stored `agent_decisions` and `audit_logs` without creating duplicate records. `in_progress` cases (awaiting human approval) are re-runnable.
