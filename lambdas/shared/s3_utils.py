"""S3 utility functions for PDF T4 pipeline."""
import boto3
import json

_s3 = boto3.client("s3")


def get_object_bytes(bucket: str, key: str) -> bytes:
    """Fetch object from S3 and return raw bytes."""
    response = _s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def put_object_bytes(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    """Upload bytes to S3."""
    _s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def list_keys(bucket: str, prefix: str) -> list[str]:
    """List object keys under the given prefix."""
    keys: list[str] = []
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def put_object_json(bucket: str, key: str, obj: dict) -> None:
    """Upload a JSON-serializable object to S3."""
    put_object_bytes(
        bucket=bucket,
        key=key,
        data=json.dumps(obj).encode("utf-8"),
        content_type="application/json",
    )


def delete_keys(bucket: str, keys: list[str]) -> None:
    """Delete multiple objects from S3. Handles batches of 1000 (S3 limit)."""
    for i in range(0, len(keys), 1000):
        batch = keys[i : i + 1000]
        _s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in batch]},
        )
