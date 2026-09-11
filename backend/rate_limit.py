"""Shared rate limiter — avoids main <-> routes circular import.

RATE_LIMITS=off (CI/tests) disables limits entirely so parallel test
suites sharing one client IP don't trip them. Default: on.
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

if os.getenv("RATE_LIMITS", "on").lower() in ("off", "false", "0"):
    limiter = Limiter(key_func=get_remote_address, enabled=False)
else:
    limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])
