"""Explicit local fixture seeding. Never called by API startup or in live mode."""
import argparse
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from .auth import wallet_address
from .db import engine
from .domain import Plan
from .marketplace import create_job, new_id
from .models import Task


def example_plan() -> Plan:
    return Plan(version=1, title="Towel-folding demonstrations", total=20, budget_atomic=20_000_000,
        reward_atomic=1_000_000, min_seconds=10, max_seconds=30, review_hours=72,
        rights_declaration="Demo only: contributor must explicitly grant the buyer-approved dataset usage rights.",
        requirements=[{"key": "large_towel", "description": "Large bath towel matching a buyer-approved reference", "minimum": 5},
                      {"key": "dark_surface", "description": "Dark tabletop matching a buyer-approved reference", "minimum": 5}])


def main():
    parser = argparse.ArgumentParser(description="Create labeled simulated listings; no chain funds are deposited.")
    parser.add_argument("--buyer", required=True, help="Public demo buyer wallet address, never a private key")
    args = parser.parse_args()
    if os.getenv("APP_MODE") != "fixture":
        parser.error("Explicit APP_MODE=fixture is required")
    buyer = wallet_address(args.buyer)
    with Session(engine()) as db:
        job = create_job(db, buyer, example_plan())
        job.fixture, job.state, job.deposited_atomic = True, "open", 20_000_000
        # Small initial batch: categories overlap; do not publish twenty redundant tasks.
        for tags, equipment in [(["large_towel", "dark_surface"], ["phone", "towel", "dark_table"]),
                                (["large_towel"], ["phone", "towel"])]:
            db.add(Task(id=new_id(), job_id=job.id, version=1, reward_atomic=1_000_000,
                slots=2, claimed=0, tags=tags, equipment=equipment, minutes=15,
                deadline=datetime.now(UTC) + timedelta(hours=24), state="open"))
        db.commit()
        print(f"Created FIXTURE job {job.id}. Simulated funds only; no chain transaction.")


if __name__ == "__main__":
    main()
