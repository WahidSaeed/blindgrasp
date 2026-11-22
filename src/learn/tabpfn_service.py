"""TabPFN learner + the background service that keeps the simulation from ever waiting on a fit.

- ContextTable: the rows TabPFN conditions on, with timestamps so stale rows can be pruned.
- TabPFNLearner: TabPFNRegressor (local GPU/MPS/CPU or hosted API, see src/config.py) with quantile output.
- LearnerService: one worker thread. `submit(X, y, Q)` returns a Future; the main loop polls `.done()`
  and keeps stepping physics meanwhile. `latest` always holds the most recent finished prediction.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from src import config
from src.learn.baselines import QUANTILES, Learner


class TabPFNLearner:
    name = "tabpfn"

    def __init__(self, backend: str | None = None, device: str | None = None, nn_features: bool = False, **kwargs):
        """nn_features: append, for each row, the target value and distance of its 2 nearest *other* context rows.
        TabPFN sees tabular rows, not space; these features tell it 'what did we measure close by, and how close',
        and it learns in-context how far to trust a neighbour (sharp box edges vs smooth table)."""
        self.reg = config.make_regressor(backend, device, **kwargs)
        self.nn_features = nn_features
        if nn_features:
            self.name = "tabpfn_nn"

    def _augment(self, Q, exclude_self: bool):
        from scipy.spatial import cKDTree

        k = 2 + int(exclude_self)
        k_eff = min(k, len(self._Xc))
        d, i = cKDTree(self._Xc).query(Q, k=k_eff)
        d, i = d.reshape(len(Q), -1), i.reshape(len(Q), -1)
        if exclude_self:
            d, i = d[:, 1:], i[:, 1:]
        while d.shape[1] < 2:  # too few rows: repeat the last neighbour
            d, i = np.hstack([d, d[:, -1:]]), np.hstack([i, i[:, -1:]])
        return np.hstack([Q, self._yc[i[:, :2]], d[:, :2]])

    MIN_ROWS = 3   # TabPFN needs >= 2 rows; below this, answer "about this value, very unsure"

    def fit(self, X, y):
        y = np.asarray(y, np.float32)
        self._tiny = y if len(y) < self.MIN_ROWS else None
        if self._tiny is None:
            X = np.asarray(X, float)
            if self.nn_features:
                self._Xc, self._yc = X, np.asarray(y, float)
                X = self._augment(X, exclude_self=True)
            self.reg.fit(np.asarray(X, np.float32), y)
        return self

    def predict_quantiles(self, Q):
        if self._tiny is not None:
            m = float(np.median(self._tiny)) if len(self._tiny) else 0.0
            half = max(float(np.ptp(self._tiny)) if len(self._tiny) > 1 else 0.0, 0.05)
            n = len(Q)
            return np.full(n, m - half), np.full(n, m), np.full(n, m + half)
        Q = np.asarray(Q, float)
        if self.nn_features:
            Q = self._augment(Q, exclude_self=False)
        q = self.reg.predict(np.asarray(Q, np.float32), output_type="quantiles", quantiles=list(QUANTILES))
        return tuple(np.asarray(a, float) for a in q)


@dataclass
class ContextTable:
    """Rows (x -> y) with the sim time each was added."""
    n_features: int
    X: list = field(default_factory=list)
    y: list = field(default_factory=list)
    t: list = field(default_factory=list)
    version: int = 0

    def add(self, x, y: float, t: float) -> None:
        self.X.append(np.asarray(x, float))
        self.y.append(float(y))
        self.t.append(float(t))
        self.version += 1

    def __len__(self) -> int:
        return len(self.y)

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.y:
            return np.zeros((0, self.n_features)), np.zeros(0)
        return np.stack(self.X), np.array(self.y)

    def keep(self, mask: np.ndarray) -> int:
        """Keep rows where mask is True; return the number dropped."""
        mask = np.asarray(mask, bool)
        dropped = int((~mask).sum())
        if dropped:
            self.X = [x for x, k in zip(self.X, mask) if k]
            self.y = [v for v, k in zip(self.y, mask) if k]
            self.t = [v for v, k in zip(self.t, mask) if k]
            self.version += 1
        return dropped

    def drop_near(self, xy, radius: float, dims=(0, 1)) -> int:
        if not self.y:
            return 0
        X, _ = self.arrays()
        d = np.linalg.norm(X[:, list(dims)] - np.asarray(xy)[None], axis=1)
        return self.keep(d > radius)

    def window(self, n: int) -> int:
        """Keep only the last n rows."""
        if len(self) <= n:
            return 0
        return self.keep(np.arange(len(self)) >= len(self) - n)

    def clear(self) -> None:
        self.X, self.y, self.t = [], [], []
        self.version += 1


@dataclass
class Prediction:
    version: int           # ContextTable.version the fit used
    q10: np.ndarray
    q50: np.ndarray
    q90: np.ndarray
    seconds: float         # wall time of fit + predict
    n_rows: int


class LearnerService:
    """Runs fit + predict on a single background thread."""

    def __init__(self, learner_factory: Callable[[], Learner]):
        self._factory = learner_factory
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="learner")
        self._learner: Learner | None = None
        self._lock = threading.Lock()
        self.latest: Prediction | None = None
        self.pending: Future | None = None
        self.error: BaseException | None = None   # last fit failure (kept so callers can show it)
        self._failed_version: int | None = None

    def _job(self, version: int, X, y, Q) -> Prediction:
        t0 = time.perf_counter()
        if self._learner is None:
            self._learner = self._factory()
        q10, q50, q90 = self._learner.fit(X, y).predict_quantiles(Q)
        pred = Prediction(version, q10, q50, q90, time.perf_counter() - t0, len(y))
        with self._lock:
            if self.latest is None or pred.version >= self.latest.version:
                self.latest = pred
        return pred

    def submit(self, version: int, X: np.ndarray, y: np.ndarray, Q: np.ndarray) -> Future:
        self.pending = self._pool.submit(self._job, version, np.array(X), np.array(y), np.array(Q))
        self._pending_version = version
        return self.pending

    def busy(self) -> bool:
        return self.pending is not None and not self.pending.done()

    def submit_if_idle(self, table: ContextTable, Q: np.ndarray) -> bool:
        """Refit when new rows arrived and no job is running. Returns True if a job was started."""
        if self.busy() or len(table) == 0:
            return False
        if self.pending is not None and self.pending.exception() is not None:
            # A failed fit used to be resubmitted forever (callers waiting for a fresh map then never finished).
            # Record it, and only retry once the table has changed.
            if self._failed_version != self._pending_version:
                self.error, self._failed_version = self.pending.exception(), self._pending_version
                print(f"[learner] fit failed on {len(table)} rows: {type(self.error).__name__}: {self.error}", flush=True)
        if self._failed_version == table.version:
            return False
        if self.latest is not None and self.latest.version == table.version:
            return False
        X, y = table.arrays()
        self.submit(table.version, X, y, Q)
        return True

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
