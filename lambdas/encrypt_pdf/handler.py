"""Encrypt PDF Lambda. Returns exact CONTRACT.md encrypt_pdf output."""
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pypdf import PdfReader, PdfWriter
from shared.logging_utils import get_json_logger
from shared.password_rules import derive_password
from shared.s3_utils import get_object_bytes, put_object_bytes, put_object_json

logger = get_json_logger(__name__)


def handler(event: dict, context: object) -> dict:
    inp = event
    job_id = inp["jobId"]
    buckets = inp["buckets"]
    prefixes = inp["prefixes"]
    page_index = inp["pageIndex"]
    split_key = inp["splitKey"]
    box12_raw = inp.get("box12Raw", "")
    box13_raw = inp.get("box13Raw", "")
    results_bucket = buckets["results"]
    protected_bucket = buckets["protected"]
    results_prefix = prefixes["results"].rstrip("/")
    protected_prefix = prefixes["protected"].rstrip("/")
    encrypt_result_key = f"{results_prefix}/{job_id}/page-{page_index:04d}-encrypt.json"
    protected_key = f"{protected_prefix}/{job_id}/page-{page_index:04d}.pdf"

    ok, password_or_reason = derive_password(box12_raw, box13_raw)

    if not ok:
        put_object_json(results_bucket, encrypt_result_key, {
            "encryptOk": False,
            "failureReason": password_or_reason,
        })
        return {
            "pageIndex": page_index,
            "encryptOk": False,
            "protectedKey": "",
            "encryptResultKey": encrypt_result_key,
            "failureReason": password_or_reason,
        }

    pdf_bytes = get_object_bytes(buckets["split"], split_key)
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.encrypt(password_or_reason)
    buf = BytesIO()
    writer.write(buf)
    put_object_bytes(protected_bucket, protected_key, buf.getvalue(), "application/pdf")
    put_object_json(results_bucket, encrypt_result_key, {
        "encryptOk": True,
        "protectedKey": protected_key,
        "failureReason": None,
    })

    return {
        "pageIndex": page_index,
        "encryptOk": True,
        "protectedKey": protected_key,
        "encryptResultKey": encrypt_result_key,
        "failureReason": None,
    }
