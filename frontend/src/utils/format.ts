/** Utility helpers for formatting and display */

export function inr(amount: number): string {
  return `₹${amount.toLocaleString("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`
}

export function pct(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

export function probLabel(prob: number): "HIGH" | "MEDIUM" | "LOW" {
  if (prob >= 0.75) return "HIGH"
  if (prob >= 0.60) return "MEDIUM"
  return "LOW"
}

export function probClass(prob: number): string {
  if (prob >= 0.75) return "high"
  if (prob >= 0.60) return "medium"
  return "low"
}

export function statusBadgeClass(status: string): string {
  switch (status?.toLowerCase()) {
    case "recovered": return "badge-success"
    case "approved":  return "badge-success"
    case "blocked":   return "badge-danger"
    case "rejected":  return "badge-danger"
    case "failed":    return "badge-danger"
    case "requires_human":
    case "in_progress": return "badge-warning"
    default:          return "badge-info"
  }
}

export function statusLabel(status: string): string {
  switch (status?.toLowerCase()) {
    case "recovered":      return "Recovered"
    case "blocked":        return "Blocked"
    case "rejected":       return "Rejected"
    case "failed":         return "Failed"
    case "in_progress":    return "In Progress"
    case "requires_human": return "Needs Approval"
    case "open":           return "Open"
    default: return status
  }
}

export function actionLabel(action: string): string {
  const map: Record<string, string> = {
    RETRY_PAYMENT:          "Retry Payment",
    SEND_PAYMENT_LINK:      "Send Payment Link",
    SUGGEST_ALTERNATE_METHOD: "Suggest Alternate Method",
    SEND_REMINDER:          "Send Reminder",
    OFFER_INCENTIVE:        "Offer Incentive",
    ESCALATE_TO_HUMAN:      "Escalate to Human",
    MARK_UNRECOVERABLE:     "Mark Unrecoverable",
    NO_ACTION:              "No Action",
  }
  return map[action] || action
}

export function rcaLabel(rootCause: string): string {
  const map: Record<string, string> = {
    network_timeout:      "Network Timeout",
    transient_bank_error: "Transient Bank Error",
    insufficient_funds:   "Insufficient Funds",
    user_abandoned:       "User Abandoned",
    bank_blocked:         "Bank Blocked",
    low_success_history:  "Low Success History",
    unknown:              "Unknown",
  }
  return map[rootCause] || rootCause
}

export function shortDate(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  })
}

export function shortDateTime(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins  = Math.floor(diff / 60_000)
  const hours = Math.floor(diff / 3_600_000)
  const days  = Math.floor(diff / 86_400_000)
  if (mins < 1)  return "just now"
  if (mins < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}
