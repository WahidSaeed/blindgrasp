"""Learners with one interface: fit(X, y) then predict_quantiles(Q) -> (q10, q50, q90).

TabPFN lives in tabpfn_service.py; the baselines here are the comparison for the in-context point.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

Z90 = 1.2815515655446004  # standard-normal 90% quantile -> 10-90% band = mean +/- Z90 * sd
QUANTILES = (0.1, 0.5, 0.9)


class Learner(Protocol):
    name: str

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Learner": ...

    def predict_quantiles(self, Q: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


class GPLearner:
    name = "gp"

    def __init__(self, length_scale: float = 0.05, noise: float = 1e-5):
        kernel = ConstantKernel(1.0, (1e-4, 1e3)) * RBF(length_scale, (5e-3, 1.0)) + WhiteKernel(noise, (1e-10, 1e-1))
        # Centre on the median, not the mean: far from data a GP reverts to its prior mean, and for a touch map
        # the mean is pulled up by probes on boxes (it sat above the 1 cm "occupied" line, so unexplored table
        # read as occupied). The median is the bare table, which is the right default.
        self.gp = GaussianProcessRegressor(kernel, normalize_y=False, n_restarts_optimizer=1, random_state=0)
        self.xs = StandardScaler()

    def fit(self, X, y):
        y = np.asarray(y, float)
        self.y0 = float(np.median(y))
        self.ys = float(np.std(y)) or 1.0
        self.gp.fit(self.xs.fit_transform(X), (y - self.y0) / self.ys)
        return self

    def predict_quantiles(self, Q):
        mu, sd = self.gp.predict(self.xs.transform(Q), return_std=True)
        mu, sd = mu * self.ys + self.y0, sd * self.ys
        return mu - Z90 * sd, mu, mu + Z90 * sd


class KNNLearner:
    name = "knn"

    def __init__(self, k: int = 5):
        self.k = k
        self.xs = StandardScaler()

    def fit(self, X, y):
        self.y = np.asarray(y)
        Xs = self.xs.fit_transform(X)
        self.nn = NearestNeighbors(n_neighbors=min(self.k, len(self.y))).fit(Xs)
        return self

    def predict_quantiles(self, Q):
        _, idx = self.nn.kneighbors(self.xs.transform(Q))
        vals = self.y[idx]
        q = np.quantile(vals, QUANTILES, axis=1)
        return q[0], q[1], q[2]


class MLPLearner:
    """Small MLP ensemble; the spread across members stands in for the 10-90% band."""

    name = "mlp"

    def __init__(self, members: int = 5, hidden=(64, 64), max_iter: int = 2000):
        self.members = [MLPRegressor(hidden_layer_sizes=hidden, max_iter=max_iter, learning_rate_init=3e-3, random_state=s)
                        for s in range(members)]
        self.xs, self.ys = StandardScaler(), StandardScaler()

    def fit(self, X, y):
        Xs = self.xs.fit_transform(X)
        ys = self.ys.fit_transform(np.asarray(y).reshape(-1, 1)).ravel()
        for m in self.members:
            m.fit(Xs, ys)
        return self

    def predict_quantiles(self, Q):
        Qs = self.xs.transform(Q)
        P = np.stack([self.ys.inverse_transform(m.predict(Qs).reshape(-1, 1)).ravel() for m in self.members])
        mu, sd = P.mean(0), P.std(0)
        return mu - Z90 * sd, mu, mu + Z90 * sd


def make_learner(name: str, **kwargs) -> Learner:
    if name in ("tabpfn", "tabpfn_nn"):
        from src.learn.tabpfn_service import TabPFNLearner

        return TabPFNLearner(nn_features=name == "tabpfn_nn", **kwargs)
    return {"gp": GPLearner, "knn": KNNLearner, "mlp": MLPLearner}[name](**kwargs)


def learner_kwargs(name: str, n_estimators: int | None = None) -> dict:
    """Options that only make sense for some learners (TabPFN's ensemble size)."""
    return {"n_estimators": n_estimators} if name.startswith("tabpfn") and n_estimators else {}
