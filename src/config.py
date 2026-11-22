"""Project config: loads .env, resolves the TabPFN backend and device.

Backend rules:
  BLINDGRASP_BACKEND=local|hosted overrides everything.
  Otherwise: local if a CUDA or Apple MPS device is available, else hosted.
Device (local only): BLINDGRASP_DEVICE=cuda|mps|cpu, else best available.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

Backend = str  # "local" | "hosted"


def tabpfn_token() -> str | None:
    tok = os.environ.get("TABPFN_TOKEN", "").strip()
    return tok if tok and not tok.startswith("<") else None


def best_device() -> str:
    forced = os.environ.get("BLINDGRASP_DEVICE", "").strip().lower()
    if forced:
        return forced
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_backend() -> Backend:
    forced = os.environ.get("BLINDGRASP_BACKEND", "").strip().lower()
    if forced in ("local", "hosted"):
        return forced
    return "local" if best_device() in ("cuda", "mps") else "hosted"


@dataclass(frozen=True)
class Config:
    backend: Backend
    device: str
    has_token: bool


def load() -> Config:
    return Config(backend=resolve_backend(), device=best_device(), has_token=tabpfn_token() is not None)


def make_regressor(backend: Backend | None = None, device: str | None = None, **kwargs):
    """Return a TabPFNRegressor for the chosen backend (same fit/predict interface)."""
    backend = backend or resolve_backend()
    if backend == "hosted":
        import tabpfn_client

        tok = tabpfn_token()
        if tok is None:
            raise RuntimeError("Hosted backend needs TABPFN_TOKEN in .env")
        tabpfn_client.set_access_token(tok)
        return tabpfn_client.TabPFNRegressor(**kwargs)
    from tabpfn import TabPFNRegressor

    return TabPFNRegressor(device=device or best_device(), **kwargs)


if __name__ == "__main__":
    print(load())
