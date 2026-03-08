"""ID generation utilities for PDF T4 pipeline."""
from uuid import uuid4


def generate_job_id() -> str:
    """Generate a unique job ID as a UUID4 string."""
    return str(uuid4())
