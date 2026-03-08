"""Starter Lambda: S3 ObjectCreated on incoming/ -> Step Functions StartExecution.

Builds SFN input from S3 event + env (bucket names). Does NOT process PDFs.
"""
import json
import os
import urllib.parse

import boto3


def _get_sfn_client():
    return boto3.client("stepfunctions")


def handler(event: dict, context: object) -> dict:
    """
    Handle S3 ObjectCreated event. Start one Step Functions execution per object.
    """
    state_machine_arn = os.environ["STATE_MACHINE_ARN"]
    split_bucket = os.environ["SPLIT_BUCKET"]
    protected_bucket = os.environ["PROTECTED_BUCKET"]
    results_bucket = os.environ["RESULTS_BUCKET"]

    prefixes = {"split": "splits/", "protected": "protected/", "results": "results/"}

    results = []
    for record in event.get("Records", []):
        try:
            s3_info = record.get("s3", {})
            bucket_name = s3_info.get("bucket", {}).get("name", "")
            object_key = s3_info.get("object", {}).get("key", "")
            # S3 sends key URL-encoded
            object_key = urllib.parse.unquote_plus(object_key)

            if not bucket_name or not object_key:
                results.append({"record": record, "error": "Missing bucket or key"})
                continue

            sfn_input = {
                "source": {"bucket": bucket_name, "key": object_key},
                "buckets": {
                    "split": split_bucket,
                    "protected": protected_bucket,
                    "results": results_bucket,
                },
                "prefixes": prefixes,
            }

            resp = _get_sfn_client().start_execution(
                stateMachineArn=state_machine_arn,
                input=json.dumps(sfn_input),
            )
            results.append({
                "bucket": bucket_name,
                "key": object_key,
                "executionArn": resp["executionArn"],
            })
        except Exception as e:
            results.append({"record": record, "error": str(e)})
            raise

    return {"started": len(results), "results": results}
