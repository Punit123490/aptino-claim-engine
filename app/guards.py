"""Deterministic contract checks, independent of model self-assessment."""
from app.models import Assessment, ClaimCase, Decision, Finding


def apply_evidence_gates(assessment: Assessment, evidence: list[dict], case: ClaimCase) -> Assessment:
    """Enforce explicit evidence gaps using retrieved clauses, never case identifiers."""
    assessment = assessment.model_copy(deep=True)
    if assessment.recommended_decision == Decision.NOT_ADMISSIBLE:
        return assessment
    hospital_clause = next((e for e in evidence if e['text'].startswith('Hospital means')), None)
    facts = case.evidence_context
    registered = facts.get('hospital_registered') is True or case.hospital.model_extra.get('registered') is True
    minimum_criteria = facts.get('hospital_minimum_criteria_documented') is True
    if case.treatment.type in ('inpatient', 'day_care') and hospital_clause and not (registered or minimum_criteria):
        gap = 'Evidence that the facility is registered as a hospital or satisfies all alternative minimum criteria.'
        if gap not in assessment.missing_evidence:
            assessment.missing_evidence.append(gap)
        if not any(f.dimension == 'hospital_evidence_gate' for f in assessment.findings):
            assessment.findings.append(Finding(
                dimension='hospital_evidence_gate', effect='uncertain',
                statement='The policy requires hospital registration or compliance with all minimum criteria; the supplied facts establish neither route.',
                evidence_ids=[hospital_clause['chunk_id']], fact_paths=['hospital', 'evidence_context'],
            ))
    if assessment.missing_evidence or any(f.effect == 'uncertain' for f in assessment.findings):
        assessment.recommended_decision = Decision.NEEDS_REVIEW
        for limit in assessment.limits:
            limit.conditional = True
    # Do not turn ambiguous normal-room wording into a confident duration calculation.
    room_clause = next((e for e in evidence if 'Normal Room expenses: 1.0%' in e['text']), None)
    if room_clause and case.expenses_inr.get('room', 0):
        for limit in assessment.limits:
            if limit.category == 'room' and not case.evidence_context.get('normal_room_billing_basis_confirmed'):
                limit.cap_inr = None
                limit.allowed_inr = None
                limit.conditional = True
                limit.description = 'The policy states a 1% basic-sum-insured normal-room sub-limit, but its duration basis is not explicit. Confirm the billing basis before calculating an allowed amount.'
                limit.evidence_ids = [room_clause['chunk_id']]
        gap = 'Confirmation of the normal-room sub-limit billing basis before calculating a payable room amount.'
        if gap not in assessment.missing_evidence:
            assessment.missing_evidence.append(gap)
        assessment.recommended_decision = Decision.NEEDS_REVIEW
        for limit in assessment.limits:
            limit.conditional = True
    return assessment


def structural_errors(assessment: Assessment, evidence: dict[str, dict], case: ClaimCase) -> list[str]:
    errors = []
    for item in [*assessment.findings, *assessment.limits]:
        label = item.statement if hasattr(item, 'statement') else item.description
        if not item.evidence_ids:
            errors.append(f'Missing citation: {label}')
        for chunk_id in item.evidence_ids:
            if chunk_id not in evidence:
                errors.append(f'Unknown evidence ID: {chunk_id}')
    for limit in assessment.limits:
        expected = case.expenses_inr.get(limit.category)
        if expected is not None and abs(limit.claimed_inr - expected) > 0.01:
            errors.append(f'{limit.category}: claimed amount differs from input')
        if limit.allowed_inr is not None:
            if limit.allowed_inr > limit.claimed_inr + 0.01:
                errors.append(f'{limit.category}: allowed amount exceeds claimed amount')
            if limit.cap_inr is not None and limit.allowed_inr > limit.cap_inr + 0.01:
                errors.append(f'{limit.category}: allowed amount exceeds stated cap')
        if assessment.recommended_decision == Decision.NEEDS_REVIEW and not limit.conditional:
            errors.append(f'{limit.category}: final amount asserted for a review case')
    if assessment.recommended_decision == Decision.NOT_ADMISSIBLE:
        if not any(x.effect == 'excludes' for x in assessment.findings):
            errors.append('Rejection has no operative exclusion finding')
    elif assessment.recommended_decision != Decision.NEEDS_REVIEW:
        if assessment.missing_evidence or any(x.effect == 'uncertain' for x in assessment.findings):
            errors.append('Final decision conflicts with unresolved material evidence')
    return errors


def material_statements(assessment: Assessment) -> list[dict]:
    statements = [{'text': x.statement, 'evidence_ids': x.evidence_ids} for x in assessment.findings]
    statements.extend({'text': x.model_dump_json(), 'evidence_ids': x.evidence_ids} for x in assessment.limits)
    return [{'index': i, **s} for i, s in enumerate(statements)]
