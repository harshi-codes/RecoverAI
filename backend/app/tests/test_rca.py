"""Unit tests for the Root Cause Analysis service."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from app.services.rca import (
    RootCause, Severity, analyze_root_cause
)


class TestRCAMapping:
    def test_network_error(self):
        r = analyze_root_cause("NETWORK_ERROR")
        assert r.root_cause == RootCause.NETWORK_TIMEOUT
        assert r.severity == Severity.LOW
        assert r.auto_recoverable is True

    def test_payment_failed(self):
        r = analyze_root_cause("PAYMENT_FAILED")
        assert r.root_cause == RootCause.ML_DECLINE
        assert r.severity == Severity.MEDIUM

    def test_insufficient_funds(self):
        r = analyze_root_cause("INSUFFICIENT_FUNDS")
        assert r.root_cause == RootCause.INSUFFICIENT_FUNDS
        assert r.auto_recoverable is False

    def test_expired_card(self):
        r = analyze_root_cause("EXPIRED_CARD")
        assert r.root_cause == RootCause.EXPIRED_CARD

    def test_user_drop(self):
        r = analyze_root_cause("USER_DROP")
        assert r.root_cause == RootCause.USER_DROP
        assert r.severity == Severity.LOW

    def test_bank_block(self):
        r = analyze_root_cause("BANK_BLOCK")
        assert r.root_cause == RootCause.BANK_BLOCK
        assert r.severity == Severity.HIGH

    def test_do_not_honor(self):
        r = analyze_root_cause("DO_NOT_HONOR")
        assert r.root_cause == RootCause.BANK_BLOCK

    def test_unknown_code(self):
        r = analyze_root_cause("SOME_UNKNOWN_CODE")
        assert r.root_cause == RootCause.UNKNOWN

    def test_case_insensitive(self):
        r = analyze_root_cause("network_error")
        assert r.root_cause == RootCause.NETWORK_TIMEOUT


class TestSeverityEscalation:
    def test_high_amount_escalates_severity(self):
        r = analyze_root_cause("NETWORK_ERROR", amount=75_000.0)
        assert r.severity == Severity.HIGH

    def test_medium_amount_escalates_low(self):
        r = analyze_root_cause("NETWORK_ERROR", amount=15_000.0)
        assert r.severity == Severity.MEDIUM

    def test_repeated_retries_escalate(self):
        r = analyze_root_cause("PAYMENT_FAILED", retry_count=3)
        assert r.severity == Severity.MEDIUM

    def test_normal_amount_no_escalation(self):
        r = analyze_root_cause("USER_DROP", amount=500.0)
        assert r.severity == Severity.LOW
