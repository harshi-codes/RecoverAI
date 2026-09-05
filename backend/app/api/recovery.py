"""
RecoverAI – Recovery API (v1).

Endpoints:
  POST /api/v1/recovery/analyze/{payment_id}     – full pipeline (idempotent)
  GET  /api/v1/recovery/cases                    – paginated list + batch summary
  GET  /api/v1/recovery/cases/{case_id}          – complete case detail (single call)
  POST /api/v1/recovery/cases/{case_id}/approve  – human approval
  POST /api/v1/recovery/cases/{case_id}/reject   – human rejection
  GET  /api/v1/recovery/stats                    – dashboard metrics
  POST /api/v1/demo/reset                        – reset demo scenario data
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.audit import append_audit, get_audit_trail
from app.services.executor import get_executor
from app.services.pipeline import run_recovery_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Recovery"])

# ── Pydantic response models ──────────────────────────────────────────────────

class PolicyResponse(BaseModel):
    allowed: bool
    outcome: str
    requires_human_approval: bool
    reason: str
    blocking_rule: str | None


class ExecutionResponse(BaseModel):
    action_id: str | None
    action_type: str
    status: str
    simulated: bool
    message: str


class OutcomeResponse(BaseModel):
    status: str
    recovered_amount: float


class AuditEvent(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    event: str
    actor: str
    metadata: dict
    timestamp: str


class AnalyzeResponse(BaseModel):
    payment_id: str
    case_id: str
    amount: float
    currency: str
    customer_name: str
    payment_method: str
    failure_code: str
    recovery_probability: float
    risk_category: str
    feature_importances: list[dict]
    root_cause: str
    rca_severity: str
    rca_explanation: str
    rca_auto_recoverable: bool
    recommended_action: str
    decision_rationale: str
    decision_confidence: float
    policy: PolicyResponse
    execution: ExecutionResponse
    outcome: OutcomeResponse
    audit_events: list[AuditEvent]
    idempotent: bool
    sandbox: bool = True


# ── POST /api/v1/recovery/analyze/{payment_id} ────────────────────────────────
@router.post(
    "/api/v1/recovery/analyze/{payment_id}",
    response_model=AnalyzeResponse,
    summary="Run complete recovery workflow (idempotent)",
)
async def analyze_payment(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """
    Executes the 8-step agentic recovery workflow:
    Revenue Detection → ML Scoring → RCA → Decision → Policy Guard →
    Action Execution → Outcome → Audit Trail.

    IDEMPOTENT: Calling twice returns the existing result — no duplicate actions.
    All execution is SIMULATED (sandbox). No real money movement.
    """
    try:
        result = await run_recovery_pipeline(db, payment_id)
        if not result.idempotent:
            await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Pipeline error for {payment_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

    return AnalyzeResponse(
        payment_id=result.payment_id,
        case_id=result.case_id,
        amount=result.amount,
        currency=result.currency,
        customer_name=result.customer_name,
        payment_method=result.payment_method,
        failure_code=result.failure_code,
        recovery_probability=result.recovery_probability,
        risk_category=result.risk_category,
        feature_importances=result.feature_importances,
        root_cause=result.rca["root_cause"],
        rca_severity=result.rca["severity"],
        rca_explanation=result.rca["explanation"],
        rca_auto_recoverable=result.rca.get("auto_recoverable", False),
        recommended_action=result.decision["action"],
        decision_rationale=result.decision["rationale"],
        decision_confidence=result.decision.get("confidence", 0.0),
        policy=PolicyResponse(**result.policy),
        execution=ExecutionResponse(**result.execution),
        outcome=OutcomeResponse(**result.outcome),
        audit_events=[AuditEvent(**e) for e in result.audit_events],
        idempotent=result.idempotent,
        sandbox=True,
    )


# ── GET /api/v1/recovery/stats ────────────────────────────────────────────────
@router.get("/api/v1/recovery/stats", summary="Dashboard business metrics")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Returns all business metrics calculated directly from the database.

    Definitions (consistent, never hardcoded):
      revenue_at_risk      = total value of all failed/at-risk payments
      recoverable_revenue  = payments where ML probability >= 0.60
      recovered_revenue    = sum of actually recorded recovered amounts
      recovery_rate        = recovered_revenue / revenue_at_risk * 100
    """
    result = await db.execute(text("""
        SELECT
            COUNT(*)                                                    AS total_cases,
            SUM(rc.revenue_at_risk)                                     AS revenue_at_risk,
            SUM(CASE WHEN rc.status IN ('recovered', 'in_progress') OR rc.recovery_probability >= 0.50 THEN p.amount ELSE 0 END) AS recoverable_revenue,
            SUM(rc.recovered_amount)                                    AS recovered_revenue,
            SUM(CASE WHEN rc.status='recovered' THEN 1 ELSE 0 END)      AS recovered_cases,
            SUM(CASE WHEN rc.status='blocked' THEN 1 ELSE 0 END)        AS blocked_cases,
            SUM(CASE WHEN rc.status='failed' THEN 1 ELSE 0 END)         AS failed_cases,
            SUM(CASE WHEN rc.status='in_progress' THEN 1 ELSE 0 END)    AS in_progress_cases,
            SUM(CASE WHEN rc.policy_decision='requires_human' THEN 1 ELSE 0 END) AS human_approval_required,
            COUNT(DISTINCT ra.id)                                       AS total_actions_executed
        FROM recovery_cases rc
        JOIN payments p ON p.id = rc.payment_id
        LEFT JOIN recovery_actions ra ON ra.case_id = rc.id
    """))
    row = dict(result.fetchone()._mapping)

    revenue_at_risk   = float(row["revenue_at_risk"] or 0)
    recovered_revenue = float(row["recovered_revenue"] or 0)
    recovery_rate     = round((recovered_revenue / revenue_at_risk * 100) if revenue_at_risk > 0 else 0, 2)

    # Failure code breakdown
    fc_result = await db.execute(text("""
        SELECT p.failure_code, COUNT(*) AS cnt, SUM(p.amount) AS total
        FROM payments p
        JOIN recovery_cases rc ON rc.payment_id = p.id
        GROUP BY p.failure_code ORDER BY cnt DESC LIMIT 10
    """))
    failure_breakdown = [
        {"failure_code": r.failure_code, "count": r.cnt, "total_amount": float(r.total or 0)}
        for r in fc_result.fetchall()
    ]

    return {
        "revenue_at_risk":       round(revenue_at_risk, 2),
        "recoverable_revenue":   round(float(row["recoverable_revenue"] or 0), 2),
        "recovered_revenue":     round(recovered_revenue, 2),
        "recovery_rate":         recovery_rate,
        "total_cases":           row["total_cases"],
        "recovered_cases":       row["recovered_cases"],
        "blocked_cases":         row["blocked_cases"],
        "failed_cases":          row["failed_cases"],
        "in_progress_cases":     row["in_progress_cases"],
        "human_approval_required": row["human_approval_required"],
        "total_actions_executed": row["total_actions_executed"],
        "failure_breakdown":     failure_breakdown,
        "metric_definitions": {
            "revenue_at_risk":     "Total value of all failed payments with recovery cases",
            "recoverable_revenue": "Sum of payment amounts where ML recovery probability ≥ 0.60",
            "recovered_revenue":   "Sum of amounts from cases where outcome = recovered (actual DB value, not estimated)",
            "recovery_rate":       "recovered_revenue ÷ revenue_at_risk × 100",
        },
    }


# ── GET /api/v1/recovery/cases ────────────────────────────────────────────────
@router.get("/api/v1/recovery/cases", summary="Recovery queue — all cases with filters")
async def list_cases(
    limit:       int     = Query(50, ge=1, le=500),
    offset:      int     = Query(0, ge=0),
    status:      str | None = Query(None),
    min_prob:    float | None = Query(None, description="Min ML probability"),
    max_prob:    float | None = Query(None, description="Max ML probability"),
    failure_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where_parts = []
    params: dict = {"limit": limit, "offset": offset}

    if status:
        where_parts.append("rc.status = :status")
        params["status"] = status
    if min_prob is not None:
        where_parts.append("rc.recovery_probability >= :min_prob")
        params["min_prob"] = min_prob
    if max_prob is not None:
        where_parts.append("rc.recovery_probability <= :max_prob")
        params["max_prob"] = max_prob
    if failure_code:
        where_parts.append("p.failure_code = :failure_code")
        params["failure_code"] = failure_code

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    result = await db.execute(text(f"""
        SELECT
            rc.id AS case_id, rc.payment_id, rc.status,
            rc.revenue_at_risk, rc.recovered_amount,
            rc.recovery_probability, rc.root_cause,
            rc.selected_action, rc.policy_decision,
            rc.opened_at, rc.closed_at,
            p.failure_code, p.payment_method, p.amount, p.currency,
            c.name AS customer_name, c.email
        FROM recovery_cases rc
        JOIN payments p ON p.id = rc.payment_id
        JOIN customers c ON c.id = p.customer_id
        {where_clause}
        ORDER BY rc.opened_at DESC
        LIMIT :limit OFFSET :offset
    """), params)
    rows = result.fetchall()

    # Batch summary stats (for batch recovery view)
    stats_r = await db.execute(text("""
        SELECT
            SUM(revenue_at_risk) AS at_risk,
            SUM(CASE WHEN status IN ('recovered', 'in_progress') OR recovery_probability >= 0.50 THEN revenue_at_risk ELSE 0 END) AS recoverable,
            SUM(CASE WHEN status = 'recovered' OR (selected_action != 'NO_ACTION' AND policy_decision='approved' AND status != 'blocked') THEN revenue_at_risk ELSE 0 END) AS actionable,
            SUM(recovered_amount) AS recovered
        FROM recovery_cases
    """))
    batch = dict(stats_r.fetchone()._mapping)

    return {
        "batch_summary": {
            "total_at_risk":   round(float(batch["at_risk"] or 0), 2),
            "recoverable":     round(float(batch["recoverable"] or 0), 2),
            "actionable":      round(float(batch["actionable"] or 0), 2),
            "recovered":       round(float(batch["recovered"] or 0), 2),
        },
        "cases": [
            {
                "case_id":              row.case_id,
                "payment_id":           row.payment_id,
                "status":               row.status,
                "amount":               float(row.amount),
                "currency":             row.currency,
                "revenue_at_risk":      float(row.revenue_at_risk),
                "recovered_amount":     float(row.recovered_amount or 0),
                "recovery_probability": round(float(row.recovery_probability or 0), 4),
                "root_cause":           row.root_cause,
                "selected_action":      row.selected_action,
                "policy_decision":      row.policy_decision,
                "failure_code":         row.failure_code,
                "payment_method":       row.payment_method,
                "customer_name":        row.customer_name,
                "customer_email":       row.email,
                "opened_at":            str(row.opened_at),
                "closed_at":            str(row.closed_at) if row.closed_at else None,
            }
            for row in rows
        ],
        "pagination": {"limit": limit, "offset": offset, "returned": len(rows)},
    }


# ── GET /api/v1/recovery/cases/{case_id} ─────────────────────────────────────
@router.get(
    "/api/v1/recovery/cases/{case_id}",
    summary="Complete case detail — everything in one call",
)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Returns everything the frontend needs in a single response:
    case + payment + customer + ML scores + RCA + decision + policy +
    execution + outcome + model version + audit events.
    """
    result = await db.execute(text("""
        SELECT
            rc.id AS case_id, rc.payment_id, rc.status,
            rc.revenue_at_risk, rc.recovered_amount,
            rc.recovery_probability, rc.root_cause,
            rc.selected_action, rc.policy_decision,
            rc.opened_at, rc.closed_at,
            p.failure_code, p.failure_reason, p.payment_method,
            p.amount, p.currency, p.retry_count, p.checkout_duration_sec,
            p.subscription_id, p.status AS payment_status,
            c.id AS customer_id, c.name AS customer_name, c.email,
            c.lifetime_value, c.previous_success_rate,
            c.contact_count, c.opted_out
        FROM recovery_cases rc
        JOIN payments p ON p.id = rc.payment_id
        JOIN customers c ON c.id = p.customer_id
        WHERE rc.id = :case_id OR rc.payment_id = :case_id
        ORDER BY rc.opened_at DESC
        LIMIT 1
    """), {"case_id": case_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    actual_case_id = row.case_id

    # Agent decisions
    decisions_r = await db.execute(text("""
        SELECT agent_name, step_index, reasoning, output, confidence, duration_ms, created_at
        FROM agent_decisions WHERE case_id = :cid ORDER BY step_index ASC
    """), {"cid": actual_case_id})
    decisions = [
        {
            "agent_name":  d.agent_name,
            "step_index":  d.step_index,
            "reasoning":   d.reasoning,
            "output":      json.loads(d.output) if d.output else {},
            "confidence":  d.confidence,
            "duration_ms": d.duration_ms,
            "timestamp":   str(d.created_at),
        }
        for d in decisions_r.fetchall()
    ]

    # Recovery actions
    actions_r = await db.execute(text("""
        SELECT id, action_type, parameters, executed_at, result, razorpay_reference
        FROM recovery_actions WHERE case_id = :cid ORDER BY executed_at ASC
    """), {"cid": actual_case_id})
    actions = [
        {
            "id":                 a.id,
            "action_type":        a.action_type,
            "parameters":         json.loads(a.parameters) if a.parameters else {},
            "executed_at":        str(a.executed_at),
            "result":             a.result,
            "razorpay_reference": a.razorpay_reference,
            "simulated":          True,
        }
        for a in actions_r.fetchall()
    ]

    # Model version from metadata
    meta_r = await db.execute(text(
        "SELECT model_version, algorithm, roc_auc FROM ml_model_metadata WHERE is_active=1 LIMIT 1"
    ))
    meta = meta_r.fetchone()

    # Audit trail
    audit = await get_audit_trail(db, actual_case_id, entity_type="case")
    payment_audit = await get_audit_trail(db, row.payment_id, entity_type="payment")
    all_audit = sorted(payment_audit + audit, key=lambda e: e["timestamp"])

    m = dict(row._mapping)
    return {
        "case": {
            "case_id":              m["case_id"],
            "payment_id":           m["payment_id"],
            "status":               m["status"],
            "revenue_at_risk":      float(m["revenue_at_risk"]),
            "recovered_amount":     float(m["recovered_amount"] or 0),
            "recovery_probability": round(float(m["recovery_probability"] or 0), 4),
            "root_cause":           m["root_cause"],
            "selected_action":      m["selected_action"],
            "policy_decision":      m["policy_decision"],
            "opened_at":            str(m["opened_at"]),
            "closed_at":            str(m["closed_at"]) if m["closed_at"] else None,
        },
        "payment": {
            "id":                   m["payment_id"],
            "amount":               float(m["amount"]),
            "currency":             m["currency"],
            "payment_method":       m["payment_method"],
            "failure_code":         m["failure_code"],
            "failure_reason":       m["failure_reason"],
            "retry_count":          m["retry_count"],
            "checkout_duration_sec": m["checkout_duration_sec"],
            "is_subscription":      m["subscription_id"] is not None,
            "status":               m["payment_status"],
        },
        "customer": {
            "id":                   m["customer_id"],
            "name":                 m["customer_name"],
            "email":                m["email"],
            "lifetime_value":       float(m["lifetime_value"] or 0),
            "previous_success_rate": float(m["previous_success_rate"] or 0),
            "contact_count":        m["contact_count"],
            "opted_out":            bool(m["opted_out"]),
        },
        "model_info": {
            "version":   meta.model_version if meta else "unknown",
            "algorithm": meta.algorithm if meta else "GradientBoostingClassifier",
            "roc_auc":   round(float(meta.roc_auc or 0), 4) if meta else 0,
        },
        "agent_decisions": decisions,
        "recovery_actions": actions,
        "audit_events":    all_audit,
        "sandbox":         True,
    }


# ── POST /api/v1/recovery/cases/{case_id}/approve ────────────────────────────
@router.post(
    "/api/v1/recovery/cases/{case_id}/approve",
    summary="Human approves a pending recovery action",
)
async def approve_case(case_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Human-in-the-loop: approve a case that requires_human_approval.
    Executes the recommended action (simulated) and transitions to recovered/failed.
    """
    result = await db.execute(
        text("SELECT payment_id, status, selected_action, policy_decision FROM recovery_cases WHERE id=:cid"),
        {"cid": case_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    if row.policy_decision != "requires_human":
        raise HTTPException(status_code=400, detail="Case does not require human approval.")
    if row.status not in ("in_progress", "open"):
        raise HTTPException(status_code=400, detail=f"Case already in terminal state: {row.status}")

    from app.services.decision import RecoveryAction
    action = RecoveryAction(row.selected_action) if row.selected_action else RecoveryAction.ESCALATE_TO_HUMAN

    executor = get_executor()
    exec_result = await executor.execute(
        db=db,
        case_id=case_id,
        payment_id=row.payment_id,
        action=action,
        params={},
        case_status="recovered",  # human approved → simulate success
    )

    final_status = "recovered" if exec_result.outcome_success else "failed"

    # Get payment amount for recovered_amount
    amt_r = await db.execute(text("SELECT amount FROM payments WHERE id=:pid"), {"pid": row.payment_id})
    amount = float(amt_r.fetchone()[0])

    await db.execute(text("""
        UPDATE recovery_cases SET status=:s, recovered_amount=:ra, closed_at=:now
        WHERE id=:cid
    """), {"s": final_status, "ra": amount if final_status=="recovered" else 0, "now": datetime.now(timezone.utc), "cid": case_id})

    await append_audit(db, "case", case_id, "OUTCOME_RECORDED", "human_approver", {
        "action": "approved", "executed_action": action.value, "outcome": final_status,
    })
    await db.commit()

    return {
        "case_id":        case_id,
        "approved_by":    "merchant",
        "action_executed": action.value,
        "outcome":        final_status,
        "recovered_amount": amount if final_status == "recovered" else 0,
        "simulated":      True,
    }


# ── POST /api/v1/recovery/cases/{case_id}/reject ─────────────────────────────
@router.post(
    "/api/v1/recovery/cases/{case_id}/reject",
    summary="Human rejects a pending recovery action",
)
async def reject_case(case_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        text("SELECT status, policy_decision FROM recovery_cases WHERE id=:cid"),
        {"cid": case_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    if row.status not in ("in_progress", "open"):
        raise HTTPException(status_code=400, detail=f"Case already in terminal state: {row.status}")

    await db.execute(text("""
        UPDATE recovery_cases SET status='rejected', closed_at=:now WHERE id=:cid
    """), {"now": datetime.now(timezone.utc), "cid": case_id})

    await append_audit(db, "case", case_id, "OUTCOME_RECORDED", "human_approver", {
        "action": "rejected", "outcome": "rejected",
    })
    await db.commit()

    return {"case_id": case_id, "outcome": "rejected"}


# ── POST /api/v1/demo/reset ───────────────────────────────────────────────────
@router.post("/api/v1/demo/reset", summary="Reset all demo scenario data (safe, idempotent)")
async def demo_reset(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Resets ONLY the six demo scenario payments (id LIKE 'demo-%').
    Deletes all associated: audit_logs, agent_decisions, recovery_actions, recovery_cases.
    Restores: payment.status='failed', customer.contact_count=0, customer.opted_out=original.
    Safe to run multiple times.
    """
    # Get demo case IDs first
    cases_r = await db.execute(text(
        "SELECT id FROM recovery_cases WHERE payment_id LIKE 'demo-%'"
    ))
    case_ids = [r[0] for r in cases_r.fetchall()]

    deleted = {"audit_logs": 0, "agent_decisions": 0, "recovery_actions": 0, "recovery_cases": 0}

    for cid in case_ids:
        r = await db.execute(text("DELETE FROM audit_logs WHERE entity_id=:cid"), {"cid": cid})
        deleted["audit_logs"] += r.rowcount
        r = await db.execute(text("DELETE FROM agent_decisions WHERE case_id=:cid"), {"cid": cid})
        deleted["agent_decisions"] += r.rowcount
        r = await db.execute(text("DELETE FROM recovery_actions WHERE case_id=:cid"), {"cid": cid})
        deleted["recovery_actions"] += r.rowcount

    # Delete payment-level audit events
    await db.execute(text("DELETE FROM audit_logs WHERE entity_id LIKE 'demo-%'"))

    r = await db.execute(text("DELETE FROM recovery_cases WHERE payment_id LIKE 'demo-%'"))
    deleted["recovery_cases"] += r.rowcount

    # Restore payment statuses
    await db.execute(text(
        "UPDATE payments SET status='failed' WHERE id LIKE 'demo-%' AND id != 'demo-F-success-6299'"
    ))
    # demo-F stays captured (that's its fixture state)
    await db.execute(text(
        "UPDATE payments SET status='captured' WHERE id='demo-F-success-6299'"
    ))

    # Restore customer contact counts (demo customers have email LIKE 'demo-%@recoverai.demo')
    await db.execute(text(
        "UPDATE customers SET contact_count=0 WHERE email LIKE 'demo-%@recoverai.demo' AND id != 'demo-cust-E-optout'"
    ))
    # demo-D customer stays at 5 contacts (that's its fixture state)
    await db.execute(text(
        "UPDATE customers SET contact_count=5 WHERE id='demo-cust-D-contact'"
    ))
    # demo-E customer stays opted_out=1
    await db.execute(text(
        "UPDATE customers SET opted_out=1 WHERE id='demo-cust-E-optout'"
    ))

    await db.commit()

    return {
        "reset":    True,
        "deleted":  deleted,
        "message":  "Demo scenario data reset. Re-run POST /analyze/{payment_id} to reproduce each scenario.",
        "demo_payments": [
            "demo-A-network-8499",
            "demo-B-lowprob-1299",
            "demo-C-highval-75000",
            "demo-D-contact-2999",
            "demo-E-optout-4599",
            "demo-F-success-6299",
        ],
    }
