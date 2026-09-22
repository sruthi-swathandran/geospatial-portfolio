"""
RS-02 stage 2b. Generate every table the write-up quotes, from the CSVs.

COMPARISON.md was assembled by hand and drifted from the artefacts. Three
numbers disagreed with the files they cited, one of them by a factor of two,
because a budget figure was read off a table in the document that had rows
missing rather than off the generated column. This script removes the hand step.

It reads both countries' comparison CSVs, computes recall at FTW's object
budget the same way for all four methods, and writes the tables as markdown
ready to paste. Every row of every sweep is emitted, since the missing rows are
what caused the error.

The budget figure is flagged as interpolated or clamped. np.interp clamps
silently below the edge of a sweep, so a method that never reached FTW's object
count returns its coarsest measured value and looks like a measurement. Those
are marked so the write-up can say so.

    python src\\build_comparison.py
    python src\\build_comparison.py --sam-setting 0p88

Writes results/comparison_tables.md and prints the headline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
COUNTRIES = ("india", "slovenia")

# Ground width in metres. The parcel_width tables carry width in 10 m units,
# so these are that column times ten. Metres rather than grid pixels, because
# the two countries sit on grids of different fineness and a band measured in
# grid pixels means a different physical size in each.
WIDTH_EDGES_M = [0, 20, 30, 50, np.inf]
WIDTH_LABELS_M = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]

# The same widths cut finer, in native 10 m pixels, for the single-country
# tables. The coarse bands above are what the two countries can be compared
# across. These show the shape of each method's curve, which the coarse bands
# flatten out, and one method turns over inside a band they merge.
FINE_EDGES = [0, 2, 3, 4, 5, 7, 10, np.inf]
FINE_LABELS = ["under 2", "2 to 3", "3 to 4", "4 to 5",
               "5 to 7", "7 to 10", "10 and over"]

# The sweep values each method was run at, as the filenames spell them.
SWEEP_TAGS = {
    "watershed": ["0p005", "0p01", "0p02", "0p05", "0p08",
                  "0p1", "0p13", "0p16", "0p2", "0p3"],
    "felzenszwalb": ["25", "50", "100", "150", "200", "300", "400", "800"],
}

PRETTY = {
    "ftw": "FTW 3-class FULL",
    "watershed": "watershed",
    "felzenszwalb": "felzenszwalb",
    "sam_true": "SAM ViT-H true colour",
    "sam_false": "SAM ViT-H false colour",
}


def results_dir(country: str) -> Path:
    return F.PROJECT / "results" / country


def load_sweeps(country: str) -> dict:
    """Every method's sweep as a list of rows, from the two comparison CSVs."""
    rd = results_dir(country)
    out = {}

    seg = pd.read_csv(rd / "segmenter_comparison_min500.csv")
    for method, grp in seg.groupby("method"):
        rows = []
        for _, r in grp.iterrows():
            rows.append({
                "setting": str(r["setting"]),
                "objects": float(r["objects_per_chip"]),
                "median_iou": float(r["median_iou"]),
                "recall": float(r["recall"]),
                "null": float(r["null_recall"]),
            })
        out[str(method)] = sorted(rows, key=lambda d: d["objects"])

    sam_path = rd / "sam_comparison_vit_h_min500.csv"
    if sam_path.exists():
        # dtype forces the composite column to stay text. Left alone, pandas
        # reads the values "true" and "false" as booleans, the key comes out
        # as sam_True, and SAM drops silently out of every table.
        sam = pd.read_csv(sam_path, dtype={"composite": str})
        for comp, grp in sam.groupby("composite"):
            comp = str(comp).strip().lower()
            rows = []
            for _, r in grp.iterrows():
                rows.append({
                    "setting": str(r["setting"]),
                    "objects": float(r["objects_per_chip"]),
                    "median_iou": float(r["median_iou"]),
                    "recall": float(r["recall"]),
                    "null": float(r["null_recall"]),
                })
            out[f"sam_{comp}"] = sorted(rows, key=lambda d: d["objects"])
    else:
        print(f"  {sam_path.name} is missing, so SAM is left out of {country}")
    return out


def at_budget(rows, budget: float) -> tuple:
    """Recall and null at a given object count, with how it was arrived at.

    A single-setting method returns its own value. Otherwise np.interp, which
    clamps outside the sweep. The flag says which happened, because a clamped
    figure is an upper or lower bound and not a measurement.
    """
    xs = [r["objects"] for r in rows]
    ys = [r["recall"] for r in rows]
    ns = [r["null"] for r in rows]
    if len(rows) == 1:
        return ys[0], ns[0], "single setting"
    if budget < min(xs):
        note = f"clamped, sweep stops at {min(xs):.0f} objects"
    elif budget > max(xs):
        note = f"clamped, sweep stops at {max(xs):.0f} objects"
    else:
        note = "interpolated"
    return (float(np.interp(budget, xs, ys)),
            float(np.interp(budget, xs, ns)), note)


def sweep_table(country: str, sweeps: dict) -> list:
    """The per-country table, every setting of every method."""
    lines = [
        "| method | setting | objects/chip | median IoU | recall | null | gap |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    order = ["ftw", "watershed", "felzenszwalb", "sam_true", "sam_false"]
    for key in order:
        if key not in sweeps:
            continue
        for r in sorted(sweeps[key], key=lambda d: -d["objects"]):
            setting = "" if key == "ftw" else r["setting"]
            gap = r["recall"] - r["null"]
            lines.append(
                f"| {PRETTY[key]} | {setting} | {r['objects']:,.0f} | "
                f"{r['median_iou']:.3f} | {r['recall']:.3f} | "
                f"{r['null']:.3f} | {gap:+.3f} |")
    return lines


def budget_table(country: str, sweeps: dict) -> tuple:
    """Every method read at FTW's object count."""
    budget = sweeps["ftw"][0]["objects"]
    lines = [
        f"| method | recall at {budget:.0f} objects/chip | null | gap | how |",
        "|---|---:|---:|---:|---|",
    ]
    vals = {}
    for key in ["ftw", "watershed", "felzenszwalb", "sam_true", "sam_false"]:
        if key not in sweeps:
            continue
        rec, nul, note = at_budget(sweeps[key], budget)
        vals[key] = rec
        lines.append(f"| {PRETTY[key]} | {rec:.3f} | {nul:.3f} | "
                     f"{rec - nul:+.3f} | {note} |")
    return lines, vals, budget


def width_file(country: str, key: str, sam_setting: str) -> Path:
    rd = results_dir(country)
    if key == "ftw":
        return rd / "parcel_width_seg_ftw_min500.csv"
    if key.startswith("sam_"):
        comp = key.split("_", 1)[1]
        return (rd / f"parcel_width_seg_sam_vit_h_{comp}_"
                     f"{sam_setting}_min500.csv")
    return rd / f"parcel_width_seg_{key}_min500.csv"


def read_widths(path: Path, iou: float, edges=None, labels=None,
                col: str = "metres") -> pd.DataFrame | None:
    if not path.exists():
        print(f"  {path.name} is missing, skipped")
        return None
    df = pd.read_csv(path)
    df["metres"] = df["width_native_px"] * 10.0
    df["hit"] = df["best_iou"] >= iou
    df["band"] = pd.cut(df[col],
                        WIDTH_EDGES_M if edges is None else edges,
                        labels=WIDTH_LABELS_M if labels is None else labels,
                        right=False)
    return df


def width_table(country: str, keys, sam_setting: str, iou: float,
                edges=None, labels=None, col: str = "metres",
                header: str = "ground width") -> list:
    """Recall by parcel width, one column per method."""
    labels = WIDTH_LABELS_M if labels is None else labels
    frames = {}
    for k in keys:
        df = read_widths(width_file(country, k, sam_setting), iou,
                         edges, labels, col)
        if df is not None:
            frames[k] = df
    if not frames:
        return []
    head = f"| {header} | parcels | " + " | ".join(
        PRETTY[k] for k in frames) + " |"
    sep = "|---|---:|" + "---:|" * len(frames)
    lines = [head, sep]
    any_df = next(iter(frames.values()))
    for lab in labels:
        n = int((any_df["band"] == lab).sum())
        if not n:
            continue
        cells = []
        for k, df in frames.items():
            s = df[df["band"] == lab]
            cells.append(f"{s['hit'].mean() * 100:.2f}%" if len(s) else "")
        lines.append(f"| {lab} | {n:,} | " + " | ".join(cells) + " |")
    return lines


def cross_country_table(keys, sam_setting: str, iou: float) -> list:
    """The same ground width band read in both countries, method by method.

    This is the check the floor claim has to survive. Both countries are the
    same Sentinel-2 at 10 m, so a parcel of a given width should be found at
    about the same rate in each if the limit is the imagery.
    """
    lines = [
        "| ground width | method | India | Slovenia | ratio |",
        "|---|---|---:|---:|---:|",
    ]
    loaded = {}
    for c in COUNTRIES:
        for k in keys:
            df = read_widths(width_file(c, k, sam_setting), iou)
            if df is not None:
                loaded[(c, k)] = df
    for k in keys:
        if ("india", k) not in loaded or ("slovenia", k) not in loaded:
            continue
        for lab in WIDTH_LABELS_M:
            a = loaded[("india", k)]
            a = a[a["band"] == lab]
            b = loaded[("slovenia", k)]
            b = b[b["band"] == lab]
            if not len(a) or not len(b):
                continue
            ra, rb = a["hit"].mean() * 100, b["hit"].mean() * 100
            ratio = f"{rb / ra:.1f}x" if ra > 0 else "not readable"
            lines.append(
                f"| {lab} | {PRETTY[k]} | {int(a['hit'].sum())}/{len(a):,}, "
                f"{ra:.2f}% | {int(b['hit'].sum())}/{len(b):,}, {rb:.2f}% | "
                f"{ratio} |")
    return lines


def legacy_map(country: str) -> list:
    """Which sweep setting each unsuffixed filename actually holds.

    The write-up cites these short names. They carry whichever setting scored
    best, which is not in the name, so a reader cannot tell what they are
    looking at. This prints the answer so the write-up can say it.
    """
    import hashlib
    rd = results_dir(country)
    lines = []

    def digest(p: Path) -> str:
        return hashlib.md5(p.read_bytes()).hexdigest()

    for method, tags in SWEEP_TAGS.items():
        legacy = rd / f"parcel_width_seg_{method}_min500.csv"
        if not legacy.exists():
            continue
        want = digest(legacy)
        match = "no sweep file matches it"
        for t in tags:
            cand = rd / f"parcel_width_seg_{method}_{t}_min500.csv"
            if cand.exists() and digest(cand) == want:
                match = t.replace("p", ".")
        lines.append(f"  {country:>9}  {legacy.name}  holds setting {match}")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sam-setting", default="0p50",
                    help="which SAM threshold the width tables use")
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()

    out = []
    headline = {}

    print(RULE)
    print("BUILDING COMPARISON TABLES FROM THE CSVs")
    print(RULE)

    for country in COUNTRIES:
        rd = results_dir(country)
        if not (rd / "segmenter_comparison_min500.csv").exists():
            sys.exit(f"{rd / 'segmenter_comparison_min500.csv'} not found")
        sweeps = load_sweeps(country)
        parcels = int(pd.read_csv(
            rd / "segmenter_comparison_min500.csv")["parcels"].iloc[0])

        out.append(f"\n## {country.capitalize()}, every setting\n")
        out.append(f"{parcels:,} labelled parcels.\n")
        out += sweep_table(country, sweeps)

        blines, vals, budget = budget_table(country, sweeps)
        headline[country] = (vals, budget)
        out.append(f"\n## {country.capitalize()}, at FTW's object budget\n")
        out += blines

        methods = ["ftw", "watershed", "sam_true", "sam_false"]
        caption = (f"SAM at threshold {args.sam_setting.replace('p', '.')}, "
                   f"classical methods at their best setting.\n")

        out.append(f"\n## {country.capitalize()}, recall by ground width\n")
        out.append(caption)
        out += width_table(country, methods, args.sam_setting, args.iou)

        out.append(f"\n## {country.capitalize()}, the same widths cut finer\n")
        out.append(caption)
        out += width_table(country, methods, args.sam_setting, args.iou,
                           FINE_EDGES, FINE_LABELS, "width_native_px",
                           "width, native 10 m px")

    out.append("\n## The same width band in both countries\n")
    out.append("Same sensor, same method, same physical parcel size.\n")
    out += cross_country_table(["ftw", "watershed", "sam_true"],
                               args.sam_setting, args.iou)

    dest = F.PROJECT / "results" / "comparison_tables.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("# Generated tables for COMPARISON.md\n"
                    "\nRebuild with `python src\\build_comparison.py`. "
                    "Do not edit by hand.\n"
                    + "\n".join(out) + "\n", encoding="utf-8")
    print(f"\n  wrote {dest.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("HEADLINE, for the text")
    print(RULE)
    for country, (vals, budget) in headline.items():
        parts = ", ".join(f"{PRETTY[k]} {v:.3f}" for k, v in vals.items())
        print(f"  {country} at {budget:.0f} objects/chip: {parts}")

    print("\n" + RULE)
    print("WHAT THE SHORT FILENAMES HOLD")
    print(RULE)
    for country in COUNTRIES:
        for line in legacy_map(country):
            print(line)

    print("\n" + RULE)
    print("Paste the tables from results/comparison_tables.md into")
    print("COMPARISON.md. Any number in the text that disagrees with them is")
    print("the text being wrong, not the table.")
    print(RULE)


if __name__ == "__main__":
    main()
