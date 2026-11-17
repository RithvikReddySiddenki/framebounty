"""Initial HTTP shell. No funding, authentication or payment behavior is implied."""
import os

from fastapi import FastAPI

from .domain import Plan

app = FastAPI(title="FrameBounty", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "mode": os.getenv("APP_MODE", "fixture"), "payments_enabled": False}


@app.post("/plans/validate", response_model=Plan)
def validate_plan(plan: Plan):
    """Validate an untrusted draft; this endpoint cannot publish or spend funds."""
    return plan
