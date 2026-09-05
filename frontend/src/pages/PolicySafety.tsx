/**
 * PolicySafety — Policy Guard Safety Control Center.
 * Features:
 * - Visual Gate Diagram: MODEL → DECISION → POLICY GUARD → EXECUTOR
 * - Configured Policy Controls Grid (6 Bounded Rules)
 * - Live Policy Guard Evaluation Tool
 */

import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { api } from "../api/client"

interface LiveExample {
  label: string
  paymentId: string
  tag: string
  tagClass: string
  expectedRule: string
}

const LIVE_EXAMPLES: LiveExample[] = [
  { label: "B — Low Probability Block",     paymentId: "demo-B-lowprob-1299",  tag: "LOW PROB",    tagClass: "badge-danger",  expectedRule: "low_probability" },
  { label: "D — Contact Limit Block",       paymentId: "demo-D-contact-2999",  tag: "CONTACT",     tagClass: "badge-danger",  expectedRule: "contact_limit" },
  { label: "E — Opted-Out Block",           paymentId: "demo-E-optout-4599",   tag: "OPT-OUT",     tagClass: "badge-danger",  expectedRule: "opted_out" },
  { label: "F — Already Succeeded",         paymentId: "demo-F-success-6299",  tag: "CAPTURED",    tagClass: "badge-info",    expectedRule: "payment_succeeded" },
  { label: "C — High Value → Human",        paymentId: "demo-C-highval-75000", tag: "HUMAN ✓",     tagClass: "badge-warning", expectedRule: "high_amount" },
  { label: "A — Approved Recovery",         paymentId: "demo-A-network-8499",  tag: "APPROVED",    tagClass: "badge-success", expectedRule: "none" },
]

const POLICY_RULES = [
  {
    name: "Low Probability Block",
    condition: "ML Probability < 60%",
    action: "BLOCK RECOVERY",
    description: "Prevents wasting merchant resources and contacting customers when recoverability is low.",
    badgeClass: "badge-danger",
  },
  {
    name: "Opted-Out Block",
    condition: "customer.opted_out = true",
    action: "HARD BLOCK",
    description: "Respects customer communication preferences. Hard constraint that overrides all ML scores.",
    badgeClass: "badge-danger",
  },
  {
    name: "Contact Limit Block",
    condition: "contact_count ≥ 3",
    action: "BLOCK RECOVERY",
    description: "Limits customer outreach attempts to maximum 3 contacts to avoid spamming customers.",
    badgeClass: "badge-danger",
  },
  {
    name: "Payment Already Succeeded",
    condition: "payment.status = captured",
    action: "CANCEL RECOVERY",
    description: "Prevents double-charging if customer already completed payment via alternative channel.",
    badgeClass: "badge-info",
  },
  {
    name: "High-Value Recovery",
    condition: "Amount > ₹50,000 & Prob ≥ 60%",
    action: "REQUIRE HUMAN APPROVAL",
    description: "Ensures merchant ops team reviews all high-value recovery opportunities before execution.",
    badgeClass: "badge-warning",
  },
  {
    name: "Approved Recovery",
    condition: "All rules pass & Prob ≥ 60%",
    action: "EXECUTE RECOVERY",
    description: "Automatically executes bounded recovery action when all safety rules pass cleanly.",
    badgeClass: "badge-success",
  },
]

export default function PolicySafety() {
  const navigate = useNavigate()
  const [liveResults, setLiveResults] = useState<Record<string, any>>({})
  const [runningId, setRunningId]     = useState<string | null>(null)

  const runExample = async (ex: LiveExample) => {
    setRunningId(ex.paymentId)
    try {
      const r = await api.analyzePayment(ex.paymentId)
      setLiveResults(prev => ({ ...prev, [ex.paymentId]: r }))
    } catch (e: any) {
      setLiveResults(prev => ({ ...prev, [ex.paymentId]: { error: e.message } }))
    } finally {
      setRunningId(null)
    }
  }

  const viewCase = (paymentId: string) => {
    const r = liveResults[paymentId]
    if (r && r.case_id) navigate(`/cases/${r.case_id}`)
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-title-area">
          <h1 className="page-title">Policy &amp; Safety</h1>
          <p className="page-subtitle">
            Autonomous recovery with explicit, deterministic boundaries.
          </p>
        </div>
        <span className="mono-tag">DETERMINISTIC SAFETY ENGINE</span>
      </div>

      {/* Visual Pipeline Gate Illustration */}
      <div
        className="card"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto 1fr auto 1.4fr auto 1fr",
          alignItems: "center",
          gap: "16px",
          padding: "24px",
          textAlign: "center"
        }}
      >
        <div style={{ padding: "12px", backgroundColor: "var(--bg-subtle)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>Step 01</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: "var(--text-primary)", marginTop: 2 }}>MODEL</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Score Recoverability</div>
        </div>

        <div style={{ fontSize: 18, color: "var(--text-tertiary)" }}>→</div>

        <div style={{ padding: "12px", backgroundColor: "var(--bg-subtle)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>Step 02</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: "var(--text-primary)", marginTop: 2 }}>DECISION</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Select Action</div>
        </div>

        <div style={{ fontSize: 18, color: "var(--text-tertiary)" }}>→</div>

        {/* Visual Gate Focus */}
        <div
          style={{
            padding: "16px",
            backgroundColor: "var(--accent-subtle)",
            border: "2px solid var(--accent)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-sm)"
          }}
        >
          <div style={{ fontSize: 10, fontWeight: 800, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            SAFETY GATE
          </div>
          <div style={{ fontSize: 16, fontWeight: 800, color: "var(--accent)", marginTop: 2 }}>
            POLICY GUARD
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Deterministic Rule Evaluation</div>
        </div>

        <div style={{ fontSize: 18, color: "var(--text-tertiary)" }}>→</div>

        <div style={{ padding: "12px", backgroundColor: "var(--bg-subtle)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>Step 03</div>
          <div style={{ fontSize: 14, fontWeight: 800, color: "var(--text-primary)", marginTop: 2 }}>EXECUTOR</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Simulated / Sandbox</div>
        </div>
      </div>

      {/* Six Bounded Policy Rules Grid */}
      <div>
        <div className="card-title" style={{ marginBottom: "12px", fontSize: 16 }}>
          Configured Policy Controls (Priority Order)
        </div>
        <div className="grid-2">
          {POLICY_RULES.map((rule) => (
            <div key={rule.name} className="card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <div style={{ fontSize: 15, fontWeight: 800, color: "var(--text-primary)" }}>{rule.name}</div>
                  <span className={`badge ${rule.badgeClass}`}>{rule.action}</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  {rule.description}
                </div>
              </div>

              <div style={{ marginTop: "16px", paddingTop: "10px", borderTop: "1px solid var(--border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>Condition Trigger</span>
                <span className="mono-tag" style={{ fontWeight: 600 }}>{rule.condition}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Policy Guard Execution Table */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Live Policy Evaluation</div>
            <div className="section-subtitle">Run Policy Guard against real payment scenarios</div>
          </div>
          <span className="mono-tag">SANDBOX RUNNER</span>
        </div>

        <div className="table-container" style={{ border: "none", boxShadow: "none" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>ML Prob</th>
                <th>Policy Outcome</th>
                <th>Evaluated Rule</th>
                <th>Outcome</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {LIVE_EXAMPLES.map((ex) => {
                const r = liveResults[ex.paymentId]
                return (
                  <tr key={ex.paymentId}>
                    <td>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{ex.label}</div>
                      <div className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{ex.paymentId}</div>
                    </td>

                    <td>
                      {r && !r.error ? (
                        <span className="mono" style={{ fontWeight: 700 }}>{(r.recovery_probability * 100).toFixed(1)}%</span>
                      ) : (
                        <span style={{ color: "var(--text-tertiary)" }}>—</span>
                      )}
                    </td>

                    <td>
                      {r && !r.error ? (
                        <span className={`badge ${r.policy.outcome === "approved" ? "badge-success" : r.policy.outcome === "requires_human" ? "badge-warning" : "badge-danger"}`}>
                          {r.policy.outcome.toUpperCase()}
                        </span>
                      ) : (
                        <span className={`badge ${ex.tagClass}`}>{ex.tag}</span>
                      )}
                    </td>

                    <td>
                      {r && !r.error ? (
                        <span className="mono-tag">{r.policy.blocking_rule || "none"}</span>
                      ) : (
                        <span className="mono-tag" style={{ color: "var(--text-tertiary)" }}>{ex.expectedRule}</span>
                      )}
                    </td>

                    <td>
                      {r && !r.error ? (
                        <span style={{ fontSize: 12, fontWeight: 600, color: r.outcome.status === "recovered" ? "var(--success)" : "var(--text-secondary)" }}>
                          {r.outcome.status === "recovered" ? `₹${r.outcome.recovered_amount} Recovered` : r.outcome.status}
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-tertiary)" }}>—</span>
                      )}
                    </td>

                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => runExample(ex)}
                          disabled={runningId === ex.paymentId}
                        >
                          {runningId === ex.paymentId ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "Evaluate →"}
                        </button>
                        {r && r.case_id && (
                          <button className="btn btn-ghost btn-sm" onClick={() => viewCase(ex.paymentId)}>
                            View Case
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
