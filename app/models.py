from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra='allow', allow_inf_nan=False)


class Patient(FlexibleModel):
    age: int = Field(ge=0, le=125)


class Hospital(FlexibleModel):
    name: str = Field(min_length=1, max_length=200)
    network_provider: bool | None = None


class Treatment(FlexibleModel):
    type: str = Field(min_length=1, max_length=80)
    admission_hours: float = Field(ge=0, le=24000)
    diagnosis: str = Field(min_length=1, max_length=2000)
    procedure: str = Field(min_length=1, max_length=2000)
    pre_existing: bool | None = None
    experimental: bool | None = None


class ClaimCase(FlexibleModel):
    case_id: str = Field(min_length=1, max_length=100)
    policy_id: str = Field(min_length=1, max_length=100)
    policy_start_date: date
    claim_date: date
    sum_insured_inr: float = Field(gt=0, le=1_000_000_000)
    continuous_coverage_months: int = Field(ge=0, le=1500)
    prior_insurer_continuous_years: int = Field(ge=0, le=125)
    patient: Patient
    hospital: Hospital
    treatment: Treatment
    expenses_inr: dict[str, float]
    documents: list[str] = Field(max_length=100)
    task: str = Field(min_length=1, max_length=4000)
    evidence_context: dict[str, Any] = Field(default_factory=dict)
    prior_policy: dict[str, Any] = Field(default_factory=dict)
    expense_timing: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check_case(self):
        if self.claim_date < self.policy_start_date:
            raise ValueError('claim_date must not precede policy_start_date')
        if len(self.expenses_inr) > 50 or any(v < 0 or v > 1e9 for v in self.expenses_inr.values()):
            raise ValueError('expenses must contain at most 50 non-negative, finite amounts')
        if any(len(x) > 200 for x in self.documents):
            raise ValueError('document labels must be at most 200 characters')
        return self


class Decision(str, Enum):
    ADMISSIBLE = 'ADMISSIBLE'
    ADMISSIBLE_WITH_LIMITS = 'ADMISSIBLE_WITH_LIMITS'
    PARTIALLY_ADMISSIBLE = 'PARTIALLY_ADMISSIBLE'
    NOT_ADMISSIBLE = 'NOT_ADMISSIBLE'
    NEEDS_REVIEW = 'NEEDS_REVIEW'


class Investigation(BaseModel):
    dimensions: list[str] = Field(min_length=1, max_length=12)
    queries: list[str] = Field(min_length=1, max_length=12)
    missing_facts: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    dimension: str
    statement: str
    effect: Literal['supports', 'excludes', 'limits', 'uncertain', 'informational']
    evidence_ids: list[str]
    fact_paths: list[str] = Field(default_factory=list)


class Limit(BaseModel):
    category: str = Field(description='Exact expenses_inr key, e.g. room, doctor_fees, medicines_diagnostics, pre_hospitalization, post_hospitalization, ambulance; use claim_total only for an aggregate cap.')
    description: str
    claimed_inr: float = Field(ge=0)
    cap_inr: float | None = Field(default=None, ge=0)
    allowed_inr: float | None = Field(default=None, ge=0)
    evidence_ids: list[str]
    conditional: bool = True


class Assessment(BaseModel):
    recommended_decision: Decision
    findings: list[Finding] = Field(min_length=1)
    limits: list[Limit] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_action: str


class AuditItem(BaseModel):
    statement_index: int = Field(ge=0)
    supported: bool
    explanation: str


class SemanticAudit(BaseModel):
    items: list[AuditItem]
    decision_supported: bool
    decision_issue: str = ''


class Citation(BaseModel):
    claim: str
    source: str
    page: int
    pages: list[int]
    section: str
    chunk_id: str
    quote: str


class ValidationReport(BaseModel):
    status: Literal['PASS', 'FAIL', 'UNAVAILABLE']
    unsupported_claims: list[str] = Field(default_factory=list)
    structural_checks_passed: bool = False
    semantic_checks: list[AuditItem] = Field(default_factory=list)


class TraceEvent(BaseModel):
    agent: str
    action: str
    elapsed_ms: float
    details: dict[str, Any] = Field(default_factory=dict)


class ClaimResult(BaseModel):
    case_id: str
    decision: Decision
    reason_code: str | None = None
    confidence: float = Field(ge=0, le=1)
    confidence_note: str = 'Evidence-completeness heuristic, not a calibrated probability of payment.'
    key_findings: list[Finding]
    applicable_limits: list[Limit]
    missing_evidence: list[str]
    next_action: str
    citations: list[Citation]
    validation: ValidationReport
    trace: list[TraceEvent]
    retrieval: dict[str, Any]
    model: str
    policy_sha256: str
    elapsed_ms: float
