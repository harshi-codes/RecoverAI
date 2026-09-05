"""
RecoverAI – Policy / Safety Guard.

DETERMINISTIC, ORDERED RULES. Every recovery action must pass ALL rules.
The first blocking rule short-circuits and returns immediately.

Rules from the implementation plan:
  1. payment already succeeded            → CANCEL RECOVERY
  2. customer opted out                   → DO NOT CONTACT
  3. customer contacted >= 3 times        → STOP
  4. amount > ₹50,000                     → HUMAN APPROVAL
  5. discount > 10%                       → HUMAN APPROVAL
  6. recovery probability < 0.60          → NO AUTOMATIC ACTION

All rules are pure functions of their arguments.
No database calls, no LLM.
"""
from dataclasses import dataclass, field
from enum import Enum


class PolicyOutcome(str, Enum):
    APPROVED         = "approved"
    BLOCKED          = "blocked"
    REQUIRES_HUMAN   = "requires_human"


@dataclass(frozen=True)
class PolicyResult:
    allowed:                  bool
    outcome:                  PolicyOutcome
    reason:                   str
    requires_human_approval:  bool
    blocking_rule:            str | None   # rule ID that fired, None if approved


# ── Individual rule functions ─────────────────────────────────────────────────
# Each returns (blocked: bool, reason: str, needs_human: bool)

def _rule_payment_succeeded(payment_status: str) -> tuple[bool, str, bool]:
    """Rule 1: If payment already captured, cancel all recovery."""
    if payment_status.lower() in ("captured", "paid", "success"):
        return True, (
            f"Payment status is '{payment_status}' — already succeeded. "
            "All recovery actions are cancelled."
        ), False
    return False, "", False


def _rule_opted_out(opted_out: bool) -> tuple[bool, str, bool]:
    """Rule 2: Do not contact opted-out customers."""
    if opted_out:
        return True, (
            "Customer has opted out of recovery communications. "
            "No contact is permitted."
        ), False
    return False, "", False


def _rule_contact_limit(contact_count: int, max_contacts: int = 3) -> tuple[bool, str, bool]:
    """Rule 3: Stop if customer has been contacted too many times."""
    if contact_count >= max_contacts:
        return True, (
            f"Customer has already been contacted {contact_count} times "
            f"(limit: {max_contacts}). Recovery workflow stopped to prevent harassment."
        ), False
    return False, "", False


def _rule_high_amount(amount: float, threshold: float = 50_000.0) -> tuple[bool, str, bool]:
    """Rule 4: Amounts above threshold require human approval."""
    if amount > threshold:
        return False, (
            f"Payment amount ₹{amount:,.0f} exceeds ₹{threshold:,.0f} threshold. "
            "Human approval is required before proceeding."
        ), True
    return False, "", False


def _rule_high_discount(discount_percent: float, max_discount: float = 10.0) -> tuple[bool, str, bool]:
    """Rule 5: Discounts above 10% require human approval."""
    if discount_percent > max_discount:
        return False, (
            f"Proposed discount {discount_percent}% exceeds maximum allowed {max_discount}%. "
            "Human approval is required."
        ), True
    return False, "", False


def _rule_low_probability(recovery_probability: float, min_prob: float = 0.60) -> tuple[bool, str, bool]:
    """Rule 6: Do not auto-intervene if recovery probability is below threshold."""
    if recovery_probability < min_prob:
        return True, (
            f"Recovery probability {recovery_probability:.0%} is below the minimum "
            f"threshold of {min_prob:.0%}. No automatic action will be taken."
        ), False
    return False, "", False


# ── Composite policy evaluation ───────────────────────────────────────────────
def evaluate_policy(
    payment_status:       str,
    opted_out:            bool,
    contact_count:        int,
    amount:               float,
    discount_percent:     float,
    recovery_probability: float,
) -> PolicyResult:
    """
    Evaluate all policy rules in order. Returns on first match.
    If all rules pass → APPROVED.

    Args:
        payment_status:       current payment status (captured/failed/etc.)
        opted_out:            customer opted-out flag
        contact_count:        number of times customer has been contacted for recovery
        amount:               payment amount in INR
        discount_percent:     discount % in the proposed action (0 if none)
        recovery_probability: ML model output [0, 1]

    Returns:
        PolicyResult
    """

    # Ordered rule evaluation — BLOCKING rules first, then HUMAN-APPROVAL rules
    rules: list[tuple[str, tuple[bool, str, bool]]] = [
        ("payment_succeeded",  _rule_payment_succeeded(payment_status)),
        ("opted_out",          _rule_opted_out(opted_out)),
        ("contact_limit",      _rule_contact_limit(contact_count)),
        ("low_probability",    _rule_low_probability(recovery_probability)),
        ("high_amount",        _rule_high_amount(amount)),
        ("high_discount",      _rule_high_discount(discount_percent)),
    ]

    for rule_id, (triggered, reason, needs_human) in rules:
        if triggered or needs_human:
            if needs_human:
                return PolicyResult(
                    allowed=False,
                    outcome=PolicyOutcome.REQUIRES_HUMAN,
                    reason=reason,
                    requires_human_approval=True,
                    blocking_rule=rule_id,
                )
            if triggered:
                return PolicyResult(
                    allowed=False,
                    outcome=PolicyOutcome.BLOCKED,
                    reason=reason,
                    requires_human_approval=False,
                    blocking_rule=rule_id,
                )

    return PolicyResult(
        allowed=True,
        outcome=PolicyOutcome.APPROVED,
        reason="All policy rules passed. Automated recovery action is permitted.",
        requires_human_approval=False,
        blocking_rule=None,
    )


def policy_to_dict(result: PolicyResult) -> dict:
    return {
        "allowed":                 result.allowed,
        "outcome":                 result.outcome.value,
        "reason":                  result.reason,
        "requires_human_approval": result.requires_human_approval,
        "blocking_rule":           result.blocking_rule,
    }
