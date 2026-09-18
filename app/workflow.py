import json
import logging
import time
import threading
from typing import TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.guards import apply_evidence_gates, material_statements, structural_errors, verified_policy_checks
from app.models import (
    Assessment, Citation, ClaimCase, ClaimResult, Decision, Investigation,
    SemanticAudit, TraceEvent, ValidationReport,
)
from app.prompts import COVERAGE, PLANNER, VALIDATOR
from app.retrieval import PolicyIndex

logger = logging.getLogger(__name__)
logging.getLogger('google_genai').setLevel(logging.ERROR)
logging.getLogger('httpx').setLevel(logging.WARNING)
_model_lock = threading.Lock()
_last_call = 0.0


class State(TypedDict, total=False):
    case: dict
    plan: dict
    evidence: list[dict]
    searches: list[dict]
    assessment: dict
    validation: dict
    audit_errors: list[str]
    trace: list[dict]
    attempts: int
    error: str
    result: dict
    started: float


def elapsed(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def event(state: State, agent: str, action: str, start: float, **details) -> list[dict]:
    return [*state.get('trace', []), TraceEvent(
        agent=agent, action=action, elapsed_ms=elapsed(start), details=details,
    ).model_dump()]


class ClaimWorkflow:
    def __init__(self, settings: Settings, index: PolicyIndex, model=None):
        self.settings, self.index = settings, index
        self.model = model or ChatGoogleGenerativeAI(
            model=settings.gemini_model, google_api_key=settings.google_api_key.get_secret_value(),
            temperature=0, timeout=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries, thinking_budget=0,
        )
        graph = StateGraph(State)
        graph.add_node('case_analysis', self.plan)
        graph.add_node('policy_evidence', self.retrieve)
        graph.add_node('coverage_exclusion', self.assess)
        graph.add_node('validation', self.validate)
        graph.add_node('decision', self.decide)
        graph.add_edge(START, 'case_analysis')
        graph.add_conditional_edges('case_analysis', lambda s: 'decision' if s.get('error') else 'policy_evidence')
        graph.add_conditional_edges('policy_evidence', lambda s: 'decision' if s.get('error') else 'coverage_exclusion')
        graph.add_conditional_edges('coverage_exclusion', lambda s: 'decision' if s.get('error') else 'validation')
        graph.add_conditional_edges('validation', self.route_validation)
        graph.add_edge('decision', END)
        self.graph = graph.compile()

    def call(self, schema, instruction: str, payload: dict):
        global _last_call
        runnable = self.model.with_structured_output(schema, method='json_schema')
        for attempt in range(2):
            with _model_lock:
                delay = self.settings.model_min_interval_seconds - (time.monotonic() - _last_call)
                if delay > 0:
                    time.sleep(delay)
                _last_call = time.monotonic()
            try:
                return runnable.invoke([
                    ('system', instruction), ('human', json.dumps(payload, ensure_ascii=False)),
                ])
            except Exception as exc:
                if attempt == 0 and 'RateLimit' in type(exc).__name__:
                    time.sleep(45)
                    continue
                raise

    def failure(self, state, agent, start, exc):
        # Provider exceptions can contain request details; never log their raw string.
        logger.warning('%s failed (%s)', agent, type(exc).__name__)
        return {'error': 'MODEL_OR_TOOL_UNAVAILABLE', 'trace': event(
            state, agent, 'Could not complete; routed to review', start, error_type=type(exc).__name__,
        )}

    def plan(self, state: State):
        start = time.perf_counter()
        try:
            plan = self.call(Investigation, PLANNER, {'case': state['case']})
            return {'plan': plan.model_dump(), 'trace': event(
                state, 'Case Analysis', 'Identified decision dimensions and search plan', start,
                dimensions=plan.dimensions, queries=plan.queries,
            )}
        except Exception as exc:
            return self.failure(state, 'Case Analysis', start, exc)

    def retrieve(self, state: State):
        start = time.perf_counter()
        try:
            case = state['case']
            # Required dimensions prevent a planner from ignoring inconvenient policy clauses.
            queries = [
                'Hospital means institution registered OR all minimum criteria nursing staff beds',
                'Medically Necessary treatment prescribed Medical Practitioner',
                'What we cover room boarding nursing doctor fees medicines diagnostic sub limits',
                '30 days waiting period first year diseases prior insurer completed years claim history',
                *state['plan']['queries'][:6],
            ]
            treatment = case['treatment']
            if treatment['type'] == 'domiciliary':
                queries.extend(['Domiciliary treatment home hospital unavailable definition 20% sub limit',
                                'Domiciliary exclusions treatment not exceeding three days diseases'])
            if treatment.get('pre_existing'):
                queries.append('Pre-existing diseases 48 months continuous coverage previous sum insured')
            if treatment['admission_hours'] < 24 and treatment['type'] != 'domiciliary':
                queries.append('NB4 Eye Surgery 24 hours waived specialised infrastructure technological advances')
            if any(case['expenses_inr'].get(k, 0) for k in ('pre_hospitalization', 'post_hospitalization', 'ambulance')):
                queries.append('Pre-Hospitalisation 30 days Post Hospitalisation 60 days same condition')
            if case['expenses_inr'].get('ambulance', 0):
                queries.append('Ambulance charges in connection with any admissible claim limited to 1000')
            evidence, searches = self.index.investigate(queries)
            return {'evidence': evidence, 'searches': searches, 'trace': event(
                state, 'Policy Evidence', 'Dense + BM25 search, reciprocal rank fusion, cross-encoder reranking',
                start, query_count=len(searches), result_count=len(evidence), per_query_top_k=4,
                chunk_ids=[x['chunk_id'] for x in evidence],
            )}
        except Exception as exc:
            return self.failure(state, 'Policy Evidence', start, exc)

    def assess(self, state: State):
        start = time.perf_counter()
        try:
            assessment = self.call(Assessment, COVERAGE, {
                'case': state['case'], 'investigation': state['plan'],
                'evidence': [{k: e[k] for k in ('chunk_id', 'text', 'section', 'pages')} for e in state['evidence']],
                'previous_audit_defects': state.get('audit_errors', []),
                'verified_policy_checks': verified_policy_checks(state['evidence'], ClaimCase.model_validate(state['case'])),
            })
            assessment = apply_evidence_gates(assessment, state['evidence'], ClaimCase.model_validate(state['case']))
            return {'assessment': assessment.model_dump(mode='json'), 'attempts': state.get('attempts', 0) + 1,
                    'trace': event(state, 'Coverage & Exclusion', 'Assessed eligibility, exceptions and limits',
                                   start, findings=len(assessment.findings), attempt=state.get('attempts', 0) + 1)}
        except Exception as exc:
            return self.failure(state, 'Coverage & Exclusion', start, exc)

    def validate(self, state: State):
        start = time.perf_counter()
        assessment = Assessment.model_validate(state['assessment'])
        evidence = {e['chunk_id']: e for e in state['evidence']}
        errors = structural_errors(assessment, evidence, ClaimCase.model_validate(state['case']))
        structural_pass = not errors
        try:
            statements = material_statements(assessment)
            audit = self.call(SemanticAudit, VALIDATOR, {
                'case': state['case'], 'decision': assessment.recommended_decision.value,
                'missing_evidence': assessment.missing_evidence,
                'statements': [{**s, 'cited_excerpts': [evidence[i] for i in s['evidence_ids'] if i in evidence]}
                               for s in statements],
            })
            indices = [x.statement_index for x in audit.items]
            if sorted(indices) != list(range(len(statements))):
                errors.append('Validator did not audit every statement exactly once')
            errors.extend(x.explanation for x in audit.items if not x.supported)
            if not audit.decision_supported:
                errors.append(audit.decision_issue or 'Decision is not supported')
            validation = ValidationReport(status='FAIL' if errors else 'PASS', unsupported_claims=errors,
                                          structural_checks_passed=structural_pass, semantic_checks=audit.items)
            return {'validation': validation.model_dump(), 'audit_errors': errors, 'trace': event(
                state, 'Validation', 'Checked citation identity, amounts and semantic support', start,
                status=validation.status, checked_statements=len(audit.items), defects=errors,
            )}
        except Exception as exc:
            return self.failure(state, 'Validation', start, exc)

    @staticmethod
    def route_validation(state):
        if state.get('error'):
            return 'decision'
        if state['validation']['status'] == 'FAIL' and state.get('attempts', 0) < 2:
            return 'coverage_exclusion'
        return 'decision'

    def decide(self, state: State):
        start = time.perf_counter()
        failed = bool(state.get('error'))
        validation = ValidationReport.model_validate(state.get('validation', {'status': 'UNAVAILABLE'}))
        assessment = Assessment.model_validate(state['assessment']) if state.get('assessment') else None
        safe = not failed and validation.status == 'PASS' and assessment is not None
        decision = assessment.recommended_decision if safe else Decision.NEEDS_REVIEW
        # Unsupported draft assertions are not republished as final findings.
        findings = assessment.findings if safe else []
        limits = assessment.limits if safe else []
        missing = assessment.missing_evidence if safe else [
            'A complete, validated policy assessment is required before deciding this claim.'
        ]
        reason = state.get('error') or ('VALIDATION_FAILED' if not safe else
                                       'INSUFFICIENT_EVIDENCE' if decision == Decision.NEEDS_REVIEW else None)
        if failed:
            validation.status = 'UNAVAILABLE'
        citations = []
        evidence = {e['chunk_id']: e for e in state.get('evidence', [])}
        if safe:
            for statement in material_statements(assessment):
                for chunk_id in statement['evidence_ids']:
                    e = evidence[chunk_id]
                    citations.append(Citation(claim=statement['text'], source=e['source'], page=e['pages'][0],
                                              pages=e['pages'], section=e['section'], chunk_id=chunk_id, quote=e['text']))
        confidence = 0.0 if not safe else 0.5 if decision == Decision.NEEDS_REVIEW else 0.85
        trace = event(state, 'Decision', 'Applied validation gate and emitted structured result', start,
                      decision=decision.value, reason_code=reason)
        result = ClaimResult(
            case_id=state['case']['case_id'], decision=decision, reason_code=reason, confidence=confidence,
            key_findings=findings, applicable_limits=limits, missing_evidence=missing,
            next_action=assessment.next_action if safe else 'Check service configuration or review the validation trace, then retry.',
            citations=citations, validation=validation, trace=trace,
            retrieval={'queries': state.get('searches', []), 'unique_chunks': len(evidence),
                       'embedding_model': self.index.embedding_model, 'reranker_model': self.index.reranker_model},
            model=self.settings.gemini_model, policy_sha256=self.index.policy_sha256,
            elapsed_ms=elapsed(state['started']),
        )
        return {'result': result.model_dump(mode='json'), 'trace': trace}

    def analyze(self, case: ClaimCase) -> ClaimResult:
        state = self.graph.invoke({'case': case.model_dump(mode='json'), 'trace': [], 'attempts': 0,
                                   'started': time.perf_counter()}, config={'recursion_limit': 15})
        return ClaimResult.model_validate(state['result'])
