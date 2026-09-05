"""
RecoverAI – Root Cause Analysis Service.

DETERMINISTIC: no LLM calls. Every failure code maps to a fixed root cause,
severity and explanation. All logic is testable in isolation.

Root causes defined in the implementation plan:
  ml_decline | insufficient_funds | bank_block | user_drop |
  expired_card | network_timeout
"""
from dataclasses import dataclass
from enum import Enum


class RootCause(str, Enum):
    ML_DECLINE        = "ml_decline"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    BANK_BLOCK        = "bank_block"
    USER_DROP         = "user_drop"
    EXPIRED_CARD      = "expired_card"
    NETWORK_TIMEOUT   = "network_timeout"
    UNKNOWN           = "unknown"


class Severity(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


@dataclass(frozen=True)
class RCAResult:
    root_cause:  RootCause
    severity:    Severity
    explanation: str
    # Is this recoverable without customer action?
    auto_recoverable: bool


# ── Primary lookup table: failure_code → RCA ──────────────────────────────────
_FAILURE_CODE_MAP: dict[str, RCAResult] = {
    "NETWORK_ERROR": RCAResult(
        root_cause=RootCause.NETWORK_TIMEOUT,
        severity=Severity.LOW,
        explanation=(
            "Temporary network or issuer connectivity issue caused the payment to fail. "
            "These failures are typically transient and resolve on retry."
        ),
        auto_recoverable=True,
    ),
    "PAYMENT_FAILED": RCAResult(
        root_cause=RootCause.ML_DECLINE,
        severity=Severity.MEDIUM,
        explanation=(
            "The payment was declined by the card network or issuer without a specific reason. "
            "May be triggered by fraud scoring, velocity checks, or issuer risk policies."
        ),
        auto_recoverable=False,
    ),
    "INSUFFICIENT_FUNDS": RCAResult(
        root_cause=RootCause.INSUFFICIENT_FUNDS,
        severity=Severity.MEDIUM,
        explanation=(
            "The customer's account did not have sufficient balance to complete the payment. "
            "Recovery is possible once funds are available or a different payment method is used."
        ),
        auto_recoverable=False,
    ),
    "EXPIRED_CARD": RCAResult(
        root_cause=RootCause.EXPIRED_CARD,
        severity=Severity.MEDIUM,
        explanation=(
            "The payment card has passed its expiry date. "
            "Recovery requires the customer to update their payment instrument."
        ),
        auto_recoverable=False,
    ),
    "USER_DROP": RCAResult(
        root_cause=RootCause.USER_DROP,
        severity=Severity.LOW,
        explanation=(
            "The customer initiated but did not complete the payment. "
            "They may have abandoned due to friction, distraction, or changed intent. "
            "A payment link or reminder can recover these effectively."
        ),
        auto_recoverable=False,
    ),
    "BANK_BLOCK": RCAResult(
        root_cause=RootCause.BANK_BLOCK,
        severity=Severity.HIGH,
        explanation=(
            "The transaction was blocked by the customer's bank or issuer. "
            "This is often due to international transaction restrictions, "
            "account flags, or spending limit policies. Requires customer to contact their bank."
        ),
        auto_recoverable=False,
    ),
    "CVV_MISMATCH": RCAResult(
        root_cause=RootCause.ML_DECLINE,
        severity=Severity.MEDIUM,
        explanation=(
            "The card verification value (CVV) did not match issuer records. "
            "Likely a data-entry error or compromised card detail."
        ),
        auto_recoverable=False,
    ),
    "DO_NOT_HONOR": RCAResult(
        root_cause=RootCause.BANK_BLOCK,
        severity=Severity.HIGH,
        explanation=(
            "Issuer returned a generic 'Do Not Honor' decline code. "
            "This indicates the bank has flagged the account or the specific transaction "
            "for risk reasons. Customer must resolve with their issuing bank."
        ),
        auto_recoverable=False,
    ),
}

# ── Severity adjustment rules (applied after base lookup) ─────────────────────
def _adjust_severity(base: RCAResult, amount: float, retry_count: int) -> Severity:
    """Escalate severity for high-value or repeatedly-failed payments."""
    sev = base.severity
    if amount > 50_000:
        sev = Severity.HIGH
    elif amount > 10_000 and sev == Severity.LOW:
        sev = Severity.MEDIUM
    if retry_count >= 3 and sev != Severity.HIGH:
        sev = Severity.MEDIUM
    return sev


# ── Public API ────────────────────────────────────────────────────────────────
def analyze_root_cause(
    failure_code: str,
    amount: float = 0.0,
    retry_count: int = 0,
) -> RCAResult:
    """
    Deterministic RCA: maps a failure code to a root cause + severity.

    Args:
        failure_code: Razorpay failure code string
        amount:       Payment amount in INR (used for severity escalation)
        retry_count:  Number of prior retries (escalates severity)

    Returns:
        RCAResult with root_cause, severity, explanation, auto_recoverable
    """
    code = (failure_code or "").strip().upper()
    base = _FAILURE_CODE_MAP.get(code, RCAResult(
        root_cause=RootCause.UNKNOWN,
        severity=Severity.MEDIUM,
        explanation=(
            f"Payment failed with code '{failure_code}'. "
            "The exact reason could not be automatically determined. "
            "Manual review is recommended."
        ),
        auto_recoverable=False,
    ))

    adjusted_severity = _adjust_severity(base, amount, retry_count)

    # Return same object if severity unchanged, else build new one
    if adjusted_severity == base.severity:
        return base
    return RCAResult(
        root_cause=base.root_cause,
        severity=adjusted_severity,
        explanation=base.explanation,
        auto_recoverable=base.auto_recoverable,
    )


def rca_to_dict(result: RCAResult) -> dict:
    return {
        "root_cause":     result.root_cause.value,
        "severity":       result.severity.value,
        "explanation":    result.explanation,
        "auto_recoverable": result.auto_recoverable,
    }
