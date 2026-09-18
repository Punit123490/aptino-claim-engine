"""Reproducible live evaluation. No recorded answers are used by the application."""
import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import ROOT, get_settings
from app.models import ClaimCase
from app.retrieval import PolicyIndex
from app.workflow import ClaimWorkflow


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def normalize(text):
    return ' '.join(text.lower().split())


def metrics_for(result, expected, index):
    cited = result['citations']
    known = index.by_id
    valid = sum(c['chunk_id'] in known and c['quote'] == known[c['chunk_id']].text
                and c['pages'] == known[c['chunk_id']].pages for c in cited)
    retrieved_ids = {r['chunk_id'] for q in result['retrieval']['queries'] for r in q['results']}
    anchor_hits = []
    for anchor in expected['evidence_anchors']:
        relevant = {c.chunk_id for c in index.chunks if normalize(anchor) in normalize(c.text)}
        if not relevant:
            raise ValueError(f'Unmatched gold anchor for {expected["case_id"]}: {anchor}')
        anchor_hits.append(bool(relevant & retrieved_ids))
    service_ok = result['reason_code'] != 'MODEL_OR_TOOL_UNAVAILABLE'
    # An outage or validation fallback must never count as a correct abstention.
    validated = result['validation']['status'] == 'PASS'
    return {
        'case_id': result['case_id'], 'expected': expected['decision'], 'actual': result['decision'],
        'success': result['decision'] == expected['decision'] and service_ok and validated,
        'service_ok': service_ok, 'validated': validated,
        'pooled_evidence_recall_at_4': sum(anchor_hits) / len(anchor_hits),
        'citation_identity_correct': valid, 'citation_count': len(cited),
        'validator_supported': sum(a['supported'] for a in result['validation']['semantic_checks']),
        'validator_checked': len(result['validation']['semantic_checks']),
        'elapsed_ms': result['elapsed_ms'], 'reason_code': result['reason_code'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'evaluation/results')
    parser.add_argument('--cases', nargs='*', help='Optional case IDs for a focused run')
    parser.add_argument('--resume', action='store_true', help='Reuse already saved results; reported explicitly')
    parser.add_argument('--pause', type=float, default=2, help='Seconds between cases for provider quota')
    args = parser.parse_args()
    settings = get_settings()
    if not settings.google_api_key.get_secret_value():
        raise SystemExit('Set GOOGLE_API_KEY before running the live evaluation.')
    public_path = ROOT / 'data/candidate_data/public_test_cases.json'
    cases = read(public_path) + read(ROOT / 'evaluation/additional_cases.json')
    gold = {x['case_id']: x for x in read(ROOT / 'evaluation/expected_outcomes.json')}
    if args.cases:
        cases = [c for c in cases if c['case_id'] in args.cases]
    args.output.mkdir(parents=True, exist_ok=True)
    print('Loading policy index and retrieval models...', flush=True)
    index = PolicyIndex(settings)
    print(f'Index ready: {len(index.chunks)} clauses. Running {len(cases)} cases.', flush=True)
    workflow = ClaimWorkflow(settings, index)
    rows, reused = [], []
    for case in cases:
        result_path = args.output / 'cases' / f'{case["case_id"]}.json'
        if args.resume and result_path.exists():
            result = read(result_path)
            reused.append(case['case_id'])
        else:
            print(f'Analyzing {case["case_id"]}...', flush=True)
            result = workflow.analyze(ClaimCase.model_validate(case)).model_dump(mode='json')
            save(result_path, result)
            time.sleep(args.pause)
        row = metrics_for(result, gold[case['case_id']], index)
        rows.append(row)
        print(f'{row["case_id"]}: {row["actual"]} | expected={row["expected"]} | success={row["success"]} | validation={result["validation"]["status"]}', flush=True)
    total = len(rows)
    valid_rows = [r for r in rows if r['validated'] and r['service_ok']]
    expected_review = [r for r in rows if r['expected'] == 'NEEDS_REVIEW']
    predicted_review = [r for r in valid_rows if r['actual'] == 'NEEDS_REVIEW']
    true_review = sum(r['actual'] == 'NEEDS_REVIEW' and r['validated'] and r['service_ok'] for r in expected_review)
    citation_count = sum(r['citation_count'] for r in rows)
    checked = sum(r['validator_checked'] for r in rows)
    summary = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'model': settings.gemini_model,
        'policy_sha256': index.policy_sha256, 'public_cases_sha256': hashlib.sha256(public_path.read_bytes()).hexdigest(),
        'case_count': total, 'public_count': sum(r['case_id'].startswith('PUB') for r in rows),
        'candidate_count': sum(r['case_id'].startswith('CAND') for r in rows),
        'accuracy': sum(r['success'] for r in rows) / total if total else None,
        'public_accuracy': sum(r['success'] for r in rows if r['case_id'].startswith('PUB')) / max(1,sum(r['case_id'].startswith('PUB') for r in rows)),
        'candidate_accuracy': sum(r['success'] for r in rows if r['case_id'].startswith('CAND')) / max(1,sum(r['case_id'].startswith('CAND') for r in rows)),
        'service_failures': sum(not r['service_ok'] for r in rows),
        'validation_pass_rate': len(valid_rows) / total if total else None,
        'mean_pooled_evidence_recall_at_4': sum(r['pooled_evidence_recall_at_4'] for r in rows) / total if total else None,
        'citation_identity_accuracy': sum(r['citation_identity_correct'] for r in rows) / citation_count if citation_count else None,
        'model_validator_support_rate': sum(r['validator_supported'] for r in rows) / checked if checked else None,
        'abstention_recall': true_review / len(expected_review) if expected_review else None,
        'abstention_precision': true_review / len(predicted_review) if predicted_review else None,
        'median_latency_seconds': sorted(r['elapsed_ms'] for r in rows)[total//2] / 1000 if total else None,
        'reused_results': reused,
        'limitations': [
            'Expected decisions are candidate-authored policy interpretations, not insurer labels.',
            'Pooled recall counts gold evidence anchors found across all queries, each returning at most four results; it is not single-query recall@4.',
            'Citation identity checks provenance only. The model validator support rate is not independent human entailment accuracy.',
            'Development cases and prompts were inspected during implementation; this is not a blind benchmark.',
        ],
    }
    save(args.output / 'summary.json', summary)
    save(args.output / 'case_metrics.json', rows)
    with (args.output / 'case_metrics.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['case_id'])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
