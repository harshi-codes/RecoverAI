"""
Idempotency test: calling the pipeline twice for the same payment must NOT
create duplicate recovery_actions or duplicate recovered_amount.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.ml.model import load_model
from app.services.pipeline import run_recovery_pipeline

settings = get_settings()


@pytest.fixture(scope="session", autouse=True)
def load_ml():
    load_model(settings.ml_artifacts_dir)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(settings.database_url, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as session:
        yield session
    await engine.dispose()


class TestIdempotency:

    @pytest.mark.asyncio
    async def test_double_call_no_duplicate_actions(self, db: AsyncSession):
        """Calling pipeline twice must not create a second recovery_actions row."""
        payment_id = "demo-A-network-8499"

        # First call
        r1 = await run_recovery_pipeline(db, payment_id)
        await db.commit()

        # Count actions after first call
        res = await db.execute(
            text("SELECT COUNT(*) FROM recovery_actions ra JOIN recovery_cases rc ON rc.id=ra.case_id WHERE rc.payment_id=:pid"),
            {"pid": payment_id},
        )
        count_after_first = res.fetchone()[0]

        # Second call — must be idempotent
        r2 = await run_recovery_pipeline(db, payment_id)
        # idempotent call should NOT commit anything new
        assert r2.idempotent is True, "Second call must return idempotent=True"

        res2 = await db.execute(
            text("SELECT COUNT(*) FROM recovery_actions ra JOIN recovery_cases rc ON rc.id=ra.case_id WHERE rc.payment_id=:pid"),
            {"pid": payment_id},
        )
        count_after_second = res2.fetchone()[0]

        assert count_after_second == count_after_first, (
            f"Duplicate recovery_actions created! "
            f"Before: {count_after_first}, After: {count_after_second}"
        )
        print(f"\n[Idempotency] recovery_actions count stable at {count_after_first}")

    @pytest.mark.asyncio
    async def test_double_call_same_outcome(self, db: AsyncSession):
        """Two calls must return the same outcome status and recovered_amount."""
        payment_id = "demo-A-network-8499"

        r1 = await run_recovery_pipeline(db, payment_id)
        await db.commit()
        r2 = await run_recovery_pipeline(db, payment_id)

        assert r1.outcome["status"] == r2.outcome["status"], (
            f"Outcome mismatch: {r1.outcome} vs {r2.outcome}"
        )
        assert r1.outcome["recovered_amount"] == r2.outcome["recovered_amount"]
        print(f"\n[Idempotency] Both calls: status={r1.outcome['status']} amount=₹{r1.outcome['recovered_amount']:,.2f}")

    @pytest.mark.asyncio
    async def test_no_duplicate_audit_events_per_idempotent_call(self, db: AsyncSession):
        """Idempotent call must not add new audit_log rows."""
        payment_id = "demo-A-network-8499"

        # Get case_id
        r1 = await run_recovery_pipeline(db, payment_id)
        await db.commit()

        res = await db.execute(
            text("SELECT COUNT(*) FROM audit_logs WHERE entity_id=:cid"),
            {"cid": r1.case_id},
        )
        count_before = res.fetchone()[0]

        # Second call (idempotent)
        r2 = await run_recovery_pipeline(db, payment_id)

        res2 = await db.execute(
            text("SELECT COUNT(*) FROM audit_logs WHERE entity_id=:cid"),
            {"cid": r1.case_id},
        )
        count_after = res2.fetchone()[0]

        assert count_after == count_before, (
            f"Idempotent call added audit events! Before: {count_before}, After: {count_after}"
        )
        print(f"\n[Idempotency] Audit events stable at {count_before}")

    @pytest.mark.asyncio
    async def test_reset_allows_rerun(self, db: AsyncSession):
        """After reset, the pipeline should run fresh (not idempotent)."""
        from sqlalchemy import text as t

        payment_id = "demo-B-lowprob-1299"

        # Run pipeline once
        await run_recovery_pipeline(db, payment_id)
        await db.commit()

        # Delete the case to simulate reset
        await db.execute(t("""
            DELETE FROM recovery_actions WHERE case_id IN
            (SELECT id FROM recovery_cases WHERE payment_id=:pid)
        """), {"pid": payment_id})
        await db.execute(t("""
            DELETE FROM agent_decisions WHERE case_id IN
            (SELECT id FROM recovery_cases WHERE payment_id=:pid)
        """), {"pid": payment_id})
        await db.execute(t("""
            DELETE FROM audit_logs WHERE entity_id IN
            (SELECT id FROM recovery_cases WHERE payment_id=:pid)
        """), {"pid": payment_id})
        await db.execute(t("DELETE FROM audit_logs WHERE entity_id=:pid"), {"pid": payment_id})
        await db.execute(t("DELETE FROM recovery_cases WHERE payment_id=:pid"), {"pid": payment_id})
        await db.commit()

        # After reset, pipeline should re-run (not idempotent)
        r = await run_recovery_pipeline(db, payment_id)
        await db.commit()

        assert r.idempotent is False, "Pipeline should run fresh after reset"
        print(f"\n[Reset] Re-ran successfully after reset: idempotent={r.idempotent}")
