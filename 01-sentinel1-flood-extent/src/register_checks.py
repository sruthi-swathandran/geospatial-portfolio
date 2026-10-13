"""
RS-01. Three measurements the October 2026 issue register asked for.

The register (I-21, I-22, I-25) named three places where the method might move
a number by an amount nobody had measured. This measures each one. The
readings are set here before any of them has run.

    lee     I-21. lee_filter takes its noise term, `overall`, from the
            variance of whatever array it is given: one 512 by 512 chip in
            validation, one padded 2,080 pixel tile in the scene. This
            scores the 65 chips twice at each operating point, once as now
            and once with `overall` fixed to one value pooled across the
            chips, and compares IoU and mapped area.

    clean   I-22. full_scene.py runs morph_clean, dropping water patches and
            holes under 25 pixels, before anything is counted. The chips were
            scored without it. This scores the chips with and without it, at
            two limits: 25 pixels, which is 0.25 ha on the 10 m chips, and 100
            pixels, which is the 1 ha that 25 pixels covers at the scene's
            20 m. The first run measured only the 0.25 ha limit (N-03); the
            1 ha rows are the ones that describe the published map.

    items   I-25. fetch_reference.py finds the 12 August frames by id with an
            _rtc suffix; full_scene.py says that returns nothing and searches
            by bounding box, date and orbit. This runs both lookups against
            Planetary Computer and compares the frames they return. It needs
            the network; the other two read only data/.

HOW IT WILL BE READ, SET BEFORE RUNNING
---------------------------------------
    Both chip checks first reproduce the published IoU at each operating
    point in final_method.json to four places. If either does not reproduce,
    they stop there.

    lee     The noise term matters if fixing it moves chip-scale mapped area
            by more than 1% or IoU by more than 0.005 at either operating
            point. If it does not, the per-tile term is recorded as a
            difference that was measured and found small. If it does, the
            next step is a scene rerun with the term fixed, which this does
            not attempt. Either way the chips cannot say how large the effect
            is on scene tiles, which hold hills the chips never do.

    clean   The validated and reported products differ materially at this
            step if morph_clean moves IoU by more than 0.005 or mapped area
            by more than 1% at either operating point. Below that, the README
            says the chips were scored without it and that the difference was
            measured and is small. Above it, the README says how large it is.
            Second round (N-03, set before rerunning): the same bars apply to
            the 1 ha rows, and wherever the README describes the published
            map, its figures come from those rows, with the 0.25 ha rows kept
            as the first measurement.

    items   The lookups agree if they return the same set of item ids. If
            they do, I-25 is closed with the ids recorded. If not, the ids
            each returns are written out and the scene's lookup, the one the
            published figures used, is the one to keep.

Outputs:
    results/register_check_lee.csv
    results/register_check_clean.csv
    results/register_check_items.csv

Usage:
    python src\\register_checks.py --part lee
    python src\\register_checks.py --part clean
    python src\\register_checks.py --part items
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (EVENT, DATA, RESULTS, TARGET_RES, SCENE_RES,      # noqa: E402
                    SPECKLE_WINDOW, pixel_ha)
from chips import (read, split_lookup, morph_clean,                  # noqa: E402
                   MIN_OBJECT_PX, MIN_HOLE_PX)
import metrics as M                                                  # noqa: E402

REF_DIR = DATA / "reference"
PIXEL_HA = pixel_ha(TARGET_RES)
AREA_BAR, IOU_BAR = 0.01, 0.005


def operating_points() -> dict:
    fm = json.loads((RESULTS / "final_method.json").read_text())
    return {name: (float(v["threshold"]), float(v["iou_all"]))
            for name, v in fm["operating_points"].items()}


def reproduces(base: dict, published: float, point: str) -> None:
    """The 'before' run has to be the published one, or nothing after it
    means anything."""
    ok = round(base["iou"], 4) == round(published, 4)
    print(f"  {point}: before reproduces final_method.json IoU "
          f"{published:.4f}: {'yes' if ok else 'NO, ' + format(base['iou'], '.4f')}")
    if not ok:
        raise SystemExit("  The baseline does not reproduce. Stop here.")


def chip_ids() -> list:
    path = RESULTS / "usable_chips.txt"
    return [c.strip() for c in path.read_text().split() if c.strip()]


def raw_vh(chip_id: str) -> np.ndarray:
    import rasterio
    with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif") as s:
        return s.read(2).astype("float64")


def lee(db: np.ndarray, overall: float | None = None,
        size: int = SPECKLE_WINDOW) -> tuple:
    """chips.lee_filter, with the noise term exposed. Returns (dB, term)."""
    from scipy.ndimage import uniform_filter
    valid = np.isfinite(db)
    linear = np.power(10.0, db / 10.0)
    x = np.where(valid, linear, np.nanmean(linear[valid]))
    mean = uniform_filter(x, size)
    var = np.clip(uniform_filter(x * x, size) - mean * mean, 0, None)
    term = float(np.var(x[valid])) if overall is None else overall
    w = var / (var + term) if term > 0 else np.zeros_like(var)
    out = 10.0 * np.log10(np.clip(mean + w * (x - mean), 1e-10, None))
    return np.where(valid, out, np.nan), float(np.var(x[valid]))


def score(preds: dict, labels: dict) -> dict:
    confs = [M.confusion(preds[c], labels[c]) for c in preds]
    a = M.aggregate(confs)
    area = sum(M.mapped_area_px(preds[c], labels[c]) for c in preds) * PIXEL_HA
    label = sum(int((labels[c] == 1).sum()) for c in preds) * PIXEL_HA
    return {"iou": a["iou"], "precision": a["precision"],
            "recall": a["recall"], "area_ha": area, "label_ha": label}


def compare(name: str, base: dict, alt: dict, point: str, t: float) -> dict:
    d_iou = alt["iou"] - base["iou"]
    d_area = alt["area_ha"] / base["area_ha"] - 1 if base["area_ha"] else 0.0
    # + 0.0 turns a rounded -0.0 into 0.0 (M-10)
    d_iou, d_area = round(d_iou, 4) + 0.0, round(d_area, 4) + 0.0
    big = abs(d_iou) > IOU_BAR or abs(d_area) > AREA_BAR
    print(f"  {point:<14}{t:>7.2f}  IoU {base['iou']:.4f} -> {alt['iou']:.4f}"
          f" ({d_iou:+.4f})   area {base['area_ha']:,.1f} -> "
          f"{alt['area_ha']:,.1f} ha ({d_area:+.2%})   "
          f"{'over the bar' if big else 'under the bar'}")
    return {"check": name, "operating_point": point, "threshold_db": t,
            "iou_before": round(base["iou"], 4),
            "iou_after": round(alt["iou"], 4),
            "precision_before": round(base["precision"], 4),
            "precision_after": round(alt["precision"], 4),
            "recall_before": round(base["recall"], 4),
            "recall_after": round(alt["recall"], 4),
            "area_ha_before": round(base["area_ha"], 1),
            "area_ha_after": round(alt["area_ha"], 1),
            "iou_change": d_iou, "area_change": d_area,
            # mapped area against the hand-labelled water, so the page and
            # the README can read the shortfall rather than compute it (R-01)
            "label_ha": round(base["label_ha"], 1),
            "area_vs_labels_before": round(base["area_ha"] / base["label_ha"]
                                           - 1, 4) + 0.0,
            "area_vs_labels_after": round(alt["area_ha"] / alt["label_ha"]
                                          - 1, 4) + 0.0,
            "over_bar": big}


def write(rows: list, name: str) -> None:
    out = RESULTS / name
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"\n  wrote results\\{name}")


def load(ids):
    raw, labels = {}, {}
    for c in ids:
        raw[c] = raw_vh(c)
        labels[c] = read("LabelHand", c)[0]
    return raw, labels


def part_lee() -> None:
    ids = chip_ids()
    raw, labels = load(ids)
    # float32, as operating_point.load_chip casts it, so the threshold sees
    # exactly the values the published scores saw
    filt, terms = {}, {}
    for c in ids:
        f, terms[c] = lee(raw[c])
        filt[c] = f.astype("float32")
    pooled = float(np.median(list(terms.values())))
    fixed = {c: lee(raw[c], overall=pooled)[0].astype("float32") for c in ids}
    t_lo, t_hi = np.percentile(list(terms.values()), (10, 90))
    print(f"\nI-21. LEE NOISE TERM, {len(ids)} chips")
    print(f"  per-chip term, linear power: median {pooled:.5f}, "
          f"10th to 90th percentile {t_lo:.5f} to {t_hi:.5f}")
    rows = []
    for point, (t, published) in operating_points().items():
        def pred(img):
            nod = ~np.isfinite(img)
            return np.where(nod, -1, (img <= t).astype(np.int8)).astype(np.int8)
        base = score({c: pred(filt[c]) for c in ids}, labels)
        reproduces(base, published, point)
        alt = score({c: pred(fixed[c]) for c in ids}, labels)
        rows.append(compare("lee_term_pooled", base, alt, point, t))
    rows[0]["pooled_term"] = rows[1]["pooled_term"] = round(pooled, 6)
    write(rows, "register_check_lee.csv")


def part_clean() -> None:
    ids = chip_ids()
    raw, labels = load(ids)
    filt = {c: lee(raw[c])[0].astype("float32") for c in ids}
    print(f"\nI-22. morph_clean BEFORE SCORING, {len(ids)} chips")
    # full_scene.process_tile calls morph_clean with its pixel defaults on
    # tiles at SCENE_RES, so on these TARGET_RES chips the same ground needs
    # the limits scaled by the pixel area ratio
    scale = int(round((SCENE_RES / TARGET_RES) ** 2))
    limits = [(1, "chip scale, as first run"), (scale, "scene scale")]
    rows = []
    for point, (t, published) in operating_points().items():
        plain, nod_of, water_of = {}, {}, {}
        for c in ids:
            img = filt[c]
            nod_of[c] = ~np.isfinite(img)
            water_of[c] = img <= t
            plain[c] = np.where(nod_of[c], -1,
                                water_of[c].astype(np.int8)).astype(np.int8)
        base = score(plain, labels)
        reproduces(base, published, point)
        for k, label in limits:
            obj, hole = MIN_OBJECT_PX * k, MIN_HOLE_PX * k
            cleaned = {}
            for c in ids:
                cw = morph_clean(water_of[c].astype(np.int8),
                                 obj, hole).astype(bool)
                cleaned[c] = np.where(nod_of[c], -1,
                                      cw.astype(np.int8)).astype(np.int8)
            print(f"  limit {obj} px, {obj * PIXEL_HA:g} ha, {label}")
            row = compare("morph_clean", base, score(cleaned, labels),
                          point, t)
            rows.append({**row, "limit_px": obj,
                         "limit_ha": round(obj * PIXEL_HA, 4),
                         "limit_scale": label})
    write(rows, "register_check_clean.csv")


def part_items() -> None:
    import fetch_reference as FR
    import full_scene as FS
    from config import FLOOD_ITEMS
    client = FS.open_catalog()
    by_id = sorted(i.id for i in FR.get_items(client, FLOOD_ITEMS))
    by_search = sorted(i.id for i in FS.flood_items(client, quiet=True))
    same = by_id == by_search
    print("\nI-25. THE 12 AUGUST FRAMES, LOOKED UP TWO WAYS")
    print(f"  by id, as fetch_reference.py does:   {len(by_id)} item(s)")
    for i in by_id:
        print(f"    {i}")
    print(f"  by search, as full_scene.py does:    {len(by_search)} item(s)")
    for i in by_search:
        print(f"    {i}")
    print(f"\n  {'the same frames' if same else 'DIFFERENT frames'}")
    rows = ([{"lookup": "by_id", "item_id": i} for i in by_id]
            + [{"lookup": "by_search", "item_id": i} for i in by_search]
            + [{"lookup": "agree", "item_id": str(same)}])
    write(rows, "register_check_items.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["lee", "clean", "items"])
    args = ap.parse_args()
    {"lee": part_lee, "clean": part_clean, "items": part_items}[args.part]()


if __name__ == "__main__":
    main()
