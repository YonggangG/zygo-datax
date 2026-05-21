"""Wavefront metric and low-order fitting utilities.

All numeric arrays are expected to be in waves unless stated otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class MetricResult:
    pv: float
    rms: float
    power_x: float
    power_y: float
    power_mean: float
    irregularity: float
    coefficients: dict[str, float]


def valid_points(wavefront: np.ndarray, mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return x, y, z vectors for finite points inside the optional mask.

    Coordinates are normalized to x,y in [-1, 1] over the image width/height.
    """
    wf = np.asarray(wavefront, dtype=float)
    if mask is None:
        valid = np.isfinite(wf)
    else:
        valid = np.asarray(mask, dtype=bool) & np.isfinite(wf)

    yy, xx = np.indices(wf.shape)
    h, w = wf.shape
    x = (xx / max(w - 1, 1)) * 2 - 1
    y = (yy / max(h - 1, 1)) * 2 - 1
    return x[valid], y[valid], wf[valid]


def design_matrix(x: np.ndarray, y: np.ndarray, terms: Iterable[str]) -> np.ndarray:
    """Build a rectangular polynomial design matrix."""
    columns = []
    for term in terms:
        if term == "piston":
            columns.append(np.ones_like(x))
        elif term == "tilt_x":
            columns.append(x)
        elif term == "tilt_y":
            columns.append(y)
        elif term == "power_x":
            columns.append(x**2)
        elif term == "power_y":
            columns.append(y**2)
        elif term == "saddle_xy":
            columns.append(x * y)
        elif term == "x3":
            columns.append(x**3)
        elif term == "y3":
            columns.append(y**3)
        elif term == "x2y":
            columns.append((x**2) * y)
        elif term == "xy2":
            columns.append(x * (y**2))
        else:
            raise ValueError(f"Unknown polynomial term: {term}")
    return np.column_stack(columns)


def fit_polynomial(
    wavefront: np.ndarray,
    mask: np.ndarray | None = None,
    terms: tuple[str, ...] = ("piston", "tilt_x", "tilt_y", "power_x", "power_y", "saddle_xy"),
) -> tuple[np.ndarray, dict[str, float]]:
    """Fit rectangular polynomial terms and return fitted surface plus coefficients."""
    x, y, z = valid_points(wavefront, mask)
    if z.size < len(terms):
        raise ValueError("Not enough valid points for polynomial fit")
    A = design_matrix(x, y, terms)
    coeff, *_ = np.linalg.lstsq(A, z, rcond=None)

    yy, xx = np.indices(np.asarray(wavefront).shape)
    h, w = wavefront.shape
    gx = (xx / max(w - 1, 1)) * 2 - 1
    gy = (yy / max(h - 1, 1)) * 2 - 1
    G = design_matrix(gx.ravel(), gy.ravel(), terms)
    fitted = (G @ coeff).reshape(wavefront.shape)
    return fitted, dict(zip(terms, map(float, coeff)))


def compute_metrics(wavefront: np.ndarray, mask: np.ndarray | None = None) -> MetricResult:
    """Compute P-V, RMS, rectangular power, and irregularity.

    Irregularity is defined as residual P-V after removing piston, tilt_x,
    tilt_y, power_x, and power_y. The saddle_xy coefficient is reported but not
    subtracted in the default irregularity fit until convention matching is done.
    """
    wf = np.asarray(wavefront, dtype=float)
    valid = np.isfinite(wf) if mask is None else (np.asarray(mask, dtype=bool) & np.isfinite(wf))
    z = wf[valid]
    pv = float(np.nanmax(z) - np.nanmin(z))
    rms = float(np.nanstd(z - np.nanmean(z)))

    fitted, coeffs = fit_polynomial(wf, mask)
    residual = wf - fitted
    rz = residual[valid]
    irregularity = float(np.nanmax(rz) - np.nanmin(rz))
    px = coeffs.get("power_x", 0.0)
    py = coeffs.get("power_y", 0.0)
    return MetricResult(
        pv=pv,
        rms=rms,
        power_x=float(px),
        power_y=float(py),
        power_mean=float((px + py) / 2),
        irregularity=irregularity,
        coefficients=coeffs,
    )
