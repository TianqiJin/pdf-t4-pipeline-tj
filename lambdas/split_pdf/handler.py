"""Split PDF Lambda. Returns exact CONTRACT.md split_pdf output."""
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pypdf import PdfReader, PdfWriter
from shared.id_utils import generate_job_id
from shared.logging_utils import get_json_logger
from shared.s3_utils import get_object_bytes, put_object_bytes

logger = get_json_logger(__name__)


def handler(event: dict, context: object) -> dict:
    inp = event
    job_id = inp.get("jobId") or generate_job_id()
    source = inp["source"]
    buckets = inp["buckets"]
    prefixes = inp["prefixes"]

    pdf_bytes = get_object_bytes(source["bucket"], source["key"])
    reader = PdfReader(BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    split_bucket = buckets["split"]
    split_prefix = prefixes["split"]
    job_prefix = f"{split_prefix.rstrip('/')}/{job_id}/"

    pages: list[dict] = []
    for i in range(page_count):
        page_index = i + 1
        split_key = f"{job_prefix}page-{page_index:04d}.pdf"
        page = reader.pages[i]
        # Fix malformed /Annots: some PDFs have NumberObject instead of array, causing
        # "'NumberObject' object has no attribute '__iter__'" when pypdf extracts links.
        annots = page.get("/Annots")
        if annots is not None:
            try:
                iter(annots)
            except (TypeError, AttributeError):
                if "/Annots" in page:
                    del page["/Annots"]
        writer = PdfWriter()
        writer.add_page(page)
        buf = BytesIO()
        writer.write(buf)
        buf = buf.getvalue()
        put_object_bytes(split_bucket, split_key, buf, "application/pdf")
        pages.append({"pageIndex": page_index, "splitKey": split_key})

    out: dict = {
        "jobId": job_id,
        "source": source,
        "buckets": buckets,
        "prefixes": prefixes,
        "split": {"bucket": split_bucket, "jobPrefix": job_prefix},
        "pages": pages,
        "pageCount": page_count,
    }
    return out
