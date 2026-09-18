"""Build the human-readable report from saved measurements, never invented scores."""
import json
from pathlib import Path

from app.config import ROOT


def main():
    result_dir = ROOT / 'evaluation/results'
    summary = json.loads((result_dir / 'summary.json').read_text())
    rows = json.loads((result_dir / 'case_metrics.json').read_text())
    gold = {x['case_id']: x for x in json.loads((ROOT / 'evaluation/expected_outcomes.json').read_text())}
    if summary['case_count'] != 21:
        raise SystemExit('The final report requires all 21 cases. Run evaluate --resume after focused reruns.')
    def percent(value):
        return 'Not measurable' if value is None else f'{100*value:.1f}%'
    lines = [
        '# Evaluation and failure analysis', '',
        f"Measured model: `{summary['model']}`. Report generated from saved results at {summary['generated_at_utc']}.", '',
        '## Scope and expected outcomes', '',
        'The suite includes all 12 unchanged supplied claims and 9 separate candidate-created cases. The company did not provide answer labels. Reference decisions were established by reading the supplied policy and recording the rationale and evidence anchors in `evaluation/expected_outcomes.json`. These are candidate interpretations, not insurer adjudications.', '',
        'A strict evidence convention is used: explicit input facts are accepted, but hospital names, network status and document filenames do not establish unprovided contents. Consequently several otherwise plausible public claims need review. The additional cases provide explicit evidence so that admissible, limited, partial, rejected and review outcomes can all be tested.', '',
        'The experimental-treatment case is not automatically rejected: a definition alone is not an operative exclusion. The day-care annexure is absent from the supplied PDF. The first-year waiting waiver considers eligible completed prior years; it does not require another completed current-policy year. These interpretation choices are visible rather than hidden in expected labels.', '',
        '## Measured results', '',
        '| Measure | Result |', '|---|---:|',
        f"| Evaluated cases | {summary['case_count']} |",
        f"| Exact decision success, including validation | {percent(summary['accuracy'])} |",
        f"| Public-case success | {percent(summary['public_accuracy'])} |",
        f"| Additional-case success | {percent(summary['candidate_accuracy'])} |",
        f"| Validation pass rate | {percent(summary['validation_pass_rate'])} |",
        f"| Mean pooled evidence recall, per-query k=4 | {percent(summary['mean_pooled_evidence_recall_at_4'])} |",
        f"| Citation provenance identity | {percent(summary['citation_identity_accuracy'])} |",
        f"| Model-validator statement support | {percent(summary['model_validator_support_rate'])} |",
        f"| Abstention precision | {percent(summary['abstention_precision'])} |",
        f"| Abstention recall | {percent(summary['abstention_recall'])} |",
        f"| Service failures | {summary['service_failures']} |",
        f"| Median local latency | {summary['median_latency_seconds']:.1f} seconds |", '',
        'Decision success requires both the expected status and PASS validation; an API outage returning NEEDS_REVIEW is a failure. Pooled evidence recall measures whether the expected clause anchors occur anywhere in the union of results from the investigation queries, each capped at four results. It is not single-query recall@4.', '',
        'Citation provenance compares source IDs, text and page lists to the extracted policy index. Semantic support is checked by the validation agent, which shares a model family with the coverage agent. Its score is therefore an automated check, not independent human citation accuracy. Development cases were inspected while improving the implementation, so these scores are not a blind generalization estimate.', '',
        '## Case-level results', '', '| Case | Expected | Actual | Validated success | Evidence recall |', '|---|---|---|---|---:|',
    ]
    for row in rows:
        lines.append(f"| {row['case_id']} | {row['expected']} | {row['actual']} | {'Yes' if row['success'] else 'No'} | {percent(row['pooled_evidence_recall_at_4'])} |")
    lines += ['', '## Reference rationale by case', '']
    for row in rows:
        lines.append(f"- **{row['case_id']}**: {gold[row['case_id']]['rationale']}")
    lines += ['', '## Observed failures and changes', '',
        '1. **Quota failures were mistaken for no evidence at the transport level.** The initial Gemini 2.5 Flash run hit the account request limit. Responses correctly carried MODEL_OR_TOOL_UNAVAILABLE and were scored as failures. Added shared call pacing and one bounded quota retry, then switched the configured model to the available Gemini 3.1 Flash-Lite and reran. Evidence: `evaluation/failure_examples/quota_failure.json`.', '',
        '2. **A broad expense query missed ambulance evidence and the model filled the gap.** The first PUB-001 assessment assumed general ambulance coverage without a citation and proposed a room amount despite ambiguous wording. The structural gate rejected it. Added a dedicated ambulance search, explicit hospital-evidence checks, and a rule that leaves ambiguous room calculations unset. Evidence: `evaluation/failure_examples/unsupported_assumptions.json`.', '',
        '3. **Unrelated gaps overrode a decisive pre-existing-disease exclusion.** PUB-003 initially returned review even though the supplied pre-existing flag, 27 months and zero prior credit satisfied an exclusion. The model validator also accepted this over-abstention. Added a deterministic precedence check whose waiting duration is parsed from the retrieved clause, followed by the normal semantic audit. Evidence: `evaluation/failure_examples/over_abstention.json`.', '',
        '4. **Both model roles misread portability.** PUB-010 was initially rejected because the model incorrectly demanded a full current-policy year despite one completed eligible prior year and received claim history. Added a retrieved-clause-derived waiver check to the coverage input and structural validation, so this mistaken rejection triggers correction. Evidence: `evaluation/failure_examples/portability_misinterpretation.json`.', '',
        'Additional engineering changes: layout-mode PDF extraction restored page 8 reading order; clauses spanning pages 7–8 remain connected; domiciliary subconditions stay under their parent; embedding batches were reduced to control memory; expense category display labels are normalized before arithmetic validation.', '',
        '## Reproduce and inspect', '',
        '```bash', 'pytest -q', 'python -m scripts.evaluate --output evaluation/runs/fresh', '```', '',
        'The live command requires a Gemini key and sufficient quota. Each response includes the model, policy hash, retrieved evidence and complete action trace. The supplied public JSON checksum is recorded in summary.json. Use a fresh output directory without --resume to regenerate every result.', '',
        'Focused regression reruns replace their case JSON files. `python -m scripts.evaluate --resume` recomputes the aggregate from all saved case files and explicitly lists reused IDs. This is how selective fixes can be combined without concealing cached results. The raw responses remain available for inspection.', '',
        '## Remaining limitations', '',
        'This small development suite does not establish production accuracy. Independent policy-expert labels, a genuinely held-out test set, document-content verification, independently judged entailment and calibrated uncertainty remain future work. The deterministic guards cover specific high-risk conditions in the assigned policy, not every possible insurance rule. Low-cost hosting can sleep, and provider quotas can still block requests.', '',
        f"Policy SHA256: `{summary['policy_sha256']}`", '',
        f"Original public JSON SHA256: `{summary['public_cases_sha256']}`", '',
    ]
    (ROOT / 'docs/EVALUATION.md').write_text('\n'.join(lines), encoding='utf-8')
    print('Wrote docs/EVALUATION.md from measured results.')


if __name__ == '__main__':
    main()
