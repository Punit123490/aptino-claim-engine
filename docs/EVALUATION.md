# Evaluation and failure analysis

Measured model: `gemini-3.1-flash-lite`. Report generated from saved results at 2026-09-19T02:48:49.747530+00:00.

## Scope and expected outcomes

The suite includes all 12 unchanged supplied claims and 9 separate candidate-created cases. The company did not provide answer labels. Reference decisions were established by reading the supplied policy and recording the rationale and evidence anchors in `evaluation/expected_outcomes.json`. These are candidate interpretations, not insurer adjudications.

A strict evidence convention is used: explicit input facts are accepted, but hospital names, network status and document filenames do not establish unprovided contents. Consequently several otherwise plausible public claims need review. The additional cases provide explicit evidence so that admissible, limited, partial, rejected and review outcomes can all be tested.

The experimental-treatment case is not automatically rejected: a definition alone is not an operative exclusion. The day-care annexure is absent from the supplied PDF. The first-year waiting waiver considers eligible completed prior years; it does not require another completed current-policy year. These interpretation choices are visible rather than hidden in expected labels.

## Measured results

| Measure | Result |
|---|---:|
| Evaluated cases | 21 |
| Exact decision success, including validation | 100.0% |
| Public-case success | 100.0% |
| Additional-case success | 100.0% |
| Validation pass rate | 100.0% |
| Mean pooled evidence recall, per-query k=4 | 94.4% |
| Citation provenance identity | 100.0% |
| Model-validator statement support | 100.0% |
| Abstention precision | 100.0% |
| Abstention recall | 100.0% |
| Service failures | 0 |
| Median local latency | 38.1 seconds |

Decision success requires both the expected status and PASS validation; an API outage returning NEEDS_REVIEW is a failure. Pooled evidence recall measures whether the expected clause anchors occur anywhere in the union of results from the investigation queries, each capped at four results. It is not single-query recall@4.

Citation provenance compares source IDs, text and page lists to the extracted policy index. Semantic support is checked by the validation agent, which shares a model family with the coverage agent. Its score is therefore an automated check, not independent human citation accuracy. Development cases were inspected while improving the implementation, so these scores are not a blind generalization estimate.

## Case-level results

| Case | Expected | Actual | Validated success | Evidence recall |
|---|---|---|---|---:|
| PUB-001 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-002 | NOT_ADMISSIBLE | NOT_ADMISSIBLE | Yes | 100.0% |
| PUB-003 | NOT_ADMISSIBLE | NOT_ADMISSIBLE | Yes | 100.0% |
| PUB-004 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-005 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-006 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-007 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-008 | NOT_ADMISSIBLE | NOT_ADMISSIBLE | Yes | 100.0% |
| PUB-009 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-010 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-011 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| PUB-012 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 66.7% |
| CAND-001 | ADMISSIBLE | ADMISSIBLE | Yes | 66.7% |
| CAND-002 | ADMISSIBLE_WITH_LIMITS | ADMISSIBLE_WITH_LIMITS | Yes | 100.0% |
| CAND-003 | NOT_ADMISSIBLE | NOT_ADMISSIBLE | Yes | 100.0% |
| CAND-004 | NEEDS_REVIEW | NEEDS_REVIEW | Yes | 100.0% |
| CAND-005 | NOT_ADMISSIBLE | NOT_ADMISSIBLE | Yes | 100.0% |
| CAND-006 | PARTIALLY_ADMISSIBLE | PARTIALLY_ADMISSIBLE | Yes | 100.0% |
| CAND-007 | ADMISSIBLE | ADMISSIBLE | Yes | 50.0% |
| CAND-008 | NOT_ADMISSIBLE | NOT_ADMISSIBLE | Yes | 100.0% |
| CAND-009 | ADMISSIBLE | ADMISSIBLE | Yes | 100.0% |

## Reference rationale by case

- **PUB-001**: Hospital definition and pre/post expense timing are not established; room basis is ambiguous.
- **PUB-002**: Claim occurs during the first 30 days without qualifying continuity.
- **PUB-003**: 27 months is below the 48-month pre-existing disease waiting period, with no prior insurer credit.
- **PUB-004**: Home-treatment trigger is asserted, but treatment duration and diagnosis exclusion checks are unresolved.
- **PUB-005**: Eye surgery has a short-stay provision, but hospital-definition and pre/post evidence remain incomplete.
- **PUB-006**: Hospital registration and medical necessity are explicitly unknown; itemized bill absent.
- **PUB-007**: General expense category caps apply; cancer does not establish optional additional cover, and eligibility/timing evidence is missing.
- **PUB-008**: The supplied treatment is cosmetic surgery for a cosmetic condition, matching the operative exclusion.
- **PUB-009**: 30/60-day windows and same condition are asserted, but hospital qualification remains unestablished.
- **PUB-010**: One completed prior eligible year and received claim history can waive the first-year cataract wait; hospital qualification still missing.
- **PUB-011**: Non-network status is not itself exclusion; neither registration nor minimum hospital criteria are established.
- **PUB-012**: Experimental definition alone is not an operative exclusion; approval/established-practice and eligibility evidence remain unresolved.
- **CAND-001**: Explicit eligibility facts, no waiting/exclusion trigger and expenses below relevant category caps.
- **CAND-002**: Doctor category capped at 125000 and medicines/diagnostics at 200000 for 500000 basic sum insured.
- **CAND-003**: Pre-existing condition at 12 months, without prior credit.
- **CAND-004**: Registration unknown and complete alternative hospital criteria absent.
- **CAND-005**: An explicitly outpatient consultation falls within the outpatient exclusion.
- **CAND-006**: Core inpatient claim supported; 31-day pre and 61-day post expenses exceed policy windows.
- **CAND-007**: Same supported claim as CAND-001; irrelevant text must not change outcome.
- **CAND-008**: Domiciliary treatment lasting two days falls under the not-exceeding-three-days provision.
- **CAND-009**: Explicit day-care and hospital evidence plus qualifying prior year/received history; claimed categories below caps.

## Observed failures and changes

1. **Quota failures were mistaken for no evidence at the transport level.** The initial Gemini 2.5 Flash run hit the account request limit. Responses correctly carried MODEL_OR_TOOL_UNAVAILABLE and were scored as failures. Added shared call pacing and one bounded quota retry, then switched the configured model to the available Gemini 3.1 Flash-Lite and reran. Evidence: `evaluation/failure_examples/quota_failure.json`.

2. **A broad expense query missed ambulance evidence and the model filled the gap.** The first PUB-001 assessment assumed general ambulance coverage without a citation and proposed a room amount despite ambiguous wording. The structural gate rejected it. Added a dedicated ambulance search, explicit hospital-evidence checks, and a rule that leaves ambiguous room calculations unset. Evidence: `evaluation/failure_examples/unsupported_assumptions.json`.

3. **Unrelated gaps overrode a decisive pre-existing-disease exclusion.** PUB-003 initially returned review even though the supplied pre-existing flag, 27 months and zero prior credit satisfied an exclusion. The model validator also accepted this over-abstention. Added a deterministic precedence check whose waiting duration is parsed from the retrieved clause, followed by the normal semantic audit. Evidence: `evaluation/failure_examples/over_abstention.json`.

4. **Both model roles misread portability.** PUB-010 was initially rejected because the model incorrectly demanded a full current-policy year despite one completed eligible prior year and received claim history. Added a retrieved-clause-derived waiver check to the coverage input and structural validation, so this mistaken rejection triggers correction. Evidence: `evaluation/failure_examples/portability_misinterpretation.json`.

Additional engineering changes: layout-mode PDF extraction restored page 8 reading order; clauses spanning pages 7–8 remain connected; domiciliary subconditions stay under their parent; embedding batches were reduced to control memory; expense category display labels are normalized before arithmetic validation.

## Reproduce and inspect

```bash
pytest -q
python -m scripts.evaluate --output evaluation/runs/fresh
```

The live command requires a Gemini key and sufficient quota. Each response includes the model, policy hash, retrieved evidence and complete action trace. The supplied public JSON checksum is recorded in summary.json. Use a fresh output directory without --resume to regenerate every result.

Focused regression reruns replace their case JSON files. `python -m scripts.evaluate --resume` recomputes the aggregate from all saved case files and explicitly lists reused IDs. This is how selective fixes can be combined without concealing cached results. The raw responses remain available for inspection.

## Remaining limitations

This small development suite does not establish production accuracy. Independent policy-expert labels, a genuinely held-out test set, document-content verification, independently judged entailment and calibrated uncertainty remain future work. The deterministic guards cover specific high-risk conditions in the assigned policy, not every possible insurance rule. Low-cost hosting can sleep, and provider quotas can still block requests.

Policy SHA256: `44899a612dfd1faba65cba00fa36a36841ea70a19b587cb0d12b34a08d61182d`

Original public JSON SHA256: `e5e286ddfd70bf4bd02ddba5d38afdf7a7fb80198cd9d0d3201c5ffe28266158`
