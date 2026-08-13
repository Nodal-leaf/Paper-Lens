"""
src/monitoring/logger.py

Structured JSON & File Logger for Paper Lens.
Tracks request_id, timestamp, endpoint, input, output, latency_ms, tokens_used, agent_invoked, errors, and log level.
Logs to both stdout and rotating JSON line logs in src/monitoring/logs/paper_lens_monitoring.jsonl.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_LOGS_DIR = Path(__file__).parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOGS_DIR / "paper_lens_monitoring.jsonl"


class PipelineLogger:
    """Centralized structured logger for API requests, agent runs, and pipeline execution."""

    def __init__(self, log_file: Path = _LOG_FILE):
        self.log_file = log_file

    def log(
        self,
        level: str = "INFO",
        endpoint: str = "pipeline",
        agent_invoked: Optional[str] = None,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        latency_ms: Optional[float] = None,
        tokens_used: Optional[Dict[str, int]] = None,
        errors: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Emits a structured JSON log entry to stdout and appends to monitoring log file.
        """
        req_id = request_id or f"req_{uuid.uuid4().hex[:10]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        tokens = tokens_used or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        log_record = {
            "request_id": req_id,
            "timestamp": timestamp,
            "level": level.upper(),
            "endpoint": endpoint,
            "agent_invoked": agent_invoked or "System",
            "input": self._sanitize_payload(input_data),
            "output": self._sanitize_payload(output_data),
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else 0.0,
            "tokens_used": tokens,
            "errors": errors,
        }

        # Format as single-line JSON
        json_line = json.dumps(log_record, ensure_ascii=False)

        # Print cleanly to stdout
        status_str = f" [ERROR: {errors}]" if errors else ""
        print(
            f"[MONITOR] [{log_record['timestamp']}] [{log_record['level']}] "
            f"Req: {req_id} | Agent: {log_record['agent_invoked']} | Endpoint: {endpoint} | "
            f"Latency: {log_record['latency_ms']}ms | Tokens: {tokens.get('total_tokens', 0)}{status_str}"
        )

        # Append to jsonl log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")
        except Exception as file_err:
            print(f"[PipelineLogger Error] Failed to write log to file: {file_err}")

        return log_record

    def _sanitize_payload(self, data: Any, max_len: int = 1000) -> Any:
        """Sanitizes input/output payloads to keep log lines clean and readable."""
        if data is None:
            return None
        if isinstance(data, (int, float, bool)):
            return data
        if isinstance(data, str):
            if len(data) > max_len:
                return data[:max_len] + f"... [truncated total {len(data)} chars]"
            return data
        if isinstance(data, list):
            if len(data) > 15:
                return f"<List with {len(data)} items>"
            return [self._sanitize_payload(item, max_len=200) for item in data[:5]]
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if k in ["pdf_bytes", "content_bytes", "raw_bytes"]:
                    sanitized[k] = "<binary bytes>"
                else:
                    sanitized[str(k)] = self._sanitize_payload(v, max_len=200)
            return sanitized
        return str(data)[:max_len]


# Global instance
monitor_logger = PipelineLogger()
