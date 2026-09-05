"""
RecoverAI – Demo Scenario Seeder.

Seeds 6 deterministic demo payments + customers into recoverai.db.
All probabilities come from the real GradientBoostingClassifier.
No ML manipulation — features chosen to produce realistic policy outcomes.

IDEMPOTENT: safe to run repeatedly (uses INSERT OR IGNORE).

Verified ML outputs (actual model, do not hardcode in frontend):
  demo-A: NETWORK_ERROR, sr=0.96 → prob≈0.9494 (HIGH) → approved → recovered
  demo-B: PAYMENT_FAILED, sr=0.10 → prob≈0.0298 (LOW)  → low_probability blocked
  demo-C: NETWORK_ERROR, sr=0.94, ₹75k → prob≈0.9334 (HIGH) → requires_human
  demo-D: USER_DROP, contacts=5    → prob≈0.1829 (LOW)  → contact_limit blocked
  demo-E: BANK_BLOCK, opted_out=1  → prob≈0.1218 (LOW)  → opted_out blocked
  demo-F: NETWORK_ERROR, status=captured → any prob → payment_succeeded blocked

Run:
  cd backend && python3 scripts/seed_demo_scenarios.py
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3


DB_PATH = Path(__file__).parent.parent / "recoverai.db"

# ── Demo fixtures ─────────────────────────────────────────────────────────────
DEMO_SCENARIOS = [
    {
        "payment_id":     "demo-A-network-8499",
        "customer_id":    "demo-cust-A-network",
        "amount":         8499.0,
        "failure_code":   "NETWORK_ERROR",
        "payment_method": "upi",
        "retry_count":    0,
        "checkout_sec":   120,
        "expected_policy": "approved → recovered",
        # Customer: very high success rate → model scores HIGH
        "customer": {
            "name":                 "Arjun Sharma",
            "email":                "demo-arjun@recoverai.demo",
            "lifetime_value":       180_000.0,
            "previous_success_rate": 0.96,
            "contact_count":        0,
            "opted_out":            0,
        },
        "payment_status": "failed",
    },
    {
        "payment_id":     "demo-B-lowprob-1299",
        "customer_id":    "demo-cust-B-lowprob",
        "amount":         1299.0,
        "failure_code":   "PAYMENT_FAILED",
        "payment_method": "card",
        "retry_count":    3,
        "checkout_sec":   30,
        "expected_policy": "blocked (low_probability)",
        # Customer: very low success rate, many failures → model scores LOW
        "customer": {
            "name":                 "Ravi Kumar",
            "email":                "demo-ravi@recoverai.demo",
            "lifetime_value":       2_000.0,
            "previous_success_rate": 0.10,
            "contact_count":        0,
            "opted_out":            0,
        },
        "payment_status": "failed",
    },
    {
        "payment_id":     "demo-C-highval-75000",
        "customer_id":    "demo-cust-C-highval",
        "amount":         75_000.0,
        "failure_code":   "NETWORK_ERROR",
        "payment_method": "netbanking",
        "retry_count":    0,
        "checkout_sec":   150,
        "expected_policy": "requires_human (high_amount >₹50k)",
        # Good customer + NETWORK_ERROR → HIGH prob → but amount>50k → requires human
        "customer": {
            "name":                 "Priya Nair",
            "email":                "demo-priya@recoverai.demo",
            "lifetime_value":       320_000.0,
            "previous_success_rate": 0.94,
            "contact_count":        0,
            "opted_out":            0,
        },
        "payment_status": "failed",
    },
    {
        "payment_id":     "demo-D-contact-2999",
        "customer_id":    "demo-cust-D-contact",
        "amount":         2_999.0,
        "failure_code":   "USER_DROP",
        "payment_method": "upi",
        "retry_count":    1,
        "checkout_sec":   45,
        "expected_policy": "blocked (contact_limit — customer contacted 5 times)",
        # contact_count=5 → policy blocks before ML even matters
        "customer": {
            "name":                 "Vikram Singh",
            "email":                "demo-vikram@recoverai.demo",
            "lifetime_value":       25_000.0,
            "previous_success_rate": 0.70,
            "contact_count":        5,   # ← triggers contact_limit rule
            "opted_out":            0,
        },
        "payment_status": "failed",
    },
    {
        "payment_id":     "demo-E-optout-4599",
        "customer_id":    "demo-cust-E-optout",
        "amount":         4_599.0,
        "failure_code":   "BANK_BLOCK",
        "payment_method": "card",
        "retry_count":    2,
        "checkout_sec":   60,
        "expected_policy": "blocked (opted_out — customer opted out of communications)",
        # opted_out=1 → policy blocks before any recovery attempt
        "customer": {
            "name":                 "Neha Joshi",
            "email":                "demo-neha@recoverai.demo",
            "lifetime_value":       45_000.0,
            "previous_success_rate": 0.80,
            "contact_count":        0,
            "opted_out":            1,   # ← triggers opted_out rule
        },
        "payment_status": "failed",
    },
    {
        "payment_id":     "demo-F-success-6299",
        "customer_id":    "demo-cust-F-success",
        "amount":         6_299.0,
        "failure_code":   "NETWORK_ERROR",
        "payment_method": "upi",
        "retry_count":    0,
        "checkout_sec":   90,
        "expected_policy": "blocked (payment_succeeded — status=captured)",
        # Payment already captured → policy blocks immediately
        "customer": {
            "name":                 "Amit Verma",
            "email":                "demo-amit@recoverai.demo",
            "lifetime_value":       95_000.0,
            "previous_success_rate": 0.88,
            "contact_count":        0,
            "opted_out":            0,
        },
        "payment_status": "captured",  # ← triggers payment_succeeded rule
    },
]


def seed(conn: sqlite3.Connection) -> None:
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    inserted = {"customers": 0, "payments": 0}

    for scenario in DEMO_SCENARIOS:
        cust = scenario["customer"]
        cust_id = scenario["customer_id"]
        pay_id  = scenario["payment_id"]

        # Customer (INSERT OR IGNORE = idempotent)
        c.execute("""
            INSERT OR IGNORE INTO customers
                (id, razorpay_customer_id, name, email, phone, lifetime_value,
                 previous_success_rate, contact_count, opted_out, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            cust_id,
            f"rzp_demo_{cust_id[-6:]}",
            cust["name"],
            cust["email"],
            "9999999999",
            cust["lifetime_value"],
            cust["previous_success_rate"],
            cust["contact_count"],
            cust["opted_out"],
            now,
        ))
        if c.rowcount:
            inserted["customers"] += 1

        # Payment (INSERT OR IGNORE = idempotent)
        c.execute("""
            INSERT OR IGNORE INTO payments
                (id, razorpay_payment_id, customer_id, amount, currency,
                 payment_method, status, failure_code, failure_reason,
                 retry_count, checkout_duration_sec, subscription_id, invoice_id,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pay_id,
            f"rzp_demo_pay_{pay_id[-6:]}",
            cust_id,
            scenario["amount"],
            "INR",
            scenario["payment_method"],
            scenario["payment_status"],
            scenario["failure_code"],
            f"Demo scenario: {scenario['expected_policy']}",
            scenario["retry_count"],
            scenario["checkout_sec"],
            None, None,
            now, now,
        ))
        if c.rowcount:
            inserted["payments"] += 1

    conn.commit()
    return inserted


def verify(conn: sqlite3.Connection) -> None:
    """Run real ML model against all demo payments and print actual probabilities."""
    from app.ml.model import load_model, get_model
    from app.config import get_settings
    import datetime as dt

    settings = get_settings()
    load_model(settings.ml_artifacts_dir)
    model = get_model()

    c = conn.cursor()
    print("\nVerifying actual ML probabilities for demo scenarios:")
    print("-" * 70)

    for s in DEMO_SCENARIOS:
        c.execute("""
            SELECT p.amount, p.payment_method, p.failure_code, p.retry_count,
                   p.checkout_duration_sec, p.subscription_id, p.created_at,
                   cust.previous_success_rate, cust.lifetime_value, cust.opted_out, cust.contact_count
            FROM payments p JOIN customers cust ON cust.id=p.customer_id
            WHERE p.id=?
        """, (s["payment_id"],))
        row = c.fetchone()
        if not row:
            print(f"  {s['payment_id']}: NOT FOUND")
            continue

        time_since = 2.0  # fixed for seed verification

        result = model.predict(
            payment_data={
                "amount":                row[0],
                "payment_method":        row[1],
                "failure_code":          row[2],
                "retry_count":           row[3],
                "checkout_duration_sec": row[4] or 60,
                "subscription_id":       row[5],
                "time_since_failure_hours": time_since,
            },
            customer_data={
                "previous_success_rate": row[7],
                "lifetime_value":        row[8],
            },
        )
        prob = result["recovery_probability"]
        cat  = result["risk_category"]
        opted_out = bool(row[9])
        contact_count = row[10]

        # Predict policy outcome
        if s["payment_status"] == "captured":
            expected_policy = "BLOCKED (payment_succeeded)"
        elif opted_out:
            expected_policy = "BLOCKED (opted_out)"
        elif contact_count >= 3:
            expected_policy = "BLOCKED (contact_limit)"
        elif prob < 0.60:
            expected_policy = "BLOCKED (low_probability)"
        elif row[0] > 50_000:
            expected_policy = "REQUIRES_HUMAN (high_amount)"
        else:
            expected_policy = "APPROVED"

        print(f"  {s['payment_id']}:")
        print(f"    ML prob={prob:.4f} ({cat})  policy={expected_policy}")

    print()


if __name__ == "__main__":
    print(f"Seeding demo scenarios into {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)

    inserted = seed(conn)
    print(f"Inserted: {inserted}")
    print("(INSERT OR IGNORE — existing rows unchanged)")

    print("\nRunning verification...")
    verify(conn)
    conn.close()
    print("Done. Run POST /api/v1/demo/reset to reset between demo runs.")
