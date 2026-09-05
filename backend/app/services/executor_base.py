"""
RecoverAI – Recovery Executor Interface.

Defines the abstract boundary between the pipeline and the execution layer.
Current implementation: SimulatedRecoveryExecutor (no real money movement).

Future implementation path:
    RecoveryExecutor
        └── SimulatedRecoveryExecutor   ← current (SANDBOX/DEMO)
        └── RazorpaySandboxExecutor     ← next (Razorpay test mode)
        └── RazorpayLiveExecutor        ← future (production)

The pipeline depends only on RecoveryExecutor, not on the concrete class.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.services.decision import RecoveryAction


@dataclass
class ExecutionResult:
    action_id:          str | None
    action_type:        str
    status:             str        # "executed" | "skipped" | "error"
    simulated:          bool
    razorpay_reference: str | None
    outcome_success:    bool
    message:            str


class RecoveryExecutor(ABC):
    """Abstract interface for all recovery action executors."""

    @abstractmethod
    async def execute(
        self,
        *,
        db,
        case_id:     str,
        payment_id:  str,
        action:      RecoveryAction,
        params:      dict,
        case_status: str,
    ) -> ExecutionResult:
        """Execute a recovery action and return the result."""
        ...

    @property
    @abstractmethod
    def executor_name(self) -> str:
        """Human-readable name for audit logs."""
        ...

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        """True if this executor does not move real money."""
        ...
