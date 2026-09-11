"""Shared helpers for the CareScribe model service.

Layering is strictly one-way:

    routers/  ->  services/  ->  utils/  ->  (config.py, catalog.py)

``utils`` never imports ``services``; ``services`` never imports ``routers``.
That keeps every model backend swappable without touching the HTTP layer.
"""
