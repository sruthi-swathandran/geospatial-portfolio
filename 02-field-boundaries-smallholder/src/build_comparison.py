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
    # The first SAM run's composites, named by what SAM was actually given.
    # Their keys stay true and false because the files carry those names
    # (B-23).
    "sam_true": "SAM ViT-H, blue-green-red",
    "sam_false": "SAM ViT-H, NIR-blue-green",
    "sam_rgb": "SAM ViT-H natural colour",
    "sam_cir": "SAM ViT-H colour infrared",
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
    order = ["ftw", "watershed", "felzenszwalb", "sam_rgb", "sam_cir",
             "sam_true", "sam_false"]
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
    for key in ["ftw", "watershed", "felzenszwalb", "sam_rgb", "sam_cir",
                "sam_true", "sam_false"]:
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



# --- tables added after the review, from the measurements it asked for -----

PIXEL_EDGES = [0, 4, 6, 8, 12, np.inf]
PIXEL_LABELS = ["under 4 px", "4 to 6 px", "6 to 8 px", "8 to 12 px",
                "12 px up"]

PRECISION_NAMES = {
    "ftw": "FTW 3-class FULL",
    "watershed_0.02": "watershed 0.02",
    "watershed_0.05": "watershed 0.05",
    "sam_vit_h_false_0p5": "SAM ViT-H NIR-blue-green 0.50",
}


def grid_m(country: str) -> float:
    """The measured pixel size, with FTW_COUNTRY pointed at the right one."""
    import importlib
    import os
    os.environ["FTW_COUNTRY"] = country
    importlib.reload(F)
    return F.grid_pixel_m()


def precision_table(country: str) -> list:
    """Fragmentation and matched share, from the per-run summary rows."""
    path = results_dir(country) / "precision_summary.csv"
    if not path.exists():
        return [f"`{path.name}` not written yet, so this table is empty."]
    d = pd.read_csv(path)
    d = d[d["min_size_m2"] == 500].sort_values("objects_per_chip")
    lines = [
        "| method | objects/chip | no object | exactly one | 5 or more | "
        "matched share | parcels |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in d.iterrows():
        name = PRECISION_NAMES.get(str(r["method"]), str(r["method"]))
        note = " (subset)" if r["subset"] else ""
        lines.append(
            f"| {name}{note} | {r['objects_per_chip']:,.1f} | "
            f"{r['no_object_pct']:.1f}% | {r['exactly_one_pct']:.1f}% | "
            f"{r['five_or_more_pct']:.1f}% | "
            f"{r['matched_share'] * 100:.2f}% | {int(r['parcels']):,} |")
    return lines


def matched_parcel_table(country: str, subset_method: str) -> list:
    """Every method read on the parcels the subset run covered.

    A method measured on 100 chips cannot be set beside one measured on 399
    without this, because the two chip sets carry different parcel sizes.
    """
    rd = results_dir(country)
    ref = rd / f"precision_{subset_method}_min500.csv"
    if not ref.exists():
        return [f"`{ref.name}` not written yet, so this table is empty."]
    keys = set(map(tuple, pd.read_csv(ref)[["chip", "parcel_id"]].values))

    summary = pd.read_csv(rd / "precision_summary.csv")
    opc = dict(zip(summary["method"], summary["objects_per_chip"]))

    lines = [
        "| method | parcels | objects/chip | no object | exactly one "
        "| 5 or more |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for f in sorted(rd.glob("precision_*_min500.csv")):
        tag = f.name[len("precision_"):-len("_min500.csv")]
        d = pd.read_csv(f)
        d = d[[tuple(x) in keys for x in d[["chip", "parcel_id"]].values]]
        if not len(d):
            continue
        o = d["objects_over"]
        name = PRECISION_NAMES.get(tag, tag)
        # A generated table that prints nan tells the reader nothing about
        # why. Say which run is missing instead.
        rate = opc.get(tag)
        rate_txt = (f"{rate:,.1f}" if rate is not None and np.isfinite(rate)
                    else "no summary row")
        lines.append(
            f"| {name} | {len(d):,} | {rate_txt} | "
            f"{float((o == 0).mean()) * 100:.1f}% | "
            f"{float((o == 1).mean()) * 100:.1f}% | "
            f"{float((o >= 5).mean()) * 100:.1f}% |")
    return lines


# holdout.py writes the SAM composites by their file keys (B-23)
HOLDOUT_NAMES = {"sam_vit_h_true": "SAM ViT-H blue-green-red",
                 "sam_vit_h_false": "SAM ViT-H NIR-blue-green",
                 "sam_vit_h_rgb": "SAM ViT-H natural colour",
                 "sam_vit_h_cir": "SAM ViT-H colour infrared"}


def holdout_table(country: str) -> list:
    path = results_dir(country) / "holdout_selection.csv"
    if not path.exists():
        return [f"`{path.name}` not written yet, so this table is empty."]
    d = pd.read_csv(path)
    lines = ["| method | published | held out | optimism | setting |",
             "|---|---:|---:|---:|---|"]
    for _, r in d.iterrows():
        name = HOLDOUT_NAMES.get(str(r["method"]), r["method"])
        lines.append(
            f"| {name} | {r['published_recall']:.4f} | "
            f"{r['heldout_recall_median']:.4f} | {r['optimism']:+.4f} | "
            f"{r['modal_setting']} in "
            f"{r['setting_stability'] * 100:.0f}% of splits |")
    return lines


def registration_tables(iou: float) -> list:
    """Label displacement and edge contrast, both countries side by side.

    Everything here is cut in metres. An earlier version banded by pixel width,
    which has no single meaning on Slovenia's grid: its pixels are 4.138 m
    across and 6.002 m tall, so a width counted in pixels is a different
    distance depending on which way the parcel runs. See B-18.
    """
    out, frames = [], {}
    for c in COUNTRIES:
        path = results_dir(c) / "label_registration.csv"
        if not path.exists():
            return [f"`label_registration.csv` missing for {c}."]
        d = pd.read_csv(path)
        d["metres"] = d["width_native_px"] * 10.0
        rec = pd.read_csv(results_dir(c) / "parcel_width_seg_ftw_min500.csv")
        d = d.merge(rec[["chip", "parcel_id", "best_iou"]],
                    on=["chip", "parcel_id"], how="left")
        d["hit"] = d["best_iou"] >= iou
        frames[c] = d

    a, b = frames["india"], frames["slovenia"]
    out.append("\n### Displacement, overall\n")
    out += ["| | India | Slovenia |", "|---|---:|---:|"]
    out.append(f"| parcels | {len(a):,} | {len(b):,} |")
    out.append(f"| pixel east to west | {a['px_x_m'].mean():.3f} m "
               f"| {b['px_x_m'].mean():.3f} m |")
    out.append(f"| pixel north to south | {a['px_y_m'].mean():.3f} m "
               f"| {b['px_y_m'].mean():.3f} m |")
    out.append(f"| signed mean displacement | {a['offset_m'].mean():+.2f} m "
               f"| {b['offset_m'].mean():+.2f} m |")
    out.append(f"| median unsigned | {a['offset_m'].abs().median():.2f} m "
               f"| {b['offset_m'].abs().median():.2f} m |")
    out.append(f"| median parcel width | {a['metres'].median():.1f} m "
               f"| {b['metres'].median():.1f} m |")
    out.append(f"| median gain | {a['gain'].median():.3f}x "
               f"| {b['gain'].median():.3f}x |")
    out.append(f"| peak on the drawn edge | "
               f"{float((a['offset_m'] == 0).mean()) * 100:.1f}% | "
               f"{float((b['offset_m'] == 0).mean()) * 100:.1f}% |")
    out.append(f"| same on a borrowed field | "
               f"{float((a['null_offset_m'] == 0).mean()) * 100:.1f}% | "
               f"{float((b['null_offset_m'] == 0).mean()) * 100:.1f}% |")

    out.append("\n### Displacement and recall at matched ground width\n")
    out += ["| ground width | India offset | India recall | Slovenia offset "
            "| Slovenia recall |", "|---|---:|---:|---:|---:|"]
    for lab in WIDTH_LABELS_M:
        sa = a[pd.cut(a["metres"], WIDTH_EDGES_M, labels=WIDTH_LABELS_M,
                      right=False) == lab]
        sb = b[pd.cut(b["metres"], WIDTH_EDGES_M, labels=WIDTH_LABELS_M,
                      right=False) == lab]
        if not len(sa) or not len(sb):
            continue
        out.append(f"| {lab} | {sa['offset_m'].mean():+.2f} m | "
                   f"{sa['hit'].mean() * 100:.2f}% | "
                   f"{sb['offset_m'].mean():+.2f} m | "
                   f"{sb['hit'].mean() * 100:.2f}% |")

    out.append("\n### Edge over the parcel's own interior\n")
    out += ["| | India | Slovenia |", "|---|---:|---:|"]
    ea = a["edge_over_interior"].dropna()
    eb = b["edge_over_interior"].dropna()
    out.append(f"| median | {ea.median():.3f}x | {eb.median():.3f}x |")
    out.append(f"| share at or below 1.0 | "
               f"{float((ea <= 1.0).mean()) * 100:.1f}% | "
               f"{float((eb <= 1.0).mean()) * 100:.1f}% |")
    out.append(f"| parcels wide enough | {len(ea):,} | {len(eb):,} |")
    for lab in WIDTH_LABELS_M:
        sa = a[pd.cut(a["metres"], WIDTH_EDGES_M, labels=WIDTH_LABELS_M,
                      right=False) == lab]
        sb = b[pd.cut(b["metres"], WIDTH_EDGES_M, labels=WIDTH_LABELS_M,
                      right=False) == lab]
        va = sa["edge_over_interior"].median()
        vb = sb["edge_over_interior"].median()
        if np.isfinite(va) and np.isfinite(vb):
            out.append(f"| by width, {lab} | {va:.3f}x | {vb:.3f}x |")
    return out


def ring_tables() -> list:
    """F-12: every headline at each ring distance cap, from ring_sensitivity.py."""
    out = []
    data = {}
    for country in COUNTRIES:
        rd = results_dir(country)
        paths = [rd / f"ring_sensitivity{s}.csv"
                 for s in ("_truth", "", "_bands")]
        if not all(p.exists() for p in paths):
            out.append(f"\n{country.capitalize()}: run ring_sensitivity.py.\n")
            continue
        truth, rec, bands = (pd.read_csv(p) for p in paths)
        data[country] = bands
        out.append(f"\n### {country.capitalize()}\n")
        methods = [m for m in ("ftw", "watershed", "felzenszwalb")
                   if m in set(rec.method)]
        head = ("| cap | ring left out | median area | median width "
                "| under 30 m | " + " | ".join(
                    f"{PRETTY.get(m, m)} recall" for m in methods) + " |")
        out.append(head)
        out.append("|---|" + "---:|" * (4 + len(methods)))
        for _, r in truth.iterrows():
            cells = [r["cap"], f"{r['orphan_share'] * 100:.2f}%",
                     f"{r['median_area_ha']:.3f} ha",
                     f"{r['median_width_m']:.1f} m",
                     f"{r['share_under_30m'] * 100:.2f}%"]
            for m in methods:
                v = rec[(rec.cap == r["cap"]) & (rec.method == m)].recall
                cells.append(f"{float(v.iloc[0]):.4f}")
            out.append("| " + " | ".join(cells) + " |")

    if len(data) == 2:
        a, b = data["india"], data["slovenia"]
        out.append("\n### FTW at matched ground width, every cap\n")
        out.append("| cap | ground width | India | Slovenia | ratio |")
        out.append("|---|---|---:|---:|---:|")
        for cap in a.cap.unique():
            for band in WIDTH_LABELS_M[1:]:
                ra = a[(a.cap == cap) & (a.method == "ftw") & (a.band == band)]
                rb = b[(b.cap == cap) & (b.method == "ftw") & (b.band == band)]
                if ra.empty or rb.empty:
                    continue
                fa, na = int(ra.found.iloc[0]), int(ra.parcels.iloc[0])
                fb, nb = int(rb.found.iloc[0]), int(rb.parcels.iloc[0])
                pa, pb = fa / max(na, 1), fb / max(nb, 1)
                ratio = f"{pb / pa:.1f}x" if pa > 0 else "not readable"
                out.append(f"| {cap} | {band} | {fa}/{na:,}, {pa * 100:.2f}% "
                           f"| {fb}/{nb:,}, {pb * 100:.2f}% | {ratio} |")
    return out



SEASON_FTW = ["shipped", "swapped", "a twice", "b twice"]
SEASON_WS = ["both", "window_a", "window_b"]
WS_NAMES = {"both": "both windows stacked", "window_a": "window_a alone",
            "window_b": "window_b alone"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def shape_tables() -> list:
    """Parcel shape against the country gap, from shape_test.py."""
    path = F.PROJECT / "results" / "shape_test.csv"
    bands = F.PROJECT / "results" / "shape_test_bands.csv"
    if not (path.exists() and bands.exists()):
        return ["\nRun `python src\\shape_test.py`.\n"]
    s = pd.read_csv(path)
    out = [
        "| method | India | Slovenia | Slovenia, India's widths "
        "| Slovenia, India's widths and shapes | ratio, widths "
        "| ratio, widths and shapes | share from shape | six-band check |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in s.iterrows():
        # the ratios come from shape_test.py, which has the unrounded rates
        rw, rs = r["ratio_width"], r["ratio_width_shape"]
        out.append(
            f"| {r['method']} | {r['india'] * 100:.2f}% "
            f"| {r['slovenia'] * 100:.2f}% "
            f"| {r['slovenia_width'] * 100:.2f}% "
            f"| {r['slovenia_width_shape'] * 100:.2f}% "
            f"| {rw:.2f}x | {rs:.2f}x "
            f"| {r['share_from_shape']:+.2f} "
            f"[{r['share_lo']:+.2f}, {r['share_hi']:+.2f}] "
            f"| {r['share_six_band']:+.2f} |")

    b = pd.read_csv(bands)
    out.append("\n### Within each width band, Slovenia given India's "
               "shapes\n")
    out.append("| method | ground width | India | Slovenia "
               "| Slovenia, India's shapes | ratio | ratio after |")
    out.append("|---|---|---:|---:|---:|---:|---:|")
    for _, r in b.iterrows():
        n_found = int(r["india_found"])
        r_i = n_found / r["india_parcels"]
        r_s = r["slovenia_found"] / r["slovenia_parcels"]
        if n_found:
            before = f"{r_s / r_i:.1f}x"
            after = f"{r['slovenia_reweighted'] / r_i:.1f}x"
        else:
            before = after = "not readable"
        out.append(
            f"| {r['method']} | {r['width_band']} "
            f"| {n_found}/{int(r['india_parcels']):,}, "
            f"{r['india_recall'] * 100:.2f}% "
            f"| {r['slovenia_recall'] * 100:.2f}% "
            f"| {r['slovenia_reweighted'] * 100:.2f}% "
            f"| {before} | {after} |")
    return out


def season_dates(country: str) -> dict:
    """Each window's date range as words, from FTW's data config."""
    import json
    path = F.PROJECT / "data" / "ftw" / country / f"data_config_{country}.json"
    if not path.exists():
        return {}
    seasons = json.loads(path.read_text(encoding="utf-8")).get("seasons", {})
    out = {}
    for w, d in seasons.items():
        y0, m0 = int(d["start"][:4]), int(d["start"][5:7])
        y1, m1 = int(d["end"][:4]), int(d["end"][5:7])
        span = (f"{MONTHS[m0 - 1]} to {MONTHS[m1 - 1]} {y1}" if y0 == y1
                else f"{MONTHS[m0 - 1]} {y0} to {MONTHS[m1 - 1]} {y1}")
        out[w] = span
    return out


def paired_change(parcels: pd.DataFrame, variant: str, boots: int,
                  rng) -> tuple:
    """Recall change from the shipped run, with whole chips resampled.

    Both runs score the same parcels, so the change is read chip by chip.
    That is tighter than comparing two separate intervals, and it keeps
    parcels in one chip together, which B-12 showed matters.
    """
    g = parcels.groupby(["chip", "variant"])["found"].agg(["sum", "count"])
    hits = g["sum"].unstack("variant")
    n = g["count"].unstack("variant")["shipped"].to_numpy()
    a = hits[variant].to_numpy()
    s = hits["shipped"].to_numpy()
    point = (a.sum() - s.sum()) / n.sum()
    k = len(n)
    draws = np.empty(boots)
    for i in range(boots):
        idx = rng.integers(0, k, k)
        draws[i] = (a[idx].sum() - s[idx].sum()) / n[idx].sum()
    lo, hi = np.percentile(draws, (2.5, 97.5))
    return point, float(lo), float(hi)


def season_tables(iou: float) -> list:
    """The two seasonal windows, from season_test.py."""
    out = []
    need = ["season_ftw.csv", "season_ftw_parcels.csv",
            "season_watershed_budget.csv", "season_windows.csv"]
    for c in COUNTRIES:
        missing = [n for n in need if not (results_dir(c) / n).exists()]
        if missing:
            return [f"\n{c.capitalize()} is missing {', '.join(missing)}. "
                    f"Run `python src\\season_test.py --country {c}`.\n"]

    out.append("### What each window shows\n")
    out.append("| country | window | dates | red, median | blue, median "
               "| blue, 95th percentile | NDVI, median | edge strength |")
    out.append("|---|---|---|---:|---:|---:|---:|---:|")
    for c in COUNTRIES:
        dates = season_dates(c)
        w = pd.read_csv(results_dir(c) / "season_windows.csv")
        med = w.groupby("window").median(numeric_only=True)
        for win in ("window_a", "window_b"):
            r = med.loc[win]
            out.append(f"| {c.capitalize()} | {win} | {dates.get(win, '')} "
                       f"| {r['red_median']:.0f} | {r['blue_median']:.0f} "
                       f"| {r['blue_p95']:.0f} | {r['ndvi_median']:.2f} "
                       f"| {r['edge_mean']:.3f} |")

    out.append("\n### FTW with its two windows rearranged\n")
    out.append("| what the model was given | India objects/chip | India recall "
               "| India null | Slovenia objects/chip | Slovenia recall "
               "| Slovenia null |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    ftw = {c: pd.read_csv(results_dir(c) / "season_ftw.csv").set_index(
        "variant") for c in COUNTRIES}
    for v in SEASON_FTW:
        cells = [v]
        for c in COUNTRIES:
            r = ftw[c].loc[v]
            cells += [f"{r['objects_per_chip']:.1f}",
                      f"{r['recall'] * 100:.2f}% [{r['lo'] * 100:.2f}, "
                      f"{r['hi'] * 100:.2f}]",
                      f"{r['null_recall'] * 100:.2f}%"]
        out.append("| " + " | ".join(cells) + " |")
    for c in COUNTRIES:
        px = ftw[c].loc["shipped", "pixels_differing_from_published"]
        out.append(f"\n{c.capitalize()}: the shipped run differs from "
                   f"`pred_3class_full` on {int(px)} pixel(s).")

    out.append("\n### The same, as a change from the shipped run, "
               "chip by chip\n")
    out.append("| what the model was given | India parcels gained "
               "| India parcels lost | India change "
               "| Slovenia parcels gained | Slovenia parcels lost "
               "| Slovenia change |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    # fixed so the paired intervals come out the same on every rebuild
    rng = np.random.default_rng(20261008)
    parcels = {c: pd.read_csv(results_dir(c) / "season_ftw_parcels.csv")
               for c in COUNTRIES}
    for v in SEASON_FTW[1:]:
        cells = [v]
        for c in COUNTRIES:
            p = parcels[c].pivot_table(index=["chip", "parcel_id"],
                                       columns="variant", values="found")
            gained = int(((p[v] == 1) & (p["shipped"] == 0)).sum())
            lost = int(((p[v] == 0) & (p["shipped"] == 1)).sum())
            pt, lo, hi = paired_change(parcels[c], v, 4000, rng)
            cells += [f"{gained:,}", f"{lost:,}",
                      f"{pt * 100:+.2f} [{lo * 100:+.2f}, {hi * 100:+.2f}]"]
        out.append("| " + " | ".join(cells) + " |")

    out.append("\n### FTW by ground width, each arrangement\n")
    out.append("| country | what the model was given | " +
               " | ".join(WIDTH_LABELS_M) + " |")
    out.append("|---|---|" + "---:|" * len(WIDTH_LABELS_M))
    for c in COUNTRIES:
        d = parcels[c].copy()
        d["band"] = pd.cut(d["width_m"], WIDTH_EDGES_M,
                           labels=WIDTH_LABELS_M, right=False)
        for v in SEASON_FTW:
            cells = [c.capitalize(), v]
            for lab in WIDTH_LABELS_M:
                s = d[(d["variant"] == v) & (d["band"] == lab)]
                cells.append(f"{int(s['found'].sum())}/{len(s):,}, "
                             f"{s['found'].mean() * 100:.2f}%"
                             if len(s) else "")
            out.append("| " + " | ".join(cells) + " |")

    out.append("\n### Watershed on each window, at FTW's object count\n")
    out.append("| gradient from | India, at 175 objects/chip "
               "| Slovenia, at 20 objects/chip |")
    out.append("|---|---:|---:|")
    ws = {c: pd.read_csv(results_dir(c) / "season_watershed_budget.csv")
          .set_index("variant") for c in COUNTRIES}
    for v in SEASON_WS:
        cells = [WS_NAMES[v]]
        for c in COUNTRIES:
            r = ws[c].loc[v]
            note = ", clamped" if str(r["clamped"]).lower() == "true" else ""
            cells.append(f"{r['recall'] * 100:.2f}% [{r['lo'] * 100:.2f}, "
                         f"{r['hi'] * 100:.2f}]{note}")
        out.append("| " + " | ".join(cells) + " |")

    r = ws["slovenia"].loc["both"]
    out.append("\n### Slovenia at FTW's budget, watershed measured\n")
    out.append("| method | recall at 20 objects/chip | how |")
    out.append("|---|---:|---|")
    out.append(f"| watershed | {r['recall']:.3f} | interpolated, sweep "
               f"extended to h 0.6 in `season_test.py` |")
    return out



RABI_SEASONS = ["2016-17", "2015-16"]
RABI_FTW = {"shipped": "shipped, b then a", "a twice": "a twice",
            "rabi for b": "rabi for b, r then a",
            "a then rabi": "a then rabi", "rabi twice": "rabi twice"}
RABI_WS = {"b and a": "b and a, as published", "a alone": "a alone",
           "r alone": "r alone", "a and r": "a and r"}


def rabi_tables() -> list:
    """The December to February image, from rabi_probe, rabi_download and
    rabi_test."""
    rd = results_dir("india")
    need = ["rabi_match.csv", "rabi_scenes.csv"] + [
        f"rabi_test_{s}_{k}.csv" for s in RABI_SEASONS
        for k in ("ftw", "changes", "watershed")]
    missing = [n for n in need if not (rd / n).exists()]
    if missing:
        return [f"\nMissing {', '.join(missing)}. Run the rabi scripts.\n"]
    out = []

    m = pd.read_csv(rd / "rabi_match.csv")
    m = m.sort_values("r_min", ascending=False).groupby(
        ["chip", "window"], as_index=False).first()
    out.append("### FTW's own chips rebuilt from the archive\n")
    out.append("| chip | window | scene date | lowest band correlation "
               "| largest median difference |")
    out.append("|---|---|---|---:|---:|")
    for _, r in m.sort_values(["chip", "window"]).iterrows():
        out.append(f"| {r['chip'].replace('.tif', '')} | {r['window']} "
                   f"| {r['date']} | {r['r_min']:.4f} "
                   f"| {r['rel_max'] * 100:.2f}% |")

    sc = pd.read_csv(rd / "rabi_scenes.csv")
    out.append("\n### The December to February images\n")
    out.append("| season | chips | at or under 10% chip cloud | December "
               "| January | February |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for season in RABI_SEASONS:
        g = sc[sc["season"] == season]
        ok = g[g["chip_cloud"] <= 0.10]
        months = pd.to_datetime(ok["date"]).dt.month.value_counts()
        out.append(f"| {season} | {len(g)} | {len(ok)} "
                   f"| {int(months.get(12, 0))} | {int(months.get(1, 0))} "
                   f"| {int(months.get(2, 0))} |")

    ftw = {s: pd.read_csv(rd / f"rabi_test_{s}_ftw.csv").set_index(
        "arrangement") for s in RABI_SEASONS}
    out.append("\n### FTW given the rabi image\n")
    head = "| what the model was given |"
    for s in RABI_SEASONS:
        head += f" {s} objects/chip | {s} recall | {s} null |"
    out.append(head)
    out.append("|---|" + "---:|" * 3 * len(RABI_SEASONS))
    for key, name in RABI_FTW.items():
        cells = [name]
        for s in RABI_SEASONS:
            r = ftw[s].loc[key]
            cells += [f"{r['objects_per_chip']:.1f}",
                      f"{r['recall'] * 100:.2f}%",
                      f"{r['null_recall'] * 100:.2f}%"]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    for s in RABI_SEASONS:
        r = ftw[s].loc["shipped"]
        out.append(f"{s}: {int(r['chips'])} labelled chips, "
                   f"{int(r['parcels']):,} parcels.")

    ws = {s: pd.read_csv(rd / f"rabi_test_{s}_watershed.csv").set_index(
        "arrangement") for s in RABI_SEASONS}
    out.append("\n### Watershed on the rabi image, at 175 objects per chip\n")
    out.append("| gradient from | " + " | ".join(RABI_SEASONS) + " |")
    out.append("|---|" + "---:|" * len(RABI_SEASONS))
    for key, name in RABI_WS.items():
        out.append(f"| {name} | " + " | ".join(
            f"{ws[s].loc[key, 'recall_at_budget'] * 100:.2f}%"
            for s in RABI_SEASONS) + " |")

    ch = {s: pd.read_csv(rd / f"rabi_test_{s}_changes.csv")
          for s in RABI_SEASONS}
    out.append("\n### The changes, chip by chip\n")
    out.append("| method | comparison | " + " | ".join(RABI_SEASONS) + " |")
    out.append("|---|---|" + "---:|" * len(RABI_SEASONS))
    base = ch[RABI_SEASONS[0]]
    for _, r in base.iterrows():
        cells = []
        for s in RABI_SEASONS:
            q = ch[s][(ch[s]["method"] == r["method"]) & (ch[s]["x"] == r["x"])
                      & (ch[s]["y"] == r["y"])].iloc[0]
            cells.append(f"{q['change'] * 100:+.2f} [{q['lo'] * 100:+.2f}, "
                         f"{q['hi'] * 100:+.2f}]")
        name = "FTW" if r["method"] == "ftw" else "watershed"
        out.append(f"| {name} | {r['x']} against {r['y']} | "
                   + " | ".join(cells) + " |")
    return out


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

        methods = ["ftw", "watershed"] + [
            k for k in ("sam_rgb", "sam_cir") if k in sweeps] + [
            "sam_true", "sam_false"]
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
    # natural colour since B-23; the first run's blue-green-red stands in
    # only if the rerun is missing
    sam_key = "sam_rgb" if all(
        width_file(c, "sam_rgb", args.sam_setting).exists()
        for c in COUNTRIES) else "sam_true"
    out += cross_country_table(["ftw", "watershed", sam_key],
                               args.sam_setting, args.iou)

    for country in COUNTRIES:
        out.append(f"\n## {country.capitalize()}, what the methods emit\n")
        out += precision_table(country)
        out.append(f"\n## {country.capitalize()}, held-out setting choice\n")
        out += holdout_table(country)

    out.append("\n## India, every method on the parcels the SAM subset "
               "covered\n")
    out += matched_parcel_table("india", "sam_vit_h_false_0p5")

    out.append("\n## Label registration\n")
    out += registration_tables(args.iou)

    out.append("\n## Ring distance sensitivity\n")
    out += ring_tables()

    out.append("\n## Parcel shape\n")
    out += shape_tables()

    out.append("\n## The two seasonal windows\n")
    out += season_tables(args.iou)

    out.append("\n## A December to February image\n")
    out += rabi_tables()

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
