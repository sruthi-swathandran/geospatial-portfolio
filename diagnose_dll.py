"""
Windows DLL conflict diagnostic.

"DLL load failed ... the specified procedure could not be found" means Windows
loaded a DLL of the right NAME but the wrong BUILD. There are only three ways
that happens in a conda env, and this script checks all three and prints which
one you have:

  1. Another program's DLLs are shadowing the environment's (ArcGIS, QGIS,
     OSGeo4W and the Anaconda base env all ship gdal / freetype / libpng).
     -> shows up as a PATH entry containing those DLLs, ahead of the env.

  2. A package came from somewhere other than conda-forge (pip, defaults,
     another channel), compiled against different C libraries.
     -> shows up in the channel audit.

  3. The DLL the extension needs is missing from the env entirely.
     -> shows up as "NOT FOUND in env" for a library the import needs.

Run it in the activated environment:
    python diagnose_dll.py
"""

from __future__ import annotations

import ctypes
import glob
import os
import subprocess
import sys
import traceback
from pathlib import Path

if os.name != "nt":
    print("This diagnostic is for Windows only.")
    raise SystemExit(0)

LINE = "=" * 74

# DLLs that rasterio / matplotlib / pyproj depend on, and that other GIS
# software commonly installs a different build of.
PATTERNS = [
    "gdal*.dll", "geos_c.dll", "geos.dll", "proj*.dll",
    "freetype*.dll", "libpng*.dll", "zlib*.dll", "libzlib*.dll",
    "tiff*.dll", "libtiff*.dll", "jpeg*.dll", "libcurl*.dll",
    "sqlite3.dll", "libexpat*.dll", "openjp2.dll", "libssl*.dll",
]

prefix = Path(os.environ.get("CONDA_PREFIX", ""))
env_bin = prefix / "Library" / "bin" if prefix.name else None

print(LINE)
print("ENVIRONMENT")
print(LINE)
print(f"python        : {sys.version.split()[0]}")
print(f"executable    : {sys.executable}")
print(f"CONDA_PREFIX  : {prefix if prefix.name else '(not set — env not activated?)'}")
print(f"env Library\\bin exists: {env_bin.is_dir() if env_bin else False}")

# ---------------------------------------------------------------------------
# 1. PATH order — who gets to answer a DLL request first
# ---------------------------------------------------------------------------
print()
print(LINE)
print("1. PATH ENTRIES THAT CONTAIN GEO/GRAPHICS DLLs  (order matters)")
print(LINE)

path_dirs = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p.strip()]
suspects = []

for idx, d in enumerate(path_dirs):
    try:
        if not os.path.isdir(d):
            continue
        hits = []
        for pat in PATTERNS:
            hits += [os.path.basename(f) for f in glob.glob(os.path.join(d, pat))]
        if not hits:
            continue
        in_env = bool(prefix.name) and str(prefix).lower() in d.lower()
        tag = "ENV " if in_env else "OTHER"
        print(f"[{idx:>3}] {tag} {d}")
        print(f"      {len(hits)} match(es): {', '.join(sorted(set(hits))[:8])}"
              f"{' ...' if len(set(hits)) > 8 else ''}")
        if not in_env:
            suspects.append((idx, d, sorted(set(hits))))
    except Exception as exc:                                   # noqa: BLE001
        print(f"[{idx:>3}] could not scan {d}: {exc}")

if suspects:
    print("\n  >> Non-environment directories carrying these DLLs:")
    for idx, d, hits in suspects:
        print(f"     position {idx}: {d}")
    print("     If any of these sits EARLIER in PATH than the env's Library\\bin,")
    print("     that is your hijacker.")
else:
    print("\n  >> No outside directories on PATH carry these DLLs. Cause 1 ruled out.")

# ---------------------------------------------------------------------------
# 2. channel audit — anything not from conda-forge
# ---------------------------------------------------------------------------
print()
print(LINE)
print("2. PACKAGES NOT FROM conda-forge")
print(LINE)

try:
    out = subprocess.run(
        ["conda", "list", "--show-channel-urls"],
        capture_output=True, text=True, shell=True, timeout=120,
    ).stdout
    odd = []
    for line in out.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        channel = parts[-1] if parts else ""
        if "conda-forge" not in channel:
            odd.append(f"  {line.rstrip()}")
    if odd:
        print("\n".join(odd))
        print(f"\n  >> {len(odd)} package(s) from elsewhere. pypi entries are usually")
        print("     harmless for pure-Python packages, and a real problem for")
        print("     anything compiled (numpy, rasterio, matplotlib, shapely, pyproj).")
    else:
        print("  Everything is from conda-forge. Cause 2 ruled out.")
except Exception as exc:                                       # noqa: BLE001
    print(f"  could not run conda list: {exc}")

# ---------------------------------------------------------------------------
# 3. are the DLLs actually present in the env, and can they load
# ---------------------------------------------------------------------------
print()
print(LINE)
print("3. DLLs PRESENT IN THE ENVIRONMENT")
print(LINE)

if env_bin and env_bin.is_dir():
    for pat in ["gdal*.dll", "proj*.dll", "geos_c.dll", "freetype*.dll", "libpng*.dll"]:
        found = sorted(p.name for p in env_bin.glob(pat))
        status = ", ".join(found) if found else "NOT FOUND in env"
        print(f"  {pat:<16} {status}")

    print("\n  direct load test (bypasses python's import machinery):")
    for pat in ["gdal*.dll", "freetype*.dll"]:
        for dll in sorted(env_bin.glob(pat)):
            try:
                ctypes.WinDLL(str(dll))
                print(f"    ok   {dll.name}")
            except OSError as exc:
                print(f"    FAIL {dll.name}: {exc}")
            break
else:
    print("  env Library\\bin not found — is the environment activated?")

# ---------------------------------------------------------------------------
# 4. the failing imports, with full tracebacks
# ---------------------------------------------------------------------------
print()
print(LINE)
print("4. FAILING IMPORTS")
print(LINE)

for name in ["rasterio", "matplotlib.ft2font", "pyproj", "fiona"]:
    try:
        __import__(name)
        print(f"  ok   {name}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")

print()
print(LINE)
print("Send this whole output back. Section 1 or 2 will name the cause.")
print(LINE)
