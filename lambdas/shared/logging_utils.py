"""JSON logging helper for PDF T4 pipeline (Lambda-compatible)."""
import json
import logging
from datetime import datetime, timezone


def get_json_logger(name: str) -> logging.Logger:
    """Return a logger that emits JSON-formatted records."""
    logger = logging.getLogger(name)

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_obj = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                log_obj["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_obj)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger
