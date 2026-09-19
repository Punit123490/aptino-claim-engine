# Review preparation

## A short explanation of the system

The application accepts a structured synthetic claim and reviews it against one supplied insurance policy. A planning agent identifies the relevant questions. A retrieval specialist combines semantic search and keyword search, then reranks the candidate clauses. A coverage specialist produces structured findings. Validation checks the citations, numbers and conclusions before a deterministic decision gate releases the result. If a material condition cannot be established, the result asks for review and identifies the missing evidence.

## Code paths to understand

1. `app/main.py`: request validation, policy selection, service readiness and API response.
2. `app/ingestion.py`: layout-aware extraction, clause boundaries, cross-page text and stable IDs.
3. `app/retrieval.py`: dense/BM25 retrieval, reciprocal rank fusion and cross-encoder reranking.
4. `app/workflow.py`: LangGraph nodes, typed state, one correction pass and final release gate.
5. `app/guards.py`: mechanical citation/amount checks and high-risk evidence/precedence checks.
6. `scripts/evaluate.py`: policy-derived references, real model calls, metrics and failure accounting.

## Questions you should be able to answer

**Why hybrid retrieval?** Semantic search handles paraphrases; BM25 preserves exact policy terms, numbers and names. Reciprocal rank fusion combines their rankings without treating their raw scores as comparable.

**Why rerank after fusion?** The cross-encoder evaluates a query and candidate clause together. It is slower than vector search, so it runs only on a small fused candidate set.

**Why no external vector database?** There is one small policy corpus. Exact cosine search over a persisted NumPy matrix is sufficient and easier to deploy. A larger multi-policy system would justify a dedicated store and richer filtering.

**What makes the agents distinct?** They have separate responsibilities and typed output schemas, not repeated copies of one prompt. Three roles use Gemini; evidence retrieval and decision release are tool-based or deterministic specialists.

**What happens when validation fails?** The coverage agent receives the defects and gets one correction attempt. If the result still fails, unsupported draft findings are withheld and the API returns NEEDS_REVIEW with VALIDATION_FAILED. Provider failures have a different reason code.

**Why do several supplied cases need review?** Their facts do not establish every required condition. A network flag is not proof of the hospital definition, and a document's filename does not reveal its contents. Conditional limits can still be explained while final eligibility remains unresolved.

**What is the biggest validation limitation?** Coverage and semantic validation use the same model family and can share mistakes. The portability failure demonstrates this. Deterministic checks help for selected conditions, but independent expert review is still needed for production use.

**Are the reported scores general accuracy?** No. They measure performance on the supplied and candidate-created development cases under documented reference interpretations. There are no company-provided labels and no blind held-out policy dataset.

**Does confidence mean an 85% payment probability?** No. The score is explicitly an uncalibrated evidence-completeness heuristic. Calibration would require a larger labeled dataset and statistical validation.

**What would you improve next?** Independent expected labels, additional policies, a held-out benchmark, document-content verification, more complete rule/amount checks, and confidence calibration. The current implementation intentionally favors a small inspectable deployment.

## Demonstration sequence

Start with a supplied waiting-period rejection and expand its policy citation. Then show an incomplete-evidence case and its requested documents. Finally upload one of the complete additional cases to show an approval or a category cap. Expand the execution trace and download a response. Discuss the observed failure examples openly and explain the specific fixes.

Read the actual final evaluation report before quoting any result. If asked about tooling or assistance, describe it accurately and focus on the decisions and code paths you understand.
