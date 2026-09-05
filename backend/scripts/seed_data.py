#!/usr/bin/env python3
"""
RecoverAI – Synthetic data seeder.

Generates 10,000+ realistic transactions with correlated features
that are meaningful for the ML recovery model.

Key design principles:
- Customers have persistent attributes (success_rate, LTV) that influence
  all their payments — not each row independent
- Failure types have realistic base recovery rates
- High success_rate + low retry_count → higher recovery likelihood
- Large amounts → lower recovery (harder to convince customer)
- Subscription payments → slightly higher recovery (recurring intent)
- Excessive retries → much lower recovery (customer gave up)
- The recovered label is generated probabilistically, NOT randomly

Run:
    cd backend
    python3 scripts/seed_data.py
"""
import asyncio
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make app importable from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

console = Console()
RANDOM_SEED = 42
rng = random.Random(RANDOM_SEED)
np_rng = np.random.default_rng(RANDOM_SEED)

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_CUSTOMERS = 1_200
TARGET_PAYMENTS = 12_000        # will generate ~12k, gives 10k+ failed
HERO_PAYMENT_ID = "hero-payment-8499-recoverai"
HERO_CUSTOMER_ID = "hero-customer-recoverai"

# ── Constants ─────────────────────────────────────────────────────────────────
PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
METHOD_WEIGHTS  = [0.45, 0.30, 0.15, 0.10]

FAILURE_CODES = [
    "PAYMENT_FAILED",
    "INSUFFICIENT_FUNDS",
    "EXPIRED_CARD",
    "NETWORK_ERROR",
    "USER_DROP",
    "BANK_BLOCK",
    "CVV_MISMATCH",
    "DO_NOT_HONOR",
]

# Base recovery probability per failure code (before adjustments)
# Tuned so the composite scoring produces ~38% recovery rate across the dataset
FAILURE_BASE_RECOVERY = {
    "PAYMENT_FAILED":     0.65,
    "INSUFFICIENT_FUNDS": 0.48,
    "EXPIRED_CARD":       0.72,
    "NETWORK_ERROR":      0.85,
    "USER_DROP":          0.52,
    "BANK_BLOCK":         0.42,
    "CVV_MISMATCH":       0.75,
    "DO_NOT_HONOR":       0.38,
}

# Root cause mapping from failure code
FAILURE_TO_ROOT_CAUSE = {
    "PAYMENT_FAILED":     "ml_decline",
    "INSUFFICIENT_FUNDS": "insufficient_funds",
    "EXPIRED_CARD":       "expired_card",
    "NETWORK_ERROR":      "network_timeout",
    "USER_DROP":          "user_drop",
    "BANK_BLOCK":         "bank_block",
    "CVV_MISMATCH":       "ml_decline",
    "DO_NOT_HONOR":       "bank_block",
}

BILLING_CYCLES = ["monthly", "quarterly", "annual"]
PLAN_NAMES = [
    "Starter Monthly", "Growth Monthly", "Pro Monthly",
    "Starter Annual", "Growth Annual", "Enterprise Annual",
    "Basic Quarterly", "Premium Quarterly",
]

INDIAN_FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh",
    "Priya", "Ananya", "Sneha", "Pooja", "Riya", "Divya", "Kavya",
    "Rahul", "Rohan", "Amit", "Vijay", "Rajesh", "Suresh", "Mahesh",
    "Neha", "Swati", "Ankita", "Shreya", "Meera", "Geeta", "Sunita",
]
INDIAN_LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Gupta", "Mehta",
    "Joshi", "Nair", "Iyer", "Reddy", "Rao", "Shah", "Agarwal",
    "Malhotra", "Chaudhary", "Tiwari", "Mishra", "Pandey", "Bhat",
]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com"]


# ── Helper functions ──────────────────────────────────────────────────────────
def rand_id() -> str:
    return str(uuid.uuid4())


def random_amount(tier: str) -> float:
    """Return a realistic INR payment amount for the customer tier."""
    if tier == "enterprise":
        return round(rng.uniform(20_000, 200_000), 2)
    elif tier == "growth":
        return round(rng.uniform(2_000, 20_000), 2)
    else:
        return round(rng.uniform(100, 2_000), 2)


def random_indian_phone() -> str:
    return f"+91{rng.randint(7000000000, 9999999999)}"


def days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def compute_recovery_probability(
    failure_code: str,
    success_rate: float,
    num_prev_failures: int,
    retry_count: int,
    ltv: float,
    time_since_hours: float,
    is_subscription: bool,
    amount: float,
    checkout_sec: int,
) -> float:
    """
    Deterministic scoring function used to generate the 'recovered' label.
    This same logic inspired the ML features but ML will learn its own weights.
    Output: probability ∈ [0, 1]
    """
    prob = FAILURE_BASE_RECOVERY[failure_code]

    # Customer reliability
    prob += (success_rate - 0.5) * 0.30          # -0.15 to +0.15

    # Past failure penalty
    prob -= min(num_prev_failures, 10) * 0.02      # up to -0.20

    # Retry penalty (excessive retries = gave up)
    if retry_count >= 4:
        prob -= 0.25
    elif retry_count >= 2:
        prob -= 0.10

    # Amount penalty (big amounts harder to recover)
    if amount > 50_000:
        prob -= 0.20
    elif amount > 10_000:
        prob -= 0.08
    elif amount < 500:
        prob += 0.05   # small amounts easier to retry

    # LTV bonus (valuable customers worth chasing)
    if ltv > 100_000:
        prob += 0.10
    elif ltv > 20_000:
        prob += 0.05

    # Time penalty (stale failures harder to recover)
    if time_since_hours > 168:    # > 1 week
        prob -= 0.15
    elif time_since_hours > 48:   # > 2 days
        prob -= 0.07
    elif time_since_hours < 2:    # very fresh → easier
        prob += 0.08

    # Subscription bonus (customer has recurring intent)
    if is_subscription:
        prob += 0.07

    # Short checkout = user wasn't committed
    if checkout_sec < 15:
        prob -= 0.10

    return float(np.clip(prob, 0.02, 0.98))


def generate_recovery_label(prob: float) -> bool:
    """Sample the recovery label from the computed probability."""
    return rng.random() < prob


# ── Customer generation ───────────────────────────────────────────────────────
def generate_customer(idx: int) -> dict:
    first = rng.choice(INDIAN_FIRST_NAMES)
    last  = rng.choice(INDIAN_LAST_NAMES)
    tier  = rng.choices(["starter", "growth", "enterprise"], weights=[60, 30, 10])[0]

    # Correlated customer attributes
    if tier == "enterprise":
        ltv = rng.uniform(100_000, 500_000)
        success_rate = rng.uniform(0.75, 0.98)
    elif tier == "growth":
        ltv = rng.uniform(10_000, 100_000)
        success_rate = rng.uniform(0.55, 0.90)
    else:
        ltv = rng.uniform(0, 10_000)
        success_rate = rng.uniform(0.30, 0.85)

    num_prev_failures = rng.randint(0, max(1, int((1 - success_rate) * 20)))

    return {
        "id": rand_id(),
        "razorpay_customer_id": f"cust_{uuid.uuid4().hex[:14]}",
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}{idx}@{rng.choice(EMAIL_DOMAINS)}",
        "phone": random_indian_phone(),
        "lifetime_value": round(ltv, 2),
        "previous_success_rate": round(success_rate, 4),
        "contact_count": 0,
        "opted_out": rng.random() < 0.03,   # 3% opted out
        "created_at": days_ago(rng.randint(30, 1000)),
        "_tier": tier,
        "_num_prev_failures": num_prev_failures,
    }


# ── Subscription generation ───────────────────────────────────────────────────
def generate_subscription(customer: dict) -> dict | None:
    # ~35% of customers have subscriptions
    if rng.random() > 0.35:
        return None
    tier = customer["_tier"]
    if tier == "enterprise":
        amount = rng.choice([4_999, 9_999, 19_999, 49_999])
    elif tier == "growth":
        amount = rng.choice([999, 1_999, 2_999, 4_999])
    else:
        amount = rng.choice([99, 199, 299, 499])
    cycle = rng.choices(BILLING_CYCLES, weights=[60, 25, 15])[0]
    statuses = rng.choices(
        ["active", "paused", "cancelled", "expired"],
        weights=[70, 10, 15, 5]
    )
    return {
        "id": rand_id(),
        "customer_id": customer["id"],
        "plan_name": rng.choice(PLAN_NAMES),
        "amount": amount,
        "status": statuses[0],
        "billing_cycle": cycle,
        "next_billing_date": (datetime.now(timezone.utc) + timedelta(days=rng.randint(1, 30))).date(),
        "created_at": days_ago(rng.randint(30, 730)),
    }


# ── Invoice generation ────────────────────────────────────────────────────────
def generate_invoice(customer: dict) -> dict | None:
    # ~20% of customers have invoices
    if rng.random() > 0.20:
        return None
    tier = customer["_tier"]
    amount = random_amount(tier)
    days_overdue = rng.randint(-10, 60)
    due = datetime.now(timezone.utc) + timedelta(days=-days_overdue)
    status = "paid" if days_overdue < 0 else (
        "overdue" if days_overdue > 14 else rng.choice(["sent", "overdue"])
    )
    return {
        "id": rand_id(),
        "customer_id": customer["id"],
        "amount": round(amount, 2),
        "due_date": due.date(),
        "status": status,
        "created_at": due - timedelta(days=30),
    }


# ── Payment generation ────────────────────────────────────────────────────────
def generate_payment(customer: dict, sub_id: str | None, inv_id: str | None) -> dict:
    tier   = customer["_tier"]
    amount = random_amount(tier)
    method = rng.choices(PAYMENT_METHODS, weights=METHOD_WEIGHTS)[0]
    failure_code = rng.choices(
        FAILURE_CODES,
        weights=[25, 20, 12, 15, 10, 8, 6, 4]
    )[0]
    retry_count = rng.choices([0, 1, 2, 3, 4, 5], weights=[30, 25, 20, 13, 8, 4])[0]
    checkout_sec = rng.randint(5, 600)
    days_since = rng.uniform(0, 30)
    time_since_hours = days_since * 24
    created_at = days_ago(int(days_since))
    is_sub = sub_id is not None and rng.random() < 0.7

    prob = compute_recovery_probability(
        failure_code=failure_code,
        success_rate=customer["previous_success_rate"],
        num_prev_failures=customer["_num_prev_failures"],
        retry_count=retry_count,
        ltv=customer["lifetime_value"],
        time_since_hours=time_since_hours,
        is_subscription=is_sub,
        amount=amount,
        checkout_sec=checkout_sec,
    )
    recovered = generate_recovery_label(prob)

    return {
        "id": rand_id(),
        "razorpay_payment_id": f"pay_{uuid.uuid4().hex[:14]}",
        "customer_id": customer["id"],
        "amount": round(amount, 2),
        "currency": "INR",
        "payment_method": method,
        "status": "failed",
        "failure_code": failure_code,
        "failure_reason": f"Payment declined: {failure_code.replace('_', ' ').lower()}",
        "retry_count": retry_count,
        "checkout_duration_sec": checkout_sec,
        "subscription_id": sub_id if is_sub else None,
        "invoice_id": inv_id if not is_sub and inv_id else None,
        "created_at": created_at,
        "updated_at": created_at,
        # Internal fields used to create recovery_case
        "_recovery_probability": round(prob, 4),
        "_recovered": recovered,
        "_root_cause": FAILURE_TO_ROOT_CAUSE[failure_code],
        "_is_subscription": is_sub,
    }


def select_recovery_action(prob: float, root_cause: str) -> str:
    """Select recovery action. All failed payments get an action;
    low-probability ones get send_reminder (lowest risk), not no_action.
    no_action is reserved only for opted-out customers (handled in policy)."""
    if root_cause == "network_timeout" and prob >= 0.60:
        return "retry"
    if root_cause == "insufficient_funds":
        return "offer_discount"
    if root_cause == "user_drop":
        return "send_reminder"
    if root_cause == "expired_card":
        return "request_card_update"
    if root_cause in ("bank_block", "ml_decline"):
        return "escalate_human" if prob < 0.60 else "send_reminder"
    return "send_reminder"


def get_policy_decision(payment: dict) -> str:
    """Policy engine rules from implementation plan.
    blocked = do not auto-intervene (prob too low)
    requires_human = human must review
    approved = proceed automatically"""
    prob   = payment["_recovery_probability"]
    amount = payment["amount"]
    if amount > 50_000:
        return "requires_human"
    # Per plan: prob < 0.60 → do not automatically intervene
    # But we still CREATE the case and record it as 'blocked'
    # so the outcome can still recover (manual/external action)
    if prob < 0.60:
        return "blocked"
    return "approved"


def generate_recovery_case(payment: dict) -> dict:
    prob        = payment["_recovery_probability"]
    root_cause  = payment["_root_cause"]
    action      = select_recovery_action(prob, root_cause)
    policy      = get_policy_decision(payment)
    recovered   = payment["_recovered"]   # ground-truth probabilistic label

    if policy == "requires_human":
        # Large-amount cases — human reviews; use recovered label as outcome
        if recovered:
            status = "recovered"
            recovered_amount = payment["amount"]
        else:
            status = rng.choices(["in_progress", "failed"], weights=[30, 70])[0]
            recovered_amount = 0.0
        closed_at = payment["created_at"] + timedelta(hours=rng.uniform(2, 120))
    elif policy == "approved":
        # Auto-intervention: outcome = probabilistic label
        if recovered:
            status = "recovered"
            recovered_amount = payment["amount"]
        else:
            status = "failed"
            recovered_amount = 0.0
        closed_at = payment["created_at"] + timedelta(hours=rng.uniform(1, 72))
    else:
        # policy == blocked (prob < 0.60): record case but don't auto-recover
        # A small fraction still recover through external means
        if recovered and rng.random() < 0.15:   # 15% of blocked cases recover externally
            status = "recovered"
            recovered_amount = payment["amount"]
        else:
            status = "blocked"
            recovered_amount = 0.0
        closed_at = payment["created_at"] + timedelta(hours=rng.uniform(0.5, 48))

    return {
        "id": rand_id(),
        "payment_id": payment["id"],
        "status": status,
        "revenue_at_risk": payment["amount"],
        "recovery_probability": prob,
        "root_cause": root_cause,
        "selected_action": action,
        "policy_decision": policy,
        "recovered_amount": round(recovered_amount, 2),
        "opened_at": payment["created_at"],
        "closed_at": closed_at,
    }


def generate_recovery_action(case: dict, payment: dict) -> dict:
    action_type = case["selected_action"]
    params: dict = {}
    if action_type == "offer_discount":
        params["discount_percent"] = rng.choice([5, 7, 10])
    elif action_type == "retry":
        params["delay_minutes"] = rng.choice([15, 30, 60])
    elif action_type == "send_reminder":
        params["channel"] = rng.choice(["email", "sms", "whatsapp"])
    elif action_type == "request_card_update":
        params["channel"] = "email"

    result = "success" if case["status"] == "recovered" else (
        "pending" if case["status"] == "in_progress" else "failure"
    )
    return {
        "id": rand_id(),
        "case_id": case["id"],
        "action_type": action_type,
        "parameters": json.dumps(params),
        "executed_at": case["opened_at"] + timedelta(minutes=rng.randint(1, 60)),
        "result": result,
        "razorpay_reference": f"rzp_{uuid.uuid4().hex[:12]}" if result == "success" else None,
    }


def generate_audit_log(entity_type: str, entity_id: str, event: str, actor: str, meta: dict) -> dict:
    return {
        "id": rand_id(),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "event": event,
        "actor": actor,
        "metadata_json": json.dumps(meta),
        "created_at": datetime.now(timezone.utc),
    }


# ── Hero payment fixture ──────────────────────────────────────────────────────
def build_hero_payment(hero_customer: dict, sub_id: str | None) -> dict:
    """Fixed ₹8,499 hero payment used in the demo walkthrough."""
    prob = compute_recovery_probability(
        failure_code="PAYMENT_FAILED",
        success_rate=hero_customer["previous_success_rate"],
        num_prev_failures=hero_customer["_num_prev_failures"],
        retry_count=0,
        ltv=hero_customer["lifetime_value"],
        time_since_hours=2.0,
        is_subscription=False,
        amount=8_499,
        checkout_sec=180,
    )
    return {
        "id": HERO_PAYMENT_ID,
        "razorpay_payment_id": "pay_hero_demo_8499",
        "customer_id": hero_customer["id"],
        "amount": 8_499.00,
        "currency": "INR",
        "payment_method": "card",
        "status": "failed",
        "failure_code": "PAYMENT_FAILED",
        "failure_reason": "Payment declined: payment failed",
        "retry_count": 0,
        "checkout_duration_sec": 180,
        "subscription_id": None,
        "invoice_id": None,
        "created_at": days_ago(1),
        "updated_at": days_ago(1),
        "_recovery_probability": round(prob, 4),
        "_recovered": False,   # hero starts as unrecovered — demo triggers recovery
        "_root_cause": "ml_decline",
        "_is_subscription": False,
    }


def build_hero_customer() -> dict:
    return {
        "id": HERO_CUSTOMER_ID,
        "razorpay_customer_id": "cust_hero_demo",
        "name": "Priya Mehta",
        "email": "priya.mehta@demo.recoverai.in",
        "phone": "+919876543210",
        "lifetime_value": 45_000.00,
        "previous_success_rate": 0.72,
        "contact_count": 0,
        "opted_out": False,
        "created_at": days_ago(365),
        "_tier": "growth",
        "_num_prev_failures": 2,
    }


# ── Main async seeder ─────────────────────────────────────────────────────────
async def seed(db_url: str) -> None:
    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # Clear existing data (re-runnable seed)
    async with engine.begin() as conn:
        for tbl in [
            "audit_logs", "agent_decisions", "recovery_actions",
            "recovery_cases", "payments", "invoices", "subscriptions",
            "customers", "ml_model_metadata",
        ]:
            await conn.execute(text(f"DELETE FROM {tbl}"))
    console.print("[yellow]Cleared existing data[/yellow]")

    # ── Generate all in-memory data first ────────────────────────────────────
    console.print("\n[bold cyan]Generating synthetic data...[/bold cyan]")

    # Hero customer/payment
    hero_cust = build_hero_customer()
    customers = [hero_cust]
    for i in range(1, TARGET_CUSTOMERS):
        customers.append(generate_customer(i))

    subscriptions: list[dict] = []
    cust_to_sub: dict[str, str | None] = {}
    for c in customers:
        sub = generate_subscription(c)
        if sub:
            subscriptions.append(sub)
            cust_to_sub[c["id"]] = sub["id"]
        else:
            cust_to_sub[c["id"]] = None

    invoices: list[dict] = []
    cust_to_inv: dict[str, str | None] = {}
    for c in customers:
        inv = generate_invoice(c)
        if inv:
            invoices.append(inv)
            cust_to_inv[c["id"]] = inv["id"]
        else:
            cust_to_inv[c["id"]] = None

    # Assign ~10 payments per customer but some get more (heavy users)
    payments: list[dict] = []
    hero_pay = build_hero_payment(hero_cust, cust_to_sub.get(hero_cust["id"]))
    payments.append(hero_pay)

    payments_per_customer = TARGET_PAYMENTS // len(customers)
    for c in customers:
        if c["id"] == HERO_CUSTOMER_ID:
            continue
        # Heavy users get more payments
        n = rng.choices(
            [1, 3, 5, 10, 20, 50],
            weights=[20, 30, 25, 15, 8, 2]
        )[0]
        for _ in range(n):
            p = generate_payment(c, cust_to_sub.get(c["id"]), cust_to_inv.get(c["id"]))
            payments.append(p)
            if len(payments) >= TARGET_PAYMENTS + 1:
                break
        if len(payments) >= TARGET_PAYMENTS + 1:
            break

    # Pad to TARGET_PAYMENTS if we're short
    all_non_hero = [c for c in customers if c["id"] != HERO_CUSTOMER_ID]
    while len(payments) < TARGET_PAYMENTS:
        c = rng.choice(all_non_hero)
        payments.append(generate_payment(c, cust_to_sub.get(c["id"]), cust_to_inv.get(c["id"])))

    # Generate recovery cases (one per failed payment)
    recovery_cases: list[dict] = []
    recovery_actions: list[dict] = []
    audit_logs: list[dict] = []
    hero_case: dict | None = None

    for p in payments:
        case = generate_recovery_case(p)
        recovery_cases.append(case)
        if case["selected_action"] not in ("no_action",):
            action = generate_recovery_action(case, p)
            recovery_actions.append(action)
        # Audit log entries (2 per case)
        audit_logs.append(generate_audit_log(
            "case", case["id"], "case_opened", "revenue_detection_agent",
            {"payment_id": p["id"], "amount": p["amount"], "prob": p["_recovery_probability"]}
        ))
        if case["status"] in ("recovered", "failed", "blocked"):
            audit_logs.append(generate_audit_log(
                "case", case["id"], f"case_{case['status']}", "outcome_agent",
                {"recovered_amount": case["recovered_amount"], "policy": case["policy_decision"]}
            ))
        if p["id"] == HERO_PAYMENT_ID:
            hero_case = case

    console.print(f"  Customers:        {len(customers):>8,}")
    console.print(f"  Subscriptions:    {len(subscriptions):>8,}")
    console.print(f"  Invoices:         {len(invoices):>8,}")
    console.print(f"  Payments:         {len(payments):>8,}")
    console.print(f"  Recovery cases:   {len(recovery_cases):>8,}")
    console.print(f"  Recovery actions: {len(recovery_actions):>8,}")
    console.print(f"  Audit logs:       {len(audit_logs):>8,}")

    # ── Bulk insert ───────────────────────────────────────────────────────────
    console.print("\n[bold cyan]Writing to database...[/bold cyan]")

    def strip_private(d: dict) -> dict:
        return {k: v for k, v in d.items() if not k.startswith("_")}

    async with Session() as session:
        with Progress(SpinnerColumn(), *Progress.get_default_columns(), TimeElapsedColumn()) as prog:
            task = prog.add_task("Inserting...", total=7)

            await session.execute(
                text("""INSERT INTO customers (id,razorpay_customer_id,name,email,phone,
                         lifetime_value,previous_success_rate,contact_count,opted_out,created_at)
                         VALUES (:id,:razorpay_customer_id,:name,:email,:phone,
                                 :lifetime_value,:previous_success_rate,:contact_count,
                                 :opted_out,:created_at)"""),
                [strip_private(c) for c in customers]
            )
            prog.advance(task)

            if subscriptions:
                await session.execute(
                    text("""INSERT INTO subscriptions (id,customer_id,plan_name,amount,status,
                             billing_cycle,next_billing_date,created_at)
                             VALUES (:id,:customer_id,:plan_name,:amount,:status,
                                     :billing_cycle,:next_billing_date,:created_at)"""),
                    subscriptions
                )
            prog.advance(task)

            if invoices:
                await session.execute(
                    text("""INSERT INTO invoices (id,customer_id,amount,due_date,status,created_at)
                             VALUES (:id,:customer_id,:amount,:due_date,:status,:created_at)"""),
                    invoices
                )
            prog.advance(task)

            await session.execute(
                text("""INSERT INTO payments (id,razorpay_payment_id,customer_id,amount,currency,
                         payment_method,status,failure_code,failure_reason,retry_count,
                         checkout_duration_sec,subscription_id,invoice_id,created_at,updated_at)
                         VALUES (:id,:razorpay_payment_id,:customer_id,:amount,:currency,
                                 :payment_method,:status,:failure_code,:failure_reason,
                                 :retry_count,:checkout_duration_sec,:subscription_id,
                                 :invoice_id,:created_at,:updated_at)"""),
                [strip_private(p) for p in payments]
            )
            prog.advance(task)

            await session.execute(
                text("""INSERT INTO recovery_cases (id,payment_id,status,revenue_at_risk,
                         recovery_probability,root_cause,selected_action,policy_decision,
                         recovered_amount,opened_at,closed_at)
                         VALUES (:id,:payment_id,:status,:revenue_at_risk,:recovery_probability,
                                 :root_cause,:selected_action,:policy_decision,:recovered_amount,
                                 :opened_at,:closed_at)"""),
                recovery_cases
            )
            prog.advance(task)

            if recovery_actions:
                await session.execute(
                    text("""INSERT INTO recovery_actions (id,case_id,action_type,parameters,
                             executed_at,result,razorpay_reference)
                             VALUES (:id,:case_id,:action_type,:parameters,
                                     :executed_at,:result,:razorpay_reference)"""),
                    recovery_actions
                )
            prog.advance(task)

            if audit_logs:
                await session.execute(
                    text("""INSERT INTO audit_logs (id,entity_type,entity_id,event,actor,
                             metadata_json,created_at)
                             VALUES (:id,:entity_type,:entity_id,:event,:actor,
                                     :metadata_json,:created_at)"""),
                    audit_logs
                )
            prog.advance(task)

        await session.commit()

    # ── Verification ──────────────────────────────────────────────────────────
    console.print("\n[bold green]Verifying database...[/bold green]")
    async with Session() as session:
        def q(sql):
            return session.execute(text(sql))

        rows = {
            "customers":        (await q("SELECT COUNT(*) FROM customers")).scalar(),
            "subscriptions":    (await q("SELECT COUNT(*) FROM subscriptions")).scalar(),
            "invoices":         (await q("SELECT COUNT(*) FROM invoices")).scalar(),
            "payments":         (await q("SELECT COUNT(*) FROM payments")).scalar(),
            "recovery_cases":   (await q("SELECT COUNT(*) FROM recovery_cases")).scalar(),
            "recovery_actions": (await q("SELECT COUNT(*) FROM recovery_actions")).scalar(),
            "audit_logs":       (await q("SELECT COUNT(*) FROM audit_logs")).scalar(),
        }
        failed_count  = (await q("SELECT COUNT(*) FROM payments WHERE status='failed'")).scalar()
        captured      = (await q("SELECT COUNT(*) FROM payments WHERE status='captured'")).scalar()
        recovered_n   = (await q("SELECT COUNT(*) FROM recovery_cases WHERE status='recovered'")).scalar()
        blocked_n     = (await q("SELECT COUNT(*) FROM recovery_cases WHERE status='blocked'")).scalar()
        total_risk    = (await q("SELECT COALESCE(SUM(revenue_at_risk),0) FROM recovery_cases")).scalar()
        total_recov   = (await q("SELECT COALESCE(SUM(recovered_amount),0) FROM recovery_cases")).scalar()
        hero_exists   = (await q(f"SELECT COUNT(*) FROM payments WHERE id='{HERO_PAYMENT_ID}'")).scalar()

    console.print()
    console.print("[bold]Row counts:[/bold]")
    for tbl, cnt in rows.items():
        console.print(f"  {tbl:<22} {cnt:>8,}")
    console.print()
    console.print(f"  [cyan]Failed payments:    {failed_count:>8,}[/cyan]")
    console.print(f"  [green]Recovered cases:    {recovered_n:>8,}[/green]")
    console.print(f"  [red]Blocked cases:      {blocked_n:>8,}[/red]")
    total_cases = rows["recovery_cases"]
    rate = recovered_n / total_cases * 100 if total_cases else 0
    console.print(f"  [yellow]Recovery rate:      {rate:>7.1f}%[/yellow]")
    console.print(f"  [magenta]Total at risk:  ₹{total_risk:>14,.2f}[/magenta]")
    console.print(f"  [green]Total recovered:₹{total_recov:>14,.2f}[/green]")
    console.print(f"  [bold]Hero payment:       {'FOUND ✓' if hero_exists else 'MISSING ✗'}[/bold]")

    if rows["payments"] < 10_000:
        console.print(f"\n[red]WARNING: only {rows['payments']} payments generated (target 10,000+)[/red]")
    else:
        console.print(f"\n[bold green]✓ Phase 1 seed complete — {rows['payments']:,} payments in database[/bold green]")

    await engine.dispose()


if __name__ == "__main__":
    settings = get_settings()
    console.print(f"[bold]RecoverAI Seed Script[/bold] → {settings.database_url}")
    asyncio.run(seed(settings.database_url))
