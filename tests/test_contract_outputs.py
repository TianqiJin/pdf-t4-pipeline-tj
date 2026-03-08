"""Tests that lambda handlers return exact CONTRACT.md top-level fields."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambdas"))


def _exact_keys(expected: set[str], got: dict) -> None:
    extra = set(got.keys()) - expected
    missing = expected - set(got.keys())
    assert not extra, f"Extra keys: {extra}"
    assert not missing, f"Missing keys: {missing}"


SPLIT_PDF_KEYS = {"jobId", "source", "buckets", "prefixes", "split", "pages", "pageCount"}
PARSE_T4_KEYS = {"pageIndex", "splitKey", "parseOk", "box12Raw", "box13Raw", "parseResultKey", "failureReason"}
ENCRYPT_PDF_KEYS = {"pageIndex", "encryptOk", "protectedKey", "encryptResultKey", "failureReason"}
FINALIZE_KEYS = {"jobId", "summaryKey", "succeededCount", "failedCount"}
CLEANUP_KEYS = {"jobId", "cleaned", "deletedCount"}


@patch("split_pdf.handler.get_object_bytes")
@patch("split_pdf.handler.put_object_bytes")
def test_split_pdf_output_shape(mock_put, mock_get):
    from pypdf import PdfReader, PdfWriter
    from io import BytesIO

    mock_get.return_value = b""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    mock_get.return_value = buf.getvalue()

    from split_pdf.handler import handler

    event = {
        "source": {"bucket": "B", "key": "k.pdf"},
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "splits/", "protected": "p/", "results": "r/"},
    }
    out = handler(event, None)
    _exact_keys(SPLIT_PDF_KEYS, out)
    assert out["pageCount"] == 1
    assert len(out["pages"]) == 1
    assert out["pages"][0]["pageIndex"] == 1


@patch("split_pdf.handler.get_object_bytes")
@patch("split_pdf.handler.put_object_bytes")
def test_split_pdf_two_page(mock_put, mock_get):
    """Split a 2-page PDF into two page PDFs."""
    from pypdf import PdfReader, PdfWriter
    from io import BytesIO

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    mock_get.return_value = buf.getvalue()

    from split_pdf.handler import handler

    event = {
        "source": {"bucket": "B", "key": "k.pdf"},
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "splits/", "protected": "p/", "results": "r/"},
    }
    out = handler(event, None)
    assert out["pageCount"] == 2
    assert len(out["pages"]) == 2
    assert out["pages"][0]["pageIndex"] == 1
    assert out["pages"][0]["splitKey"].endswith("page-0001.pdf")
    assert out["pages"][1]["pageIndex"] == 2
    assert out["pages"][1]["splitKey"].endswith("page-0002.pdf")
    assert mock_put.call_count == 2


@patch("parse_t4.handler._parse_t4_page")
@patch("parse_t4.handler.get_object_bytes")
@patch("parse_t4.handler.put_object_json")
def test_parse_t4_output_shape_failure(mock_put, mock_get, mock_parse):
    mock_get.return_value = b"not a real pdf"
    mock_parse.return_value = (False, "", "", None, "Not a T4 slip")

    import parse_t4.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "splitBucket": "S",
        "page": {"pageIndex": 1, "splitKey": "s/uuid-1/page-0001.pdf"},
    }
    out = m.handler(event, None)
    _exact_keys(PARSE_T4_KEYS, out)
    assert out["parseOk"] is False
    assert out["box12Raw"] == ""
    assert out["failureReason"] is not None


@patch("parse_t4.handler._parse_t4_page")
@patch("parse_t4.handler.get_object_bytes")
@patch("parse_t4.handler.put_object_json")
def test_parse_t4_t4a_box012_success(mock_put, mock_get, mock_parse):
    """T4A slips use Box 012; handler correctly processes and outputs slipType."""
    mock_get.return_value = b"fake pdf"
    mock_parse.return_value = (True, "123456789", "", {"slipType": "T4A", "year": 2024, "boxes": {"012": "123456789"}}, "")

    import parse_t4.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "splitBucket": "S",
        "page": {"pageIndex": 1, "splitKey": "s/uuid-1/page-0001.pdf"},
    }
    out = m.handler(event, None)
    _exact_keys(PARSE_T4_KEYS, out)
    assert out["parseOk"] is True
    assert out["box12Raw"] == "123456789"
    assert out["failureReason"] is None
    put_call = mock_put.call_args_list[0]
    put_json = put_call[0][2]
    assert put_json.get("slipType") == "T4A"


@patch("parse_t4.handler.extract_t4_from_pdf")
def test_parse_t4_page_accepts_box12_or_012(mock_extract):
    """_parse_t4_page extracts box12/box13 from boxes['12']/['012'] and ['13']/['013']."""
    import parse_t4.handler as m

    # T4: box "12"
    mock_extract.return_value = '{"isAbleToGetContent":true,"slipType":"T4","year":2024,"boxes":{"12":"111222333"},"codes":{}}'
    ok, box12, box13, _, _ = m._parse_t4_page(b"pdf", 0)
    assert ok is True and box12 == "111222333" and box13 == ""

    # T4A: box "012"
    mock_extract.return_value = '{"isAbleToGetContent":true,"slipType":"T4A","year":2024,"boxes":{"012":"444555666"},"codes":{}}'
    ok, box12, box13, _, _ = m._parse_t4_page(b"pdf", 0)
    assert ok is True and box12 == "444555666" and box13 == ""

    # Fallback: box 12 empty, box 13 has value
    mock_extract.return_value = '{"isAbleToGetContent":true,"slipType":"T4A","year":2024,"boxes":{"013":"777888999RT"},"codes":{}}'
    ok, box12, box13, _, _ = m._parse_t4_page(b"pdf", 0)
    assert ok is True and box12 == "" and box13 == "777888999RT"


@patch("encrypt_pdf.handler.get_object_bytes")
@patch("encrypt_pdf.handler.put_object_bytes")
@patch("encrypt_pdf.handler.put_object_json")
def test_encrypt_pdf_output_shape_success(mock_put_json, mock_put_bytes, mock_get):
    from pypdf import PdfWriter
    from io import BytesIO

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    mock_get.return_value = buf.getvalue()

    import encrypt_pdf.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "pageIndex": 1,
        "splitKey": "s/uuid-1/page-0001.pdf",
        "box12Raw": "12345",
    }
    out = m.handler(event, None)
    _exact_keys(ENCRYPT_PDF_KEYS, out)
    assert out["encryptOk"] is True
    assert out["failureReason"] is None


@patch("encrypt_pdf.handler.put_object_json")
def test_encrypt_pdf_output_shape_failure(mock_put):
    import encrypt_pdf.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "pageIndex": 1,
        "splitKey": "s/uuid-1/page-0001.pdf",
        "box12Raw": "invalid",
    }
    out = m.handler(event, None)
    _exact_keys(ENCRYPT_PDF_KEYS, out)
    assert out["encryptOk"] is False
    assert out["protectedKey"] == ""
    assert "Box12 invalid" in str(out["failureReason"])


@patch("encrypt_pdf.handler.get_object_bytes")
@patch("encrypt_pdf.handler.put_object_bytes")
@patch("encrypt_pdf.handler.put_object_json")
def test_encrypt_pdf_encrypted_requires_password(mock_put_json, mock_put_bytes, mock_get):
    """Encrypted PDF requires correct password to decrypt."""
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    mock_get.return_value = buf.getvalue()

    import encrypt_pdf.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "pageIndex": 1,
        "splitKey": "s/uuid-1/page-0001.pdf",
        "box12Raw": "12345RT",
    }
    out = m.handler(event, None)
    assert out["encryptOk"] is True
    # Capture the encrypted PDF bytes (second call to put_object is the protected PDF)
    put_calls = mock_put_bytes.call_args_list
    protected_call = next((c for c in put_calls if c[0][1].endswith(".pdf")), None)
    assert protected_call is not None
    encrypted_bytes = protected_call[0][2]
    reader = PdfReader(BytesIO(encrypted_bytes))
    assert reader.is_encrypted
    reader.decrypt("12345")
    assert len(reader.pages) == 1


@patch("encrypt_pdf.handler.get_object_bytes")
@patch("encrypt_pdf.handler.put_object_bytes")
@patch("encrypt_pdf.handler.put_object_json")
def test_encrypt_pdf_box13_fallback(mock_put_json, mock_put_bytes, mock_get):
    """Encrypt uses Box13 when Box12 empty; digits before RT from Box13."""
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    mock_get.return_value = buf.getvalue()

    import encrypt_pdf.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "pageIndex": 1,
        "splitKey": "s/uuid-1/page-0001.pdf",
        "box12Raw": "",
        "box13Raw": "999888777RT",
    }
    out = m.handler(event, None)
    assert out["encryptOk"] is True
    put_calls = mock_put_bytes.call_args_list
    protected_call = next((c for c in put_calls if c[0][1].endswith(".pdf")), None)
    assert protected_call is not None
    encrypted_bytes = protected_call[0][2]
    reader = PdfReader(BytesIO(encrypted_bytes))
    assert reader.is_encrypted
    reader.decrypt("999888777")
    assert len(reader.pages) == 1


@patch("finalize_job.handler.put_object_json")
def test_finalize_job_output_shape(mock_put):
    import finalize_job.handler as m

    event = {
        "jobId": "uuid-1",
        "buckets": {"split": "S", "protected": "P", "results": "R"},
        "prefixes": {"split": "s/", "protected": "p/", "results": "r/"},
        "pages": [{"pageIndex": 1, "splitKey": "s/1.pdf"}],
        "pageOutcomes": [
            {
                "pageIndex": 1,
                "splitKey": "s/1.pdf",
                "parseOk": True,
                "encryptOk": True,
                "parseResultKey": "r/1-parse.json",
                "encryptResultKey": "r/1-encrypt.json",
                "protectedKey": "p/1.pdf",
                "failureStage": None,
                "failureReason": None,
            },
        ],
    }
    out = m.handler(event, None)
    _exact_keys(FINALIZE_KEYS, out)
    assert out["succeededCount"] == 1
    assert out["failedCount"] == 0


@patch("starter.handler._get_sfn_client")
def test_starter_builds_sfn_input_and_starts_execution(mock_get_client):
    """Starter builds SFN input from S3 event + env, calls StartExecution. No PDF processing."""
    mock_client = mock_get_client.return_value
    mock_client.start_execution.return_value = {"executionArn": "arn:aws:states:us-east-1:123:execution:sm:run-1"}

    import os
    import starter.handler as m

    with patch.dict(os.environ, {
        "STATE_MACHINE_ARN": "arn:aws:states:us-east-1:123:stateMachine:sm",
        "SPLIT_BUCKET": "S",
        "PROTECTED_BUCKET": "P",
        "RESULTS_BUCKET": "R",
    }):
        event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    "object": {"key": "incoming/test.pdf"},
                }
            }]
        }
        out = m.handler(event, None)

    mock_client.start_execution.assert_called_once()
    call_args = mock_client.start_execution.call_args
    assert call_args[1]["stateMachineArn"] == "arn:aws:states:us-east-1:123:stateMachine:sm"
    inp = __import__("json").loads(call_args[1]["input"])
    assert inp["source"] == {"bucket": "source-bucket", "key": "incoming/test.pdf"}
    assert inp["buckets"] == {"split": "S", "protected": "P", "results": "R"}
    assert inp["prefixes"] == {"split": "splits/", "protected": "protected/", "results": "results/"}
    assert out["started"] == 1
    assert out["results"][0]["executionArn"] == "arn:aws:states:us-east-1:123:execution:sm:run-1"


@patch("cleanup_splits.handler.list_keys")
@patch("cleanup_splits.handler.delete_keys")
def test_cleanup_splits_output_shape(mock_del, mock_list):
    mock_list.return_value = ["s/uuid-1/p1.pdf", "s/uuid-1/p2.pdf"]

    import cleanup_splits.handler as m

    event = {
        "jobId": "uuid-1",
        "split": {"bucket": "S", "jobPrefix": "s/uuid-1/"},
    }
    out = m.handler(event, None)
    _exact_keys(CLEANUP_KEYS, out)
    assert out["cleaned"] is True
    assert out["deletedCount"] == 2
