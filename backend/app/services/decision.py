"""
RecoverAI – Recovery Decision Engine.

DETERMINISTIC: a structured decision tree selects the recovery action.
No LLM involvement. Logic is testable and auditable.

Action taxonomy (from implementation plan):
  RETRY_PAYMENT          – auto-retry via payment processor
  SEND_PAYMENT_LINK      – send fresh checkout link to customer
  SUGGEST_ALTERNATE_METHOD – ask customer to use UPI/wallet/etc.
  SEND_REMINDER          – reminder email/SMS to complete payment
  OFFER_INCENTIVE        – discount or cashback to motivate retry
  ESCALATE_TO_HUMAN      – flag for merchant/ops team review
  NO_ACTION              – do nothing (probability too low or opt-out)
"""
from dataclasses import dataclass
from enum import Enum

from app.services.rca import RootCause, Severity


class RecoveryAction(str, Enum):
    RETRY_PAYMENT           = "RETRY_PAYMENT"
    SEND_PAYMENT_LINK       = "SEND_PAYMENT_LINK"
    SUGGEST_ALTERNATE_METHOD = "SUGGEST_ALTERNATE_METHOD"
    SEND_REMINDER           = "SEND_REMINDER"
    OFFER_INCENTIVE         = "OFFER_INCENTIVE"
    ESCALATE_TO_HUMAN       = "ESCALATE_TO_HUMAN"
    NO_ACTION               = "NO_ACTION"


@dataclass(frozen=True)
class DecisionResult:
    action:     RecoveryAction
    rationale:  str
    params:     dict          # e.g. {"discount_percent": 5, "channel": "email"}
    confidence: float         # 0–1, how confident we are in this action


# ── Thresholds (from implementation plan) ────────────────────────────────────
PROB_HIGH    = 0.75   # AUTO_RETRY / link-send
PROB_MEDIUM  = 0.60   # send reminder, suggest alternate
PROB_LOW     = 0.40   # soft incentive
# below PROB_LOW → NO_ACTION or human escalation


def decide_recovery_action(
    recovery_probability: float,
    root_cause: RootCause,
    retry_count: int,
    amount: float,
    is_subscription: bool,
    time_since_failure_hours: float,
    customer_lifetime_value: float,
    contact_count: int,
) -> DecisionResult:
    """
    Deterministic decision tree.

    Priority order:
    1. Safety short-circuits (already exceeded contact limits handled by policy; checked here for decision quality)
    2. Root-cause × probability combinations
    3. Amount / LTV tier
    4. Fallback
    """
    p = recovery_probability

    # ── 1. Too many retries / low probability → escalate or no-action ─────────
    if p < PROB_LOW:
        if customer_lifetime_value > 50_000:
            return DecisionResult(
                action=RecoveryAction.ESCALATE_TO_HUMAN,
                rationale=(
                    f"Recovery probability {p:.0%} is low but customer LTV ₹{customer_lifetime_value:,.0f} "
                    "is high. Escalating for personalised merchant outreach."
                ),
                params={"priority": "high"},
                confidence=0.80,
            )
        return DecisionResult(
            action=RecoveryAction.NO_ACTION,
            rationale=(
                f"Recovery probability {p:.0%} is below threshold ({PROB_LOW:.0%}). "
                "Automated intervention is unlikely to be cost-effective."
            ),
            params={},
            confidence=0.90,
        )

    # ── 2. Root-cause specific logic ──────────────────────────────────────────

    # Network timeout: safe to auto-retry immediately if not already retried
    if root_cause == RootCause.NETWORK_TIMEOUT:
        if retry_count <= 1 and p >= PROB_MEDIUM:
            return DecisionResult(
                action=RecoveryAction.RETRY_PAYMENT,
                rationale=(
                    "Network/connectivity failure is transient. "
                    f"Recovery probability {p:.0%} and only {retry_count} prior retries — "
                    "safe to auto-retry."
                ),
                params={"delay_minutes": 5, "max_retries": 2},
                confidence=0.92,
            )

    # Expired card: customer must update payment method
    if root_cause == RootCause.EXPIRED_CARD:
        if p >= PROB_MEDIUM:
            return DecisionResult(
                action=RecoveryAction.SUGGEST_ALTERNATE_METHOD,
                rationale=(
                    "Card is expired — a new payment method is required. "
                    "Sending alternate payment options (UPI/netbanking/wallet)."
                ),
                params={"channel": "email", "methods": ["upi", "wallet", "netbanking"]},
                confidence=0.88,
            )

    # Insufficient funds: offer a modest discount or deferred payment link
    if root_cause == RootCause.INSUFFICIENT_FUNDS:
        if p >= PROB_HIGH and amount <= 10_000:
            return DecisionResult(
                action=RecoveryAction.OFFER_INCENTIVE,
                rationale=(
                    f"Insufficient funds with high recovery probability {p:.0%}. "
                    "Small discount may tip customer to complete payment."
                ),
                params={"discount_percent": 5, "channel": "sms"},
                confidence=0.75,
            )
        if p >= PROB_MEDIUM:
            return DecisionResult(
                action=RecoveryAction.SEND_PAYMENT_LINK,
                rationale=(
                    "Insufficient funds — sending a fresh payment link so customer can "
                    "retry when balance is available or use an alternate method."
                ),
                params={"channel": "email", "expiry_hours": 48},
                confidence=0.70,
            )

    # User drop / checkout abandonment
    if root_cause == RootCause.USER_DROP:
        if p >= PROB_MEDIUM:
            # Fresh abandonment → payment link; stale → reminder
            if time_since_failure_hours <= 6:
                return DecisionResult(
                    action=RecoveryAction.SEND_PAYMENT_LINK,
                    rationale=(
                        f"Customer abandoned checkout {time_since_failure_hours:.1f}h ago. "
                        "Sending a direct payment link while intent is still warm."
                    ),
                    params={"channel": "whatsapp", "expiry_hours": 24},
                    confidence=0.82,
                )
            return DecisionResult(
                action=RecoveryAction.SEND_REMINDER,
                rationale=(
                    f"Checkout abandoned {time_since_failure_hours:.0f}h ago. "
                    "Sending a payment reminder to re-engage the customer."
                ),
                params={"channel": "email", "include_cart": True},
                confidence=0.68,
            )

    # Bank block / generic decline: usually needs customer action with bank
    if root_cause in (RootCause.BANK_BLOCK, RootCause.ML_DECLINE):
        if p >= PROB_HIGH:
            return DecisionResult(
                action=RecoveryAction.SUGGEST_ALTERNATE_METHOD,
                rationale=(
                    f"{root_cause.value} with high recovery probability {p:.0%}. "
                    "Suggesting alternate payment method to bypass the block."
                ),
                params={"channel": "email", "methods": ["upi", "wallet"]},
                confidence=0.78,
            )
        if p >= PROB_MEDIUM:
            if is_subscription:
                return DecisionResult(
                    action=RecoveryAction.SEND_PAYMENT_LINK,
                    rationale=(
                        "Subscription payment declined. Sending a dedicated link to "
                        "update payment details and maintain service continuity."
                    ),
                    params={"channel": "email", "type": "subscription_recovery"},
                    confidence=0.72,
                )
            return DecisionResult(
                action=RecoveryAction.SEND_REMINDER,
                rationale=(
                    f"Decline with moderate probability {p:.0%}. "
                    "Sending a soft reminder to try again."
                ),
                params={"channel": "email"},
                confidence=0.60,
            )

    # ── 3. High-value payment: escalate for VIP treatment ────────────────────
    if amount > 25_000 and p >= PROB_MEDIUM:
        return DecisionResult(
            action=RecoveryAction.ESCALATE_TO_HUMAN,
            rationale=(
                f"High-value payment ₹{amount:,.0f} with probability {p:.0%}. "
                "Routing to merchant ops for personalised recovery."
            ),
            params={"priority": "high", "sla_hours": 4},
            confidence=0.85,
        )

    # ── 4. General medium-probability fallback ────────────────────────────────
    if p >= PROB_MEDIUM:
        return DecisionResult(
            action=RecoveryAction.SEND_REMINDER,
            rationale=(
                f"Moderate recovery probability {p:.0%}. "
                "Sending a payment reminder as the safest default action."
            ),
            params={"channel": "email"},
            confidence=0.65,
        )

    # ── 5. Low-medium probability → no-action ────────────────────────────────
    return DecisionResult(
        action=RecoveryAction.NO_ACTION,
        rationale=(
            f"Recovery probability {p:.0%} does not meet the minimum threshold "
            "for automated intervention."
        ),
        params={},
        confidence=0.70,
    )


def decision_to_dict(result: DecisionResult) -> dict:
    return {
        "action":     result.action.value,
        "rationale":  result.rationale,
        "params":     result.params,
        "confidence": result.confidence,
    }
