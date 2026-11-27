"""Logging helpers that work in both UI and headless sessions."""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "UniversalRigBridge"
_logger = logging.getLogger(LOGGER_NAME)
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("[URB] %(levelname)s %(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def debug(message):
    _logger.debug(message)


def info(message):
    _logger.info(message)


def warning(message):
    _logger.warning(message)


def error(message):
    _logger.error(message)


class Report:
    """Accumulates issues raised while analysing or exporting."""

    def __init__(self):
        self.issues = []

    def add(self, severity, message, context=""):
        self.issues.append({"severity": severity, "message": message, "context": context})

    def info(self, message, context=""):
        self.add("info", message, context)

    def warn(self, message, context=""):
        self.add("warning", message, context)

    def fail(self, message, context=""):
        self.add("error", message, context)

    @property
    def errors(self):
        return [issue for issue in self.issues if issue["severity"] == "error"]

    @property
    def warnings(self):
        return [issue for issue in self.issues if issue["severity"] == "warning"]

    def as_dict(self):
        return {
            "issues": list(self.issues),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }
