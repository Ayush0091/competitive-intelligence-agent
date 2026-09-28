"""Tagged console logging ([PLAN], [TOOL], ...) plus a JSONL trace file.

Only concise actions/results are logged — never hidden reasoning or secrets.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

LOGGER_NAME = "ci_agent"


class _TagFormatter(logging.Formatter):
    def __init__(self, verbose: bool = False) -> None:
        super().__init__()
        self.verbose = verbose

    def format(self, record: logging.LogRecord) -> str:
        tag = getattr(record, "tag", record.levelname)
        prefix = f"{self.formatTime(record, '%H:%M:%S')} " if self.verbose else ""
        return f"{prefix}[{tag}] {record.getMessage()}"


class _RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 6]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self.secrets:
            msg = msg.replace(s, "***REDACTED***")
        record.msg, record.args = msg, None
        return True


def redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, "***REDACTED***")
    return text


class Tracer:
    """Writes human-readable tagged lines and machine-readable JSONL events."""

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        jsonl_path: Path | None = None,
        secrets: list[str] | None = None,
        verbose: bool = False,
        quiet: bool = False,
    ) -> None:
        self.secrets = secrets or []
        self.logger = logging.getLogger(f"{LOGGER_NAME}.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.handlers.clear()
        if not quiet:
            handler = logging.StreamHandler(stream or sys.stdout)
            handler.setFormatter(_TagFormatter(verbose))
            handler.addFilter(_RedactFilter(self.secrets))
            self.logger.addHandler(handler)
        self._jsonl = jsonl_path.open("a", encoding="utf-8") if jsonl_path else None
        self.lines: list[str] = []  # kept for tests / transcripts

    def log(self, tag: str, message: str, **fields: Any) -> None:
        message = redact(message, self.secrets)
        self.lines.append(f"[{tag}] {message}")
        self.logger.info(message, extra={"tag": tag})
        if self._jsonl:
            event = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "tag": tag,
                "message": message,
                **{k: v for k, v in fields.items() if v is not None},
            }
            self._jsonl.write(json.dumps(event, default=str) + "\n")
            self._jsonl.flush()

    def raw(self, text: str) -> None:
        """Print a pre-formatted block (the plan) without a tag."""
        text = redact(text, self.secrets)
        self.lines.extend(text.splitlines())
        for handler in self.logger.handlers:
            stream = getattr(handler, "stream", None)
            if stream:
                stream.write(text + "\n")
                stream.flush()

    def close(self) -> None:
        if self._jsonl:
            self._jsonl.close()
            self._jsonl = None
