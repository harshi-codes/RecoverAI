/**
 * RecoverAI — Typed API Client
 * All communication with FastAPI backend.
 */

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retries = 3
): Promise<T> {
  let attempt = 0;
  while (attempt < retries) {
    try {
      const res = await fetch(`${BASE_URL}${path}`, {
        headers: { "Content-Type": "application/json", ...options.headers },
        ...options,
      });

      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          msg = body.detail || body.message || msg;
        } catch {}

        if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) {
          throw new ApiError(res.status, msg);
        }
        attempt++;
        if (attempt >= retries) throw new ApiError(res.status, msg);
        await new Promise((r) => setTimeout(r, 300 * attempt));
        continue;
      }

      return await res.json();
    } catch (err: any) {
      if (err instanceof ApiError) throw err;
      attempt++;
      if (attempt >= retries) {
        throw new ApiError(0, err.message || "Unable to connect to RecoverAI backend");
      }
      await new Promise((r) => setTimeout(r, 300 * attempt));
    }
  }
  throw new ApiError(0, "Unable to connect to RecoverAI backend");
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface Policy {
  allowed: boolean;
  outcome: "approved" | "blocked" | "requires_human";
  requires_human_approval: boolean;
  reason: string;
  blocking_rule: string | null;
}

export interface Execution {
  action_id: string | null;
  action_type: string;
  status: string;
  simulated: boolean;
  message: string;
}

export interface Outcome {
  status: string;
  recovered_amount: number;
}

export interface AuditEvent {
  id: string;
  entity_type: string;
  entity_id: string;
  event: string;
  actor: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface FeatureImportance {
  feature: string;
  importance: number;
  value?: number;
}

export interface AnalyzeResult {
  payment_id: string;
  case_id: string;
  amount: number;
  currency: string;
  customer_name: string;
  payment_method: string;
  failure_code: string;
  recovery_probability: number;
  risk_category: "HIGH" | "MEDIUM" | "LOW";
  feature_importances: FeatureImportance[];
  root_cause: string;
  rca_severity: string;
  rca_explanation: string;
  rca_auto_recoverable: boolean;
  recommended_action: string;
  decision_rationale: string;
  decision_confidence: number;
  policy: Policy;
  execution: Execution;
  outcome: Outcome;
  audit_events: AuditEvent[];
  idempotent: boolean;
  sandbox: boolean;
}

export interface Stats {
  revenue_at_risk: number;
  recoverable_revenue: number;
  recovered_revenue: number;
  recovery_rate: number;
  total_cases: number;
  recovered_cases: number;
  blocked_cases: number;
  failed_cases: number;
  in_progress_cases: number;
  human_approval_required: number;
  total_actions_executed: number;
  failure_breakdown: Array<{ failure_code: string; count: number; total_amount: number }>;
  metric_definitions: Record<string, string>;
}

export interface CaseRow {
  case_id: string;
  payment_id: string;
  status: string;
  amount: number;
  currency: string;
  revenue_at_risk: number;
  recovered_amount: number;
  recovery_probability: number;
  root_cause: string | null;
  selected_action: string | null;
  policy_decision: string | null;
  failure_code: string;
  payment_method: string;
  customer_name: string;
  customer_email: string;
  opened_at: string;
  closed_at: string | null;
}

export interface CasesResponse {
  batch_summary: {
    total_at_risk: number;
    recoverable: number;
    actionable: number;
    recovered: number;
  };
  cases: CaseRow[];
  pagination: { limit: number; offset: number; returned: number };
}

export interface CaseDetail {
  case: {
    case_id: string;
    payment_id: string;
    status: string;
    revenue_at_risk: number;
    recovered_amount: number;
    recovery_probability: number;
    root_cause: string | null;
    selected_action: string | null;
    policy_decision: string | null;
    opened_at: string;
    closed_at: string | null;
  };
  payment: {
    id: string;
    amount: number;
    currency: string;
    payment_method: string;
    failure_code: string;
    failure_reason: string | null;
    retry_count: number;
    checkout_duration_sec: number | null;
    is_subscription: boolean;
    status: string;
  };
  customer: {
    id: string;
    name: string;
    email: string;
    lifetime_value: number;
    previous_success_rate: number;
    contact_count: number;
    opted_out: boolean;
  };
  model_info: {
    version: string;
    algorithm: string;
    roc_auc: number;
  };
  agent_decisions: Array<{
    agent_name: string;
    step_index: number;
    reasoning: string;
    output: Record<string, unknown>;
    confidence: number;
    duration_ms: number;
    timestamp: string;
  }>;
  recovery_actions: Array<{
    id: string;
    action_type: string;
    parameters: Record<string, unknown>;
    executed_at: string;
    result: string;
    razorpay_reference: string | null;
    simulated: boolean;
  }>;
  audit_events: AuditEvent[];
  sandbox: boolean;
}

export interface ModelInfo {
  model_version: string;
  algorithm: string;
  roc_auc: number;
  precision: number;
  recall: number;
  accuracy: number;
  training_samples: number;
  test_samples: number;
  positive_rate: number;
  n_features: number;
  feature_importances: FeatureImportance[];
  trained_at: string;
}

// ── API Functions ─────────────────────────────────────────────────────────────

export const api = {
  health: () => request<{ status: string; ml_model_loaded: boolean }>("/health"),

  analyzePayment: (paymentId: string) =>
    request<AnalyzeResult>(`/api/v1/recovery/analyze/${paymentId}`, { method: "POST" }),

  getStats: () => request<Stats>("/api/v1/recovery/stats"),

  getCases: (params?: {
    limit?: number;
    offset?: number;
    status?: string;
    min_prob?: number;
    max_prob?: number;
    failure_code?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.status) qs.set("status", params.status);
    if (params?.min_prob != null) qs.set("min_prob", String(params.min_prob));
    if (params?.max_prob != null) qs.set("max_prob", String(params.max_prob));
    if (params?.failure_code) qs.set("failure_code", params.failure_code);
    return request<CasesResponse>(`/api/v1/recovery/cases?${qs}`);
  },

  getCase: (caseId: string) =>
    request<CaseDetail>(`/api/v1/recovery/cases/${caseId}`),

  approveCase: (caseId: string) =>
    request<{ outcome: string; recovered_amount: number }>(
      `/api/v1/recovery/cases/${caseId}/approve`,
      { method: "POST" }
    ),

  rejectCase: (caseId: string) =>
    request<{ outcome: string }>(
      `/api/v1/recovery/cases/${caseId}/reject`,
      { method: "POST" }
    ),

  demoReset: () =>
    request<{ reset: boolean; deleted: Record<string, number> }>(
      "/api/v1/demo/reset",
      { method: "POST" }
    ),

  getModelInfo: () =>
    request<ModelInfo>("/api/v1/ml/model-info"),
};
