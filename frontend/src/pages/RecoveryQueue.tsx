/**
 * RecoveryQueue — Prioritized failed payments ranked by expected recovery opportunity.
 * Razorpay-Quality Fintech Operations Table.
 */

import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type CaseRow, type CasesResponse } from '../api/client'
import { inr, statusBadgeClass, statusLabel } from '../utils/format'

const FILTER_OPTIONS = [
  { value: '', label: 'All Cases' },
  { value: 'in_progress', label: 'Actionable / Pending' },
  { value: 'recovered', label: 'Recovered' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'failed', label: 'Failed' },
]

export default function RecoveryQueue() {
  const [data, setData]           = useState<CasesResponse | null>(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [analyzingId, setAnalyzingId]   = useState<string | null>(null)
  const [offset, setOffset]       = useState(0)
  const LIMIT = 25
  const navigate = useNavigate()

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getCases({ limit: LIMIT, offset, status: statusFilter || undefined })
      setData(res)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [offset, statusFilter])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleAnalyze = async (paymentId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setAnalyzingId(paymentId)
    try {
      const result = await api.analyzePayment(paymentId)
      navigate(`/cases/${result.case_id}`)
    } catch (err: any) {
      alert(`Analysis error: ${err.message}`)
    } finally {
      setAnalyzingId(null)
    }
  }

  const handleRowClick = (caseId: string) => navigate(`/cases/${caseId}`)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-title-area">
          <h1 className="page-title">Recovery Queue</h1>
          <p className="page-subtitle">
            Prioritized by expected recovery opportunity across all payment failures.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadData}>
          ↻ Refresh Queue
        </button>
      </div>

      {/* Summary Metric Header Strip */}
      {data && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '16px',
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-xl)',
            padding: '16px 24px',
            boxShadow: 'var(--shadow-xs)'
          }}
        >
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Revenue at Risk
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-primary)', marginTop: 4 }}>
              {inr(data.batch_summary.total_at_risk)}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Recoverable Opportunity
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--warning-text)', marginTop: 4 }}>
              {inr(data.batch_summary.recoverable)}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Actionable Opportunities
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--accent)', marginTop: 4 }}>
              {inr(data.batch_summary.actionable)}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Recovered Revenue
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--success)', marginTop: 4 }}>
              {inr(data.batch_summary.recovered)}
            </div>
          </div>
        </div>
      )}

      {/* Segmented Controls / Filter Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '6px', backgroundColor: 'var(--bg-subtle)', padding: '4px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
          {FILTER_OPTIONS.map((f) => (
            <button
              key={f.value}
              onClick={() => {
                setStatusFilter(f.value)
                setOffset(0)
              }}
              style={{
                padding: '6px 14px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12px',
                fontWeight: statusFilter === f.value ? 700 : 500,
                border: 'none',
                backgroundColor: statusFilter === f.value ? 'var(--surface)' : 'transparent',
                color: statusFilter === f.value ? 'var(--text-primary)' : 'var(--text-secondary)',
                boxShadow: statusFilter === f.value ? 'var(--shadow-xs)' : 'none',
                cursor: 'pointer'
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        {data && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Showing {offset + 1}–{offset + data.pagination.returned} cases
          </span>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="card" style={{ borderColor: 'var(--danger-border)', backgroundColor: 'var(--danger-bg)' }}>
          <div style={{ color: 'var(--danger-text)', fontWeight: 700 }}>Error loading queue</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>{error}</div>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ padding: '60px 0', textAlign: 'center' }}>
          <div className="spinner" style={{ margin: '0 auto 12px auto', width: 24, height: 24, borderColor: '#cbd5e1', borderTopColor: '#0052ff' }} />
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading recovery queue...</span>
        </div>
      )}

      {/* Queue Data Table */}
      {!loading && data && (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Payment / Customer</th>
                <th>Amount</th>
                <th>Failure</th>
                <th>Recoverability</th>
                <th>Recommended Action</th>
                <th>Policy</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.cases.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                    <div>No recovery cases match the selected filter.</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>Run the RecoverAI demo to populate the recovery queue.</div>
                  </td>
                </tr>
              ) : (
                data.cases.map((c: CaseRow) => {
                  const pct = Math.round(c.recovery_probability * 100)
                  const isHighOpportunity = c.amount >= 50000 || c.recovery_probability >= 0.85

                  return (
                    <tr
                      key={c.case_id}
                      onClick={() => handleRowClick(c.case_id)}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: isHighOpportunity ? 'rgba(0, 82, 255, 0.02)' : undefined
                      }}
                    >
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{c.customer_name}</div>
                        <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                          {c.payment_id}
                        </div>
                      </td>

                      <td style={{ fontWeight: 800, color: 'var(--text-primary)' }}>
                        {inr(c.amount)}
                      </td>

                      <td>
                        <span className="mono-tag">{c.failure_code}</span>
                      </td>

                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div style={{ flex: 1, height: '6px', backgroundColor: 'var(--bg-subtle)', borderRadius: '3px', overflow: 'hidden', minWidth: '60px' }}>
                            <div
                              style={{
                                width: `${pct}%`,
                                height: '100%',
                                backgroundColor: pct >= 75 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)'
                              }}
                            />
                          </div>
                          <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
                            {(c.recovery_probability * 100).toFixed(1)}%
                          </span>
                        </div>
                      </td>

                      <td style={{ color: 'var(--text-secondary)' }}>
                        {c.selected_action ? (
                          <span style={{ fontWeight: 600, color: 'var(--accent)' }}>{c.selected_action.replace(/_/g, ' ')}</span>
                        ) : (
                          <span style={{ color: 'var(--text-tertiary)' }}>—</span>
                        )}
                      </td>

                      <td>
                        {c.policy_decision ? (
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              color: c.policy_decision === 'approved' ? 'var(--success)' : c.policy_decision === 'requires_human' ? 'var(--warning-text)' : 'var(--danger-text)'
                            }}
                          >
                            {c.policy_decision}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-tertiary)' }}>—</span>
                        )}
                      </td>

                      <td>
                        <span className={`badge ${statusBadgeClass(c.policy_decision || c.status)}`}>
                          {statusLabel(c.policy_decision === 'requires_human' ? 'requires_human' : c.status)}
                        </span>
                      </td>

                      <td style={{ textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={(e) => handleAnalyze(c.payment_id, e)}
                          disabled={analyzingId === c.payment_id}
                          title="Run full recovery pipeline"
                        >
                          {analyzingId === c.payment_id ? (
                            <span className="spinner" style={{ width: 12, height: 12 }} />
                          ) : (
                            'Analyze →'
                          )}
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination Footer */}
      {data && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Showing {offset + 1}–{offset + data.pagination.returned} cases
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            >
              ← Previous
            </button>
            <button
              className="btn btn-secondary btn-sm"
              disabled={data.pagination.returned < LIMIT}
              onClick={() => setOffset(offset + LIMIT)}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
