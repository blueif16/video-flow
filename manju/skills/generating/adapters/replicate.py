"""Replicate provider adapter — STUB.

Identical interface to mock.generate(req, project_dir) -> envelope. Wiring a real
key is the ONLY change: read REPLICATE_API_KEY, map the canonical request to the
chosen Replicate model's params (lossy), run it, download the result to
artifact_path(...), and return the same envelope shape mock returns.
"""
from __future__ import annotations

import os


def generate(req: dict, project_dir: str) -> dict:
    if not os.environ.get("REPLICATE_API_KEY"):
        raise RuntimeError("set REPLICATE_API_KEY")
    raise RuntimeError("replicate adapter not implemented — fill in generate() (see mock.py)")
