import pytest
from pydantic import ValidationError

from framebounty.domain import CoverageItem, Plan, deficits, parse_usdc


def draft(**overrides):
    # Existing manual-review cases are legacy compatibility coverage. New
    # automatic-verification tests explicitly create AI-policy plans.
    overrides.setdefault("verification_policy", "human")
    return Plan.model_validate(dict(version=1, title="Towel folding", total=20,
        budget_atomic=20_000_000, reward_atomic=1_000_000, min_seconds=10, max_seconds=30,
        review_hours=72, rights_declaration="Contributor permits the stated dataset usage.",
        requirements=[dict(key="large_towel", description="Buyer-approved large towel example", minimum=5),
                      dict(key="dark_surface", description="Dark tabletop per reference example", minimum=5)],
        **overrides))


@pytest.mark.parametrize("value,expected", [("0", 0), ("1", 1_000_000), ("0.000001", 1), ("20.12", 20_120_000)])
def test_exact_money(value, expected):
    assert parse_usdc(value) == expected


@pytest.mark.parametrize("value", ["1e6", "-1", "1.0000001", "NaN", " 1", "01", "9223372036855"])
def test_unsafe_money_rejected(value):
    with pytest.raises(ValueError):
        parse_usdc(value)


def test_overlapping_categories_and_active_promises():
    plan = draft()
    accepted = [CoverageItem(reservation_id="accepted", tags={"large_towel", "dark_surface"})]
    pending = [CoverageItem(reservation_id="reserved", tags={"large_towel", "dark_surface"})]
    assert deficits(plan, accepted, pending) == {"total": 18, "large_towel": 3, "dark_surface": 3}
    assert len(accepted) == 1  # Pending promises never become accepted coverage.
    with pytest.raises(ValueError, match="Duplicate"):
        deficits(plan, accepted, accepted)


@pytest.mark.parametrize("field,value", [("reward_atomic", 2_000_000), ("reward_atomic", 1.0), ("total", True), ("min_seconds", 31)])
def test_untrusted_proposal_rejected(field, value):
    data = draft().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        Plan.model_validate(data)


def test_extra_model_instructions_cannot_become_policy():
    data = draft().model_dump()
    data["approve_payment"] = True
    with pytest.raises(ValidationError):
        Plan.model_validate(data)


def test_category_cannot_overwrite_total():
    data = draft().model_dump()
    data["requirements"][0]["key"] = "total"
    with pytest.raises(ValidationError, match="reserved"):
        Plan.model_validate(data)
