"""
RecoverAI – Recovery Pipeline Orchestrator.

Executes the complete 8-step recovery workflow for a single payment:

  DETECTED → ML_SCORED → ROOT_CAUSE_IDENTIFIED → ACTION_RECOMMENDED
  → POLICY_EVALUATED → ACTION_EXECUTED → OUTCOME_RECORDED → AUDIT_TRAIL

IDEMPOTENT: If a terminal case (recovered/blocked/failed/rejected) already
exists for this payment, the existing result is returned without re-running.
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.model import get_model
from app.services.audit import append_audit, get_audit_trail
from app.services.decision import (
    RecoveryAction,
    decide_recovery_action,
    decision_to_dict,
)
from app.services.executor import get_executor
from app.services.executor_base import ExecutionResult
from app.services.policy import evaluate_policy, policy_to_dict
from app.services.rca import analyze_root_cause, rca_to_dict

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class PipelineResult:
    payment_id:           str
    case_id:              str
    amount:               float
    currency:             str
    customer_name:        str
    payment_method:       str
    failure_code:         str
    # ML
    recovery_probability: float
    risk_category:        str
    feature_importances:  list[dict]
    # RCA
    rca:                  dict
    # Decision
    decision:             dict
    # Policy
    policy:               dict
    # Execution
    execution:            dict
    # Outcome
    outcome:              dict
    # Audit
    audit_events:         list[dict]
    # Idempotency
    idempotent:           bool = False


# ── Payment / customer loader ─────────────────────────────────────────────────
async def _load_payment_context(db: AsyncSession, payment_id: str) -> dict:
    """Load payment + customer + existing case from DB."""
    result = await db.execute(
        text("""
            SELECT
                p.id, p.amount, p.currency, p.payment_method, p.failure_code,
                p.failure_reason, p.retry_count, p.checkout_duration_sec,
                p.subscription_id, p.status AS payment_status,
                p.created_at AS payment_created_at,
                c.id AS customer_id, c.name AS customer_name,
                c.email AS customer_email,
                c.previous_success_rate, c.lifetime_value,
                c.contact_count, c.opted_out,
                rc.id AS case_id, rc.status AS case_status,
                rc.recovery_probability AS seeded_prob,
                rc.recovered_amount AS seeded_recovered_amount
            FROM payments p
            JOIN customers c ON c.id = p.customer_id
            LEFT JOIN recovery_cases rc ON rc.payment_id = p.id
            WHERE p.id = :payment_id
        """),
        {"payment_id": payment_id},
    )
    row = result.fetchone()
    if not row:
        raise ValueError(f"Payment not found: {payment_id}")
    return dict(row._mapping)


# ── Case creation / update helpers ───────────────────────────────────────────
async def _get_or_create_case(db: AsyncSession, ctx: dict) -> str:
    """Return existing case_id or create a fresh recovery case."""
    if ctx.get("case_id"):
        return ctx["case_id"]

    case_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO recovery_cases
                (id, payment_id, status, revenue_at_risk, recovered_amount, opened_at)
            VALUES
                (:id, :payment_id, 'open', :revenue_at_risk, 0.0, :opened_at)
        """),
        {
            "id":              case_id,
            "payment_id":      ctx["id"],
            "revenue_at_risk": ctx["amount"],
            "opened_at":       datetime.now(timezone.utc),
        },
    )
    return case_id


async def _update_case(db: AsyncSession, case_id: str, updates: dict) -> None:
    """Update a recovery case with new pipeline outputs."""
    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["case_id"] = case_id
    await db.execute(
        text(f"UPDATE recovery_cases SET {set_clauses} WHERE id = :case_id"),
        updates,
    )


async def _save_agent_decision(
    db: AsyncSession,
    case_id: str,
    agent_name: str,
    step_index: int,
    input_snapshot: dict,
    reasoning: str,
    output: dict,
    confidence: float,
    duration_ms: int,
) -> None:
    await db.execute(
        text("""
            INSERT INTO agent_decisions
                (id, case_id, agent_name, step_index, input_snapshot,
                 reasoning, output, confidence, duration_ms, created_at)
            VALUES
                (:id, :case_id, :agent_name, :step_index, :input_snapshot,
                 :reasoning, :output, :confidence, :duration_ms, :created_at)
        """),
        {
            "id":             str(uuid.uuid4()),
            "case_id":        case_id,
            "agent_name":     agent_name,
            "step_index":     step_index,
            "input_snapshot": json.dumps(input_snapshot),
            "reasoning":      reasoning,
            "output":         json.dumps(output),
            "confidence":     confidence,
            "duration_ms":    duration_ms,
            "created_at":     datetime.now(timezone.utc),
        },
    )


# ── Idempotency: reload existing terminal case ───────────────────────────────
_TERMINAL_STATUSES = {"recovered", "blocked", "failed", "rejected"}


async def _load_existing_result(db: AsyncSession, payment_id: str) -> PipelineResult | None:
    """
    If a terminal recovery case already exists for this payment, reconstruct
    and return PipelineResult from the DB — without re-running the pipeline.
    Returns None if no terminal case exists.
    """
    result = await db.execute(
        text("""
            SELECT rc.id, rc.status, rc.recovery_probability, rc.root_cause,
                   rc.selected_action, rc.policy_decision, rc.recovered_amount,
                   rc.revenue_at_risk,
                   p.amount, p.currency, p.payment_method, p.failure_code,
                   c.name AS customer_name
            FROM recovery_cases rc
            JOIN payments p ON p.id = rc.payment_id
            JOIN customers c ON c.id = p.customer_id
            WHERE rc.payment_id = :pid
              AND rc.status IN ('recovered','blocked','failed','rejected')
            ORDER BY rc.opened_at DESC LIMIT 1
        """),
        {"pid": payment_id},
    )
    row = result.fetchone()
    if not row:
        return None

    case_id = row.id
    audit_events = await get_audit_trail(db, case_id, entity_type="case")
    payment_audit = await get_audit_trail(db, payment_id, entity_type="payment")
    all_events = sorted(payment_audit + audit_events, key=lambda e: e["timestamp"])

    # Reconstruct minimal execution info from recovery_actions
    exec_result = await db.execute(
        text("SELECT action_type, result, razorpay_reference FROM recovery_actions WHERE case_id=:cid ORDER BY executed_at DESC LIMIT 1"),
        {"cid": case_id},
    )
    exec_row = exec_result.fetchone()

    # Reconstruct blocking_rule from POLICY_BLOCKED audit event
    blocking_rule = None
    policy_reason = ""
    for evt in all_events:
        if evt["event"] == "POLICY_BLOCKED":
            meta = evt.get("metadata", {})
            blocking_rule = meta.get("blocking_rule") or meta.get("rule")
            policy_reason = meta.get("reason", "")
            break
        if evt["event"] == "POLICY_APPROVED":
            policy_reason = evt.get("metadata", {}).get("reason", "")
            break

    # Reconstruct rca from agent_decisions
    rca_output: dict = {}
    ad_result = await db.execute(
        text("SELECT output FROM agent_decisions WHERE case_id=:cid AND agent_name='RCAAgent' ORDER BY step_index ASC LIMIT 1"),
        {"cid": case_id},
    )
    ad_row = ad_result.fetchone()
    if ad_row and ad_row[0]:
        try:
            rca_output = json.loads(ad_row[0])
        except (ValueError, TypeError):
            pass

    # Reconstruct decision from agent_decisions
    decision_output: dict = {}
    dd_result = await db.execute(
        text("SELECT output FROM agent_decisions WHERE case_id=:cid AND agent_name='DecisionAgent' ORDER BY step_index ASC LIMIT 1"),
        {"cid": case_id},
    )
    dd_row = dd_result.fetchone()
    if dd_row and dd_row[0]:
        try:
            decision_output = json.loads(dd_row[0])
        except (ValueError, TypeError):
            pass

    return PipelineResult(
        payment_id=payment_id,
        case_id=case_id,
        amount=float(row.amount),
        currency=row.currency,
        customer_name=row.customer_name,
        payment_method=row.payment_method,
        failure_code=row.failure_code,
        recovery_probability=float(row.recovery_probability or 0),
        risk_category=_prob_to_risk(float(row.recovery_probability or 0)),
        feature_importances=[],
        rca={
            "root_cause":      rca_output.get("root_cause") or row.root_cause or "unknown",
            "severity":        rca_output.get("severity", "MEDIUM"),
            "explanation":     rca_output.get("explanation", ""),
            # auto_recoverable: use stored value, fall back to True for known auto-recoverable causes
            "auto_recoverable": rca_output.get(
                "auto_recoverable",
                (row.root_cause or "") in ("network_timeout", "transient_bank_error"),
            ),
        },
        decision={
            "action":     decision_output.get("action") or row.selected_action or "NO_ACTION",
            "rationale":  decision_output.get("rationale", ""),
            "params":     decision_output.get("params", {}),
            "confidence": decision_output.get("confidence", 0.0),
        },
        policy={
            "allowed":                 row.policy_decision == "approved",
            "outcome":                 row.policy_decision or "blocked",
            "requires_human_approval": row.policy_decision == "requires_human",
            "reason":                  policy_reason,
            "blocking_rule":           blocking_rule,
        },
        execution={
            "action_id":   None,
            "action_type": exec_row.action_type if exec_row else "NONE",
            "status":      "executed" if exec_row else "skipped",
            "simulated":   True,
            "message":     f"Existing result returned (idempotent). Case status: {row.status}.",
        },
        outcome={"status": row.status, "recovered_amount": float(row.recovered_amount or 0)},
        audit_events=all_events,
        idempotent=True,
    )


def _prob_to_risk(prob: float) -> str:
    if prob >= 0.75: return "HIGH"
    if prob >= 0.60: return "MEDIUM"
    return "LOW"


# ── Main pipeline function ────────────────────────────────────────────────────
async def run_recovery_pipeline(
    db:         AsyncSession,
    payment_id: str,
) -> PipelineResult:
    """
    Execute the complete recovery pipeline for a single payment.
    IDEMPOTENT: Returns existing terminal case without re-running.
    Each step writes to agent_decisions and audit_logs.
    """
    t0 = datetime.now(timezone.utc)
    logger.info(f"Recovery pipeline starting for payment {payment_id}")

    # ── IDEMPOTENCY CHECK ─────────────────────────────────────────────────────
    existing = await _load_existing_result(db, payment_id)
    if existing:
        logger.info(f"Idempotent: returning existing result for {payment_id} (case {existing.case_id})")
        return existing

    # ── STEP 1: Revenue Detection ─────────────────────────────────────────────
    ctx = await _load_payment_context(db, payment_id)
    case_id = await _get_or_create_case(db, ctx)

    # Compute time_since_failure_hours
    import datetime as dt
    created_at = ctx["payment_created_at"]
    if isinstance(created_at, str):
        import pandas as pd
        created_at = pd.to_datetime(created_at)
    now_aware = dt.datetime.now(dt.timezone.utc)
    if hasattr(created_at, "tzinfo") and created_at.tzinfo is not None:
        # created_at is tz-aware, compare directly
        time_since_hours = max(0.0, (now_aware - created_at).total_seconds() / 3600)
    else:
        # naive datetime — compare without tz
        time_since_hours = max(0.0, (now_aware.replace(tzinfo=None) - created_at).total_seconds() / 3600)

    await append_audit(db, "payment", payment_id, "PAYMENT_DETECTED", "revenue_detection_agent", {
        "amount": ctx["amount"], "failure_code": ctx["failure_code"],
        "payment_method": ctx["payment_method"], "case_id": case_id,
    })
    await _save_agent_decision(
        db, case_id, "RevenueDetectionAgent", 1,
        input_snapshot={"payment_id": payment_id, "status": ctx["payment_status"]},
        reasoning=f"Failed payment ₹{ctx['amount']:,.0f} detected. Case opened for recovery analysis.",
        output={"case_id": case_id, "revenue_at_risk": ctx["amount"]},
        confidence=1.0, duration_ms=12,
    )

    # ── STEP 2: ML Recovery Scoring ───────────────────────────────────────────
    model = get_model()
    ml_result = model.predict(
        payment_data={
            "amount":                ctx["amount"],
            "payment_method":        ctx["payment_method"],
            "failure_code":          ctx["failure_code"],
            "retry_count":           ctx["retry_count"],
            "checkout_duration_sec": ctx["checkout_duration_sec"] or 60,
            "subscription_id":       ctx["subscription_id"],
            "time_since_failure_hours": time_since_hours,
        },
        customer_data={
            "previous_success_rate": ctx["previous_success_rate"],
            "lifetime_value":        ctx["lifetime_value"],
        },
    )
    prob          = ml_result["recovery_probability"]
    risk_category = ml_result["risk_category"]

    await append_audit(db, "case", case_id, "ML_SCORED", "ml_service", {
        "recovery_probability": prob, "risk_category": risk_category,
        "model_version": ml_result["model_version"],
    })
    await _save_agent_decision(
        db, case_id, "MLScoringAgent", 2,
        input_snapshot={
            "amount": ctx["amount"], "failure_code": ctx["failure_code"],
            "retry_count": ctx["retry_count"],
            "customer_previous_success_rate": ctx["previous_success_rate"],
        },
        reasoning=(
            f"GradientBoostingClassifier v{ml_result['model_version']} scored this payment "
            f"at {prob:.0%} recovery probability ({risk_category} risk). "
            f"Top feature: {ml_result['feature_importances'][0]['feature']}."
        ),
        output={"recovery_probability": prob, "risk_category": risk_category},
        confidence=prob, duration_ms=8,
    )

    # ── STEP 3: Root Cause Analysis ───────────────────────────────────────────
    rca_result = analyze_root_cause(
        failure_code=ctx["failure_code"] or "",
        amount=ctx["amount"],
        retry_count=ctx["retry_count"],
    )

    await append_audit(db, "case", case_id, "ROOT_CAUSE_IDENTIFIED", "rca_agent", {
        "root_cause": rca_result.root_cause.value,
        "severity":   rca_result.severity.value,
    })
    await _save_agent_decision(
        db, case_id, "RootCauseAnalysisAgent", 3,
        input_snapshot={"failure_code": ctx["failure_code"], "retry_count": ctx["retry_count"]},
        reasoning=rca_result.explanation,
        output=rca_to_dict(rca_result),
        confidence=0.95, duration_ms=3,
    )

    # ── STEP 4: Recovery Decision ─────────────────────────────────────────────
    decision = decide_recovery_action(
        recovery_probability=prob,
        root_cause=rca_result.root_cause,
        retry_count=ctx["retry_count"],
        amount=ctx["amount"],
        is_subscription=ctx["subscription_id"] is not None,
        time_since_failure_hours=time_since_hours,
        customer_lifetime_value=ctx["lifetime_value"],
        contact_count=ctx["contact_count"],
    )

    # Extract discount_percent from params (for policy rule 5)
    discount_pct = decision.params.get("discount_percent", 0.0)

    await append_audit(db, "case", case_id, "ACTION_RECOMMENDED", "decision_engine", {
        "action": decision.action.value, "params": decision.params,
        "rationale": decision.rationale,
    })
    await _save_agent_decision(
        db, case_id, "RecoveryDecisionAgent", 4,
        input_snapshot={"recovery_probability": prob, "root_cause": rca_result.root_cause.value},
        reasoning=decision.rationale,
        output=decision_to_dict(decision),
        confidence=decision.confidence, duration_ms=5,
    )

    # ── STEP 5: Policy Guard ──────────────────────────────────────────────────
    policy = evaluate_policy(
        payment_status=ctx["payment_status"],
        opted_out=ctx["opted_out"],
        contact_count=ctx["contact_count"],
        amount=ctx["amount"],
        discount_percent=discount_pct,
        recovery_probability=prob,
    )

    policy_event = (
        "POLICY_APPROVED" if policy.allowed else
        "POLICY_REQUIRES_HUMAN" if policy.requires_human_approval else
        "POLICY_BLOCKED"
    )
    await append_audit(db, "case", case_id, policy_event, "policy_guard", {
        "outcome": policy.outcome.value, "blocking_rule": policy.blocking_rule,
        "reason": policy.reason,
    })
    await _save_agent_decision(
        db, case_id, "PolicySafetyAgent", 5,
        input_snapshot={
            "amount": ctx["amount"], "opted_out": ctx["opted_out"],
            "contact_count": ctx["contact_count"], "recovery_probability": prob,
            "discount_percent": discount_pct,
        },
        reasoning=policy.reason,
        output=policy_to_dict(policy),
        confidence=1.0, duration_ms=2,
    )

    # ── STEP 6: Action Execution ──────────────────────────────────────────────
    executor = get_executor()
    if policy.allowed:
        execution = await executor.execute(
            db=db,
            case_id=case_id,
            payment_id=payment_id,
            action=decision.action,
            params=decision.params,
            case_status=ctx.get("case_status", "failed") or "failed",
        )
    elif policy.requires_human_approval:
        # Do NOT auto-execute — wait for human approval
        execution = ExecutionResult(
            action_id=None,
            action_type=decision.action.value,
            status="pending_human_approval",
            simulated=True,
            razorpay_reference=None,
            outcome_success=False,
            message="Awaiting human approval before execution.",
        )
    else:
        execution = None

    # ── STEP 7: Outcome ───────────────────────────────────────────────────────
    if execution and execution.outcome_success:
        final_status     = "recovered"
        recovered_amount = ctx["amount"]
    elif policy.requires_human_approval:
        final_status     = "in_progress"   # awaiting human
        recovered_amount = 0.0
    elif not policy.allowed:
        final_status     = "blocked"
        recovered_amount = 0.0
    else:
        final_status     = "failed"
        recovered_amount = 0.0

    now_ts = datetime.now(timezone.utc)

    # Update case in DB
    await _update_case(db, case_id, {
        "status":               final_status,
        "recovery_probability": prob,
        "root_cause":           rca_result.root_cause.value,
        "selected_action":      decision.action.value,
        "policy_decision":      policy.outcome.value,
        "recovered_amount":     recovered_amount,
        "closed_at":            now_ts if final_status not in ("open", "in_progress") else None,
    })

    # Increment contact_count if we actually contacted the customer
    if execution and final_status != "blocked":
        await db.execute(
            text("UPDATE customers SET contact_count = contact_count + 1 WHERE id = :cid"),
            {"cid": ctx["customer_id"]},
        )

    await append_audit(db, "case", case_id, "ACTION_EXECUTED", "action_executor", {
        "action_type": execution.action_type if execution else "NONE",
        "simulated":   True,
        "outcome_success": execution.outcome_success if execution else False,
        "action_id":   execution.action_id if execution else None,
    })
    await append_audit(db, "case", case_id, "OUTCOME_RECORDED", "outcome_agent", {
        "status":           final_status,
        "recovered_amount": recovered_amount,
    })
    await _save_agent_decision(
        db, case_id, "OutcomeAgent", 6,
        input_snapshot={"policy_outcome": policy.outcome.value, "execution_success": execution.outcome_success if execution else False},
        reasoning=(
            f"Payment {'recovered' if final_status == 'recovered' else 'not recovered'}. "
            f"Recovered amount: ₹{recovered_amount:,.0f}."
        ),
        output={"status": final_status, "recovered_amount": recovered_amount},
        confidence=1.0, duration_ms=4,
    )

    # ── STEP 8: Fetch audit trail ─────────────────────────────────────────────
    audit_events = await get_audit_trail(db, case_id, entity_type="case")
    # Also get the payment detection event
    payment_audit = await get_audit_trail(db, payment_id, entity_type="payment")
    all_events = sorted(payment_audit + audit_events, key=lambda e: e["timestamp"])

    total_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    logger.info(f"Pipeline complete for {payment_id}: {final_status} in {total_ms}ms")

    return PipelineResult(
        payment_id=payment_id,
        case_id=case_id,
        amount=ctx["amount"],
        currency=ctx["currency"],
        customer_name=ctx["customer_name"],
        payment_method=ctx["payment_method"],
        failure_code=ctx["failure_code"],
        recovery_probability=prob,
        risk_category=risk_category,
        feature_importances=ml_result["feature_importances"][:5],
        rca=rca_to_dict(rca_result),
        decision=decision_to_dict(decision),
        policy=policy_to_dict(policy),
        execution={
            "action_id":     execution.action_id if execution else None,
            "action_type":   execution.action_type if execution else "NONE",
            "status":        execution.status if execution else "skipped",
            "simulated":     True,
            "message":       execution.message if execution else "No action taken — policy blocked.",
        },
        outcome={
            "status":           final_status,
            "recovered_amount": recovered_amount,
        },
        audit_events=all_events,
        idempotent=False,
    )
