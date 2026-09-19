# Engineering verification

The test suite passes **25 tests** locally on Python 3.12. GitHub Actions is configured to run the same suite on Ubuntu for every push.

Run the deterministic tests with:

```bash
pytest -q
```

The tests do not require a Gemini key or model downloads. They cover:

* Validation of all 12 supplied cases.
* Negative, NaN and infinite expenses; inconsistent dates; tolerated non-critical fields.
* Preservation of cross-page day-care provisions and domiciliary exclusion context.
* Reciprocal rank fusion ordering.
* Missing/unknown citations, inconsistent amounts and unsupported final decisions.
* Hospital-evidence gates, room-billing ambiguity, decisive waiting-period precedence and partial component denials.
* Portability rejection that contradicts qualifying prior coverage.
* Invalid API requests, unknown policies, request-size limits and optional token protection.
* Bounded validation correction, fail-closed output and provider-outage classification.
* Availability of the frontend, supplied cases and policy PDF routes.

A live browser smoke test loaded the frontend, selected PUB-002, submitted it to `/analyze`, received NOT_ADMISSIBLE with PASS validation, displayed policy citations, and expanded the five-step execution trace. `/health` reported the configured model and 125 indexed clauses. This was a real Gemini request, not a mocked response.

The design note was rendered and visually inspected as a two-page PDF. The delivery archive is separately scanned to exclude the Gemini key, `.env`, model caches, virtual environments and Git internals.

The model evaluation is distinct from these engineering tests. Its measured outcomes and limitations are in `docs/EVALUATION.md` and `evaluation/results/`.
