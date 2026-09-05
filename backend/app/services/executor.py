"""
RecoverAI – Simulated Recovery Executor.

Implements RecoveryExecutor interface in SANDBOX / DEMO mode.
No real money movement. No live Razorpay API calls.

All recovery_actions records written by this executor use:
  razorpay_reference = "rzp_sim_<uuid>"   ← never "pay_<id>" (live format)
  simulated = True

Future swap:
  Replace SimulatedRecoveryExecutor with RazorpaySandboxExecutor
  by changing the DI binding in pipeline.py.
"""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.decision import RecoveryAction
from app.services.executor_base import ExecutionResult, RecoveryExecutor


class SimulatedRecoveryExecutor(RecoveryExecutor):
    """
    Sandbox executor: simulates recovery actions using seeded DB outcomes.
    Uses the pre-seeded recovery_cases.status to determine simulated success.
    """

    @property
    def executor_name(self) -> str:
        return "SimulatedRecoveryExecutor"

    @property
    def is_simulated(self) -> bool:
        return True

    async def execute(
        self,
        *,
        db: AsyncSession,
        case_id:     str,
        payment_id:  str,
        action:      RecoveryAction,
        params:      dict,
        case_status: str,
    ) -> ExecutionResult:
        """
        Simulate executing a recovery action.

        Outcome logic (SANDBOX simulation):
        - RETRY_PAYMENT with high recovery probability → success (simulates network-error recovery)
        - SEND_PAYMENT_LINK / SEND_REMINDER → success 60% of the time (realistic baseline)
        - ESCALATE_TO_HUMAN / NO_ACTION → not a direct recovery action; outcome_success=False
        - case_status=='recovered' (pre-seeded/idempotent) → honour the seeded outcome
        """
        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Honour pre-seeded terminal status (idempotent path)
        if case_status == "recovered":
            outcome_success = True
        elif action in (RecoveryAction.RETRY_PAYMENT,):
            # High-recovery network-error cases → simulate the auto-retry succeeding
            outcome_success = True
        elif action in (RecoveryAction.SEND_PAYMENT_LINK, RecoveryAction.SEND_REMINDER,
                        RecoveryAction.SUGGEST_ALTERNATE_METHOD, RecoveryAction.OFFER_INCENTIVE):
            # Realistic: ~55% of manual-link actions convert
            import hashlib
            seed_val = int(hashlib.md5(payment_id.encode()).hexdigest(), 16) % 100
            outcome_success = seed_val < 55
        else:
            # ESCALATE_TO_HUMAN, NO_ACTION → not a final recovery step
            outcome_success = False

        razorpay_ref = f"rzp_sim_{uuid.uuid4().hex[:12]}" if outcome_success else None
        msg = _build_message(action, params, outcome_success)
        result_status = "success" if outcome_success else "failure"

        await db.execute(
            text("""
                INSERT INTO recovery_actions
                    (id, case_id, action_type, parameters, executed_at, result, razorpay_reference)
                VALUES
                    (:id, :case_id, :action_type, :parameters, :executed_at, :result, :razorpay_reference)
            """),
            {
                "id":                 action_id,
                "case_id":            case_id,
                "action_type":        action.value,
                "parameters":         json.dumps(params),
                "executed_at":        now,
                "result":             result_status,
                "razorpay_reference": razorpay_ref,
            },
        )

        return ExecutionResult(
            action_id=action_id,
            action_type=action.value,
            status="executed",
            simulated=True,
            razorpay_reference=razorpay_ref,
            outcome_success=outcome_success,
            message=msg,
        )



# ── Helper ────────────────────────────────────────────────────────────────────
def _build_message(action: RecoveryAction, params: dict, success: bool) -> str:
    status_str = "succeeded" if success else "did not result in recovery"
    channel = params.get("channel", "email")

    messages = {
        RecoveryAction.RETRY_PAYMENT:
            f"Auto-retry payment initiated (delay: {params.get('delay_minutes', 5)} min). {status_str.capitalize()}.",
        RecoveryAction.SEND_PAYMENT_LINK:
            f"Payment link sent via {channel}. Customer action {status_str}.",
        RecoveryAction.SUGGEST_ALTERNATE_METHOD:
            f"Alternate payment methods suggested via {channel}. Customer {status_str}.",
        RecoveryAction.SEND_REMINDER:
            f"Payment reminder sent via {channel}. Customer {status_str}.",
        RecoveryAction.OFFER_INCENTIVE:
            f"{params.get('discount_percent', 5)}% discount offered via {channel}. Customer {status_str}.",
        RecoveryAction.ESCALATE_TO_HUMAN:
            f"Case escalated to merchant ops team (priority: {params.get('priority', 'normal')}). {status_str.capitalize()}.",
        RecoveryAction.NO_ACTION:
            "No action taken (below recovery threshold).",
    }
    return messages.get(action, f"Action {action.value} executed. {status_str.capitalize()}.")


# ── Module-level singleton (pipeline uses this) ───────────────────────────────
_default_executor = SimulatedRecoveryExecutor()


def get_executor() -> RecoveryExecutor:
    """
    Returns the active executor instance.
    Swap this to RazorpaySandboxExecutor() for Razorpay test-mode integration.
    """
    return _default_executor
