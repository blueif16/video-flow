"""Per-model adapters for the generating runner.

Each adapter exposes the SAME interface so a real provider is a drop-in swap:

    def generate(req: dict, project_dir: str) -> dict
        # req:  the CANONICAL, already-validated request (see CONTRACTS §2),
        #       plus the runner-injected key `_node_id` (str | None).
        # ret:  the envelope {"model","output_files":[abs...],"data":{...}}

The runner's presence-router selects an adapter by `model`; everything upstream
(validate-before-spend, normalization, content-addressing) is model-agnostic and
lives in runner.py. To plug in fal/replicate, fill in their `generate` — nothing
else changes.
"""
from . import mock, fal, replicate

# model name -> module exposing generate(req, project_dir) -> envelope
ADAPTERS = {
    "mock": mock,
    "fal": fal,
    "replicate": replicate,
}

__all__ = ["ADAPTERS", "mock", "fal", "replicate"]
