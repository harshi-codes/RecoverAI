# RecoverAI — Demo Script (Judge Walkthrough)

**Duration:** 4–5 minutes  
**Purpose:** Demonstrate RecoverAI's full revenue recovery intelligence workflow to judges.

---

## Pre-Demo Setup

Start services (two terminal tabs):

```bash
# Tab 1 — Backend
cd raz/backend
uvicorn app.main:app --reload

# Tab 2 — Frontend
cd raz/frontend
npm run dev
```

Open browser to: **http://localhost:5173**

---

## Step 1 — Dashboard Overview (45 sec)

**What to show:**
- Point out **Revenue at Risk**, **Recoverable Revenue**, **Recovery Rate** — all calculated from real DB aggregates, not hardcoded.
- Show the **Revenue Funnel** bar chart (At Risk → Recoverable → Recovered).
- Show the **Failure Code Breakdown** table.
- Point out the **SANDBOX · NO REAL MONEY** badge in the top bar.

**Say:** *"RecoverAI calculates real metrics from your payment database. Every number here is a live SQL aggregate."*

---

## Step 2 — Run RecoverAI Demo (30 sec)

Click the **"▶ Run RecoverAI Demo"** button.

Watch the demo log as it:
1. Resets all 6 demo scenarios (clears previous runs)
2. Processes all 6 payments through the full pipeline
3. Refreshes dashboard metrics

**Say:** *"This runs the complete agentic workflow — ML scoring, RCA, decision engine, policy guard, execution — for six different scenarios."*

After it finishes, point to the **Recent Recovery Cases** table which now shows all 6 with their policy outcomes.

---

## Step 3 — Hero Case: Successful Recovery (60 sec)

Click **"A — Network Error ₹8,499"** from the Recent Cases or Demo Reference.

This opens the **Case Detail** page. Walk through:

1. **ML Recovery Score ring** — 91% (HIGH). *"Our GradientBoostingClassifier, trained on real payment data, gives this an 91% recovery probability."*

2. **Feature Importances** — *"These are the model input signals. Note: customer success rate and amount are the top signals. We're showing you what the model used — we never make causal claims from these."*

3. **Root Cause Analysis** — `network_timeout`, AUTO-RECOVERABLE. *"Deterministic rule engine — not an LLM — maps the failure code to a recoverable network error."*

4. **Recovery Decision** — RETRY_PAYMENT. *"Rule engine selects the action based on root cause + ML signal."*

5. **Policy Guard** — `approved`. *"All six safety rules passed. No policy violation."*

6. **Execution** — RETRY_PAYMENT executed. `rzp_sim_*` reference. *"SANDBOX — simulated, no real Razorpay call."*

7. **Outcome** — `recovered`, **₹8,499** recovered.

8. Click **Decision Trace** tab — show the 8-step animated workflow timeline.

---

## Step 4 — Human Approval Case: ₹75,000 (60 sec)

Go back. Click **"C — High Value ₹75,000"**.

**Show:**
- **Orange ⚠ Human Approval Required banner** at top.
- ML probability: ~89% (HIGH) — the model is confident.
- Policy Guard shows `requires_human` / `high_amount`.
- *"RecoverAI never auto-executes actions above ₹50,000 — even if the model is confident. A human must approve."*

Click **"✓ Approve Recovery"**.

Watch the case refresh automatically — policy transitions to `approved`, action executes, outcome becomes `recovered`, amount changes to ₹75,000.

*"After approval, the workflow resumes from exactly where it was paused."*

---

## Step 5 — Policy Safety Cases (45 sec)

Navigate to **Policy & Safety** in the sidebar.

Click **"▶ Run"** for each blocked scenario to get live results:

| Scenario | Block Reason |
|---|---|
| B — Low Prob ₹1,299 | `low_probability` — ML says 3.3% |
| D — Contact Limit ₹2,999 | `contact_limit` — customer contacted 5× already |
| E — Opted Out ₹4,599 | `opted_out` — hard block, cannot be overridden |
| F — Already Captured ₹6,299 | `payment_succeeded` — no duplicate charge |

*"These are deterministic rules, not LLM guardrails. They evaluate in order. First match wins."*

---

## Step 6 — Model Info (30 sec)

Navigate to **Model Info** in the sidebar.

Show:
- **Algorithm**: GradientBoostingClassifier
- **ROC-AUC**: 0.857 (from actual training run)
- **Precision / Recall**: 0.704 / 0.461
- **Training samples**, feature count
- **Feature Importance** bar chart

*"These numbers come directly from the model evaluation — not hardcoded. You can retrain the model and these update automatically."*

---

## Step 7 — Recovery Queue (30 sec)

Navigate to **Recovery Queue**.

Show:
- **Batch Summary** (At Risk / Recoverable / Actionable / Recovered)
- Filter by `blocked`, `recovered`, `in_progress`
- Click any row to jump to case detail

*"Merchants can triage their entire payment failure backlog here, sorted by recovery probability."*

---

## Summary Talking Points

1. **Real ML, not hardcoded probabilities.** Model trained on actual data. Probabilities vary by payment attributes.
2. **Deterministic safety.** Policy Guard is a rule engine — bounded, auditable, not an LLM.
3. **Immutable audit trail.** Every action is logged. No deletions. Fully traceable.
4. **Idempotent.** Safe to re-run. No duplicate recovery actions created.
5. **Sandbox.** All execution is simulated. `rzp_sim_*` references. No real money moved.
6. **No generic chatbot.** The LLM, if added, would only generate human-readable RCA explanations — it never decides what to do.
