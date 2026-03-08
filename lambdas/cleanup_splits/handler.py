"""Cleanup Splits Lambda. Returns exact CONTRACT.md cleanup_splits output."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.logging_utils import get_json_logger
from shared.s3_utils import delete_keys, list_keys

logger = get_json_logger(__name__)


def handler(event: dict, context: object) -> dict:
    inp = event
    job_id = inp["jobId"]
    split_info = inp["split"]
    bucket = split_info["bucket"]
    job_prefix = split_info["jobPrefix"]

    keys = list_keys(bucket, job_prefix)
    delete_keys(bucket, keys)

    return {
        "jobId": job_id,
        "cleaned": True,
        "deletedCount": len(keys),
    }
