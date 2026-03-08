# pdf-t4-pipeline-tj

PDF T4 pipeline using AWS Step Functions and Lambda. Splits multi-page PDFs, parses Canada T4 slips via OpenAI, encrypts with Box12-derived passwords, and writes protected outputs.

## Structure

- `lambdas/` — Lambda functions (starter, split_pdf, parse_t4, encrypt_pdf, finalize_job, cleanup_splits) and shared utilities
- `infra/` — CDK app and pipeline stack
- `tests/` — Pytest unit tests

## Requirements

- Python 3.12
- AWS CDK v2
- Docker (for Lambda bundling)

## Development

```bash
pip install -r requirements-dev.txt
pip install -r lambdas/requirements.txt
pytest
ruff check .
```

## Run and test Lambdas individually

### 1. Unit tests (local, no AWS)

Run all tests or focus on a specific Lambda:

```bash
# All tests
pytest

# Split Lambda only
pytest -k "split_pdf"

# Parse T4 only
pytest -k "parse_t4"

# Encrypt only
pytest -k "encrypt_pdf"

# Finalize only
pytest -k "finalize_job"

# Cleanup only
pytest -k "cleanup_splits"

# Starter only
pytest -k "starter"
```

Tests use mocks for S3 and OpenAI. Contract shapes are enforced; see `CONTRACT.md` for payload formats.

### 2. Invoke deployed Lambdas (AWS CLI)

After deploying the stack, invoke each Lambda with a JSON payload. CDK adds hash suffixes to logical IDs (e.g. `SplitPdfB8B0E630`), so use `contains()` to resolve function names. Alternative: `aws lambda list-functions --query "Functions[?contains(FunctionName,'SplitPdf')].FunctionName" --output text`.

```bash
STACK=PdfT4PipelineStack
SPLIT_FN=$(aws cloudformation describe-stack-resources --stack-name $STACK --query "StackResources[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId, 'SplitPdf')].PhysicalResourceId" --output text)
PARSE_FN=$(aws cloudformation describe-stack-resources --stack-name $STACK --query "StackResources[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId, 'ParseT4')].PhysicalResourceId" --output text)
ENCRYPT_FN=$(aws cloudformation describe-stack-resources --stack-name $STACK --query "StackResources[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId, 'EncryptPdf')].PhysicalResourceId" --output text)
FINALIZE_FN=$(aws cloudformation describe-stack-resources --stack-name $STACK --query "StackResources[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId, 'FinalizeJob')].PhysicalResourceId" --output text)
CLEANUP_FN=$(aws cloudformation describe-stack-resources --stack-name $STACK --query "StackResources[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId, 'CleanupSplits')].PhysicalResourceId" --output text)
STARTER_FN=$(aws cloudformation describe-stack-resources --stack-name $STACK --query "StackResources[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId, 'Starter')].PhysicalResourceId" --output text)
```

**split_pdf** — Requires a PDF at `s3://SOURCE_BUCKET/incoming/your.pdf`:

```bash
SOURCE_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='SourceBucketName'].OutputValue" --output text)
SPLIT_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='SplitBucketName'].OutputValue" --output text)
PROTECTED_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='ProtectedBucketName'].OutputValue" --output text)
RESULTS_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='ResultsBucketName'].OutputValue" --output text)

echo '{"source":{"bucket":"'$SOURCE_BUCKET'","key":"incoming/your.pdf"},"buckets":{"split":"'$SPLIT_BUCKET'","protected":"'$PROTECTED_BUCKET'","results":"'$RESULTS_BUCKET'"},"prefixes":{"split":"splits/","protected":"protected/","results":"results/"}}' > /tmp/split_in.json
aws lambda invoke --function-name "$SPLIT_FN" --payload fileb:///tmp/split_in.json /tmp/split_out.json --cli-binary-format raw-in-base64-out
cat /tmp/split_out.json | jq .
```

**parse_t4** — Uses output from split_pdf. Pass one page:

```bash
# Use jobId and pages from split_pdf output
echo '{"jobId":"YOUR_JOB_ID","buckets":{"split":"'$SPLIT_BUCKET'","protected":"'$PROTECTED_BUCKET'","results":"'$RESULTS_BUCKET'"},"prefixes":{"split":"splits/","protected":"protected/","results":"results/"},"splitBucket":"'$SPLIT_BUCKET'","page":{"pageIndex":1,"splitKey":"splits/YOUR_JOB_ID/page-0001.pdf"}}' > /tmp/parse_in.json
aws lambda invoke --function-name "$PARSE_FN" --payload fileb:///tmp/parse_in.json /tmp/parse_out.json --cli-binary-format raw-in-base64-out
cat /tmp/parse_out.json | jq .
```

**encrypt_pdf** — Uses output from parse_t4 (box12Raw):

```bash
echo '{"jobId":"YOUR_JOB_ID","buckets":{"split":"'$SPLIT_BUCKET'","protected":"'$PROTECTED_BUCKET'","results":"'$RESULTS_BUCKET'"},"prefixes":{"split":"splits/","protected":"protected/","results":"results/"},"pageIndex":1,"splitKey":"splits/YOUR_JOB_ID/page-0001.pdf","box12Raw":"123456RT"}' > /tmp/encrypt_in.json
aws lambda invoke --function-name "$ENCRYPT_FN" --payload fileb:///tmp/encrypt_in.json /tmp/encrypt_out.json --cli-binary-format raw-in-base64-out
cat /tmp/encrypt_out.json | jq .
```

**finalize_job** — Needs `pages` and `pageOutcomes` (from split + map results):

```bash
echo '{"jobId":"YOUR_JOB_ID","buckets":{"split":"'$SPLIT_BUCKET'","protected":"'$PROTECTED_BUCKET'","results":"'$RESULTS_BUCKET'"},"prefixes":{"split":"splits/","protected":"protected/","results":"results/"},"pages":[{"pageIndex":1,"splitKey":"splits/YOUR_JOB_ID/page-0001.pdf"}],"pageOutcomes":[{"pageIndex":1,"splitKey":"splits/YOUR_JOB_ID/page-0001.pdf","parseOk":true,"encryptOk":true,"parseResultKey":"results/YOUR_JOB_ID/page-0001-parse.json","encryptResultKey":"results/YOUR_JOB_ID/page-0001-encrypt.json","protectedKey":"protected/YOUR_JOB_ID/page-0001.pdf","failureStage":null,"failureReason":null}]}' > /tmp/finalize_in.json
aws lambda invoke --function-name "$FINALIZE_FN" --payload fileb:///tmp/finalize_in.json /tmp/finalize_out.json --cli-binary-format raw-in-base64-out
cat /tmp/finalize_out.json | jq .
```

**cleanup_splits** — Deletes objects under job prefix:

```bash
echo '{"jobId":"YOUR_JOB_ID","split":{"bucket":"'$SPLIT_BUCKET'","jobPrefix":"splits/YOUR_JOB_ID/"}}' > /tmp/cleanup_in.json
aws lambda invoke --function-name "$CLEANUP_FN" --payload fileb:///tmp/cleanup_in.json /tmp/cleanup_out.json --cli-binary-format raw-in-base64-out
cat /tmp/cleanup_out.json | jq .
```

**starter** — Expects S3 ObjectCreated event shape (or simulate):

```bash
echo '{"Records":[{"s3":{"bucket":{"name":"'$SOURCE_BUCKET'"},"object":{"key":"incoming/your.pdf"}}}]}' > /tmp/starter_in.json
# Starter needs STATE_MACHINE_ARN, SPLIT_BUCKET, etc. in env (set by CDK); invoke works when deployed
aws lambda invoke --function-name "$STARTER_FN" --payload fileb:///tmp/starter_in.json /tmp/starter_out.json --cli-binary-format raw-in-base64-out
cat /tmp/starter_out.json | jq .
```

### 3. Local handler invocation (Python)

To call handlers directly from Python (e.g. with real S3 if AWS creds are configured):

```bash
cd lambdas
PYTHONPATH=. python3 -c "
from split_pdf.handler import handler
event = {
    'source': {'bucket': 'YOUR_SOURCE_BUCKET', 'key': 'incoming/test.pdf'},
    'buckets': {'split': 'SPLIT', 'protected': 'PROT', 'results': 'RES'},
    'prefixes': {'split': 'splits/', 'protected': 'protected/', 'results': 'results/'},
}
out = handler(event, None)
print(out)
"
```

Use the same event shapes as in `CONTRACT.md`. For parse_t4, set `OPENAI_API_KEY` or `OPENAI_PARAM_NAME` if using SSM.

## Deploy

### 1. Bootstrap CDK (once per account/region)

```bash
cdk bootstrap
```

### 2. Optional: Store OpenAI API key for parse_t4

Create an SSM SecureString parameter:

```bash
aws ssm put-parameter \
  --name "/pdf-t4/openai-api-key" \
  --type "SecureString" \
  --value "sk-..."
```

Or use an existing Secrets Manager secret and pass its ARN.

### 3. Deploy the stack

```bash
cd infra
pip install -r requirements.txt
cdk deploy --require-approval never
```

With OpenAI from SSM:

```bash
cdk deploy --require-approval never -c openai_param_name=/pdf-t4/openai-api-key
```

With OpenAI from Secrets Manager:

```bash
cdk deploy --require-approval never -c openai_secret_arn=arn:aws:secretsmanager:REGION:ACCOUNT:secret:secret-name
```

With custom model:

```bash
cdk deploy -c openai_param_name=/pdf-t4/openai-api-key -c openai_model=gpt-4o
```

### 4. Optional: Automatic S3 trigger (starter)

The stack includes a **starter** Lambda that listens for S3 ObjectCreated on `incoming/`. When a PDF is uploaded to `s3://SOURCE_BUCKET/incoming/`, the starter builds the SFN input and calls `StartExecution`. No PDF processing happens in the starter.

### 5. Capture outputs

After deploy, note the outputs:

```bash
aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query 'Stacks[0].Outputs'
```

## End-to-end test

### 1. Upload a test PDF (triggers pipeline automatically)

Uploading to `incoming/` invokes the starter Lambda, which starts the Step Functions execution.

```bash
SOURCE_BUCKET=$(aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query "Stacks[0].Outputs[?OutputKey=='SourceBucketName'].OutputValue" --output text)
aws s3 cp test.pdf "s3://${SOURCE_BUCKET}/incoming/test.pdf"
```

### 2. Get bucket names and execution status (for verification)

```bash
SPLIT_BUCKET=$(aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query "Stacks[0].Outputs[?OutputKey=='SplitBucketName'].OutputValue" --output text)
PROTECTED_BUCKET=$(aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query "Stacks[0].Outputs[?OutputKey=='ProtectedBucketName'].OutputValue" --output text)
RESULTS_BUCKET=$(aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query "Stacks[0].Outputs[?OutputKey=='ResultsBucketName'].OutputValue" --output text)
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks --stack-name PdfT4PipelineStack --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" --output text)
```

For manual runs (without S3 trigger), start an execution:

```bash
EXEC_INPUT=$(jq -n \
  --arg src "$SOURCE_BUCKET" \
  --arg split "$SPLIT_BUCKET" \
  --arg prot "$PROTECTED_BUCKET" \
  --arg results "$RESULTS_BUCKET" \
  '{source:{bucket:$src,key:"incoming/test.pdf"},buckets:{split:$split,protected:$prot,results:$results},prefixes:{split:"splits/",protected:"protected/",results:"results/"}}')
EXEC_ARN=$(aws stepfunctions start-execution --state-machine-arn "$STATE_MACHINE_ARN" --input "$EXEC_INPUT" --query 'executionArn' --output text)
```

### 3. Wait for execution

```bash
aws stepfunctions wait execution-successful --execution-arn "$EXEC_ARN"
```

### 4. Get execution output (contains jobId)

If you triggered via S3 upload, find the execution in the Step Functions console or list recent executions. Otherwise use EXEC_ARN from the manual start.

```bash
EXEC_OUTPUT=$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query 'output' --output text)
JOB_ID=$(echo "$EXEC_OUTPUT" | jq -r '.splitResult.payload.jobId // .cleanup.payload.jobId // empty')
# If jobId in final output structure differs, adjust the jq path
JOB_ID=$(echo "$EXEC_OUTPUT" | jq -r '.. | .jobId? // empty' | head -1)
```

### 5. Verify protected outputs

```bash
aws s3 ls "s3://${PROTECTED_BUCKET}/protected/${JOB_ID}/"
# Expect: page-0001.pdf, page-0002.pdf, etc. for succeeded pages
```

### 6. Verify results/summary.json

```bash
aws s3 cp "s3://${RESULTS_BUCKET}/results/${JOB_ID}/summary.json" - | jq .
# Expect: succeededPages, failedPages, totalPages, succeededCount, failedCount, resultsPrefix
```

## All-in-one e2e script

Save as `scripts/e2e_test.sh`:

```bash
#!/bin/bash
set -e
STACK=PdfT4PipelineStack
SOURCE_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='SourceBucketName'].OutputValue" --output text)
SPLIT_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='SplitBucketName'].OutputValue" --output text)
PROTECTED_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='ProtectedBucketName'].OutputValue" --output text)
RESULTS_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='ResultsBucketName'].OutputValue" --output text)
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" --output text)

[[ -n "$1" ]] || { echo "Usage: $0 <path-to-pdf>"; exit 1; }
PDF="$1"
aws s3 cp "$PDF" "s3://${SOURCE_BUCKET}/incoming/$(basename "$PDF")"

INPUT=$(jq -n \
  --arg src "$SOURCE_BUCKET" \
  --arg key "incoming/$(basename "$PDF")" \
  --arg split "$SPLIT_BUCKET" \
  --arg prot "$PROTECTED_BUCKET" \
  --arg results "$RESULTS_BUCKET" \
  '{source:{bucket:$src,key:$key},buckets:{split:$split,protected:$prot,results:$results},prefixes:{split:"splits/",protected:"protected/",results:"results/"}}')

EXEC_ARN=$(aws stepfunctions start-execution --state-machine-arn "$STATE_MACHINE_ARN" --input "$INPUT" --query 'executionArn' --output text)
echo "Started execution: $EXEC_ARN"
aws stepfunctions wait execution-successf ul --execution-arn "$EXEC_ARN"
echo "Execution succeeded."

OUTPUT=$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query 'output' --output text)
JOB_ID=$(echo "$OUTPUT" | jq -r '.splitResult.payload.jobId')
echo "JobId: $JOB_ID"

echo "Protected files:"
aws s3 ls "s3://${PROTECTED_BUCKET}/protected/${JOB_ID}/" || true

echo "Summary:"
aws s3 cp "s3://${RESULTS_BUCKET}/results/${JOB_ID}/summary.json" - | jq .
echo "E2E test passed."
```

Usage: `./scripts/e2e_test.sh test.pdf`