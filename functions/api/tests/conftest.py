"""Shared fixtures — sets TABLE_NAME before any import.

API modules read TABLE_NAME at import time, so we have to set it here
before pytest collection touches anything in functions/api/.
"""
from __future__ import annotations

import os

os.environ.setdefault("TABLE_NAME", "F1Data-test")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
