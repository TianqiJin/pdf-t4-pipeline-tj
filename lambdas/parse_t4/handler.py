"""Parse T4 Lambda. Returns exact CONTRACT.md parse_t4 output."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.logging_utils import get_json_logger
from shared.openai_client import extract_t4_from_pdf
from shared.s3_utils import get_object_bytes, put_object_json

from parse_t4.prompt import T4_T4A_EXTRACTION_INSTRUCTIONS

MAX_PARSE_ATTEMPTS = 3  # Try up to 3 times per page before giving up

logger = get_json_logger(__name__)


def _parse_json_output(text: str) -> dict | None:
    """Parse JSON from model output. Strip markdown code blocks if present."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    # Remove optional markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if m:
        cleaned = m.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _parse_t4_page(pdf_bytes: bytes, page_index: int) -> tuple[bool, str, str, dict | None, str]:
    """
    Parse T4 from PDF page via OpenAI.
    Returns (parse_ok, box12_raw, box13_raw, success_data, failure_reason).
    Parse succeeds if Box 12 or Box 13 has a value (encrypt will validate).
    """
    raw = extract_t4_from_pdf(
        pdf_bytes,
        instructions=T4_T4A_EXTRACTION_INSTRUCTIONS,
        filename=f"page-{page_index:04d}.pdf",
    )
    obj = _parse_json_output(raw)
    if obj is None:
        return False, "", "", None, "Invalid model output JSON"
    if not obj.get("isAbleToGetContent"):
        reason = obj.get("Reason", "Unable to extract content")
        return False, "", "", None, reason
    boxes = obj.get("boxes") or {}
    box12 = boxes.get("12") or boxes.get("012")  # T4 uses "12", T4A may use "012"
    box13 = boxes.get("13") or boxes.get("013")  # T4 uses "13", T4A may use "013"
    box12_raw = str(box12).strip() if box12 is not None and box12 != "" else ""
    box13_raw = str(box13).strip() if box13 is not None and box13 != "" else ""
    if not box12_raw and not box13_raw:
        return False, "", "", None, "Box 12 and Box 13 both missing; need at least one for encryption"
    return True, box12_raw, box13_raw, obj, ""


def handler(event: dict, context: object) -> dict:
    inp = event
    job_id = inp["jobId"]
    buckets = inp["buckets"]
    prefixes = inp["prefixes"]
    page = inp["page"]
    page_index = page["pageIndex"]
    split_key = page["splitKey"]
    results_bucket = buckets["results"]
    results_prefix = prefixes["results"].rstrip("/")
    parse_result_key = f"{results_prefix}/{job_id}/page-{page_index:04d}-parse.json"

    pdf_bytes = get_object_bytes(inp["splitBucket"], split_key)
    parse_ok, box12_raw, box13_raw, success_data, failure_reason = False, "", "", None, ""
    for attempt in range(1, MAX_PARSE_ATTEMPTS + 1):
        parse_ok, box12_raw, box13_raw, success_data, failure_reason = _parse_t4_page(pdf_bytes, page_index)
        if parse_ok:
            break
        if attempt < MAX_PARSE_ATTEMPTS:
            logger.info(
                "Parse failed, retrying",
                extra={"pageIndex": page_index, "attempt": attempt, "maxAttempts": MAX_PARSE_ATTEMPTS},
            )

    if parse_ok and success_data is not None:
        put_object_json(results_bucket, parse_result_key, {
            "isAbleToGetContent": True,
            "slipType": success_data.get("slipType", "T4"),
            "year": success_data.get("year"),
            "employerName": success_data.get("employerName", ""),
            "employeeName": success_data.get("employeeName", ""),
            "employeeAddress": success_data.get("employeeAddress", ""),
            "boxes": success_data.get("boxes", {}),
            "codes": success_data.get("codes", {}),
        })
        out: dict = {
            "pageIndex": page_index,
            "splitKey": split_key,
            "parseOk": True,
            "box12Raw": box12_raw,
            "box13Raw": box13_raw,
            "parseResultKey": parse_result_key,
            "failureReason": None,
        }
    else:
        put_object_json(results_bucket, parse_result_key, {
            "isAbleToGetContent": False,
            "Reason": failure_reason,
        })
        out = {
            "pageIndex": page_index,
            "splitKey": split_key,
            "parseOk": False,
            "box12Raw": "",
            "box13Raw": "",
            "parseResultKey": parse_result_key,
            "failureReason": failure_reason,
        }
    return out
