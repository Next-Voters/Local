"""Centralized logging utility.

All modules should import ``get_logger`` from here instead of
repeating ``import logging; logger = logging.getLogger(__name__)``.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance."""
    return logging.getLogger(name)
