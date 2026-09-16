"""
Shared paths, constants and the one piece of geometry every RS-02 script needs.

WHICH COUNTRY
-------------
Every script reads the FTW_COUNTRY environment variable and defaults to india.
Results and figures are written under that country, so a second country can be
measured with the same code and neither overwrites the other.

    python src\\measure_fields.py                  india
    set FTW_COUNTRY=slovenia                       (Windows cmd)
    python src\\measure_fields.py                  slovenia

WHICH RASTER SAYS WHAT
----------------------
FTW ships three label rasters per chip, and only the 3-class one is
unambiguous:

    label_masks/instance          a parcel ID per pixel, with the parcel's own
                                  outer pixel ring eroded away
    label_masks/semantic_3class   0 background, 1 interior, 2 boundary ring,
                                  3 unlabelled
    label_masks/semantic_2class   0 NOT-FIELD, 1 interior, 3 unlabelled

The 2-class mask collapses background and boundary into a single 0, and that
collapse cost this project a wrong run. In India there is no background at all,
so 2class==0 and 3class==2 cover the identical pixels and either works. In
Slovenia 2class==0 is 87% of the chip, almost all of it verified background,
while the boundary ring is 2.67%. Keying the ring off the 2-class mask there
dilated every parcel three pixels into open ground.

So the ring is 3class == 2. Always. Everywhere.

THE RECONSTRUCTION
------------------
Eroding the ring is deliberate: a mask marking whole parcels lets adjacent
fields merge into one blob, and coding the ring separately is how a model is
taught to keep touching parcels apart. Counting instance pixels therefore
measures the parcel with its edge removed.

Measured on India, the ring is one pixel thick: 96.74% of ring pixels sit at
Euclidean distance 1.00 or 1.41 from an interior pixel, which is one ring
reached orthogonally and diagonally. full_fields() gives it back, assigning
each ring pixel to the nearest interior so adjacent parcels split a shared
boundary.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

COUNTRY = (os.environ.get("FTW_COUNTRY") or "india").strip().lower()

DATA = PROJECT / "data" / "ftw" / COUNTRY
RESULTS = PROJECT / "results" / COUNTRY
FIGURES = PROJECT / "figures" / COUNTRY

INSTANCE = DATA / "label_masks" / "instance"
C2_DIR = DATA / "label_masks" / "semantic_2class"
C3_DIR = DATA / "label_masks" / "semantic_3class"
IMG_A = DATA / "s2_images" / "window_a"
IMG_B = DATA / "s2_images" / "window_b"

# semantic_3class. The authority on what a pixel is.
C3_BACKGROUND = 0
C3_INTERIOR = 1
C3_BOUNDARY = 2
C3_UNLABELLED = 3

# semantic_2class. Value 0 is background OR boundary and cannot tell you which.
C2_NOT_FIELD = 0
C2_INTERIOR = 1
C2_UNLABELLED = 3

NATIVE_M = 10.0         # Sentinel-2's finest bands
MAX_RING_DIST = 3.0     # pixels; a ring further out than this is orphaned

SOURCE = ("Fields of The World (CC-BY-4.0), Kerner Lab via Source "
          "Cooperative. Sentinel-2 imagery, Copernicus / ESA.")

print(f"[ftw] country={COUNTRY}  data={DATA}")
if not DATA.exists():
    print(f"[ftw] WARNING: {DATA} does not exist. Download it, or set "
          f"FTW_COUNTRY to one you have.")


def chip_names():
    if not INSTANCE.exists():
        raise SystemExit(f"{INSTANCE} not found. Has the download finished?")
    return [p.name for p in sorted(INSTANCE.glob("*.tif"))]


def read_band(path, band=1, window=None):
    with rasterio.open(path) as s:
        return s.read(band, window=window)


def grid_pixel_m(names=None, n=80):
    """Ground size of one grid pixel, measured geodesically. Not assumed.

    This is a property of the country, not of FTW: 6.067 m in India,
    4.139 m in Slovenia. Never inherit it.
    """
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    names = names or chip_names()
    sizes = []
    for name in names[:n]:
        with rasterio.open(INSTANCE / name) as s:
            l, b, r, t = s.bounds
            _, _, w_m = geod.inv(l, (b + t) / 2, r, (b + t) / 2)
            sizes.append(w_m / s.width)
    return float(np.mean(sizes))


def full_fields(inst, c3, max_dist=MAX_RING_DIST, return_orphans=False):
    """Parcels with their eroded boundary ring given back.

    c3 is semantic_3class. The ring is value 2 there, and only there: the
    2-class mask cannot distinguish a boundary from background.

    Each ring pixel goes to the nearest interior, so two parcels sharing a
    boundary split it rather than one swallowing the whole band.

    The distance cap matters. Erosion can wipe out a parcel small enough that
    nothing survives of its interior, and its ring is then left with no parent.
    Without a cap those pixels get handed to whatever parcel happens to be
    nearest, which in testing was as far as 137 pixels away. Capped, they stay
    unassigned and are counted rather than silently inflating a neighbour.
    """
    ring = (c3 == C3_BOUNDARY)
    if inst.max() == 0:
        return (inst.copy(), int(ring.sum())) if return_orphans else inst.copy()
    if not ring.any():
        return (inst.copy(), 0) if return_orphans else inst.copy()

    from scipy.ndimage import distance_transform_edt
    # distance_transform_edt measures to the nearest ZERO of its input, so
    # passing (inst == 0) gives every non-interior pixel the distance to, and
    # the location of, the nearest labelled interior pixel.
    dist, idx = distance_transform_edt(inst == 0, return_indices=True)
    claim = ring & (dist <= max_dist)
    orphans = int((ring & ~claim).sum())

    full = inst.copy()
    nearest = inst[tuple(idx)]
    full[claim] = nearest[claim]
    return (full, orphans) if return_orphans else full


def load_labels(name, window=None, return_orphans=False):
    """instance, 2class, 3class and the reconstructed parcels, for one chip."""
    inst = read_band(INSTANCE / name, window=window)

    c3p = C3_DIR / name
    c3 = read_band(c3p, window=window) if c3p.exists() \
        else np.full(inst.shape, C3_UNLABELLED, np.uint8)

    c2p = C2_DIR / name
    c2 = read_band(c2p, window=window) if c2p.exists() \
        else np.full(inst.shape, C2_UNLABELLED, np.uint8)

    if return_orphans:
        full, orphans = full_fields(inst, c3, return_orphans=True)
        return inst, c2, c3, full, orphans
    return inst, c2, c3, full_fields(inst, c3)
