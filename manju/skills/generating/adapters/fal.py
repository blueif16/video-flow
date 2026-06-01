"""fal.ai provider adapter — STUB.

Identical interface to mock.generate(req, project_dir) -> envelope. Wiring a real
key is the ONLY change: read FAL_API_KEY, map the canonical request to fal's
params (lossy — drop what the chosen fal model can't take), submit, download the
result to artifact_path(...), and return the same envelope shape mock returns.
"""
from __future__ import annotations

import os


def generate(req: dict, project_dir: str) -> dict:
    if not os.environ.get("FAL_API_KEY"):
        raise RuntimeError("set FAL_API_KEY")
    raise RuntimeError("fal adapter not implemented — fill in generate() (see mock.py)")
