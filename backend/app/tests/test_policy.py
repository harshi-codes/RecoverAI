"""
Unit tests for the Policy Guard.

Tests every rule from the implementation plan:
1. high-probability payment (APPROVED)
2. low-probability payment (BLOCKED)
3. amount > ₹50,000 (REQUIRES_HUMAN)
4. repeated contact (BLOCKED)
5. opted-out customer (BLOCKED)
6. already successful payment (BLOCKED)
7. high discount > 10% (REQUIRES_HUMAN)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from app.services.policy import (
    PolicyOutcome,
    evaluate_policy,
)

# ── Baseline "all-pass" kwargs ────────────────────────────────────────────────
_BASE = dict(
    payment_status="failed",
    opted_out=False,
    contact_count=0,
    amount=8_499.0,
    discount_percent=0.0,
    recovery_probability=0.75,
)


def _eval(**overrides):
    kwargs = {**_BASE, **overrides}
    return evaluate_policy(**kwargs)


# ── Rule 1: payment already succeeded ────────────────────────────────────────
class TestPaymentSucceeded:
    def test_captured_is_blocked(self):
        r = _eval(payment_status="captured")
        assert r.outcome == PolicyOutcome.BLOCKED
        assert r.allowed is False
        assert r.blocking_rule == "payment_succeeded"

    def test_paid_is_blocked(self):
        r = _eval(payment_status="paid")
        assert r.outcome == PolicyOutcome.BLOCKED

    def test_failed_is_not_blocked_by_this_rule(self):
        r = _eval(payment_status="failed")
        # Should pass this rule (may fail on others depending on params)
        assert r.blocking_rule != "payment_succeeded"


# ── Rule 2: opted out ─────────────────────────────────────────────────────────
class TestOptedOut:
    def test_opted_out_is_blocked(self):
        r = _eval(opted_out=True)
        assert r.outcome == PolicyOutcome.BLOCKED
        assert r.blocking_rule == "opted_out"
        assert "opted out" in r.reason.lower()

    def test_not_opted_out_passes(self):
        r = _eval(opted_out=False)
        assert r.blocking_rule != "opted_out"


# ── Rule 3: contact limit ─────────────────────────────────────────────────────
class TestContactLimit:
    def test_exactly_3_contacts_is_blocked(self):
        r = _eval(contact_count=3)
        assert r.outcome == PolicyOutcome.BLOCKED
        assert r.blocking_rule == "contact_limit"

    def test_4_contacts_is_blocked(self):
        r = _eval(contact_count=4)
        assert r.outcome == PolicyOutcome.BLOCKED

    def test_2_contacts_is_allowed(self):
        r = _eval(contact_count=2)
        assert r.blocking_rule != "contact_limit"

    def test_0_contacts_is_allowed(self):
        r = _eval(contact_count=0)
        assert r.blocking_rule != "contact_limit"


# ── Rule 4: amount > ₹50,000 requires human ──────────────────────────────────
class TestHighAmount:
    def test_50001_requires_human(self):
        r = _eval(amount=50_001.0)
        assert r.outcome == PolicyOutcome.REQUIRES_HUMAN
        assert r.requires_human_approval is True
        assert r.blocking_rule == "high_amount"

    def test_exactly_50000_is_approved(self):
        r = _eval(amount=50_000.0)
        assert r.blocking_rule != "high_amount"

    def test_large_amount_requires_human(self):
        r = _eval(amount=200_000.0)
        assert r.outcome == PolicyOutcome.REQUIRES_HUMAN

    def test_normal_amount_passes(self):
        r = _eval(amount=8_499.0)
        assert r.blocking_rule != "high_amount"


# ── Rule 5: discount > 10% requires human ────────────────────────────────────
class TestHighDiscount:
    def test_11_percent_requires_human(self):
        r = _eval(discount_percent=11.0)
        assert r.outcome == PolicyOutcome.REQUIRES_HUMAN
        assert r.blocking_rule == "high_discount"

    def test_10_percent_is_allowed(self):
        r = _eval(discount_percent=10.0)
        assert r.blocking_rule != "high_discount"

    def test_5_percent_is_allowed(self):
        r = _eval(discount_percent=5.0)
        assert r.blocking_rule != "high_discount"


# ── Rule 6: low recovery probability ─────────────────────────────────────────
class TestLowProbability:
    def test_below_60_is_blocked(self):
        r = _eval(recovery_probability=0.59)
        assert r.outcome == PolicyOutcome.BLOCKED
        assert r.blocking_rule == "low_probability"

    def test_exactly_60_passes(self):
        r = _eval(recovery_probability=0.60)
        assert r.blocking_rule != "low_probability"

    def test_very_low_is_blocked(self):
        r = _eval(recovery_probability=0.10)
        assert r.outcome == PolicyOutcome.BLOCKED

    def test_high_probability_passes(self):
        r = _eval(recovery_probability=0.90)
        assert r.blocking_rule != "low_probability"


# ── Happy path: all rules pass ────────────────────────────────────────────────
class TestApproved:
    def test_hero_payment_is_approved(self):
        """Hero payment characteristics should be fully approved."""
        r = _eval(
            payment_status="failed",
            opted_out=False,
            contact_count=0,
            amount=8_499.0,
            discount_percent=0.0,
            recovery_probability=0.75,
        )
        assert r.outcome == PolicyOutcome.APPROVED
        assert r.allowed is True
        assert r.requires_human_approval is False
        assert r.blocking_rule is None

    def test_subscription_recovery_approved(self):
        r = _eval(
            amount=2_999.0,
            recovery_probability=0.82,
            contact_count=1,
            discount_percent=5.0,
        )
        assert r.outcome == PolicyOutcome.APPROVED


# ── Rule priority: first triggered rule wins ──────────────────────────────────
class TestRulePriority:
    def test_opted_out_takes_priority_over_low_prob(self):
        """opted_out should fire before low_probability."""
        r = _eval(opted_out=True, recovery_probability=0.30)
        assert r.blocking_rule == "opted_out"

    def test_payment_succeeded_takes_priority_over_opted_out(self):
        """payment_succeeded is checked first."""
        r = _eval(payment_status="captured", opted_out=True)
        assert r.blocking_rule == "payment_succeeded"
