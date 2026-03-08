# PDF T4 Pipeline – Project Context

AWS Step Functions pipeline that splits multi-page PDFs, parses Canada T4 and T4A slips via OpenAI, encrypts pages with Box12-derived passwords, and writes protected outputs to S3.

---

## Architecture

**Flow:** Split → Map(Parse T4 → Encrypt) → Finalize → Cleanup

| Step | Lambda | Purpose |
|------|--------|---------|
| SplitPdf | `split_pdf` | Splits PDF with pypdf, uploads pages to S3 split bucket |
| MapPages | `parse_t4` | Per-page: OpenAI extracts T4/T4A, returns Box12; retries up to 3 times on failure |
| MapPages | `encrypt_pdf` | Encrypts page with password from Box12 rules |
| FinalizeJob | `finalize_job` | Builds `summary.json` (succeededPages, failedPages, totalPages) |
| CleanupSplits | `cleanup_splits` | Deletes split objects under job prefix |

**Optional trigger:** S3 ObjectCreated on `incoming/` → `starter` Lambda → StartExecution (no PDF processing).

**Individual state machines** (single-step, for per-Lambda testing/invocation):

| State Machine | Lambda | Input (per CONTRACT.md) |
|---------------|--------|------------------------|
| SplitOnly | `split_pdf` | source, buckets, prefixes |
| ParseOnly | `parse_t4` | jobId, buckets, prefixes, splitBucket, page |
| EncryptOnly | `encrypt_pdf` | jobId, buckets, prefixes, pageIndex, splitKey, box12Raw, box13Raw |

These reuse the same `StateMachineRole` and Lambda ARNs as the full pipeline.

---

## Directory Structure

```
lambdas/           # Lambda functions and shared utilities
├── starter/       # S3 trigger → SFN StartExecution
├── split_pdf/     # PDF split via pypdf
├── parse_t4/      # T4 extraction via OpenAI Responses API
├── encrypt_pdf/   # Box12-derived password encryption
├── finalize_job/  # summary.json assembly
├── cleanup_splits/
├── shared/        # openai_client, password_rules, s3_utils, id_utils, logging_utils
└── requirements.txt

infra/             # CDK v2
├── app.py         # CDK app, reads context for openai_param_name / openai_secret_arn / openai_model
├── stacks/pipeline_stack.py
└── cdk.json

tests/             # Pytest (12 tests)
scripts/e2e_test.sh  # End-to-end run with real AWS
```

---

## Key Documents

| File | Purpose |
|------|---------|
| **CONTRACT.md** | Lambda input/output schemas, payload shapes, result file formats |
| **STATE_MACHINE_WIRING.md** | Step Functions ASL JSON; placeholders `${SplitLambdaArn}` etc. for CDK substitution |
| **README.md** | Deploy steps, SSM/Secrets setup, S3 trigger, e2e commands |

---

## S3 Buckets

| Bucket | Use |
|--------|-----|
| **source** | Incoming PDFs (`incoming/`). S3 trigger fires on ObjectCreated here. |
| **split** | Per-page PDFs under `splits/{jobId}/`. 1-day lifecycle on `splits/` prefix. |
| **protected** | Encrypted PDFs under `protected/{jobId}/` |
| **results** | Parse JSONs, encrypt JSONs, `summary.json` under `results/{jobId}/` |

---

## Lambda Contracts (summary)

All payload shapes are in **CONTRACT.md**. Lambdas must return exactly the top-level fields defined there; tests enforce this.

- **split_pdf:** Input = source, buckets, prefixes. Output = jobId, split, pages, pageCount.
- **parse_t4:** Input per page. Output = pageIndex, splitKey, parseOk, box12Raw, box13Raw, parseResultKey, failureReason.
- **encrypt_pdf:** Uses box12Raw (primary) and box13Raw (fallback) to derive password via `password_rules.py`. Output = pageIndex, encryptOk, protectedKey, encryptResultKey, failureReason.
- **finalize_job:** Merges pages + pageOutcomes → summary.json. Output = jobId, summaryKey, succeededCount, failedCount.
- **cleanup_splits:** Deletes objects under split.jobPrefix. Output = jobId, cleaned, deletedCount.

---

## Shared Modules

| Module | Role |
|--------|------|
| `openai_client.py` | OpenAI Responses API. Lazy imports. Resolves API key from `OPENAI_SECRET_ARN`, `OPENAI_PARAM_NAME`, or `OPENAI_API_KEY`. |
| `password_rules.py` | `derive_password(box12, box13)` – Box12 primary, Box13 fallback; digits or digits before RT. |
| `parse_t4/prompt.py` | Strict JSON-only T4/T4A extraction instructions for the model. |

---

## Configuration

**OpenAI:** One of:
- `OPENAI_PARAM_NAME` (SSM Parameter Store SecureString)
- `OPENAI_SECRET_ARN` (Secrets Manager)
- `OPENAI_API_KEY` (env, e.g. local dev)

**CDK context:**
- `-c openai_param_name=/pdf-t4/openai-api-key`
- `-c openai_secret_arn=arn:aws:secretsmanager:...`
- `-c openai_model=gpt-4o` (default)

---

## Security

**Do not log Box12 values.** Box12 must never appear in logs (per CONTRACT.md).

---

## Tests

- **test_contract_outputs.py:** Contract shape checks for split, parse, encrypt, finalize, cleanup, starter.
- **test_password_rules.py:** Password derivation (all digits, digits-before-RT, invalid cases).
- **test_individual_state_machines.py:** CDK assertions for SplitOnly, ParseOnly, EncryptOnly state machines and their stack outputs.
- Tests patch S3/OpenAI; `sys.path` includes `lambdas/`.

Run: `pytest` (from repo root). Focus on one Lambda: `pytest -k "split_pdf"` etc.

**Per-Lambda testing:** README "Run and test Lambdas individually" covers: (1) unit tests with `-k`, (2) `aws lambda invoke` against deployed Lambdas with JSON payloads, (3) local Python handler invocation with `PYTHONPATH=lambdas`.

---

## Deployment

```bash
cd infra && pip install -r requirements.txt && cdk deploy --require-approval never
```

With OpenAI from SSM:
```bash
cdk deploy -c openai_param_name=/pdf-t4/openai-api-key
```

Outputs: SourceBucketName, SplitBucketName, ProtectedBucketName, ResultsBucketName, StateMachineArn, SplitOnlyStateMachineArn, ParseOnlyStateMachineArn, EncryptOnlyStateMachineArn.

---

## E2E

```bash
./scripts/e2e_test.sh path/to/test.pdf
```

Uploads to `incoming/`, starts execution manually (or use S3 trigger), waits for success, then shows protected files and summary.json.

---

## Stack Outputs

- `SourceBucketName`, `SplitBucketName`, `ProtectedBucketName`, `ResultsBucketName`
- `StateMachineArn`
- `SplitOnlyStateMachineArn`, `ParseOnlyStateMachineArn`, `EncryptOnlyStateMachineArn`

Query via: `aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query 'Stacks[0].Outputs'`
