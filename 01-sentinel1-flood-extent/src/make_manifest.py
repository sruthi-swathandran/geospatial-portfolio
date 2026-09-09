"""
RS-01 / provenance - generate the data and results manifest.

Review finding F-14: without a manifest, "reproduces from a clean state" cannot
be checked. An analyst who re-runs the fetch scripts has no way to know whether
they got what we got.

This walks data/ and results/ and records, per directory group, the file count,
total size, and for small text artefacts a SHA-256 so the numbers themselves can
be checked rather than the byte counts around them. Rasters are recorded by
count and size only, since they are large and their content is checked by the
figures they produce.

The manifest is generated rather than written by hand, so it cannot drift away
from the tree it describes.

Outputs:
    MANIFEST.csv        one row per directory group
    MANIFEST_files.csv  one row per tracked small file, with digest

Usage:
    python src\\make_manifest.py
"""

from __future__ import annotations

import csv
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import PROJECT, DATA, RESULTS      # noqa: E402

# digested in full, because these carry the reported numbers
DIGEST_SUFFIXES = {".csv", ".json", ".txt", ".geojson"}
DIGEST_MAX_BYTES = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def group_of(path: Path) -> str:
    rel = path.relative_to(PROJECT)
    parts = rel.parts
    if len(parts) <= 2:
        return "/".join(parts[:-1]) or "."
    return "/".join(parts[:2])


def main() -> None:
    roots = [d for d in (DATA, RESULTS) if d.exists()]
    if not roots:
        raise SystemExit("neither data/ nor results/ exists; run the fetch "
                         "scripts first")

    groups: dict[str, dict] = defaultdict(
        lambda: {"files": 0, "bytes": 0, "suffixes": defaultdict(int)})
    rows = []

    for root in roots:
        for p in sorted(root.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            g = groups[group_of(p)]
            size = p.stat().st_size
            g["files"] += 1
            g["bytes"] += size
            g["suffixes"][p.suffix.lower() or "(none)"] += 1
            if p.suffix.lower() in DIGEST_SUFFIXES and size <= DIGEST_MAX_BYTES:
                rows.append({
                    "path": p.relative_to(PROJECT).as_posix(),
                    "bytes": size,
                    "sha256": sha256(p),
                })

    with open(PROJECT / "MANIFEST.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "files", "bytes", "megabytes", "file_types"])
        for name in sorted(groups):
            g = groups[name]
            types = ", ".join(f"{k} x{v}" for k, v in
                              sorted(g["suffixes"].items(), key=lambda kv: -kv[1]))
            w.writerow([name, g["files"], g["bytes"],
                        round(g["bytes"] / 1e6, 2), types])

    with open(PROJECT / "MANIFEST_files.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "bytes", "sha256"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["path"]))

    total_f = sum(g["files"] for g in groups.values())
    total_b = sum(g["bytes"] for g in groups.values())
    print(f"{total_f:,} files, {total_b/1e9:.2f} GB across "
          f"{len(groups)} group(s)\n")
    print(f"  {'group':<34}{'files':>8}{'MB':>12}")
    for name in sorted(groups):
        g = groups[name]
        print(f"  {name:<34}{g['files']:>8,}{g['bytes']/1e6:>12,.1f}")
    print(f"\n  {len(rows)} small artefact(s) digested into MANIFEST_files.csv")
    print("\n  A clean re-run should reproduce the group counts. The digests "
          "check the\n  reported numbers themselves: any change to a results "
          "CSV changes its\n  hash, which is what makes a claim of "
          "reproduction verifiable rather than\n  asserted.")


if __name__ == "__main__":
    main()
