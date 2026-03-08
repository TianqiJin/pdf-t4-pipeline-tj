"""Finalize Job Lambda. Returns exact CONTRACT.md finalize_job output."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.logging_utils import get_json_logger
from shared.s3_utils import put_object_json

logger = get_json_logger(__name__)


def _stage_for_outcome(o: dict) -> str | None:
    if not o.get("parseOk"):
        return "parse"
    if not o.get("encryptOk"):
        return "encrypt"
    return None


def handler(event: dict, context: object) -> dict:
    inp = event
    job_id = inp["jobId"]
    buckets = inp["buckets"]
    prefixes = inp["prefixes"]
    pages = inp["pages"]
    page_outcomes = inp["pageOutcomes"]
    results_bucket = buckets["results"]
    results_prefix = prefixes["results"].rstrip("/")
    summary_key = f"{results_prefix}/{job_id}/summary.json"
    results_prefix_full = f"{results_prefix}/{job_id}/"

    succeeded: list[dict] = []
    failed: list[dict] = []
    for o in page_outcomes:
        stage = _stage_for_outcome(o)
        reason = o.get("failureReason")
        if stage is None:
            succeeded.append({"pageIndex": o["pageIndex"], "protectedKey": o.get("protectedKey", "")})
        else:
            failed.append({"pageIndex": o["pageIndex"], "stage": stage, "reason": reason})

    put_object_json(results_bucket, summary_key, {
        "succeededPages": succeeded,
        "failedPages": failed,
        "totalPages": len(pages),
        "succeededCount": len(succeeded),
        "failedCount": len(failed),
        "resultsPrefix": results_prefix_full,
    })

    return {
        "jobId": job_id,
        "summaryKey": summary_key,
        "succeededCount": len(succeeded),
        "failedCount": len(failed),
    }
