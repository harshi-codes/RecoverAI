/**
 * CaseDetail — The Core Intelligence Screen for RecoverAI.
 * Features:
 * - Clean horizontal decision journey: DETECT → SCORE → DIAGNOSE → DECIDE → POLICY → EXECUTE → OUTCOME
 * - Model signals breakdown
 * - Visually signature Policy Guard safety boundary gate
 * - Large Amber Attention Panel for Human Approval (₹75,000 case)
 * - Decision Trace & Immutable Audit Timeline
 */

import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, type CaseDetail as CaseDetailType, type AnalyzeResult } from '../api/client'
import DecisionTrace from '../components/DecisionTrace'
import {
  inr, statusBadgeClass, statusLabel,
  actionLabel, rcaLabel, shortDateTime
} from '../utils/format'

function InfoRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: mono ? 'var(--font-mono)' : undefined, fontWeight: 600 }}>
        {value}
      </span>
    </div>
  )
}

export default function CaseDetail() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const [data, setData]               = useState<CaseDetailType | null>(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)
  const [approving, setApproving]     = useState(false)
  const [rejecting, setRejecting]     = useState(false)
  const [activeTab, setActiveTab]     = useState<'overview' | 'trace' | 'audit'>('overview')
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResult | null>(null)

  const loadData = useCallback(async () => {
    if (!caseId) return
    setLoading(true)
    setError(null)
    try {
      let d: CaseDetailType
      try {
        d = await api.getCase(caseId)
      } catch (firstErr) {
        // Fallback: If not found as case_id, attempt to analyze payment_id first
        const ar = await api.analyzePayment(caseId)
        d = await api.getCase(ar.case_id)
        setAnalyzeResult(ar)
      }

      setData(d)
      if (!analyzeResult) {
        try {
          const ar = await api.analyzePayment(d.case.payment_id)
          setAnalyzeResult(ar)
        } catch {
          // Fallback gracefully if re-analysis is unavailable
        }
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [caseId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleApprove = async () => {
    if (!caseId) return
    setApproving(true)
    try {
      await api.approveCase(caseId)
      await loadData()
    } catch (e: any) {
      alert(`Approval failed: ${e.message}`)
    } finally {
      setApproving(false)
    }
  }

  const handleReject = async () => {
    if (!caseId) return
    setRejecting(true)
    try {
      await api.rejectCase(caseId)
      await loadData()
    } catch (e: any) {
      alert(`Rejection failed: ${e.message}`)
    } finally {
      setRejecting(false)
    }
  }

  if (loading && !data) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center' }}>
        <div className="spinner" style={{ margin: '0 auto 12px auto', width: 24, height: 24, borderColor: '#cbd5e1', borderTopColor: '#0052ff' }} />
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading recovery case details...</span>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger-border)', backgroundColor: 'var(--danger-bg)', padding: '24px' }}>
        <div style={{ color: 'var(--danger-text)', fontWeight: 700 }}>Error loading case</div>
        <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>{error}</div>
        <button className="btn btn-secondary btn-sm" style={{ marginTop: 12 }} onClick={() => navigate(-1)}>← Back</button>
      </div>
    )
  }

  if (!data) return null

  const { case: c, payment, customer, model_info, recovery_actions, audit_events } = data
  const prob = c.recovery_probability
  const pct = (prob * 100).toFixed(1)
  const policyDecision = c.policy_decision || 'unknown'
  const isHumanApproval = policyDecision === 'requires_human' && c.status === 'in_progress'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Header & Breadcrumb */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate(-1)}>
            ← Back
          </button>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="mono-tag" style={{ fontSize: 12, fontWeight: 700 }}>RECOVERY CASE</span>
              <h1 className="page-title" style={{ fontSize: '20px' }}>{c.case_id}</h1>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
              Amount: <strong style={{ color: 'var(--text-primary)' }}>{inr(payment.amount)}</strong> · Failure: <span className="mono" style={{ color: 'var(--text-primary)' }}>{payment.failure_code}</span> · Customer: <strong>{customer.name}</strong>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className={`badge ${statusBadgeClass(policyDecision === 'requires_human' ? 'requires_human' : c.status)}`} style={{ padding: '6px 12px', fontSize: 12 }}>
            {statusLabel(policyDecision === 'requires_human' ? 'requires_human' : c.status)}
          </span>
          <span className="connection-badge connected">SANDBOX EXECUTION</span>
        </div>
      </div>

      {/* ── REQUIREMENT 14: LARGE AMBER ATTENTION PANEL (Human Approval Required) ── */}
      {isHumanApproval && (
        <div className="human-approval-panel">
          <div>
            <div className="human-approval-title">HUMAN APPROVAL REQUIRED</div>
            <div className="human-approval-desc">
              High-value recovery opportunity of <strong>{inr(c.revenue_at_risk)}</strong> exceeds autonomous execution threshold (&gt; ₹50,000).
              <br />
              Action selected: <strong>{actionLabel(c.selected_action || '')}</strong>. Please review and confirm execution.
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              id="approve-btn"
              className="btn btn-success"
              onClick={handleApprove}
              disabled={approving || rejecting}
              style={{ padding: '10px 18px' }}
            >
              {approving ? <span className="spinner" /> : '✓'} Approve Recovery
            </button>
            <button
              className="btn btn-danger"
              onClick={handleReject}
              disabled={approving || rejecting}
              style={{ padding: '10px 18px' }}
            >
              {rejecting ? <span className="spinner" /> : '✗'} Reject
            </button>
          </div>
        </div>
      )}

      {/* ── HORIZONTAL DECISION JOURNEY ── */}
      <div className="card" style={{ padding: '20px 24px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 14 }}>
          Decision Pipeline Journey
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '12px', textAlign: 'center' }}>
          {[
            { label: '1. Detect', val: payment.failure_code, status: 'done' },
            { label: '2. Score', val: `${pct}% Prob`, status: 'done' },
            { label: '3. Diagnose', val: rcaLabel(c.root_cause || ''), status: 'done' },
            { label: '4. Decide', val: c.selected_action || 'NO_ACTION', status: 'done' },
            { label: '5. Policy Guard', val: policyDecision.toUpperCase(), status: policyDecision === 'approved' ? 'done' : policyDecision === 'requires_human' ? 'amber' : 'red' },
            { label: '6. Execute', val: recovery_actions.length > 0 ? 'Executed' : 'Pending', status: c.status === 'recovered' ? 'done' : c.status === 'in_progress' ? 'amber' : 'red' },
            { label: '7. Outcome', val: c.status.toUpperCase(), status: c.status === 'recovered' ? 'done' : c.status === 'in_progress' ? 'amber' : 'red' },
          ].map((node) => (
            <div
              key={node.label}
              style={{
                padding: '10px 8px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: node.status === 'done' ? 'var(--bg-subtle)' : node.status === 'amber' ? 'var(--warning-bg)' : 'var(--danger-bg)',
                border: `1px solid ${node.status === 'done' ? 'var(--border)' : node.status === 'amber' ? 'var(--warning-border)' : 'var(--danger-border)'}`
              }}
            >
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)' }}>{node.label}</div>
              <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--text-primary)', marginTop: 2 }} className="mono">
                {node.val}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border)', paddingBottom: '8px' }}>
        <button
          className={`btn ${activeTab === 'overview' ? 'btn-primary' : 'btn-ghost'} btn-sm`}
          onClick={() => setActiveTab('overview')}
        >
          Overview &amp; Policy
        </button>
        <button
          className={`btn ${activeTab === 'trace' ? 'btn-primary' : 'btn-ghost'} btn-sm`}
          onClick={() => setActiveTab('trace')}
        >
          Decision Trace
        </button>
        <button
          className={`btn ${activeTab === 'audit' ? 'btn-primary' : 'btn-ghost'} btn-sm`}
          onClick={() => setActiveTab('audit')}
        >
          Immutable Audit Trail ({audit_events.length})
        </button>
      </div>

      {/* OVERVIEW TAB */}
      {activeTab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Row 1: Probability & Decision */}
          <div className="grid-2">
            {/* Recovery Score Box */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">Recovery Probability</span>
                <span className="mono-tag">GradientBoosting v{model_info.version}</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '24px', margin: '12px 0' }}>
                <div>
                  <div style={{ fontSize: '42px', fontWeight: 800, letterSpacing: '-0.04em', color: 'var(--text-primary)', lineHeight: 1 }}>
                    {pct}%
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: prob >= 0.75 ? 'var(--success)' : prob >= 0.50 ? 'var(--warning-text)' : 'var(--danger-text)', marginTop: 4 }}>
                    {prob >= 0.75 ? 'HIGH Confidence' : prob >= 0.50 ? 'MEDIUM Confidence' : 'LOW Confidence'}
                  </div>
                </div>

                <div style={{ flex: 1, borderLeft: '1px solid var(--border-subtle)', paddingLeft: '20px' }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Target Variable</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginTop: 2 }}>
                    recovered_within_24h
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                    ROC-AUC Score: <span className="mono" style={{ fontWeight: 600 }}>{model_info.roc_auc}</span>
                  </div>
                </div>
              </div>

              {/* Signals used by model */}
              <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '8px' }}>
                  Model Signals Evaluated
                </div>
                <InfoRow label="Customer success rate" value={`${(customer.previous_success_rate * 100).toFixed(0)}%`} mono />
                <InfoRow label="Retry count" value={payment.retry_count} mono />
                <InfoRow label="Failure code" value={<span className="mono">{payment.failure_code}</span>} />
                <InfoRow label="Payment amount" value={inr(payment.amount)} mono />
              </div>
            </div>

            {/* Decision & Recommendation */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">Recovery Decision</span>
                <span className="badge badge-info">Deterministic Rules</span>
              </div>

              <div style={{ margin: '8px 0' }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Recommended Action</div>
                <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--accent)', marginTop: 4 }}>
                  {c.selected_action ? actionLabel(c.selected_action) : 'NO_ACTION'}
                </div>
                {analyzeResult?.decision_rationale && (
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5 }}>
                    {analyzeResult.decision_rationale}
                  </div>
                )}
              </div>

              <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-subtle)' }}>
                <InfoRow label="Customer Lifetime Value" value={inr(customer.lifetime_value)} mono />
                <InfoRow label="Contact Count Limit" value={`${customer.contact_count} / 3`} mono />
                <InfoRow label="Customer Opted Out" value={customer.opted_out ? 'Yes (Blocked)' : 'No'} />
              </div>
            </div>
          </div>

          {/* ── REQUIREMENT 13: POLICY GUARD SIGNATURE VISUAL GATE ── */}
          <div className="card">
            <div className="card-header">
              <div>
                <span className="card-title">Policy Guard Safety Boundary</span>
                <div className="section-subtitle" style={{ marginTop: 2 }}>
                  Deterministic gate enforcing merchant safety rules before execution
                </div>
              </div>
              <span className="mono-tag">DETERMINISTIC GATE</span>
            </div>

            {/* Visual Gate Diagram: MODEL → DECISION → [ POLICY GUARD ] → EXECUTOR */}
            <div className="policy-gate-container">
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                Intervention Execution Flow
              </div>

              <div className={`policy-gate-box ${policyDecision}`}>
                <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: policyDecision === 'approved' ? 'var(--success-text)' : policyDecision === 'requires_human' ? 'var(--warning-text)' : 'var(--danger-text)' }}>
                  POLICY GUARD SAFETY BOUNDARY
                </div>
                <div style={{ fontSize: 16, fontWeight: 800, marginTop: 4, color: policyDecision === 'approved' ? 'var(--success-text)' : policyDecision === 'requires_human' ? 'var(--warning-text)' : 'var(--danger-text)' }}>
                  {policyDecision === 'approved' && '✓ ACTION PERMITTED — All policy rules passed'}
                  {policyDecision === 'requires_human' && '! APPROVAL REQUIRED — Amount exceeds ₹50,000 threshold'}
                  {policyDecision === 'blocked' && '× ACTION BLOCKED — Safety rule triggered'}
                </div>
                {analyzeResult?.policy?.reason && (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
                    {analyzeResult.policy.reason}
                  </div>
                )}
              </div>

              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
                The AI model does NOT have unrestricted access to execute monetary recovery without passing this gate.
              </div>
            </div>

            <InfoRow label="Rule Evaluated" value={analyzeResult?.policy?.blocking_rule || 'All rules passed'} mono />
            <InfoRow label="Autonomous Execution Threshold" value="≤ ₹50,000" mono />
            <InfoRow label="Execution Status" value={policyDecision === 'approved' ? 'Allowed' : 'Not permitted'} />
          </div>

          {/* Execution & Outcome */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Sandbox Execution &amp; Outcome</span>
              <span className="connection-badge connected">SIMULATED</span>
            </div>

            <InfoRow label="Final Case Status" value={<span className={`badge ${statusBadgeClass(c.status)}`}>{statusLabel(c.status)}</span>} />
            <InfoRow label="Recovered Amount" value={<strong style={{ color: c.recovered_amount > 0 ? 'var(--success)' : 'var(--text-primary)' }}>{inr(c.recovered_amount)}</strong>} mono />
            <InfoRow
              label="Simulated Reference"
              value={
                recovery_actions.length > 0 && recovery_actions[0].razorpay_reference ? (
                  <span className="mono">{recovery_actions[0].razorpay_reference}</span>
                ) : (
                  <span className="mono" style={{ color: 'var(--text-tertiary)' }}>rzp_sim_none</span>
                )
              }
            />
            <InfoRow label="Opened At" value={shortDateTime(c.opened_at)} mono />
            <InfoRow label="Closed At" value={c.closed_at ? shortDateTime(c.closed_at) : 'Still active'} mono />
          </div>
        </div>
      )}

      {/* DECISION TRACE TAB */}
      {activeTab === 'trace' && analyzeResult && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Decision Trace Timeline</span>
            <span className="connection-badge connected">LIVE AGENT STEPS</span>
          </div>
          <DecisionTrace result={analyzeResult} />
        </div>
      )}

      {/* AUDIT TRAIL TAB */}
      {activeTab === 'audit' && (
        <div className="card">
          <div className="card-header">
            <div>
              <span className="card-title">Immutable Audit Trail</span>
              <div className="section-subtitle">Append-only audit events ({audit_events.length} events)</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px' }}>
            {audit_events.map((evt) => (
              <div
                key={evt.id}
                style={{
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-subtle)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{evt.event}</div>
                  <div className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{shortDateTime(evt.timestamp)}</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                  Actor: <strong style={{ color: 'var(--text-primary)' }}>{evt.actor}</strong> · Entity: <span className="mono">{evt.entity_type}:{evt.entity_id}</span>
                </div>
                {Object.keys(evt.metadata).length > 0 && (
                  <div className="mono-tag" style={{ marginTop: 6, display: 'inline-block', wordBreak: 'break-all' }}>
                    {JSON.stringify(evt.metadata)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
