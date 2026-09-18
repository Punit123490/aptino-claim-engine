# Policy Review architecture and design

## Objective and boundaries

The service assesses synthetic health-insurance claims against one supplied policy. It prioritizes inspectable evidence and appropriate abstention over producing a definitive answer for every input. The source PDF is the authority; neither external insurance knowledge nor a case's requested conclusion creates a rule.

The implementation uses Python, FastAPI, LangChain's Gemini integration and LangGraph. FastAPI also serves a small browser interface, allowing the frontend and API to share a deployment and avoiding an extra build system. The source cases remain immutable and candidate-created cases are stored separately.

## Agent boundaries and structured state

The Case Analysis Agent uses Gemini to identify dimensions and generate targeted queries. It outputs an Investigation schema, not a decision. The Policy Evidence Agent executes local retrieval tools. It supplements the plan with mandatory coverage, waiting-period and expense searches, and adds domiciliary or day-care searches when relevant. Its output is ranked evidence with source metadata and query-level scores.

The Coverage and Exclusion Agent receives the claim, plan and retrieved clauses. It outputs an Assessment schema containing findings, effects, cited chunk IDs, fact paths, conditional limits, missing evidence and a recommended status. The Validation Agent checks that IDs exist, arithmetic respects the stated bounds, and final statuses do not conflict with missing evidence. A separate Gemini call audits each numbered statement against its cited clauses and the actual facts.

Validation failure causes one bounded correction pass. A second failure or a provider error goes to review. The Decision Agent applies this release gate deterministically. Unsupported drafts are omitted from final findings; defects remain visible in the trace. Model/tool outages have a different reason code from policy uncertainty. Typed graph state carries case, plan, evidence, searches, assessment, audit, attempts and action trace.

## Retrieval and provenance

The PDF is extracted in visual layout order. Definitions, numbered clauses, NB provisions and paragraph boundaries determine chunks; a clause can span pages. This fixes page 8's content-stream ordering and keeps the domiciliary parent with its numbered conditions on page 10. Every chunk retains its section, page list, source filename and stable hash-derived ID.

BGE-small produces local dense embeddings and BM25 supplies lexical scores. Each query retrieves twelve candidates per channel. Reciprocal rank fusion with a constant of sixty combines ranks without mixing incomparable raw scores. A TinyBERT cross-encoder reranks up to eighteen candidates, then four are retained per query. NumPy exact cosine search is sufficient for this small corpus. The vector cache includes the policy fingerprint and is checked against current chunk IDs.

The API includes every retrieval query and rank/score metadata. Citations expand chunk IDs into exact source text and page references. The browser links directly to the policy page. Action traces contain tools, result counts, validation findings and timings, without hidden chain-of-thought.

## Reliability and interpretation

Unknown facts remain unknown. Network membership alone does not establish the policy's hospital definition, and document filenames do not establish their contents. A decisive exclusion can support rejection despite unrelated missing documents; an approval cannot ignore unresolved material conditions. Expense caps may be shown conditionally while payment remains undecided.

Three policy pitfalls are explicit: the 75% provision requires agreed package charges; cancer does not itself establish purchase of the optional critical-illness extension; an experimental-treatment definition is not automatically a standalone exclusion. The source's ambiguous normal-room basis and absent day-care annexure are documented limitations. Confidence is a fixed evidence-completeness heuristic, not a calibrated probability.

## Evaluation and deployment trade-offs

Evaluation covers all twelve public claims and nine additional claims with separate policy-derived reference outcomes. The harness distinguishes provider/validation failures from valid abstention, and reports decision success, pooled evidence recall, citation identity, validator support, abstention and latency. The reference outcomes are candidate-authored, not insurer labels. Model validation cannot substitute for independent human entailment review.

The Docker image includes the public retrieval models and starts one API process on port 7860. Secrets are environment variables; request size and review concurrency are bounded. Local CPU retrieval avoids embedding-provider costs, but increases memory and startup requirements. A single service simplifies same-day deployment. The next improvements would be external expert labels, a held-out policy set, document-content verification, stronger arithmetic derivation checks, and an independently calibrated confidence/abstention model.
