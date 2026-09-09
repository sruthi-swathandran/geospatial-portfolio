"""
Shared chip I/O and SAR processing — no plotting, no heavy imports.

Split out of mask_chips.py so that scripts which only need to read chips and
filter SAR don't drag matplotlib (and therefore the whole font/XML stack) in
with them. That is good hygiene generally, and on your machine right now it is
the difference between a script running and a script dying on a DLL error in a
library it never uses.

Everything here is pure numpy / scipy / skimage / rasterio.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import uniform_filter
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_holes, remove_small_objects

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, LABELS_DIR, SPECKLE_WINDOW      # noqa: E402

SPLITS_DIR = LABELS_DIR / "splits"

MIN_OBJECT_PX = 25
MIN_HOLE_PX = 25
ASHMAN_MIN = 2.0
MIN_CLASS_FRAC = 0.10


# ---------------------------------------------------------------- io
def split_lookup() -> dict[str, str]:
    out = {}
    for path in sorted(SPLITS_DIR.glob("*.csv")):
        name = path.stem.replace("flood_", "").replace("_data", "")
        for row in csv.reader(path.read_text().splitlines()):
            if row and row[0].startswith(f"{EVENT}_"):
                out[row[0].split("_")[1]] = name
    return out


def read(layer: str, chip_id: str) -> np.ndarray:
    with rasterio.open(LABELS_DIR / layer / f"{EVENT}_{chip_id}_{layer}.tif") as src:
        return src.read()


def chip_ids() -> list[str]:
    return sorted(p.name.split("_")[1]
                  for p in (LABELS_DIR / "S1Hand").glob(f"{EVENT}_*_S1Hand.tif"))


# ---------------------------------------------------------------- SAR
def lee_filter(db: np.ndarray, size: int = SPECKLE_WINDOW) -> np.ndarray:
    """Lee speckle filter, applied in linear power, returned in dB."""
    valid = np.isfinite(db)
    if not valid.any():
        return db
    linear = np.power(10.0, db / 10.0)
    x = np.where(valid, linear, np.nanmean(linear[valid]))
    mean = uniform_filter(x, size)
    var = np.clip(uniform_filter(x * x, size) - mean * mean, 0, None)
    overall = float(np.var(x[valid]))
    w = var / (var + overall) if overall > 0 else np.zeros_like(var)
    out = 10.0 * np.log10(np.clip(mean + w * (x - mean), 1e-10, None))
    return np.where(valid, out, np.nan)


def block_mean(a: np.ndarray, size: int = 5) -> np.ndarray:
    """
    Mean filter that tolerates NaN, keeping NaN where the input had it.

    Used before comparing two SAR images. Speckle is an independent random
    realisation in each processing chain, so over low-contrast ground it
    dominates the variance and drives pixel correlation towards zero even when
    both images are correct. Averaging suppresses speckle by roughly the square
    root of the window area while leaving real structure intact, which is what
    makes correlation a usable agreement measure at all.
    """
    valid = np.isfinite(a)
    if not valid.any():
        return a
    filled = np.where(valid, a, np.nanmean(a[valid]))
    return np.where(valid, uniform_filter(filled, size), np.nan)


def ashman_d(values: np.ndarray, threshold: float) -> float:
    lo, hi = values[values <= threshold], values[values > threshold]
    if lo.size < 2 or hi.size < 2:
        return 0.0
    denom = np.sqrt(lo.std() ** 2 + hi.std() ** 2)
    return 0.0 if denom == 0 else float(np.sqrt(2) * abs(hi.mean() - lo.mean()) / denom)


def global_otsu(db: np.ndarray) -> float | None:
    vals = db[np.isfinite(db)]
    return None if vals.size < 100 else float(threshold_otsu(vals))


def tiled_otsu(db: np.ndarray, tile: int, gated: bool,
               max_threshold: float) -> tuple[float | None, int, int]:
    """
    Otsu per tile, keeping only tiles that look like they contain water.

    gated=False falls back to a global Otsu when nothing qualifies (round 1
    behaviour, kept so the ablation still reproduces). gated=True returns None,
    meaning "no water here", which is the honest answer for a dry chip.
    """
    h, w = db.shape
    accepted, examined = [], 0
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            patch = db[y:y + tile, x:x + tile]
            vals = patch[np.isfinite(patch)]
            examined += 1
            if vals.size < 0.5 * patch.size or vals.size < 100:
                continue
            try:
                t = float(threshold_otsu(vals))
            except ValueError:
                continue
            frac_lo = float(np.mean(vals <= t))
            if frac_lo < MIN_CLASS_FRAC or (1 - frac_lo) < MIN_CLASS_FRAC:
                continue
            if ashman_d(vals, t) < ASHMAN_MIN:
                continue
            if gated and t > max_threshold:
                continue
            accepted.append(t)
    if accepted:
        return float(np.median(accepted)), len(accepted), examined
    return (None if gated else global_otsu(db)), 0, examined


def morph_clean(mask: np.ndarray) -> np.ndarray:
    """
    Drop specks, fill pinholes.

    scikit-image 0.26 renamed these parameters and changed the comparison from
    "smaller than" to "smaller than or equal to", so max_size = N - 1 matches
    the old min_size = N. Both spellings are handled.
    """
    m = mask.astype(bool)
    try:
        m = remove_small_objects(m, max_size=MIN_OBJECT_PX - 1)
        m = remove_small_holes(m, max_size=MIN_HOLE_PX - 1)
    except TypeError:
        m = remove_small_objects(m, min_size=MIN_OBJECT_PX)
        m = remove_small_holes(m, area_threshold=MIN_HOLE_PX)
    return m.astype(np.int8)
