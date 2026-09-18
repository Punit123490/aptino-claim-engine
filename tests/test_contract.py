import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import ROOT, get_settings
from app.guards import apply_evidence_gates, structural_errors
from app.ingestion import ingest_policy
from app.models import Assessment, ClaimCase
from app.retrieval import reciprocal_rank_fusion


@pytest.fixture
def case_data():
    return json.loads((ROOT / 'data/candidate_data/public_test_cases.json').read_text())[0]


def test_all_supplied_cases_validate():
    cases = json.loads((ROOT / 'data/candidate_data/public_test_cases.json').read_text())
    assert len(cases) == 12
    for case in cases:
        ClaimCase.model_validate(case)


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf')])
def test_invalid_expenses_rejected(case_data, value):
    case_data['expenses_inr']['room'] = value
    with pytest.raises(ValidationError):
        ClaimCase.model_validate(case_data)


def test_unknown_fields_tolerated(case_data):
    case_data['favorite_color'] = 'blue'
    assert ClaimCase.model_validate(case_data).model_dump()['favorite_color'] == 'blue'


def test_invalid_date_order(case_data):
    case_data['claim_date'] = '2020-01-01'
    with pytest.raises(ValidationError):
        ClaimCase.model_validate(case_data)


def test_clauses_preserve_context_and_pages():
    chunks, _ = ingest_policy(get_settings().policy_path)
    short_stay = next(c for c in chunks if c.text.startswith('NB4:'))
    assert short_stay.pages == [7, 8]
    assert 'specialised infrastructure' in short_stay.text
    domiciliary = next(c for c in chunks if c.text.startswith('17. Any expense under Domiciliary'))
    assert 'not exceeding three days' in domiciliary.text
    assert 'Asthma' in domiciliary.text
    waiting = next(c for c in chunks if c.text.startswith('2. 30 days'))
    assert waiting.pages == [9]
    assert 'WHAT WE EXCLUDE' in waiting.section
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_rrf_rewards_agreement():
    scores = reciprocal_rank_fusion([[1, 2, 3], [2, 4, 1]])
    assert scores[2] > scores[3]
    assert scores[1] > scores[4]


def assessment(**updates):
    value = dict(recommended_decision='ADMISSIBLE', findings=[{
        'dimension':'coverage', 'statement':'Supported coverage', 'effect':'supports',
        'evidence_ids':['known'], 'fact_paths':['treatment.type'],
    }], limits=[], missing_evidence=[], next_action='Review result')
    value.update(updates)
    return Assessment.model_validate(value)


def test_unknown_citation_fails(case_data):
    assert structural_errors(assessment(), {}, ClaimCase.model_validate(case_data))


def test_missing_evidence_cannot_be_approved(case_data):
    errors = structural_errors(assessment(missing_evidence=['hospital registration']), {'known':{}}, ClaimCase.model_validate(case_data))
    assert any('unresolved' in e for e in errors)


def test_payable_amount_cannot_exceed_bill(case_data):
    result = assessment(limits=[dict(category='doctor_fees', description='Fee cap', claimed_inr=30000,
                                   allowed_inr=40000, cap_inr=50000, evidence_ids=['known'])])
    assert any('exceeds claimed' in e for e in structural_errors(result, {'known':{}}, ClaimCase.model_validate(case_data)))


def test_hospital_gap_blocks_approval_using_retrieved_definition(case_data):
    evidence = [dict(chunk_id='hospital', text='Hospital means a registered institution OR all minimum criteria.')]
    result = apply_evidence_gates(assessment(), evidence, ClaimCase.model_validate(case_data))
    assert result.recommended_decision.value == 'NEEDS_REVIEW'
    assert result.findings[-1].evidence_ids == ['hospital']


def test_registered_hospital_does_not_trigger_missing_evidence_gate(case_data):
    case_data['evidence_context'] = {'hospital_registered': True}
    evidence = [dict(chunk_id='hospital', text='Hospital means a registered institution OR all minimum criteria.')]
    result = apply_evidence_gates(assessment(), evidence, ClaimCase.model_validate(case_data))
    assert result.recommended_decision.value == 'ADMISSIBLE'


def test_room_ambiguity_does_not_publish_unproven_daily_amount(case_data):
    draft = assessment(limits=[dict(category='room', description='Per-day cap', claimed_inr=30000,
                                   allowed_inr=20000, cap_inr=20000, evidence_ids=['room'])])
    evidence = [dict(chunk_id='room', text='Normal Room expenses: 1.0% of Basic Sum Insured.')]
    result = apply_evidence_gates(draft, evidence, ClaimCase.model_validate(case_data))
    assert result.limits[0].allowed_inr is None
    assert result.limits[0].conditional is True
    assert result.recommended_decision.value == 'NEEDS_REVIEW'


def test_decisive_ped_exclusion_precedes_unrelated_missing_documents(case_data):
    case_data['treatment']['pre_existing'] = True
    evidence = [dict(chunk_id='ped', text='Pre-existing diseases will not be covered until 48 months of continuous coverage.')]
    result = apply_evidence_gates(assessment(missing_evidence=['hospital registration']), evidence, ClaimCase.model_validate(case_data))
    assert result.recommended_decision.value == 'NOT_ADMISSIBLE'
    assert result.missing_evidence == []
    assert result.findings[0].evidence_ids == ['ped']


def test_portability_rejection_cannot_ignore_completed_prior_year(case_data):
    case_data['prior_insurer_continuous_years'] = 1
    case_data['prior_policy'] = dict(continuous_years=1, insurer_type='Indian individual health insurer',
                                   database_and_claim_history_received=True, previous_sum_insured_inr=500000)
    draft = assessment(recommended_decision='NOT_ADMISSIBLE', findings=[dict(
        dimension='waiting', statement='Cataract is excluded because current coverage is less than one year.',
        effect='excludes', evidence_ids=['prior'])])
    evidence = {'prior':dict(chunk_id='prior', text='The waiting period of 1 year will not apply if previously insured.')}
    assert any('prior coverage' in error for error in structural_errors(draft, evidence, ClaimCase.model_validate(case_data)))


@pytest.fixture
def client(monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'PolicyIndex', lambda settings: SimpleNamespace(chunks=[], policy_sha256='test'))
    monkeypatch.setenv('APP_API_TOKEN', '')
    with TestClient(main.app) as test_client:
        yield test_client


def test_api_malformed_request(client):
    response = client.post('/analyze', json={'case_id':'invalid'})
    assert response.status_code == 422
    assert all('input' not in e for e in response.json()['detail'])


def test_api_rejects_unknown_policy(client, case_data):
    case_data['policy_id'] = 'OTHER'
    assert client.post('/analyze', json=case_data).status_code == 422


def test_large_body_rejected(client):
    assert client.post('/analyze', content='x' * 100001).status_code == 413


def test_optional_token_enforced(client, monkeypatch, case_data):
    monkeypatch.setenv('APP_API_TOKEN', 'test-reviewer-token')
    assert client.post('/analyze', json=case_data).status_code == 401


def test_frontend_and_cases(client):
    assert client.get('/').status_code == 200
    assert len(client.get('/cases').json()) == 12
    assert client.get('/policy').headers['content-type'] == 'application/pdf'
