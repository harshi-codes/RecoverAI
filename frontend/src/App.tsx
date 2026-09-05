import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import RecoveryQueue from './pages/RecoveryQueue'
import CaseDetail from './pages/CaseDetail'
import PolicySafety from './pages/PolicySafety'
import ModelInfo from './pages/ModelInfo'
import { api } from './api/client'

function Sidebar({ connectionStatus }: { connectionStatus: 'connected' | 'connecting' | 'offline' }) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `nav-item${isActive ? ' active' : ''}`

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="sidebar-header">
          <div className="sidebar-brand-name">
            <span>RECOVER</span>
            <span style={{ color: 'var(--accent)' }}>AI</span>
          </div>
          <div className="sidebar-brand-sub">Revenue Recovery</div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Overview</div>
          <NavLink to="/" end className={linkClass}>
            <span className="nav-icon">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="7" height="7" rx="1.5" />
                <rect x="14" y="3" width="7" height="7" rx="1.5" />
                <rect x="14" y="14" width="7" height="7" rx="1.5" />
                <rect x="3" y="14" width="7" height="7" rx="1.5" />
              </svg>
            </span>
            Overview
          </NavLink>
          <NavLink to="/queue" className={linkClass}>
            <span className="nav-icon">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <line x1="4" y1="6" x2="20" y2="6" />
                <line x1="4" y1="12" x2="20" y2="12" />
                <line x1="4" y1="18" x2="20" y2="18" />
              </svg>
            </span>
            Recovery Queue
          </NavLink>

          <div className="nav-section-label" style={{ marginTop: '16px' }}>Control</div>
          <NavLink to="/policy" className={linkClass}>
            <span className="nav-icon">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </span>
            Policy &amp; Safety
          </NavLink>
          <NavLink to="/model" className={linkClass}>
            <span className="nav-icon">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </span>
            Model
          </NavLink>
        </nav>
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-system-label">System Status</div>
        <div className="sidebar-status-row">
          <span
            className={`status-dot ${
              connectionStatus === 'connected' ? 'green' : connectionStatus === 'connecting' ? 'amber' : 'red'
            }`}
          />
          <span>
            {connectionStatus === 'connected'
              ? 'Sandbox connected'
              : connectionStatus === 'connecting'
              ? 'Connecting...'
              : 'Offline'}
          </span>
        </div>
      </div>
    </aside>
  )
}

function Topbar({ connectionStatus }: { connectionStatus: 'connected' | 'connecting' | 'offline' }) {
  const navigate = useNavigate()
  const location = useLocation()

  const getPageTitle = (path: string) => {
    if (path === '/') return 'Overview'
    if (path === '/queue') return 'Recovery Queue'
    if (path.startsWith('/cases/')) return 'Case Detail'
    if (path === '/policy') return 'Policy & Safety'
    if (path === '/model') return 'Model'
    return 'Revenue Recovery'
  }

  return (
    <header className="topbar">
      <div className="topbar-left">
        <NavLink to="/" className="topbar-brand">
          <div className="topbar-logo-mark">R</div>
          <span className="topbar-brand-title">
            Recover<span className="topbar-brand-ai">AI</span>
          </span>
        </NavLink>
        <div className="topbar-divider" />
        <div className="topbar-breadcrumb">
          <span>RecoverAI</span>
          <span style={{ color: 'var(--text-tertiary)' }}>/</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{getPageTitle(location.pathname)}</span>
        </div>
      </div>

      <div className="topbar-right">
        <div className={`connection-badge ${connectionStatus}`}>
          <span
            className={`status-dot ${
              connectionStatus === 'connected' ? 'green' : connectionStatus === 'connecting' ? 'amber' : 'red'
            }`}
          />
          <span>
            {connectionStatus === 'connected'
              ? 'SANDBOX CONNECTED'
              : connectionStatus === 'connecting'
              ? 'CONNECTING'
              : 'OFFLINE'}
          </span>
        </div>

        <button
          id="topbar-run-demo-btn"
          className="btn btn-primary btn-sm"
          onClick={() => navigate('/')}
        >
          <span>Run Demo</span>
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </header>
  )
}

export default function App() {
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'connecting' | 'offline'>('connecting')

  useEffect(() => {
    let isMounted = true
    const checkHealth = async () => {
      try {
        await api.health()
        if (isMounted) setConnectionStatus('connected')
      } catch {
        if (isMounted) setConnectionStatus('offline')
      }
    }

    checkHealth()
    const interval = setInterval(checkHealth, 10000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  return (
    <BrowserRouter>
      <div className="app-shell">
        <Topbar connectionStatus={connectionStatus} />
        <Sidebar connectionStatus={connectionStatus} />
        <main className="main-content">
          <div className="content-container">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/queue" element={<RecoveryQueue />} />
              <Route path="/cases/:caseId" element={<CaseDetail />} />
              <Route path="/policy" element={<PolicySafety />} />
              <Route path="/model" element={<ModelInfo />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
