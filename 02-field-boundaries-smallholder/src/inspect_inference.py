"""
RS-02 stage 3, piece 1. Read FTW's inference CLI before building on it.

The district run needs three things the package may already do: fetch
Sentinel-2 for a season and stack it the way the model expects, run a
checkpoint over an arbitrary raster rather than over their chip dataset, and
turn a prediction into polygons.

Band order and normalisation have to match training exactly. Getting either
wrong produces a model running on inputs it never saw and a district map that
looks plausible and means nothing. The help text does not say what the order
is, so this reads the installed source.

Nothing is downloaded and nothing is written.

    python src\\inspect_inference.py
    python src\\inspect_inference.py --full
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

def module_names():
    """Every module in the installed ftw packages, so nothing is missed."""
    import pkgutil
    names = []
    for pkg in ("ftw_cli", "ftw"):
        try:
            mod = __import__(pkg)
        except Exception:                                     # noqa: BLE001
            continue
        names.append(pkg)
        for m in pkgutil.iter_modules(mod.__path__):
            names.append(f"{pkg}.{m.name}")
    return names

INTERESTING = ("download", "run", "polygonize", "inference", "stack",
               "preprocess", "normalize", "normalise", "bands", "signed")


def show(obj, label, limit):
    try:
        src = inspect.getsource(obj)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  {label}: source unavailable ({exc})")
        return
    lines = src.splitlines()
    print(f"\n  --- {label}  ({len(lines)} lines) ---")
    for line in lines[:limit]:
        print("  " + line)
    if len(lines) > limit:
        print(f"  ... {len(lines) - limit} more, rerun with --full ...")


def constants(mod, name):
    shown = False
    for attr in sorted(dir(mod)):
        if attr.startswith("_") or not attr.isupper():
            continue
        val = getattr(mod, attr)
        if not isinstance(val, (str, int, float, list, tuple, dict)):
            continue
        if not shown:
            print(f"\n  module constants in {name}")
            shown = True
        text = repr(val)
        print(f"    {attr} = {text[:300]}"
              + (" ..." if len(text) > 300 else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="print whole functions rather than the first 120 lines")
    ap.add_argument("--only", default="",
                    help="print only functions whose name contains this")
    args = ap.parse_args()
    limit = 10_000 if args.full else 120
    keys = (args.only.lower(),) if args.only else INTERESTING

    for name in module_names():
        try:
            mod = __import__(name, fromlist=["*"])
        except Exception as exc:                              # noqa: BLE001
            print(f"\n{name}: not importable ({type(exc).__name__}: {exc})")
            continue

        print("\n" + RULE)
        print(name)
        print(RULE)
        print(f"  file: {getattr(mod, '__file__', 'unknown')}")

        constants(mod, name)

        for attr in sorted(dir(mod)):
            if attr.startswith("_"):
                continue
            if not any(k in attr.lower() for k in keys):
                continue
            obj = getattr(mod, attr)
            if not callable(obj):
                continue
            owner = getattr(obj, "__module__", "") or ""
            if not owner.startswith(("ftw", "ftw_cli")):
                continue
            show(obj, f"{name}.{attr}", limit)

    print("\n" + RULE)
    print("What I need from this output: which STAC collection the download")
    print("uses, which bands it asks for and in what order, whether the two")
    print("seasonal windows are stacked window_b first as the dataset does,")
    print("what divisor the normalisation applies, and whether the run step")
    print("reads the raster in windows or loads it whole. Memory matters,")
    print("since a Rewa-sized mosaic is roughly a gigabyte per season.")
    print(RULE)

if __name__ == "__main__":
    main()