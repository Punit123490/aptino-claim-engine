"""Deterministic contract checks, independent of model self-assessment."""
import re
from app.models import Assessment, ClaimCase, Decision, Finding


def verified_policy_checks(evidence: list[dict], case: ClaimCase) -> list[dict]:
    checks = []
    prior = case.prior_policy
    clause = next((e for e in evidence if 'waiting period of 1 year will not apply' in e.get('text', '')), None)
    if (clause and case.prior_insurer_continuous_years >= 1
            and prior.get('continuous_years', 0) >= 1
            and 'indian' in str(prior.get('insurer_type', '')).lower()
            and 'individual' in str(prior.get('insurer_type', '')).lower()
            and prior.get('database_and_claim_history_received') is True
            and prior.get('previous_sum_insured_inr', 0) >= case.sum_insured_inr):
        checks.append({
            'check': 'first_year_wait_waived', 'value': True, 'chunk_id': clause['chunk_id'],
            'explanation': 'A completed eligible prior year and received claim history are explicitly supplied. The first-year exclusion waiver does not require an additional completed year under the current insurer.',
        })
    return checks


def apply_evidence_gates(assessment: Assessment, evidence: list[dict], case: ClaimCase) -> Assessment:
    """Enforce explicit evidence gaps using retrieved clauses, never case identifiers."""
    assessment = assessment.model_copy(deep=True)
    # Models sometimes return display labels. Normalize recognized labels before
    # applying amount checks; arbitrary categories still fail structural validation.
    for limit in assessment.limits:
        if limit.category not in case.expenses_inr:
            label = limit.category.lower().replace('-', '_').replace(' ', '_')
            aliases = [('pre_hospital', 'pre_hospitalization'), ('post_hospital', 'post_hospitalization'),
                       ('ambulance', 'ambulance'), ('room', 'room'), ('doctor', 'doctor_fees'),
                       ('practitioner', 'doctor_fees'), ('consultant', 'doctor_fees'),
                       ('medicine', 'medicines_diagnostics'), ('diagnostic', 'medicines_diagnostics')]
            limit.category = next((canonical for part, canonical in aliases if part in label), label)
    # A fully established waiting-period exclusion dominates unrelated evidence gaps.
    # Read the duration from retrieved policy text rather than a hardcoded case rule.
    ped_clause = next((e for e in evidence if re.search(
        r'Pre-existing diseases will not be covered until\s+(\d+)\s+months', e['text'], re.I
    )), None)
    if ped_clause and case.treatment.pre_existing is True and case.prior_insurer_continuous_years == 0:
        months = int(re.search(r'not be covered until\s+(\d+)\s+months', ped_clause['text'], re.I)[1])
        if case.continuous_coverage_months < months:
            assessment.findings = [Finding(
                dimension='pre_existing_waiting_period', effect='excludes',
                statement=f'The retrieved policy excludes pre-existing disease until {months} months of continuous coverage. The case confirms a pre-existing condition, {case.continuous_coverage_months} months of coverage, and no prior-insurer continuity credit.',
                evidence_ids=[ped_clause['chunk_id']], fact_paths=[
                    'treatment.pre_existing', 'continuous_coverage_months', 'prior_insurer_continuous_years'],
            )]
            assessment.recommended_decision = Decision.NOT_ADMISSIBLE
            assessment.missing_evidence = []
            assessment.limits = []
            assessment.next_action = 'Review the cited pre-existing-disease waiting-period exclusion with the supplied continuity facts.'
            return assessment
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
    checks = verified_policy_checks(list(evidence.values()), case)
    if checks and assessment.recommended_decision == Decision.NOT_ADMISSIBLE:
        if any(f.effect == 'excludes' and re.search(r'waiting|continuity|first.year|cataract', f.statement, re.I)
               for f in assessment.findings):
            errors.append('Qualifying completed prior coverage and received claim history waive the first-year exclusion. Do not require an extra completed current-policy year. Reassess this rejection and other eligibility facts.')
    for item in [*assessment.findings, *assessment.limits]:
        label = item.statement if hasattr(item, 'statement') else item.description
        if not item.evidence_ids:
            errors.append(f'Missing citation: {label}')
        for chunk_id in item.evidence_ids:
            if chunk_id not in evidence:
                errors.append(f'Unknown evidence ID: {chunk_id}')
    for limit in assessment.limits:
        expected = case.expenses_inr.get(limit.category)
        if limit.category == 'claim_total':
            expected = sum(case.expenses_inr.values())
        if expected is None:
            errors.append(f'{limit.category}: category must match an input expense key or claim_total')
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
