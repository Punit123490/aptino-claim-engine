# Submission checklist

## Required links

Before sending the submission, record the actual URLs in your email:

1. Public GitHub repository.
2. Live web application.
3. Live API documentation at the application's `/docs` URL.
4. Health endpoint at the application's `/health` URL.

Repository: https://github.com/Punit123490/aptino-claim-engine

Live application: https://aptino-policy-review.onrender.com  
API documentation: https://aptino-policy-review.onrender.com/docs  
Health endpoint: https://aptino-policy-review.onrender.com/health

Do not send a localhost address or a deployment that is still building.

## GitHub publication

Create a public repository called `aptino-claim-engine` (or your preferred name). Upload the contents of this project directory, including the policy, public cases, additional cases, code, docs and measured evaluation results. The repository root must contain README.md, Dockerfile and requirements.lock.txt.

Never upload `.env`, `.cache`, virtual environments, credentials or private account tokens. The delivery ZIP is generated with these excluded. Preserve the supplied public JSON exactly.

## Render publication

Render provides a Free Docker web service option. Create a Web Service using the public GitHub repository URL. Select Docker and the Free instance, and add `GOOGLE_API_KEY` as a secret environment variable. Set `GEMINI_MODEL=gemini-3.1-flash-lite`. Keep the health check at `/health`. This service listens on port 7860, which Render detects.

The repository includes `render.yaml` with `plan: free`; do not select a paid instance unless you intend to pay. The free service has 512 MB RAM and can sleep after inactivity. Verify successful startup and a live case after deployment. If the host requests a card or plan upgrade, account setup must be completed by the account owner.

## Optional Hugging Face publication

Hugging Face currently requires a paid plan for Docker Spaces. If you already have an eligible plan, create a public Space and choose Docker with a blank template. Upload the project contents. Under Space Settings, add `GOOGLE_API_KEY` as a secret and `GEMINI_MODEL=gemini-3.1-flash-lite` as a variable. The README already specifies Docker and port 7860. Wait for the image to build.

Open the live app. Confirm `/health` is ready, `/docs` loads, the policy link opens, and a supplied claim produces a real validated response. If your Gemini model name differs, update the variable and rerun the evaluation with the same name.

## Contents to submit

* Public repository and working application/API links.
* README with architecture diagram, local setup, examples, trade-offs and limitations.
* `docs/DESIGN_NOTE.pdf` (short architecture note), also available as Markdown.
* `docs/EVALUATION.md` plus the `evaluation/results/` directory.
* All 12 public-case results and 9 additional cases/results.
* Source code and the reproducible evaluation command.

The ZIP is a convenient backup attachment, not a replacement for the required public repository and live deployment.

## Final personal review

Read the README, design note and evaluation report. Run one approved case, one rejected case and one review case. Inspect their citations. Be ready to explain why the agents have distinct roles, why hybrid retrieval and reranking are separate, how the validation retry works, and why several incomplete public cases lead to review.

Confirm the deadline and submission address from the recruiting email. The assignment permits AI coding assistance; describe assistance accurately if asked. Do not claim measured results that have not been generated or verified.
