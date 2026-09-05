/**
 * ModelInfo — Recovery Intelligence Model Card.
 * Razorpay-Quality ML Specifications.
 */

import { useEffect, useState } from 'react'
import { api, type ModelInfo as ModelInfoType } from '../api/client'

export default function ModelInfo() {
  const [model, setModel]     = useState<ModelInfoType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    api.getModelInfo()
      .then(r => setModel(r))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center' }}>
        <div className="spinner" style={{ margin: '0 auto 12px auto', width: 24, height: 24, borderColor: '#cbd5e1', borderTopColor: '#0052ff' }} />
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading model parameters...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger-border)', backgroundColor: 'var(--danger-bg)', padding: '24px' }}>
        <div style={{ color: 'var(--danger-text)', fontWeight: 700 }}>Error loading model info</div>
        <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>{error}</div>
      </div>
    )
  }

  if (!model) return null

  const maxImportance = Math.max(...model.feature_importances.map(f => f.importance), 0.001)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-title-area">
          <h1 className="page-title">Recovery Intelligence</h1>
          <p className="page-subtitle">
            {model.algorithm} · Predicts recovery probability for failed payments.
          </p>
        </div>
        <span className="mono-tag">v{model.model_version}</span>
      </div>

      {/* Trust Message Note & Boundary Diagram */}
      <div
        style={{
          padding: '16px 20px',
          backgroundColor: 'var(--accent-subtle)',
          border: '1px solid var(--accent-border)',
          borderRadius: 'var(--radius-xl)',
          fontSize: '13px',
          color: 'var(--accent)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ fontSize: '18px' }}>ℹ</div>
          <div>
            <strong>System Boundary Note:</strong> The model estimates recoverability. Deterministic policy controls whether an action can execute.
          </div>
        </div>

        <div className="mono" style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.04em' }}>
          MODEL → DECISION → POLICY
        </div>
      </div>

      {/* Top Key Metrics Row */}
      <div className="grid-4">
        <div className="card">
          <div className="section-subtitle" style={{ fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>ROC-AUC Score</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--accent)', marginTop: 4, letterSpacing: '-0.03em' }}>{model.roc_auc.toFixed(3)}</div>
          <div className="section-subtitle" style={{ marginTop: 2 }}>Area under ROC curve</div>
        </div>

        <div className="card">
          <div className="section-subtitle" style={{ fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Precision</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--success)', marginTop: 4, letterSpacing: '-0.03em' }}>{model.precision.toFixed(3)}</div>
          <div className="section-subtitle" style={{ marginTop: 2 }}>True positive ratio</div>
        </div>

        <div className="card">
          <div className="section-subtitle" style={{ fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Recall</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--warning-text)', marginTop: 4, letterSpacing: '-0.03em' }}>{model.recall.toFixed(3)}</div>
          <div className="section-subtitle" style={{ marginTop: 2 }}>Sensitivity score</div>
        </div>

        <div className="card">
          <div className="section-subtitle" style={{ fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Dataset Size</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', marginTop: 4, letterSpacing: '-0.03em' }}>
            {(model.training_samples + model.test_samples).toLocaleString()}
          </div>
          <div className="section-subtitle" style={{ marginTop: 2 }}>9,600 Train / 2,400 Test split</div>
        </div>
      </div>

      {/* Architecture & Feature Importances */}
      <div className="grid-2">
        {/* Model Architecture Metadata */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="card-header">
              <span className="card-title">Model Specifications</span>
              <span className="mono-tag">{model.algorithm}</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Algorithm</span>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{model.algorithm}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Total Features</span>
                <span className="mono" style={{ fontWeight: 600 }}>{model.n_features} features</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Training Set</span>
                <span className="mono" style={{ fontWeight: 600 }}>{model.training_samples.toLocaleString()} (80%)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Test Set</span>
                <span className="mono" style={{ fontWeight: 600 }}>{model.test_samples.toLocaleString()} (20%)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Positive Target Rate</span>
                <span className="mono" style={{ fontWeight: 600 }}>{(model.positive_rate * 100).toFixed(1)}%</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Last Trained</span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                  {new Date(model.trained_at).toLocaleString('en-IN')}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Target Variable & Definition */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Target Variable Definition</span>
            <span className="mono-tag">Binary Outcome</span>
          </div>

          <div
            style={{
              padding: '18px',
              backgroundColor: 'var(--bg-subtle)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              lineHeight: 1.8,
              color: 'var(--text-secondary)'
            }}
          >
            <div style={{ color: 'var(--accent)', fontWeight: 700, marginBottom: '6px' }}>
              target: recovered_within_24h
            </div>
            <div>1 — Payment status = "captured"</div>
            <div>    AND recovery outcome = "recovered"</div>
            <div>    AND time to recovery &lt; 24h</div>
            <div style={{ marginTop: '8px', color: 'var(--text-tertiary)' }}>0 — Otherwise</div>
          </div>
        </div>
      </div>

      {/* Feature Importance Horizontal Bars */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Feature Importances</div>
            <div className="section-subtitle">Relative contribution of input features to model prediction</div>
          </div>
          <span className="mono-tag">{model.feature_importances.length} features evaluated</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '12px' }}>
          {model.feature_importances.map((f) => {
            const widthPct = (f.importance / maxImportance) * 100
            return (
              <div key={f.feature} style={{ display: 'grid', gridTemplateColumns: '220px 1fr 60px', alignItems: 'center', gap: '16px' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                  {f.feature.replace(/_/g, ' ')}
                </div>
                <div style={{ height: '8px', backgroundColor: 'var(--bg-subtle)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.max(2, widthPct)}%`,
                      height: '100%',
                      backgroundColor: 'var(--accent)'
                    }}
                  />
                </div>
                <div className="mono" style={{ fontSize: 12, textAlign: 'right', fontWeight: 700, color: 'var(--text-secondary)' }}>
                  {(f.importance * 100).toFixed(1)}%
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
