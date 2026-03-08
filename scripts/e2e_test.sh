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
aws stepfunctions wait execution-successful --execution-arn "$EXEC_ARN"
echo "Execution succeeded."

OUTPUT=$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query 'output' --output text)
JOB_ID=$(echo "$OUTPUT" | jq -r '.splitResult.payload.jobId')
echo "JobId: $JOB_ID"

echo "Protected files:"
aws s3 ls "s3://${PROTECTED_BUCKET}/protected/${JOB_ID}/" || true

echo "Summary:"
aws s3 cp "s3://${RESULTS_BUCKET}/results/${JOB_ID}/summary.json" - | jq .
echo "E2E test passed."
