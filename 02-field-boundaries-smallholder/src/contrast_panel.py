"""
RS-02. Does the contrast measure agree with a person?

F-14 in REVIEW.md. `label_registration.py` now measures each parcel's boundary
against its own interior, the machinery passes a self-test against known
displacements, and the number separates the two countries. None of that says
the number means what its name says. A measure can be reproducible, internally
consistent and still be measuring the wrong thing.

The only test left needs eyes. This draws twenty Indian parcels spanning the
measured range, numbered, in an order that carries no information, with the
measured value withheld. You say which ones sit on a boundary you can see. The
key is written to a separate file and compared afterwards.

Blind on purpose. Shown the number first, a person agrees with it, and the
exercise proves nothing. For the same reason a panel can be scored once. After
scoring, the measured values have been printed, so that panel is spent: the
next draw moves its key aside and never shows those parcels again.

Five parcels are drawn from each quartile of edge_over_interior, so the panel
spans what the measure claims to distinguish rather than sampling the middle
twenty times.

The main score is rank based. Take every pair of one crop you marked visible
and one you did not; the score is the share of pairs where the measure puts
the visible one higher. 0.5 is a coin, 1.0 is perfect. A permutation test says
how often shuffled answers would do as well. This does not care how many crops
you mark, which a median split does, since a median split always calls exactly
half of them visible.

The bars were set before any real answers existed:
    rank score 0.75 or more, permutation p under 0.05: the measure tracks
        what a person sees, and F-14 closes
    rank score 0.60 or more: weak, fine as a country summary, not per parcel
    below 0.60: not tracking visibility, and the documents must stop calling
        it contrast

    python src\\contrast_panel.py --country india
    python src\\contrast_panel.py --country india --redraw
    python src\\contrast_panel.py --country india --score <numbers>

The second form draws the current panel again without changing which parcels
are on it. In the third, replace <numbers> with the panel numbers you judged as
having a visible edge, separated by commas and nothing else.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
PAD_M = 40.0          # context around the parcel, in metres
N_PER_QUARTILE = 5
# The panel was drawn, and judged, with blue, green and red in the red, green
# and blue channels, because the code then assumed FTW stores blue first. It
# stores red first (B-23). Kept as it was so --redraw reproduces the crops the
# marks were made on. A new panel should use ("B04", "B03", "B02").
PANEL_BANDS = ("B02", "B03", "B04")
N_PERMUTATIONS = 20000
TRACKS_AUC, TRACKS_P, WEAK_AUC = 0.75, 0.05, 0.60


def crop(chip, mask, pad_px):
    """A window around one parcel in PANEL_BANDS, stretched for looking at."""
    import rasterio
    ys, xs = np.nonzero(mask)
    y0 = max(0, ys.min() - pad_px)
    y1 = min(mask.shape[0], ys.max() + pad_px + 1)
    x0 = max(0, xs.min() - pad_px)
    x1 = min(mask.shape[1], xs.max() + pad_px + 1)
    path = F.IMG_A / chip
    with rasterio.open(path) as s:
        arr = s.read(F.band_index(path, PANEL_BANDS),
                     window=((y0, y1), (x0, x1))).astype(np.float32)
    out = np.empty(arr.shape, np.float32)
    for i in range(arr.shape[0]):
        lo, hi = np.percentile(arr[i], (2, 98))
        out[i] = (np.zeros_like(arr[i]) if hi <= lo
                  else np.clip((arr[i] - lo) / (hi - lo), 0, 1))
    return np.transpose(out, (1, 2, 0)), mask[y0:y1, x0:x1]


def rank_score(values: np.ndarray, marked: np.ndarray) -> float:
    """Share of (marked, unmarked) pairs where the marked crop measures higher.

    Ties count half. This is the Mann-Whitney U scaled to 0..1.
    """
    a, b = values[marked], values[~marked]
    diff = a[:, None] - b[None, :]
    return float(((diff > 0).sum() + 0.5 * (diff == 0).sum()) / diff.size)


def spent_keys(results: Path) -> list[Path]:
    return sorted(results.glob("contrast_panel_key_spent_*.csv"))


def score(args, key_path: Path) -> None:
    import pandas as pd
    if not key_path.exists():
        sys.exit(f"{key_path} not found. Draw the panel first.")
    key = pd.read_csv(key_path)
    n = len(key)

    text = args.score.replace(" ", "")
    if not re.fullmatch(r"\d+(,\d+)*", text):
        sys.exit("--score takes panel numbers separated by commas, for "
                 "example 3,11,17. Nothing was scored.")
    said = {int(x) for x in text.split(",")}
    bad = sorted(x for x in said if not 1 <= x <= n)
    if bad:
        sys.exit(f"there is no crop numbered {bad} on this panel, which runs "
                 f"1 to {n}. Nothing was scored.")

    scores_path = F.RESULTS / "contrast_panel_scores.csv"
    seed = int(key["seed"].iloc[0]) if "seed" in key.columns else -1
    if scores_path.exists() and not args.force:
        done = pd.read_csv(scores_path)
        if (done["seed"] == seed).any():
            sys.exit("this panel has already been scored and its values "
                     "printed, so it is no longer blind. Draw a fresh one.")

    key["you_said_visible"] = key["panel_no"].isin(said)
    marked = key["you_said_visible"].to_numpy()
    values = key["edge_over_interior"].to_numpy(float)

    print(RULE)
    print(f"CONTRAST MEASURE AGAINST YOUR EYES, {F.COUNTRY.upper()}")
    print(RULE)
    print(f"  you marked {int(marked.sum())} of {n} as visible\n")

    if marked.all() or not marked.any():
        print("  Every crop was marked the same way, so there is nothing to")
        print("  rank. That is an answer in itself: at this resolution the")
        print("  boundaries all look alike to a person, whatever the measure")
        print("  says. The panel stays unspent; think it over and score again.")
        print(RULE)
        return

    auc = rank_score(values, marked)
    rng = np.random.default_rng(12345)
    null = np.array([rank_score(values, rng.permutation(marked))
                     for _ in range(N_PERMUTATIONS)])
    p = float((null >= auc).mean())

    cut = float(np.median(values))
    key["measure_says_visible"] = key["edge_over_interior"] > cut
    agree = int((key["you_said_visible"]
                 == key["measure_says_visible"]).sum())

    print(f"  {'no':>3} {'measured':>9} {'you':>5}")
    for _, r in key.sort_values("edge_over_interior",
                                ascending=False).iterrows():
        y = "yes" if r["you_said_visible"] else "no"
        print(f"  {int(r['panel_no']):>3} {r['edge_over_interior']:>9.3f} "
              f"{y:>5}")
    print("\n  sorted from highest measured to lowest, so your yeses should")
    print("  gather at the top if the measure is tracking what you see")

    print(f"\n  rank score        {auc:.3f}   (0.5 is a coin, 1.0 is perfect)")
    print(f"  permutation p     {p:.4f}  ({N_PERMUTATIONS:,} shuffles of "
          f"your answers)")
    print(f"  median split      {agree} of {n} agree, at {cut:.3f}x "
          f"(secondary)")

    row = pd.DataFrame([{
        "seed": seed, "country": F.COUNTRY, "n": n,
        "marked_visible": int(marked.sum()),
        "marked_numbers": " ".join(str(x) for x in sorted(said)),
        "rank_score": round(auc, 4), "permutation_p": round(p, 4),
        "median_split_agree": agree,
    }])
    if scores_path.exists():
        row = pd.concat([pd.read_csv(scores_path), row], ignore_index=True)
    row.to_csv(scores_path, index=False)
    print(f"\n  wrote {scores_path.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    if auc >= TRACKS_AUC and p < TRACKS_P:
        print("The measure is tracking what you can see. F-14 closes.")
    elif auc >= WEAK_AUC:
        print("Better than a coin and not by enough. The measure separates")
        print("countries but should not be read as visibility per parcel.")
    else:
        print("The measure is not tracking visibility. Every sentence that")
        print("calls it a contrast measure needs rewriting.")
    print(RULE)
    print("This panel is now spent. Its values are on screen.")
    print(RULE)


def render(sel):
    """Draw each parcel twice, plain on the left and outlined on the right.

    The outline is a contour traced between pixels, so it sits on the pixel
    edges instead of painting over the boundary pixels themselves. The plain
    copy is there because those boundary pixels are exactly what is being
    judged.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    px_m = F.grid_pixel_m()
    pad_px = int(round(PAD_M / px_m))
    pairs_per_row = 4
    rows = int(np.ceil(len(sel) / pairs_per_row))
    ratios = []
    for i in range(pairs_per_row):
        ratios += [1, 1] + ([0.28] if i < pairs_per_row - 1 else [])
    fig = plt.figure(figsize=(16, rows * 2.25 + 0.9))
    fig.patch.set_facecolor("#fcfcfb")
    gs = GridSpec(rows, len(ratios), figure=fig, width_ratios=ratios,
                  left=0.015, right=0.985, top=1 - 0.85 / (rows * 2.25 + 0.9),
                  bottom=0.015, wspace=0.04, hspace=0.22)

    for k, (_, r) in enumerate(sel.iterrows()):
        row, slot = divmod(k, pairs_per_row)
        col = slot * 3
        _, _, _, full = F.load_labels(r["chip"])
        mask = full == int(r["parcel_id"])
        img, sub = crop(r["chip"], mask, pad_px)
        a_plain = fig.add_subplot(gs[row, col])
        a_line = fig.add_subplot(gs[row, col + 1])
        for ax in (a_plain, a_line):
            ax.imshow(img, interpolation="nearest")
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#e4e3df")
        a_line.contour(sub.astype(float), levels=[0.5], colors=["#ffe81a"],
                       linewidths=1.4)
        a_plain.set_title(f"{int(r['panel_no'])}", fontsize=11,
                          color="#0b0b0b", loc="left", pad=3)

    top_in = rows * 2.25 + 0.9
    fig.text(0.015, 1 - 0.18 / top_in,
             "Can you see a field boundary where the yellow line runs?",
             fontsize=13.5, color="#0b0b0b", ha="left", va="top")
    fig.text(0.015, 1 - 0.52 / top_in,
             "Each parcel appears twice: plain on the left, outlined on the "
             "right. Judge the plain copy, using the outline to know where "
             "to look. The measured value is withheld until you have.",
             fontsize=9.5, color="#52514e", ha="left", va="top")

    dest = F.PROJECT / "figures" / f"contrast_panel_{F.COUNTRY}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=170, facecolor="#fcfcfb")
    plt.close(fig)
    return dest


def redraw(key_path: Path) -> None:
    """Draw the current panel again from its key, without spending it."""
    import pandas as pd
    if not key_path.exists():
        sys.exit(f"{key_path} not found. Draw a panel first.")
    sel = pd.read_csv(key_path).sort_values("panel_no")
    dest = render(sel)
    print(RULE)
    print(f"CONTRAST PANEL REDRAWN, {F.COUNTRY.upper()}")
    print(RULE)
    print(f"  wrote {dest.relative_to(F.PROJECT)}, the same {len(sel)} "
          f"parcels in the same order")
    print("  the key is untouched and the panel is still blind")
    print(RULE)


def draw(args, key_path: Path) -> None:
    import pandas as pd
    reg = F.RESULTS / "label_registration.csv"
    if not reg.exists():
        sys.exit(f"{reg} not found. Run label_registration.py first.")
    d = pd.read_csv(reg).dropna(subset=["edge_over_interior"])

    # an earlier key has been seen, so move it aside and keep its parcels out
    if key_path.exists():
        n_old = len(spent_keys(F.RESULTS)) + 1
        key_path.rename(F.RESULTS / f"contrast_panel_key_spent_{n_old}.csv")
    seen = set()
    for old in spent_keys(F.RESULTS):
        o = pd.read_csv(old)
        seen |= set(zip(o["chip"], o["parcel_id"].astype(int)))
    if seen:
        keep = [(c, int(p)) not in seen
                for c, p in zip(d["chip"], d["parcel_id"])]
        d = d[keep]

    rng = np.random.default_rng(args.seed)
    q = pd.qcut(d["edge_over_interior"], 4, labels=False, duplicates="drop")
    picks = []
    for level in sorted(pd.unique(q.dropna())):
        pool = d[q == level]
        take = min(N_PER_QUARTILE, len(pool))
        picks.append(pool.sample(take, random_state=int(rng.integers(1e6))))
    sel = pd.concat(picks).sample(frac=1.0,
                                  random_state=args.seed).reset_index(drop=True)
    sel["panel_no"] = np.arange(1, len(sel) + 1)
    sel["seed"] = args.seed

    dest = render(sel)

    sel[["panel_no", "seed", "chip", "parcel_id", "edge_over_interior",
         "drawn_contrast", "width_native_px"]].to_csv(key_path, index=False)

    print(RULE)
    print(f"CONTRAST PANEL, {F.COUNTRY.upper()}, seed {args.seed}")
    print(RULE)
    print(f"  wrote {dest.relative_to(F.PROJECT)}, {len(sel)} parcels")
    print(f"  {len(seen)} parcel(s) from earlier panels left out")
    print(f"  wrote {key_path.relative_to(F.PROJECT)}, the answer key\n")
    print("  Open the panel. For each numbered crop, decide whether there is")
    print("  a field boundary you can actually see along the yellow line.")
    print("  Then run --score followed by your own numbers, commas between")
    print("  them and no spaces.")
    print("\n" + RULE)
    print("Do not open the key first. The measure and the eye agreeing after")
    print("the eye has seen the measure is worth nothing.")
    print(RULE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--score", default="",
                    help="comma separated panel numbers you judged visible")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--redraw", action="store_true",
                    help="draw the current panel again, same parcels")
    ap.add_argument("--force", action="store_true",
                    help="score a panel that has been scored before")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    key_path = F.RESULTS / "contrast_panel_key.csv"
    if args.score:
        score(args, key_path)
    elif args.redraw:
        redraw(key_path)
    else:
        draw(args, key_path)


if __name__ == "__main__":
    main()
