"""Emit application and server logs as JSON records understood by Dozzle."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Message


def get_log_level() -> str:
    """Read the shared severity threshold for Python and Gunicorn.

    Accept standard level names and common aliases only, so a setting valid
    for the application cannot fail later when Gunicorn starts its workers.

    Returns:
        Standard uppercase severity name.
    """
    level = os.environ.get("LOG_LEVEL", "DEBUG").strip().upper()
    level = {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(level, level)
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"Unsupported LOG_LEVEL: {level!r}")
    return level


def _level_name(name: str) -> str:
    """Normalize custom severities to levels supported by log viewers.

    Loguru's SUCCESS is informational and TRACE is diagnostic; mapping them
    keeps those records visible under Dozzle's corresponding level filters.

    Args:
        name: Python or Loguru severity name.

    Returns:
        Severity label recognized by the container log viewer.
    """
    return {"SUCCESS": "info", "TRACE": "debug", "WARNING": "warn",
            "CRITICAL": "fatal"}.get(name, name.lower())


def _json_sink(message: "Message") -> None:
    """Write each Loguru event as one JSON line to the container stream.

    Tracebacks stay inside the message string so Docker does not split their
    continuation lines into separate events without a severity.

    Args:
        message: Formatted Loguru event with its original record attached.

    Returns:
        None.
    """
    record = message.record
    payload = {
        "time": record["time"].astimezone(timezone.utc).isoformat(),
        "level": _level_name(record["level"].name),
        "message": str(message).rstrip("\n"),
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "extra": record["extra"],
    }
    pipeline = record["extra"].get("pipeline")
    if pipeline:
        payload["pipeline"] = pipeline
        payload["message"] = f"[{pipeline}] {payload['message']}"
    sys.stderr.write(json.dumps(payload, default=str) + "\n")
    sys.stderr.flush()


class DozzleFormatter(logging.Formatter):
    """Give standard-library and Gunicorn events the same JSON envelope."""

    def format(self, record: logging.LogRecord) -> str:
        """Preserve formatted arguments and exception text in one JSON event.

        Flask and Gunicorn use standard-library logging rather than Loguru,
        so their records need an independent formatter with the same fields.

        Args:
            record: Server or library event to serialize.

        Returns:
            Single JSON line containing the message and severity.
        """
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            message += "\n" + self.formatStack(record.stack_info)
        return json.dumps({
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": _level_name(record.levelname),
            "message": message,
            "logger": record.name,
            "function": record.funcName,
            "line": record.lineno,
        })


class SharedLogHandler(logging.Handler):
    """Forward standard-library events to the shared console and file sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        """Preserve standard formatting and exceptions when forwarding to Loguru.

        Logger-level filters run before this handler, keeping Flask's optional
        source-map suppression intact. Original caller fields replace this
        bridge's location so diagnostics still point to the emitting code.

        Args:
            record: Standard-library event accepted by its originating logger.

        Returns:
            None.
        """
        def preserve_caller(log_record: dict[str, Any]) -> None:
            """Keep source locations from the original standard-library event.

            Loguru otherwise attributes forwarded events to this handler.

            Args:
                log_record: Mutable Loguru record receiving caller fields.

            Returns:
                None.
            """
            log_record.update(name=record.name, function=record.funcName,
                              line=record.lineno)

        message = record.getMessage()
        if record.stack_info:
            message += "\n" + record.stack_info
        try:
            logger.level(record.levelname)
            level = record.levelname
        except ValueError:
            level = record.levelno
        logger.patch(preserve_caller).opt(exception=record.exc_info).log(level, message)


def configure_logging(logfile: str | None = None, pipeline: str | None = None) -> None:
    """Configure shared console logging and an optional rotating pipeline file.

    DEBUG is enabled by default because filtering in Dozzle cannot recover
    events discarded by Python. LOG_LEVEL can raise the threshold. Replacing
    sinks prevents imports and repeated pipeline runs from duplicating events;
    file logs retain their readable format and seven-day retention.

    Args:
        logfile: Optional rotating log path; a leading tilde is expanded.
        pipeline: Job label applied to all logs, including shared helper calls.

    Returns:
        None.
    """
    level = get_log_level()
    # Validate before removing working sinks, including Loguru's custom levels.
    severity = logger.level(level).no
    logger.remove()
    logger.configure(extra={"pipeline": pipeline} if pipeline else {})
    logger.add(_json_sink, format="{message}", level=level,
               colorize=False, backtrace=False, diagnose=False)
    if logfile:
        file_format = "{time} | {level} | {name}:{function}:{line} | "
        if pipeline:
            file_format += "[{extra[pipeline]}] "
        file_format += "{message}"
        logger.add(Path(logfile).expanduser(), level=level, rotation="10 MB",
                   retention="7 days", backtrace=False, diagnose=False,
                   format=file_format)
    logging.basicConfig(level=severity, handlers=[SharedLogHandler()], force=True)
