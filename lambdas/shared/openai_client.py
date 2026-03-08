"""OpenAI client for PDF T4 pipeline. Uses Responses API for document extraction."""
import io
import os

from shared.logging_utils import get_json_logger

_client = None
logger = get_json_logger(__name__)


def _resolve_api_key() -> str | None:
    """Resolve API key from env: OPENAI_SECRET_ARN, OPENAI_PARAM_NAME, or OPENAI_API_KEY."""
    import boto3
    secret_arn = os.environ.get("OPENAI_SECRET_ARN")
    if secret_arn:
        logger.info("Resolving OpenAI API key from Secrets Manager", extra={"source": "OPENAI_SECRET_ARN"})
        sm = boto3.client("secretsmanager")
        r = sm.get_secret_value(SecretId=secret_arn)
        return r.get("SecretString", "")
    param_name = os.environ.get("OPENAI_PARAM_NAME")
    if param_name:
        raw_param = param_name
        param_name = param_name.strip()
        # AWS rejects names where "ssm" is a prefix; extract from ARN or strip invalid prefix
        # Invalid chars (e.g. @) or missing leading / can also trigger the "ssm" error
        lower = param_name.lower()
        if lower.startswith("arn:aws:ssm:"):
            # ARN: arn:aws:ssm:region:account:parameter/name -> extract name
            idx = lower.find("parameter/")
            param_name = param_name[idx + 10:] if idx >= 0 else param_name.split(":", 5)[-1].lstrip("/")
        elif lower.startswith("ssm") or lower.startswith("/ssm"):
            # Strip ssm:, ssm/, /ssm/ (AWS rejects prefix "ssm")
            param_name = param_name.lstrip("/")
            if param_name.lower().startswith("ssm"):
                param_name = param_name[3:].lstrip(":/")
            param_name = param_name.lstrip("/")
        # Hierarchical params require leading slash; root params can use either
        if param_name and "/" in param_name and not param_name.startswith("/"):
            param_name = "/" + param_name
        logger.info(
            "Resolving OpenAI API key from SSM",
            extra={
                "raw_openai_param_name": raw_param,
                "normalized_param_name": param_name,
                "source": "OPENAI_PARAM_NAME",
            },
        )
        try:
            ssm = boto3.client("ssm")
            r = ssm.get_parameter(Name=param_name, WithDecryption=True)
            return r["Parameter"]["Value"]
        except Exception as e:
            logger.error(
                "SSM GetParameter failed",
                extra={
                    "param_name": param_name,
                    "raw_param_name": raw_param,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            raise
    return os.environ.get("OPENAI_API_KEY")


def get_client():
    """Return configured OpenAI client."""
    global _client
    if _client is None:
        from openai import OpenAI
        api_key = _resolve_api_key()
        _client = OpenAI(api_key=api_key)
    return _client


def extract_t4_from_pdf(pdf_bytes: bytes, instructions: str, filename: str = "page.pdf") -> str:
    """
    Upload PDF to OpenAI and call Responses API to extract Canada T4 fields.
    Returns raw model output text (expect JSON).
    """
    client = get_client()
    file_obj = io.BytesIO(pdf_bytes)
    file_obj.name = filename

    file_response = client.files.create(file=file_obj, purpose="user_data")
    file_id = file_response.id

    response = client.responses.create(
        model=os.environ.get("OPENAI_T4_MODEL", "gpt-4o"),
        instructions=instructions,
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": file_id},
                    {"type": "input_text", "text": "Extract T4 or T4A slip data from this PDF. Return JSON only."},
                ],
            },
        ],
    )

    if hasattr(response, "output_text") and response.output_text:
        return response.output_text
    text_parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if hasattr(item, "content") and item.content:
            for block in item.content:
                if hasattr(block, "text") and block.text:
                    text_parts.append(block.text)
        elif hasattr(item, "text") and item.text:
            text_parts.append(item.text)
    return "".join(text_parts) if text_parts else ""
