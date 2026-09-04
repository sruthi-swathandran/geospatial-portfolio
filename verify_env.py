"""
Step 0 check — does the environment work, and can it reach the data?

Run this BEFORE anything else. It separates the three things that can go wrong
into three clearly labelled sections, so when something fails you know which
problem you have instead of guessing:

  A. imports        -> the conda environment is broken (usually GDAL/DLL)
  B. rasterio + CRS -> GDAL and PROJ are installed but not talking to each other
  C. STAC reach     -> the libraries are fine, the network or the API is not

Usage:
    conda activate geo-portfolio
    python verify_env.py
"""

from __future__ import annotations

import sys
import traceback

OK = "  ok   "
BAD = " FAIL  "


def section(title):
    print(f"\n{title}\n{'-' * len(title)}")


# --------------------------------------------------------------------------
# A. imports
# --------------------------------------------------------------------------
section("A. imports")

MODULES = [
    "numpy", "pandas", "scipy", "skimage", "sklearn",
    "rasterio", "rioxarray", "xarray", "dask",
    "geopandas", "shapely", "pyproj",
    "pystac_client", "odc.stac", "matplotlib", "pyarrow",
]

missing = []
for name in MODULES:
    try:
        mod = __import__(name)
        version = getattr(mod, "__version__", "")
        print(f"{OK} {name:<16} {version}")
    except Exception as exc:                                   # noqa: BLE001
        missing.append(name)
        print(f"{BAD} {name:<16} {type(exc).__name__}: {exc}")

# planetary_computer is optional — only needed for the Planetary Computer route
try:
    import planetary_computer
    print(f"{OK} {'planetary_computer':<16} {getattr(planetary_computer, '__version__', '')}")
except Exception as exc:                                       # noqa: BLE001
    print(f"  note  planetary_computer not importable ({exc}). "
          "Only needed for the Planetary Computer access route; "
          "install with: pip install planetary-computer")

# --------------------------------------------------------------------------
# B. rasterio + PROJ actually functioning
# --------------------------------------------------------------------------
section("B. rasterio / GDAL / PROJ")

try:
    import rasterio
    from rasterio.crs import CRS
    from pyproj import Transformer

    print(f"{OK} GDAL version reported by rasterio: {rasterio.__gdal_version__}")

    # A CRS round-trip exercises PROJ's data files. If PROJ's grid directory is
    # missing (the classic broken-conda-mix symptom), this is where it shows up.
    crs = CRS.from_epsg(32646)      # UTM 46N — covers the Brahmaputra AOI
    print(f"{OK} EPSG:32646 -> {crs.to_string()}")

    t = Transformer.from_crs("EPSG:4326", "EPSG:32646", always_xy=True)
    x, y = t.transform(93.10, 26.47)     # centroid of the India flood event
    print(f"{OK} reprojected 93.10E 26.47N -> {x:,.0f}E {y:,.0f}N (UTM 46N)")
except Exception:                                              # noqa: BLE001
    print(f"{BAD} rasterio/PROJ check failed:")
    traceback.print_exc()

# --------------------------------------------------------------------------
# C. can this machine reach the STAC APIs
# --------------------------------------------------------------------------
section("C. STAC API reachability")

APIS = [
    ("Planetary Computer", "https://planetarycomputer.microsoft.com/api/stac/v1",
     "sentinel-1-rtc"),
    ("Earth Search",       "https://earth-search.aws.element84.com/v1",
     "sentinel-1-grd"),
]

reachable = []
for label, url, collection in APIS:
    try:
        from pystac_client import Client
        client = Client.open(url)
        coll = client.get_collection(collection)
        extent = coll.extent.temporal.intervals[0]
        start = extent[0].date().isoformat() if extent[0] else "?"
        end = extent[1].date().isoformat() if extent[1] else "open"
        print(f"{OK} {label:<20} {collection} available, temporal extent {start} .. {end}")
        reachable.append(label)
    except Exception as exc:                                   # noqa: BLE001
        print(f"{BAD} {label:<20} {type(exc).__name__}: {exc}")

# --------------------------------------------------------------------------
section("summary")
print(f"python           : {sys.version.split()[0]}")
print(f"missing modules  : {', '.join(missing) if missing else 'none'}")
print(f"STAC APIs reached: {', '.join(reachable) if reachable else 'NONE'}")

if missing:
    print("\n-> Fix the environment first:  conda env update -f environment.yml --prune")
elif not reachable:
    print("\n-> Environment is fine; the network is the problem. Check whether a "
          "corporate proxy or VPN is intercepting HTTPS, and try again off the "
          "office network before we change any code.")
else:
    print("\n-> Ready. Next: python 01-sentinel1-flood-extent/src/find_scenes.py --event India")
