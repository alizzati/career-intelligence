"""Structured findings produced by the Step 12 verification agent."""
from typing import Literal

from pydantic import BaseModel


VerificationStatus = Literal["PASS", "FAIL", "REVISE"]


class VerificationCheck(BaseModel):
    check: str
    status: VerificationStatus
    reason: str
    source_ids: list[str] = []


class UnsupportedClaim(BaseModel):
    component: str
    claim: str
    source_ids: list[str] = []


class VerificationResult(BaseModel):
    status: VerificationStatus
    checks: list[VerificationCheck]
    unsupported_claims: list[UnsupportedClaim] = []
    required_revision: list[str] = []
    llm_error: str | None = None
