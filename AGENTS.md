# AGENTS.md — pdf-t4-pipeline-tj

Project context for AI coding agents (OpenClaw, Cursor) working on this codebase.

## Project Overview

AWS Step Functions pipeline that splits multi-page PDFs, parses Canada T4 and T4A slips via OpenAI, encrypts pages with Box12-derived passwords, and writes protected outputs to S3.

## Architecture

**Flow:** Split → Map(Parse T4 → Encrypt) → Finalize → Cleanup

| Step | Lambda | Purpose |
|------|--------|---------|
| SplitPdf | `split_pdf` | Splits PDF with pypdf, uploads pages to S3 split bucket |
| MapPages | `parse_t4` | Per-page: OpenAI extracts T4/T4A, returns Box12; retries up to 3 times on failure |
| MapPages | `encrypt_pdf` | Encrypts page with password from Box12 rules |
| FinalizeJob | `finalize_job` | Builds `summary.json` (succeededPages, failedPages, totalPages) |
| CleanupSplits | `cleanup_splits` | Deletes split objects under job prefix |

**Optional trigger:** S3 ObjectCreated on `incoming/` → `starter` Lambda → StartExecution.

## Directory Structure

- **lambdas/** — Lambda functions (starter, split_pdf, parse_t4, encrypt_pdf, finalize_job, cleanup_splits) and shared utilities (`openai_client`, `password_rules`, `s3_utils`, etc.)
- **infra/** — CDK v2 app and pipeline stack
- **tests/** — Pytest unit tests (12 tests)
- **scripts/** — E2E test script (`e2e_test.sh`)

## Key Documents

Consult these before making changes:

| File | Purpose |
|------|---------|
| **CLAUDE.md** | Architecture, conventions, deployment — primary source of truth |
| **CONTRACT.md** | Lambda input/output schemas, payload shapes, result file formats |
| **STATE_MACHINE_WIRING.md** | Step Functions ASL; placeholders for CDK substitution |
| **README.md** | Deploy steps, SSM/Secrets setup, per-Lambda invoke commands |

## Development Environment

- Python 3.12
- AWS CDK v2
- Docker (for Lambda bundling)

Setup:

```bash
pip install -r requirements-dev.txt
pip install -r lambdas/requirements.txt
```

## Build & Test

```bash
# All tests (from repo root)
pytest

# Per-Lambda focus
pytest -k "split_pdf"
pytest -k "parse_t4"
pytest -k "encrypt_pdf"
pytest -k "finalize_job"
pytest -k "cleanup_splits"
pytest -k "starter"

# Lint
ruff check .
```

Tests patch S3 and OpenAI; `sys.path` includes `lambdas/`.

## Deploy

```bash
cd infra
pip install -r requirements.txt
cdk deploy --require-approval never
```

With OpenAI from SSM:

```bash
cdk deploy -c openai_param_name=/pdf-t4/openai-api-key
```

With Secrets Manager:

```bash
cdk deploy -c openai_secret_arn=arn:aws:secretsmanager:REGION:ACCOUNT:secret:secret-name
```

With custom model:

```bash
cdk deploy -c openai_param_name=/pdf-t4/openai-api-key -c openai_model=gpt-4o
```

## E2E

```bash
./scripts/e2e_test.sh path/to/test.pdf
```

Uploads to `incoming/`, starts execution, waits for success, shows protected files and `summary.json`.

## Coding Conventions

- **Always consult CLAUDE.md** before making changes.
- When changing architecture, APIs, config, or deployment, **update CLAUDE.md** to keep it accurate.
- Follow `.cursor/rules/pdf-t4-conventions.mdc` (references CLAUDE.md).

## Lambda Contracts

Lambdas must return exactly the top-level fields defined in **CONTRACT.md**. Tests enforce this.

- `split_pdf`: jobId, split, pages, pageCount
- `parse_t4`: pageIndex, splitKey, parseOk, box12Raw, box13Raw, parseResultKey, failureReason
- `encrypt_pdf`: pageIndex, encryptOk, protectedKey, encryptResultKey, failureReason
- `finalize_job`: jobId, summaryKey, succeededCount, failedCount
- `cleanup_splits`: jobId, cleaned, deletedCount

For payload shapes and result file formats, see CONTRACT.md.

## Security (Critical)

**Do not log Box12 or Box13 values.** These must never appear in logs. CONTRACT.md enforces this.
