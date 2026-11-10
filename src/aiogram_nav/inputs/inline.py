"""Opaque inline callback declarations."""

from .bindings import CallbackEntry
from .tokens import parse_callback_data, prepare_token

__all__ = ["CallbackEntry", "parse_callback_data", "prepare_token"]
