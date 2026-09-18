import json
from types import SimpleNamespace

from app.config import ROOT, get_settings
from app.models import Assessment, ClaimCase, Investigation, SemanticAudit
from app.workflow import ClaimWorkflow


class FakeIndex:
    policy_sha256 = 'test-sha'
    embedding_model = 'test-embedding'
    reranker_model = 'test-reranker'

    def investigate(self, queries):
        return [dict(chunk_id='known', text='Evidence', section='Test', pages=[7], source='policy.pdf')], []


class ScriptedModel:
    def __init__(self, mode):
        self.mode = mode
        self.assessments = 0

    def with_structured_output(self, schema, **kwargs):
        def invoke(messages):
            if self.mode == 'outage':
                raise TimeoutError('simulated')
            if schema is Investigation:
                return Investigation(dimensions=['coverage'], queries=['coverage'])
            if schema is Assessment:
                self.assessments += 1
                return Assessment(recommended_decision='ADMISSIBLE', findings=[dict(
                    dimension='coverage', statement='Supported', effect='supports', evidence_ids=['known'],
                )], next_action='Review')
            supported = self.mode == 'pass' or (self.mode == 'retry' and self.assessments == 2)
            return SemanticAudit(items=[dict(statement_index=0, supported=supported, explanation='Unsupported' if not supported else '')],
                                 decision_supported=supported, decision_issue='' if supported else 'Unsupported decision')
        return SimpleNamespace(invoke=invoke)


def run(mode):
    model = ScriptedModel(mode)
    flow = ClaimWorkflow(get_settings().model_copy(update={'model_min_interval_seconds':0}), FakeIndex(), model=model)
    case = ClaimCase.model_validate(json.loads((ROOT / 'data/candidate_data/public_test_cases.json').read_text())[0])
    return flow.analyze(case), model


def test_validation_retries_once_then_abstains():
    result, model = run('fail')
    assert model.assessments == 2
    assert result.decision.value == 'NEEDS_REVIEW'
    assert result.reason_code == 'VALIDATION_FAILED'
    assert result.key_findings == []
    assert result.citations == []
    assert result.validation.status == 'FAIL'


def test_corrected_assessment_can_pass():
    result, model = run('retry')
    assert model.assessments == 2
    assert result.validation.status == 'PASS'
    assert result.decision.value == 'ADMISSIBLE'
    assert len(result.citations) == 1


def test_outage_not_misreported_as_policy_abstention():
    result, _ = run('outage')
    assert result.reason_code == 'MODEL_OR_TOOL_UNAVAILABLE'
    assert result.validation.status == 'UNAVAILABLE'
    assert result.confidence == 0
