"""Utility helper functions."""
import uuid
import os
from typing import Optional


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def ensure_directory(path: str) -> None:
    """Ensure a directory exists, create if it doesn't."""
    os.makedirs(path, exist_ok=True)

