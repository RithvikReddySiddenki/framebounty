"""Canonical plan rules. Atomic USDC values are integers; overlapping tags are sets.

These pure functions do not assert funding, ownership or model accuracy. Those require
authenticated services and verified chain evidence before any task becomes claimable.
"""
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

USDC_DECIMALS = 6  # Application token interface; never use this for native gas values.
Atomic = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
PositiveAtomic = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]


def parse_usdc(value: str) -> int:
    """Parse a decimal string exactly, rejecting exponent notation and rounding."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?", value):
        raise ValueError("Use a nonnegative decimal with at most six decimal places")
    whole, _, fraction = value.partition(".")
    atomic = int(whole) * 10**USDC_DECIMALS + int(fraction.ljust(6, "0") or "0")
    if atomic > 2**63 - 1:
        raise ValueError("Amount exceeds application storage limit")
    return atomic


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReservationIntent(ClosedModel):
    """Canonical confirmed intention shared by UI and contributor tools."""
    confirmation_id: str = Field(min_length=32, max_length=32)
    task_id: str = Field(min_length=1, max_length=64)
    version: int = Field(strict=True, ge=1)
    reward_atomic: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")
    confirmed: bool = Field(strict=True)


class Requirement(ClosedModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    description: str = Field(min_length=8, max_length=1000)
    minimum: int = Field(strict=True, ge=1, le=20)


class Plan(ClosedModel):
    media_type: Literal["image", "video"] = "video"
    verification_policy: Literal["human", "ai"] = "ai"
    posting_hours: int = Field(strict=True, ge=1, le=720, default=24)
    expected_minutes: int = Field(strict=True, ge=1, le=720, default=15)
    version: int = Field(strict=True, ge=1)
    title: str = Field(min_length=3, max_length=160)
    total: int = Field(strict=True, ge=1, le=20)
    budget_atomic: PositiveAtomic
    reward_atomic: PositiveAtomic
    min_seconds: int = Field(strict=True, ge=10, le=30)
    max_seconds: int = Field(strict=True, ge=10, le=30)
    review_hours: int = Field(strict=True, ge=1, le=168)
    rights_declaration: str = Field(min_length=10, max_length=2000)
    requirements: tuple[Requirement, ...] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.total * self.reward_atomic > self.budget_atomic:
            raise ValueError("Promised rewards exceed approved budget")
        if self.min_seconds > self.max_seconds:
            raise ValueError("Invalid duration interval")
        keys = [r.key for r in self.requirements]
        if "total" in keys:
            raise ValueError("total is reserved for aggregate coverage")
        if len(set(keys)) != len(keys):
            raise ValueError("Requirement keys must be unique")
        if any(r.minimum > self.total for r in self.requirements):
            raise ValueError("A category cannot exceed total clip count")
        return self


class CoverageItem(ClosedModel):
    reservation_id: str
    tags: frozenset[str]


def deficits(plan: Plan, accepted: list[CoverageItem], committed: list[CoverageItem]) -> dict[str, int]:
    """Prevent redundant purchases without reporting pending promises as accepted data.

    Inputs are unique reviewed clips or immutable reservation targets from trusted services,
    never model-provided counts. A reservation can occur in exactly one input collection.
    """
    items = accepted + committed
    ids = [item.reservation_id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate reservation in coverage inputs")
    return {
        "total": max(0, plan.total - len(items)),
        **{r.key: max(0, r.minimum - sum(r.key in item.tags for item in items)) for r in plan.requirements},
    }
