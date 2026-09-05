/**
 * DecisionTrace — Step-by-step display of the agentic recovery workflow.
 * Shows 8 pipeline steps: Revenue Detection → ML → RCA → Decision → Policy →
 * Action Execution → Outcome → Audit Trail
 */

import type { AnalyzeResult } from "../api/client"
import { actionLabel, rcaLabel, shortDateTime } from "../utils/format"

interface Props {
  result: AnalyzeResult
}

interface TraceStep {
  index: number
  name: string
  actor: string
  status: "done" | "blocked" | "human" | "pending"
  summary: string
  detail: Record<string, unknown>
  timestamp?: string
}

function buildSteps(r: AnalyzeResult): TraceStep[] {
  const ts = (i: number) => r.audit_events[i]?.timestamp

  const policyStatus =
    r.policy.outcome === "blocked"        ? "blocked" :
    r.policy.outcome === "requires_human" ? "human"   : "done"

  const outcomeStatus =
    r.outcome.status === "recovered" ? "done" :
    r.outcome.status === "blocked"   ? "blocked" :
    r.outcome.status === "failed"    ? "blocked" : "human"

  return [
    {
      index:   1,
      name:    "Revenue Detection",
      actor:   "DetectionAgent",
      status:  "done",
      summary: `Failed payment of ₹${r.amount.toLocaleString("en-IN")} detected (${r.failure_code})`,
      detail:  {
        payment_id:     r.payment_id,
        failure_code:   r.failure_code,
        payment_method: r.payment_method,
        customer:       r.customer_name,
        amount_inr:     `₹${r.amount.toLocaleString("en-IN")}`,
      },
      timestamp: ts(0),
    },
    {
      index:   2,
      name:    "ML Recovery Scoring",
      actor:   "MLScoringAgent (GradientBoostingClassifier)",
      status:  "done",
      summary: `Recovery probability: ${(r.recovery_probability * 100).toFixed(1)}% (${r.risk_category})`,
      detail:  {
        recovery_probability: r.recovery_probability,
        risk_category:        r.risk_category,
        top_features:         r.feature_importances.slice(0, 5).map(f =>
          `${f.feature}: ${(f.importance * 100).toFixed(1)}%`
        ),
      },
      timestamp: ts(1),
    },
    {
      index:   3,
      name:    "Root Cause Analysis",
      actor:   "RCAAgent (deterministic rule engine)",
      status:  "done",
      summary: `Root cause: ${rcaLabel(r.root_cause)} (${r.rca_severity})`,
      detail:  {
        root_cause:       r.root_cause,
        severity:         r.rca_severity,
        auto_recoverable: r.rca_auto_recoverable,
        explanation:      r.rca_explanation || "(deterministic rule match)",
      },
      timestamp: ts(2),
    },
    {
      index:   4,
      name:    "Recovery Decision",
      actor:   "DecisionAgent (deterministic rules + ML signal)",
      status:  "done",
      summary: `Recommended action: ${actionLabel(r.recommended_action)}`,
      detail:  {
        action:     r.recommended_action,
        rationale:  r.decision_rationale,
        confidence: `${(r.decision_confidence * 100).toFixed(0)}%`,
      },
      timestamp: ts(3),
    },
    {
      index:   5,
      name:    "Policy Guard",
      actor:   "PolicyGuard (deterministic, bounded constraints)",
      status:  policyStatus,
      summary: r.policy.outcome === "approved"
        ? "✓ All policy checks passed. Action approved."
        : r.policy.outcome === "requires_human"
        ? "⚠ Requires human approval"
        : `✗ Blocked: ${r.policy.blocking_rule || r.policy.reason}`,
      detail:  {
        outcome:                r.policy.outcome,
        blocking_rule:          r.policy.blocking_rule ?? "none",
        requires_human_approval: r.policy.requires_human_approval,
        reason:                 r.policy.reason,
      },
      timestamp: ts(4),
    },
    {
      index:   6,
      name:    "Action Execution",
      actor:   "SimulatedRecoveryExecutor",
      status:  r.execution.status === "executed" ? "done" : "blocked",
      summary: `${r.execution.action_type} — ${r.execution.status} (${r.execution.simulated ? "SIMULATED" : "LIVE"})`,
      detail:  {
        action_type: r.execution.action_type,
        status:      r.execution.status,
        simulated:   r.execution.simulated,
        action_id:   r.execution.action_id ?? "(blocked, no action created)",
        message:     r.execution.message,
      },
      timestamp: ts(5),
    },
    {
      index:   7,
      name:    "Outcome Recording",
      actor:   "Pipeline Orchestrator",
      status:  outcomeStatus,
      summary: `Status: ${r.outcome.status} — Recovered: ₹${r.outcome.recovered_amount.toLocaleString("en-IN")}`,
      detail:  {
        status:           r.outcome.status,
        recovered_amount: `₹${r.outcome.recovered_amount.toLocaleString("en-IN")}`,
        idempotent:       r.idempotent,
      },
      timestamp: ts(6),
    },
    {
      index:   8,
      name:    "Immutable Audit Trail",
      actor:   "AuditLogger (append-only)",
      status:  "done",
      summary: `${r.audit_events.length} events recorded. No deletions permitted.`,
      detail:  {
        event_count:  r.audit_events.length,
        events:       r.audit_events.map(e => e.event),
        sandbox:      r.sandbox,
      },
      timestamp: r.audit_events[r.audit_events.length - 1]?.timestamp,
    },
  ]
}

export default function DecisionTrace({ result }: Props) {
  const steps = buildSteps(result)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {steps.map((step) => {
        let badgeClass = "badge-neutral"
        if (step.status === "done") badgeClass = "badge-success"
        else if (step.status === "blocked") badgeClass = "badge-danger"
        else if (step.status === "human") badgeClass = "badge-warning"

        return (
          <div
            key={step.index}
            style={{
              display: "flex",
              gap: "16px",
              padding: "16px",
              borderRadius: "8px",
              backgroundColor: "var(--surface-hover)",
              border: "1px solid var(--border-subtle)"
            }}
          >
            <div
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                backgroundColor: step.status === "done" ? "var(--success-bg)" : step.status === "blocked" ? "var(--danger-bg)" : "var(--warning-bg)",
                border: `1px solid ${step.status === "done" ? "var(--success-border)" : step.status === "blocked" ? "var(--danger-border)" : "var(--warning-border)"}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "12px",
                fontWeight: 700,
                color: step.status === "done" ? "var(--success)" : step.status === "blocked" ? "var(--danger)" : "var(--warning-text)",
                flexShrink: 0
              }}
            >
              {step.index}
            </div>

            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)" }}>{step.name}</span>
                  <span className={`badge ${badgeClass}`}>{step.status.toUpperCase()}</span>
                </div>
                {step.timestamp && (
                  <span className="mono" style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>
                    {shortDateTime(step.timestamp)}
                  </span>
                )}
              </div>

              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>by {step.actor}</div>
              <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary)", marginTop: "6px" }}>
                {step.summary}
              </div>

              <div
                style={{
                  marginTop: "8px",
                  padding: "8px 12px",
                  backgroundColor: "var(--bg-subtle)",
                  borderRadius: "4px",
                  border: "1px solid var(--border-subtle)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "11px",
                  color: "var(--text-secondary)",
                  whiteSpace: "pre-wrap"
                }}
              >
                {JSON.stringify(step.detail, null, 2)}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
