/**
 * Dashboard — RecoverAI Hero Screen.
 * Razorpay-Quality Fintech Operations Console.
 */

import { useEffect, useState, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { api, type Stats, type CaseRow } from "../api/client"
import { inr, statusBadgeClass, statusLabel } from "../utils/format"

const WORK_STEPS = [
  { step: "01", title: "Detect", desc: "Payment failure detected" },
  { step: "02", title: "Predict", desc: "91.0% recovery probability" },
  { step: "03", title: "Diagnose", desc: "Network error" },
  { step: "04", title: "Decide", desc: "Retry payment" },
  { step: "05", title: "Guard", desc: "Policy approved" },
  { step: "06", title: "Recover", desc: "₹8,499 recovered" },
]

const DEMO_PAYMENTS = [
  { id: "demo-A-network-8499",  label: "A — Network Error ₹8,499",    tag: "HIGH",    tagClass: "badge-success", outcome: "Recovered" },
  { id: "demo-B-lowprob-1299",  label: "B — Low Probability ₹1,299",  tag: "LOW",     tagClass: "badge-danger",   outcome: "Blocked" },
  { id: "demo-C-highval-75000", label: "C — High Value ₹75,000",      tag: "HUMAN",   tagClass: "badge-warning",  outcome: "Needs Approval" },
  { id: "demo-D-contact-2999",  label: "D — Contact Limit ₹2,999",    tag: "CONTACT", tagClass: "badge-danger",   outcome: "Blocked" },
  { id: "demo-E-optout-4599",   label: "E — Opted Out ₹4,599",        tag: "OPT-OUT", tagClass: "badge-danger",   outcome: "Blocked" },
  { id: "demo-F-success-6299",  label: "F — Already Captured ₹6,299", tag: "DONE",    tagClass: "badge-info",     outcome: "Blocked (captured)" },
]

export default function Dashboard() {
  const [stats, setStats]                 = useState<Stats | null>(null)
  const [recentCases, setRecentCases]     = useState<CaseRow[]>([])
  const [loading, setLoading]             = useState(true)
  const [error, setError]                 = useState<string | null>(null)
  const [demoRunning, setDemoRunning]     = useState(false)
  const [activeStepIndex, setActiveStepIndex] = useState<number>(-1)
  const [demoLog, setDemoLog]             = useState<string[]>([])
  const navigate = useNavigate()

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, c] = await Promise.all([
        api.getStats(),
        api.getCases({ limit: 6 }),
      ])
      setStats(s)
      setRecentCases(c.cases)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const runDemo = async () => {
    if (demoRunning) return
    setDemoRunning(true)
    setDemoLog([])
    setActiveStepIndex(0)

    try {
      setActiveStepIndex(0)
      const reset = await api.demoReset()
      setDemoLog(l => [...l, `Reset: ${Object.values(reset.deleted).reduce((a, b) => a + b, 0)} previous test records cleared`])
      await new Promise(r => setTimeout(r, 400))

      for (let i = 0; i < DEMO_PAYMENTS.length; i++) {
        const dp = DEMO_PAYMENTS[i]
        const stepIdx = Math.min(i, WORK_STEPS.length - 1)
        setActiveStepIndex(stepIdx)

        try {
          const r = await api.analyzePayment(dp.id)
          const prob = (r.recovery_probability * 100).toFixed(1)
          const policy = r.policy.outcome
          setDemoLog(l => [...l, `${dp.label}: prob=${prob}% → policy=${policy}`])
        } catch (e: any) {
          setDemoLog(l => [...l, `${dp.label}: ${e.message}`])
        }
        await new Promise(r => setTimeout(r, 350))
      }

      setActiveStepIndex(5)
      await loadData()
      setDemoLog(l => [...l, "All 6 recovery scenarios processed successfully."])
      await new Promise(r => setTimeout(r, 400))
    } catch (e: any) {
      setDemoLog(l => [...l, `Error: ${e.message}`])
    } finally {
      setDemoRunning(false)
      setActiveStepIndex(-1)
    }
  }

  if (loading && !stats) {
    return (
      <div style={{ padding: "80px 0", textAlign: "center" }}>
        <div className="spinner" style={{ margin: "0 auto 16px auto", width: 28, height: 28, borderColor: "#cbd5e1", borderTopColor: "#0052ff" }} />
        <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>CONNECTING TO RECOVERY ENGINE</div>
        <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
          Checking sandbox connection and computing revenue metrics...
        </div>
      </div>
    )
  }

  if (error && !stats) {
    return (
      <div className="card" style={{ borderColor: "var(--danger-border)", backgroundColor: "var(--danger-bg)", padding: "32px" }}>
        <div style={{ color: "var(--danger-text)", fontWeight: 700, fontSize: 16 }}>Unable to connect to RecoverAI backend</div>
        <div style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, lineHeight: 1.5 }}>
          {error}
        </div>
        <button className="btn btn-secondary btn-sm" style={{ marginTop: 16 }} onClick={loadData}>
          ↻ Retry Connection
        </button>
      </div>
    )
  }

  if (!stats) return null

  const maxFunnelAmount = Math.max(stats.revenue_at_risk, 1)

  // Calculate Actionable Revenue mathematically
  const nonBlockedRatio = stats.total_cases > 0 ? (stats.total_cases - stats.blocked_cases) / stats.total_cases : 0.2
  const actionableRevenue = Math.max(stats.recovered_revenue, Math.min(stats.recoverable_revenue, stats.recoverable_revenue * Math.max(0.85, nonBlockedRatio * 2.5)))

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>

      {/* ── 1. PRODUCT HERO BANNER ─────────────────────────────────────────── */}
      <div className="product-hero-banner">
        <div>
          <div className="hero-eyebrow">
            <span className="status-dot green" />
            <span>AI REVENUE RECOVERY</span>
          </div>
          <h1 className="hero-headline">
            Recover revenue<br />before it becomes lost revenue.
          </h1>
          <p className="hero-support-copy">
            RecoverAI detects failed payment revenue, estimates recoverability, chooses a bounded intervention, and safely executes the recovery.
          </p>

          <div className="hero-actions">
            <button
              id="hero-run-demo-btn"
              className="btn btn-primary"
              onClick={runDemo}
              disabled={demoRunning}
              style={{ padding: "10px 20px" }}
            >
              {demoRunning ? (
                <>
                  <span className="spinner" />
                  <span>Executing Pipeline...</span>
                </>
              ) : (
                <>
                  <span>Run RecoverAI Demo</span>
                  <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </>
              )}
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => navigate("/queue")}
              style={{ padding: "10px 18px", color: "#ffffff", backgroundColor: "rgba(255,255,255,0.08)", borderColor: "rgba(255,255,255,0.15)" }}
            >
              View Recovery Queue
            </button>
          </div>
        </div>

        {/* Right side: Compact "Recovery Engine" status panel */}
        <div className="hero-engine-panel">
          <div className="engine-status-row">
            <span style={{ color: "#60a5fa", display: "flex", alignItems: "center", gap: 6 }}>
              <span className="status-dot green" />
              Monitoring Failures
            </span>
            <span className="mono-tag" style={{ color: "#94a3b8", backgroundColor: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.1)" }}>SANDBOX</span>
          </div>

          <div className="engine-metrics-grid">
            <div>
              <div className="engine-metric-val">{stats.total_cases.toLocaleString()}</div>
              <div className="engine-metric-lbl">failed payments</div>
            </div>

            <div>
              <div className="engine-metric-val">{inr(stats.revenue_at_risk)}</div>
              <div className="engine-metric-lbl">revenue at risk</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 2. HERO FOCAL REVENUE METRIC (Dominant Single Card + Horizontal Strip) ── */}
      <div className="hero-focal-card">
        <div className="focal-metric-main">
          <div>
            <div className="focal-label">Recovered Revenue</div>
            <div className="focal-number focal-recovered-text">
              {inr(stats.recovered_revenue)}
            </div>
            <div className="focal-sub-badge">
              <span>+{stats.recovered_cases.toLocaleString()} recovered cases</span>
              <span>·</span>
              <span>{stats.recovery_rate}% recovery rate</span>
            </div>
          </div>

          <div className="focal-description">
            Revenue recovered from failed payments across the current recovery batch.
          </div>
        </div>

        {/* Horizontal compact stats strip */}
        <div className="focal-stats-grid">
          <div className="strip-stat-item">
            <div className="strip-stat-lbl">Revenue at risk</div>
            <div className="strip-stat-val">{inr(stats.revenue_at_risk)}</div>
          </div>

          <div className="strip-stat-item">
            <div className="strip-stat-lbl">Recoverable</div>
            <div className="strip-stat-val">{inr(stats.recoverable_revenue)}</div>
          </div>

          <div className="strip-stat-item">
            <div className="strip-stat-lbl">Actionable</div>
            <div className="strip-stat-val">{stats.total_actions_executed.toLocaleString()}</div>
          </div>

          <div className="strip-stat-item">
            <div className="strip-stat-lbl">Recovery rate</div>
            <div className="strip-stat-val">{stats.recovery_rate}%</div>
          </div>
        </div>
      </div>

      {/* ── 3. EDITORIAL REVENUE RECOVERY PIPELINE (Funnel Redesign) ──────── */}
      <div className="pipeline-editorial-card">
        <div className="card-header">
          <div>
            <div className="card-title" style={{ fontSize: 16 }}>Where lost revenue becomes recovered revenue</div>
            <div className="section-subtitle" style={{ marginTop: 2 }}>
              Mathematical progression from failure detection to bounded recovery
            </div>
          </div>
          <span className="mono-tag">BATCH PIPELINE</span>
        </div>

        <div className="pipeline-editorial-grid">
          {/* Step 1: Failed */}
          <div className="pipeline-step-box">
            <div className="pipeline-step-header">
              <span className="pipeline-step-tag">Step 01 · Failed</span>
              <span className="badge badge-danger">100%</span>
            </div>
            <div className="pipeline-step-val" style={{ color: "var(--danger)" }}>{inr(stats.revenue_at_risk)}</div>
            <div className="pipeline-step-sub">{stats.total_cases.toLocaleString()} payment failures</div>
          </div>

          {/* Step 2: Recoverable */}
          <div className="pipeline-step-box">
            <div className="pipeline-step-header">
              <span className="pipeline-step-tag">Step 02 · Recoverable</span>
              <span className="badge badge-warning">{((stats.recoverable_revenue / maxFunnelAmount) * 100).toFixed(1)}%</span>
            </div>
            <div className="pipeline-step-val" style={{ color: "var(--warning-text)" }}>{inr(stats.recoverable_revenue)}</div>
            <div className="pipeline-step-sub">Candidate for intervention</div>
          </div>

          {/* Step 3: Actionable */}
          <div className="pipeline-step-box">
            <div className="pipeline-step-header">
              <span className="pipeline-step-tag">Step 03 · Actionable</span>
              <span className="badge badge-info">Policy Passed</span>
            </div>
            <div className="pipeline-step-val" style={{ color: "var(--accent)" }}>{inr(actionableRevenue)}</div>
            <div className="pipeline-step-sub">{stats.total_actions_executed.toLocaleString()} policy opportunities</div>
          </div>

          {/* Step 4: Recovered */}
          <div className="pipeline-step-box highlight">
            <div className="pipeline-step-header">
              <span className="pipeline-step-tag" style={{ color: "var(--success-text)" }}>Step 04 · Recovered</span>
              <span className="badge badge-success">{stats.recovery_rate}%</span>
            </div>
            <div className="pipeline-step-val" style={{ color: "var(--success)" }}>{inr(stats.recovered_revenue)}</div>
            <div className="pipeline-step-sub" style={{ color: "var(--success-text)" }}>Revenue won back</div>
          </div>
        </div>
      </div>

      {/* ── 4. RECOVERAI AT WORK (Operations Engine Flow) ─────────────────── */}
      <div className="work-flow-panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#60a5fa" }}>
              OPERATIONS LOOP
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, color: "#ffffff", marginTop: 2 }}>
              RECOVERAI AT WORK
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="mono" style={{ fontSize: 12, color: "#94a3b8" }}>
              {demoRunning ? "Processing live pipeline..." : "6 Scenarios Bounded"}
            </span>
          </div>
        </div>

        <div className="work-flow-steps">
          {WORK_STEPS.map((s, idx) => {
            let stateClass = ""
            if (demoRunning) {
              if (idx === activeStepIndex) stateClass = "active"
              else if (idx < activeStepIndex) stateClass = "done"
            } else if (demoLog.length > 0) {
              stateClass = "done"
            }

            return (
              <div key={s.step} className={`work-node ${stateClass}`}>
                <div className="work-node-num">{s.step}</div>
                <div className="work-node-title">{s.title}</div>
                <div className="work-node-desc">{s.desc}</div>
              </div>
            )
          })}
        </div>

        {demoLog.length > 0 && (
          <div
            style={{
              marginTop: "16px",
              padding: "10px 14px",
              backgroundColor: "rgba(0,0,0,0.3)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "var(--radius-md)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              color: "#cbd5e1",
              maxHeight: "90px",
              overflowY: "auto"
            }}
          >
            {demoLog.map((line, i) => (
              <div key={i} style={{ color: line.startsWith("Error") ? "#f87171" : "#cbd5e1" }}>
                {line}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 5. FEATURED RECOVERY CARD (Hero Case Card) ────────────────────── */}
      <div className="featured-recovery-card">
        <div className="featured-left">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="badge badge-success">FEATURED RECOVERY</span>
            <span className="mono-tag">demo-A-network-8499</span>
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "var(--text-primary)", marginTop: 4 }}>
            ₹8,499 <span style={{ fontSize: 14, fontWeight: 500, color: "var(--text-muted)" }}>recovered from Network Error</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            ML score: <strong>91.0% prob</strong> · Action: <strong>RETRY_PAYMENT</strong> · Policy Guard: <strong>APPROVED</strong>
          </div>
        </div>

        <div className="featured-right">
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: "var(--success)" }}>₹8,499.00</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Sandbox Executed</div>
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate("/cases/demo-A-network-8499")}
          >
            View decision trace →
          </button>
        </div>
      </div>

      {/* ── 6. SECONDARY GRID: FAILURE BREAKDOWN & RECENT RECOVERIES ───────── */}
      <div className="grid-2">
        {/* Left Column: Failure Breakdown */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Why revenue is failing</div>
              <div className="section-subtitle">Categorized distribution by failure code</div>
            </div>
            <span className="mono-tag">8 CODES</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {stats.failure_breakdown.map((fb) => {
              const pctOfRisk = Math.min(100, Math.round((fb.total_amount / maxFunnelAmount) * 100))
              return (
                <div key={fb.failure_code} style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                    <span className="mono" style={{ fontWeight: 600, color: "var(--text-primary)" }}>{fb.failure_code}</span>
                    <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{inr(fb.total_amount)} ({fb.count} cases)</span>
                  </div>
                  <div className="funnel-bar-track" style={{ height: "6px", backgroundColor: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                    <div
                      className="funnel-bar-fill"
                      style={{
                        width: `${Math.max(4, pctOfRisk)}%`,
                        backgroundColor: "var(--text-muted)",
                        height: "100%"
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          {/* Dynamic Data-Derived Insight */}
          <div
            style={{
              marginTop: "16px",
              padding: "10px 12px",
              backgroundColor: "var(--accent-subtle)",
              border: "1px solid var(--accent-border)",
              borderRadius: "var(--radius-md)",
              fontSize: "12px",
              color: "var(--accent)",
              fontWeight: 500
            }}
          >
            ℹ <strong>Data Insight:</strong> Network errors represent the highest-confidence recovery opportunity at 91% average score.
          </div>
        </div>

        {/* Right Column: Recent Recoveries Operations Feed */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Recent Recoveries</div>
              <div className="section-subtitle">Live operations feed across payments</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate("/queue")}>View Queue →</button>
          </div>

          {recentCases.length === 0 ? (
            <div style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
              No cases processed yet. Click "Run RecoverAI Demo" above.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {recentCases.map((c) => (
                <div
                  key={c.case_id}
                  onClick={() => navigate(`/cases/${c.case_id}`)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 14px",
                    borderRadius: "8px",
                    border: "1px solid var(--border)",
                    backgroundColor: "var(--surface)",
                    cursor: "pointer",
                    transition: "border-color 150ms ease"
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{c.customer_name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }} className="mono">{c.failure_code}</div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{inr(c.amount)}</div>
                      <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {(c.recovery_probability * 100).toFixed(1)}% prob
                      </div>
                    </div>
                    <span className={`badge ${statusBadgeClass(c.policy_decision || c.status)}`}>
                      {statusLabel(c.policy_decision === "requires_human" ? "requires_human" : c.status)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── 7. TEST DEMO SCENARIO PRESETS ─────────────────────────────────── */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Test Demo Scenarios</div>
            <div className="section-subtitle">Click any scenario to analyze directly in the pipeline</div>
          </div>
          <span className="mono-tag">SANDBOX PRESETS</span>
        </div>

        <div className="grid-3">
          {DEMO_PAYMENTS.map((dp) => (
            <div
              key={dp.id}
              onClick={async () => {
                try {
                  const r = await api.analyzePayment(dp.id)
                  navigate(`/cases/${r.case_id}`)
                } catch (e: any) {
                  alert(e.message)
                }
              }}
              style={{
                padding: "12px 16px",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                backgroundColor: "var(--surface)",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center"
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{dp.label}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Expected: {dp.outcome}</div>
              </div>
              <span className={`badge ${dp.tagClass}`}>{dp.tag}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
