"""
RS-01 / step 3 — look at the data before modelling it, and get the number to beat.

Two jobs:

  1. INVENTORY. What are these chips actually made of? Units, nodata encoding,
     value ranges, label class balance. Every one of these has bitten a flood
     mapping pipeline before: a VV band in linear power rather than dB makes
     Otsu pick a nonsense threshold, and a -1 nodata class counted as "not
     water" inflates every accuracy figure.

  2. THE BASELINE. Score the dataset authors' own Otsu output
     (S1OtsuLabelHand) against the hand labels, on the official splits. That
     is the number your pipeline has to beat, computed by you, on your machine,
     with your metric code — which is a far stronger claim than quoting a paper.

Outputs:
    results/chip_inventory.csv
    results/baseline_otsu_scores.csv
    results/figures/example_chips.png

Usage:
    python src\\explore_chips.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # no GUI; write straight to file
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np               # noqa: E402
import rasterio                  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, LABELS_DIR, RESULTS     # noqa: E402
import metrics as M                               # noqa: E402

FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)
SPLITS_DIR = LABELS_DIR / "splits"


def split_lookup() -> dict[str, str]:
    out = {}
    for path in sorted(SPLITS_DIR.glob("*.csv")):
        name = path.stem.replace("flood_", "").replace("_data", "")
        for row in csv.reader(path.read_text().splitlines()):
            if row and row[0].startswith(f"{EVENT}_"):
                out[row[0].split("_")[1]] = name
    return out


def read(layer: str, chip_id: str) -> np.ndarray:
    path = LABELS_DIR / layer / f"{EVENT}_{chip_id}_{layer}.tif"
    with rasterio.open(path) as src:
        return src.read()


def chip_ids() -> list[str]:
    return sorted(p.name.split("_")[1]
                  for p in (LABELS_DIR / "S1Hand").glob(f"{EVENT}_*_S1Hand.tif"))


def describe_units(vv: np.ndarray) -> str:
    """Guess the radiometric units from the value distribution."""
    finite = vv[np.isfinite(vv)]
    if finite.size == 0:
        return "all nodata"
    lo, hi = np.percentile(finite, [1, 99])
    if lo < -40 or (lo < 0 and hi < 10):
        return f"decibels (1st-99th pct {lo:.1f} .. {hi:.1f} dB)"
    if 0 <= lo and hi <= 2:
        return f"linear power / sigma0 ({lo:.4f} .. {hi:.4f})"
    return f"unclear ({lo:.3f} .. {hi:.3f}) — inspect before thresholding"


def main() -> None:
    ids = chip_ids()
    if not ids:
        raise SystemExit("No chips found. Run fetch_labels.py --download first.")
    splits = split_lookup()

    print(f"{len(ids)} {EVENT} chips\n")

    # ---------------------------------------------------------------- inventory
    rows = []
    confs_by_split: dict[str, list[dict]] = {}
    all_confs: list[dict] = []
    units_seen = set()

    for chip_id in ids:
        s1 = read("S1Hand", chip_id).astype("float64")
        label = read("LabelHand", chip_id)[0]
        otsu = read("S1OtsuLabelHand", chip_id)[0]
        jrc = read("JRCWaterHand", chip_id)[0]

        vv, vh = s1[0], s1[1]
        units_seen.add(describe_units(vv).split(" (")[0])

        c = M.confusion(otsu, label)
        split = splits.get(chip_id, "unknown")
        confs_by_split.setdefault(split, []).append(c)
        all_confs.append(c)

        rows.append({
            "chip_id": chip_id,
            "split": split,
            "vv_min": np.nanmin(vv), "vv_max": np.nanmax(vv), "vv_mean": np.nanmean(vv),
            "vh_min": np.nanmin(vh), "vh_max": np.nanmax(vh), "vh_mean": np.nanmean(vh),
            "s1_nonfinite_px": int(np.sum(~np.isfinite(s1))),
            "label_nodata_px": int(np.sum(label == -1)),
            "label_water_px": int(np.sum(label == 1)),
            "label_land_px": int(np.sum(label == 0)),
            "otsu_water_px": int(np.sum(otsu == 1)),
            "jrc_water_px": int(np.sum(jrc == 1)),
            "otsu_iou": M.scores(c)["iou"],
        })

    out_csv = RESULTS / "chip_inventory.csv"
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---------------------------------------------------------------- summary
    label_vals = {}
    for layer in ("LabelHand", "S1OtsuLabelHand", "JRCWaterHand"):
        vals = set()
        for chip_id in ids[:10]:
            vals |= set(np.unique(read(layer, chip_id)).tolist())
        label_vals[layer] = sorted(vals)

    total_water = sum(r["label_water_px"] for r in rows)
    total_land = sum(r["label_land_px"] for r in rows)
    total_nodata = sum(r["label_nodata_px"] for r in rows)
    total_px = total_water + total_land + total_nodata

    print("DATA")
    print("----")
    print(f"  S1 units          : {', '.join(sorted(units_seen))}")
    print(f"  S1 non-finite px  : {sum(r['s1_nonfinite_px'] for r in rows):,}")
    for layer, vals in label_vals.items():
        print(f"  {layer:<17} : values {vals}")
    print(f"  class balance     : water {total_water/total_px:6.2%}   "
          f"land {total_land/total_px:6.2%}   nodata {total_nodata/total_px:6.2%}")
    print(f"  -> {total_nodata:,} no-data pixels are excluded from every metric below.")

    print("\nBASELINE — the authors' Otsu output vs the hand labels")
    print("------------------------------------------------------")
    for split in ("train", "valid", "test", "bolivia", "unknown"):
        if split not in confs_by_split:
            continue
        confs = confs_by_split[split]
        agg = M.aggregate(confs)
        print(M.format_row(f"{split} (n={len(confs)}) micro", agg))
    print(M.format_row(f"ALL (n={len(all_confs)}) micro", M.aggregate(all_confs)))
    mac = M.macro(all_confs)
    print(f"{'ALL macro (per-chip mean)':<28} IoU {mac['iou']:.3f}  P {mac['precision']:.3f}  "
          f"R {mac['recall']:.3f}  F1 {mac['f1']:.3f}   "
          f"[{mac['n_chips_with_water']}/{mac['n_chips']} chips contain water]")

    with open(RESULTS / "baseline_otsu_scores.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["split", "n_chips", "tp", "fp", "fn", "tn",
                    "iou", "precision", "recall", "f1", "accuracy"])
        for split, confs in sorted(confs_by_split.items()):
            a = M.aggregate(confs)
            w.writerow([split, len(confs), a["tp"], a["fp"], a["fn"], a["tn"],
                        f"{a['iou']:.4f}", f"{a['precision']:.4f}",
                        f"{a['recall']:.4f}", f"{a['f1']:.4f}", f"{a['accuracy']:.4f}"])
        a = M.aggregate(all_confs)
        w.writerow(["all", len(all_confs), a["tp"], a["fp"], a["fn"], a["tn"],
                    f"{a['iou']:.4f}", f"{a['precision']:.4f}",
                    f"{a['recall']:.4f}", f"{a['f1']:.4f}", f"{a['accuracy']:.4f}"])

    # ---------------------------------------------------------------- figure
    wettest = sorted(rows, key=lambda r: -r["label_water_px"])[:3]
    fig, axes = plt.subplots(len(wettest), 4, figsize=(13, 3.3 * len(wettest)))
    if len(wettest) == 1:
        axes = axes[None, :]

    for i, r in enumerate(wettest):
        chip_id = r["chip_id"]
        s1 = read("S1Hand", chip_id).astype("float64")
        label = read("LabelHand", chip_id)[0].astype(float)
        otsu = read("S1OtsuLabelHand", chip_id)[0].astype(float)
        label[label == -1] = np.nan
        otsu[otsu == -1] = np.nan

        for j, (img, title, kw) in enumerate([
            (s1[0], "VV", dict(cmap="gray")),
            (s1[1], "VH", dict(cmap="gray")),
            (label, "hand label", dict(cmap="Blues", vmin=0, vmax=1)),
            (otsu, "authors' Otsu", dict(cmap="Blues", vmin=0, vmax=1)),
        ]):
            ax = axes[i, j]
            if j < 2:
                finite = img[np.isfinite(img)]
                kw["vmin"], kw["vmax"] = np.percentile(finite, [2, 98])
            ax.imshow(img, **kw)
            ax.set_xticks([]); ax.set_yticks([])
            if i == 0:
                ax.set_title(title, fontsize=11)
            if j == 0:
                ax.set_ylabel(f"{chip_id}\n{r['split']}  IoU {r['otsu_iou']:.2f}",
                              fontsize=9)

    fig.suptitle(f"{EVENT} — Sen1Floods11 hand-labelled chips, wettest three",
                 fontsize=12)
    fig.tight_layout()
    out_png = FIGURES / "example_chips.png"
    fig.savefig(out_png, dpi=130)
    print(f"\nwrote {out_csv.name}, baseline_otsu_scores.csv, figures/{out_png.name}")


if __name__ == "__main__":
    main()
