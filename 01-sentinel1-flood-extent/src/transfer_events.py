"""
RS-01 / F-07. Does the India threshold carry to other floods?

The operating threshold, -18.75 dB on Lee-filtered RTC gamma0 VH, was chosen on
the valid split of the India event, and the test split is adjacent chips from
the same scene. That checks the threshold was not fitted to one split. It says
nothing about another river, another season or another sensor geometry.
Sen1Floods11 has hand labels for ten other events, 378 chips, none of which
this project has used. This script scores the same method on them.

Each event goes through the steps India went through:

  meta     fetch Sen1Floods11_Metadata.geojson, list what it records per event,
           and check the dates and orbits find_scenes.py transcribed from it
  labels   download the hand labels, the chip imagery the dataset shipped
           (S1Hand, Earth Engine sigma0, used only to align against) and the
           authors' own Otsu result for every chip of an event
  rtc      read Planetary Computer RTC gamma0 for the event's date onto each
           chip's grid, as fetch_reference.py did for India
  align    shift each RTC chip onto the label grid by correlating it with
           S1Hand, as coregister.py did; chips that never correlate above 0.5
           are left out, as India's three were
  score    the fixed -18.75 dB on every event, against two references: the best
           single threshold for that event, which is an in-sample ceiling and
           flatters itself, and the authors' per-chip Otsu labels. India is
           scored by the same code from its own aligned chips, and must come
           out at the IoU of 0.519 in results/accuracy_ci.csv

Nothing here tunes anything. The threshold is read from final_method.json.

Outputs
-------
  data/transfer/<Event>_<chip>_FLOODRTC.tif, _FLOODRTC_ALIGNED.tif   not committed
  results/transfer/events.csv        what the metadata records, per event
  results/transfer/rtc_<Event>.csv   items found and read, per chip
  results/transfer/coreg_<Event>.csv shifts and correlation, per chip
  results/transfer/transfer_scores.csv   one row per event
  results/transfer/transfer_sweep.csv    IoU across thresholds, per event

Usage
-----
    python src\\transfer_events.py meta
    python src\\transfer_events.py labels --event all
    python src\\transfer_events.py rtc --event Bolivia --limit 3    # smoke test
    python src\\transfer_events.py rtc --event all
    python src\\transfer_events.py align --event all
    python src\\transfer_events.py score
    python src\\transfer_events.py probe --event Paraguay  # why no RTC was found
Each step skips chips it has already done, so it can be stopped and rerun.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics as M                                                   # noqa: E402
from chips import SPLITS_DIR, block_mean, lee_filter                   # noqa: E402
from config import DATA, LABELS_DIR, MPC_STAC, RESULTS, S1_COLLECTION  # noqa: E402

TRANSFER = DATA / "transfer"
OUT = RESULTS / "transfer"
LAYERS = ["S1Hand", "LabelHand", "S1OtsuLabelHand"]
GET_URL = "https://storage.googleapis.com/sen1floods11/{name}"
META_NAME = "v1.1/Sen1Floods11_Metadata.geojson"
META = LABELS_DIR / "Sen1Floods11_Metadata.geojson"
MAX_SHIFT = 5
MIN_CORR = 0.50
SWEEP = np.round(np.arange(-24.0, -12.0 + 1e-9, 0.25), 2)
N_BOOT = 2000
BOOT_SEED = 20161007
ALIAS = {"Mekong": "Cambodia"}     # split files say Mekong, find_scenes Cambodia


def threshold():
    d = json.loads((RESULTS / "final_method.json").read_text())
    return float(d["operating_points"]["max_iou"]["threshold"])


def split_chips():
    """{event: {chip: split}} from the official split files."""
    out = {}
    for p in sorted(SPLITS_DIR.glob("*.csv")):
        split = p.stem.replace("flood_", "").replace("_data", "")
        for row in csv.reader(p.read_text().splitlines()):
            if row:
                ev, chip = row[0].split("_")[:2]
                out.setdefault(ev, {})[chip] = split
    return out


def events(arg):
    known = sorted(e for e in split_chips() if e != "India")
    if arg == "all":
        return known
    if arg not in known:
        sys.exit(f"unknown event {arg}; choose from {', '.join(known)} or all")
    return [arg]


def event_table():
    from find_scenes import EVENTS
    return EVENTS


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def get(url, dest, size=None):
    import requests
    if dest.exists() and (size is None or dest.stat().st_size == size):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for block in r.iter_content(1 << 20):
                fh.write(block)
    return True


# ---------------------------------------------------------------- meta
def cmd_meta(args):
    get(GET_URL.format(name=META_NAME), META)
    feats = json.loads(META.read_text(encoding="utf-8"))["features"]
    print(f"{META.name}: {len(feats)} features")
    print(f"  properties: {sorted(feats[0]['properties'])}\n")
    table, chips = event_table(), split_chips()
    rows = []
    for f in feats:
        p = dict(f["properties"])
        name = str(p.get("location") or p.get("name") or p.get("event") or "")
        key = next((e for e in chips if e.lower() == name.lower()
                    or ALIAS.get(e, "").lower() == name.lower()), name)
        p["event_in_splits"] = key
        p["chips_in_splits"] = len(chips.get(key, {}))
        t = table.get(ALIAS.get(key, key))
        if t:
            p["find_scenes_s1_date"] = t["s1"]
            p["find_scenes_orbit"] = t["rel"]
        rows.append(p)
    write_csv(OUT / "events.csv", rows)
    for r in rows:
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items()))
    print(f"\n  wrote {OUT / 'events.csv'}")
    print("  Check the dates and orbits against find_scenes.py before the rtc step,\n"
          "  and whether any field records a per-event threshold.")


# ---------------------------------------------------------------- labels
def cmd_labels(args):
    listing = json.loads((LABELS_DIR / "_bucket_listing.json").read_text())["items"]
    want = set(events(args.event))
    todo = []
    for obj in listing:
        name = obj["name"]
        if "/HandLabeled/" not in name or not name.endswith(".tif"):
            continue
        layer, base = name.split("/")[-2], name.split("/")[-1]
        if layer in LAYERS and base.split("_")[0] in want:
            todo.append((name, LABELS_DIR / layer / base, int(obj.get("size", 0))))
    print(f"{len(todo)} files for {len(want)} event(s), "
          f"{sum(s for *_, s in todo) / 1e6:,.0f} MB")
    got = 0
    for n, (name, dest, size) in enumerate(todo, 1):
        got += get(GET_URL.format(name=name), dest, size)
        print(f"\r  {n}/{len(todo)}  ({got} downloaded, the rest already here)",
              end="", flush=True)
    print()


# ---------------------------------------------------------------- rtc
def chip_path(layer, ev, chip):
    return LABELS_DIR / layer / f"{ev}_{chip}_{layer}.tif"


def cmd_rtc(args):
    import planetary_computer
    import pystac_client
    import rioxarray                                    # noqa: F401
    import odc.geo.xr                                   # noqa: F401
    import xarray as xr
    from odc.stac import load as odc_load

    client = pystac_client.Client.open(MPC_STAC,
                                       modifier=planetary_computer.sign_inplace)
    table, chips = event_table(), split_chips()
    for ev in events(args.event):
        t = table[ALIAS.get(ev, ev)]
        day = datetime.strptime(t["s1"], "%Y-%m-%d")
        when = f"{day:%Y-%m-%d}T00:00:00Z/{day + timedelta(days=1):%Y-%m-%d}T00:00:00Z"
        ids = sorted(chips[ev])[:args.limit] if args.limit else sorted(chips[ev])
        print(f"\n{ev}: {len(ids)} chips, {t['s1']}, relative orbit {t['rel']}")
        rows, t0 = [], time.time()
        for n, chip in enumerate(ids, 1):
            out = TRANSFER / f"{ev}_{chip}_FLOODRTC.tif"
            row = dict(event=ev, chip=chip)
            src = chip_path("S1Hand", ev, chip)
            if not src.exists():
                row["status"] = "no S1Hand; run the labels step"
            elif out.exists():
                row["status"] = "already read"
            else:
                gbox = rioxarray.open_rasterio(src).odc.geobox
                bbox = list(gbox.extent.to_crs("EPSG:4326").boundingbox)
                items = list(client.search(collections=[S1_COLLECTION], bbox=bbox,
                                           datetime=when).items())
                same = [i for i in items
                        if i.properties.get("sat:relative_orbit") == t["rel"]]
                row["items_found"] = len(items)
                row["items_on_orbit"] = len(same)
                use = same or items
                if not use:
                    row["status"] = "no RTC item on that date"
                else:
                    row["item"] = use[0].id
                    ds = odc_load(use, bands=["vv", "vh"], like=gbox,
                                  groupby="solar_day", chunks={})
                    ds = ds.isel(time=0) if "time" in ds.dims else ds
                    db = [10.0 * np.log10(ds[b].where(ds[b] > 0)).compute()
                          for b in ("vv", "vh")]
                    stack = xr.concat(db, dim="band").astype("float32")
                    stack = stack.assign_coords(band=[1, 2]).rio.write_crs(gbox.crs)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    stack.rio.to_raster(out)
                    arr = stack.values
                    row["vh_median_db"] = round(float(np.nanmedian(arr[1])), 2)
                    row["nan_frac"] = round(float(np.mean(~np.isfinite(arr[1]))), 4)
                    row["status"] = "read" if same else "read, orbit not matched"
            rows.append(row)
            print(f"\r  {n}/{len(ids)}  ({time.time() - t0:.0f}s)", end="", flush=True)
        print()
        write_csv(OUT / f"rtc_{ev}.csv", rows)
        counts = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        for k, v in counts.items():
            print(f"  {v:>4}  {k}")


def cmd_probe(args):
    """For an event where rtc found nothing: what the catalogues hold around
    its date over its first chip, in RTC and in the GRD it is made from."""
    import planetary_computer
    import pystac_client
    import rioxarray                                    # noqa: F401
    import odc.geo.xr                                   # noqa: F401
    client = pystac_client.Client.open(MPC_STAC,
                                       modifier=planetary_computer.sign_inplace)
    table, chips = event_table(), split_chips()
    rows = []
    for ev in events(args.event):
        t = table[ALIAS.get(ev, ev)]
        day = datetime.strptime(t["s1"], "%Y-%m-%d")
        chip = sorted(chips[ev])[0]
        gbox = rioxarray.open_rasterio(chip_path("S1Hand", ev, chip)).odc.geobox
        bbox = list(gbox.extent.to_crs("EPSG:4326").boundingbox)
        when = (f"{day - timedelta(days=6):%Y-%m-%d}T00:00:00Z/"
                f"{day + timedelta(days=7):%Y-%m-%d}T00:00:00Z")
        print(f"\n{ev}, chip {chip}, {t['s1']} +/- 6 days, orbit {t['rel']}")
        for coll in (S1_COLLECTION, "sentinel-1-grd"):
            items = sorted(client.search(collections=[coll], bbox=bbox,
                                         datetime=when).items(),
                           key=lambda i: i.datetime)
            print(f"  {coll}: {len(items)} item(s)")
            for i in items:
                orbit = i.properties.get("sat:relative_orbit")
                print(f"    {i.datetime:%Y-%m-%d %H:%M} UTC  orbit {orbit}  {i.id}")
                rows.append(dict(event=ev, chip=chip, collection=coll,
                                 datetime=f"{i.datetime:%Y-%m-%d %H:%M}",
                                 relative_orbit=orbit, item=i.id))
    if rows:
        write_csv(OUT / f"probe_{'_'.join(events(args.event))}.csv", rows)


# ---------------------------------------------------------------- align
def cmd_align(args):
    from coregister import apply_shift, corr
    rng = range(-MAX_SHIFT, MAX_SHIFT + 1)
    for ev in events(args.event):
        rows = []
        for f in sorted(TRANSFER.glob(f"{ev}_*_FLOODRTC.tif")):
            chip = f.name.split("_")[1]
            with rasterio.open(f) as src:
                ours = src.read().astype("float32")
                profile = src.profile
            with rasterio.open(chip_path("S1Hand", ev, chip)) as src:
                theirs = src.read().astype("float64")
            ob, tb = block_mean(ours[1].astype("float64")), block_mean(theirs[1])
            grid = {(dy, dx): corr(ob, tb, dy, dx) for dy in rng for dx in rng}
            best = max(grid, key=lambda k: grid[k] if np.isfinite(grid[k]) else -9)
            with rasterio.open(TRANSFER / f"{ev}_{chip}_FLOODRTC_ALIGNED.tif", "w",
                               **profile) as dst:
                dst.write(apply_shift(ours, *best))
            after = grid[best]
            rows.append(dict(event=ev, chip=chip, dy=best[0], dx=best[1],
                             at_search_edge=int(MAX_SHIFT in map(abs, best)),
                             corr_before=round(grid[(0, 0)], 4)
                             if np.isfinite(grid[(0, 0)]) else "",
                             corr_after=round(after, 4) if np.isfinite(after) else "",
                             usable=int(np.isfinite(after) and after >= MIN_CORR)))
        if not rows:
            print(f"{ev}: nothing read yet")
            continue
        write_csv(OUT / f"coreg_{ev}.csv", rows)
        ok = sum(r["usable"] for r in rows)
        edge = sum(r["at_search_edge"] for r in rows)
        print(f"{ev:<10} {len(rows):>3} chips aligned, {ok} usable, "
              f"{edge} at the search edge")


# ---------------------------------------------------------------- score
def load_event(ev):
    """[(vh_filtered, label, otsu, at_search_edge)] for the usable chips."""
    out = []
    if ev == "India":
        ids = (RESULTS / "usable_chips.txt").read_text().split()
        with open(RESULTS / "coregistration.csv", encoding="utf-8") as fh:
            edge = {r["chip_id"]: r["at_search_edge"] == "1"
                    for r in csv.DictReader(fh)}
        paths = [(c, DATA / "reference" / f"India_{c}_FLOODRTC_ALIGNED.tif") for c in ids]
    else:
        p = OUT / f"coreg_{ev}.csv"
        if not p.exists():
            return out
        with open(p, encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["usable"] == "1"]
        edge = {r["chip"]: r["at_search_edge"] == "1" for r in rows}
        paths = [(r["chip"], TRANSFER / f"{ev}_{r['chip']}_FLOODRTC_ALIGNED.tif")
                 for r in rows]
    for chip, path in paths:
        with rasterio.open(path) as src:
            vh = lee_filter(src.read(2).astype("float64")).astype("float32")
        with rasterio.open(chip_path("LabelHand", ev, chip)) as src:
            label = src.read(1)
        with rasterio.open(chip_path("S1OtsuLabelHand", ev, chip)) as src:
            otsu = src.read(1)
        out.append((vh, label, otsu, edge.get(chip, False)))
    return out


def predict(vh, t):
    return np.where(np.isfinite(vh), (vh <= t).astype(np.int8), -1).astype(np.int8)


def authors_thresholds():
    """{event: VH_thresh} from the metadata, the dataset's own per-event value,
    set on Earth Engine sigma0 and so not on the scale of RTC gamma0."""
    if not META.exists():
        return {}
    out = {}
    for f in json.loads(META.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        name = {v: k for k, v in ALIAS.items()}.get(p["location"], p["location"])
        out[name] = p.get("VH_thresh")
    return out


def score_set(name, data, t0, rng, authors):
    """Every figure for one set of chips: an event, or several pooled."""
    confs = {t: [M.confusion(predict(vh, t), lab) for vh, lab, _, _ in data]
             for t in SWEEP}
    ious = {t: M.aggregate(confs[t])["iou"] for t in SWEEP}
    fixed = [M.confusion(predict(vh, t0), lab) for vh, lab, _, _ in data]
    a = M.aggregate(fixed)
    boots = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(fixed), len(fixed))
        boots.append(M.aggregate([fixed[i] for i in pick])["iou"])
    best_t = max(ious, key=ious.get)
    otsu = M.aggregate([M.confusion(o, lab) for _, lab, o, _ in data])
    water = sum(c["tp"] + c["fn"] for c in fixed) / max(
        sum(c["n_valid"] for c in fixed), 1)
    edge = [c for c, d in zip(fixed, data) if d[3]]
    inner = [c for c, d in zip(fixed, data) if not d[3]]
    row = dict(
        event=name, chips=len(data), chips_at_search_edge=len(edge),
        labelled_water_share=round(water, 4),
        iou_at_operating=round(a["iou"], 4),
        iou_ci_low=round(float(np.percentile(boots, 2.5)), 4),
        iou_ci_high=round(float(np.percentile(boots, 97.5)), 4),
        precision=round(a["precision"], 4), recall=round(a["recall"], 4),
        iou_without_edge_chips=round(M.aggregate(inner)["iou"], 4)
        if edge and inner else "",
        best_threshold=float(best_t), iou_at_best=round(ious[best_t], 4),
        iou_authors_otsu=round(otsu["iou"], 4),
        authors_event_threshold_sigma0=authors.get(name, ""))
    return row, ious


def cmd_score(args):
    t0 = threshold()
    authors = authors_thresholds()
    names = ["India"] + events("all")
    rows, sweep_rows, pooled = [], [], []
    rng = np.random.default_rng(BOOT_SEED)
    for ev in names:
        data = load_event(ev)
        if not data:
            print(f"  {ev:<10} not aligned yet, skipped")
            continue
        row, ious = score_set(ev, data, t0, rng, authors)
        rows.append(row)
        sweep_rows += [dict(event=ev, threshold=float(t), iou=round(ious[t], 4))
                       for t in SWEEP]
        if ev != "India":
            pooled += data
    others = [r for r in rows if r["event"] != "India"]
    if others:
        row, ious = score_set("other events, pooled", pooled, t0, rng, authors)
        rows.append(row)
        sweep_rows += [dict(event=row["event"], threshold=float(t),
                            iou=round(ious[t], 4)) for t in SWEEP]
        rows.append(dict(event="other events, mean of events", chips=len(pooled),
                         iou_at_operating=round(float(np.mean(
                             [r["iou_at_operating"] for r in others])), 4),
                         iou_at_best=round(float(np.mean(
                             [r["iou_at_best"] for r in others])), 4),
                         iou_authors_otsu=round(float(np.mean(
                             [r["iou_authors_otsu"] for r in others])), 4)))
    write_csv(OUT / "transfer_scores.csv", rows)
    write_csv(OUT / "transfer_sweep.csv", sweep_rows)

    print(f"\nTHE INDIA THRESHOLD, {t0:g} dB, ON EVERY EVENT")
    print(f"  {'event':<29} {'chips':>5} {'water':>6} {'IoU':>6} {'95% CI':>13} "
          f"{'P':>6} {'R':>6} {'best t':>7} {'IoU':>6} {'Otsu':>6}")
    for r in rows:
        if "precision" not in r:
            print(f"  {r['event']:<29} {r['chips']:>5} {'':>6} "
                  f"{r['iou_at_operating']:>6.3f} {'':>13} {'':>6} {'':>6} {'':>7} "
                  f"{r['iou_at_best']:>6.3f} {r['iou_authors_otsu']:>6.3f}")
            continue
        print(f"  {r['event']:<29} {r['chips']:>5} {r['labelled_water_share']:>6.1%} "
              f"{r['iou_at_operating']:>6.3f} {r['iou_ci_low']:>6.3f}-{r['iou_ci_high']:<6.3f} "
              f"{r['precision']:>6.3f} {r['recall']:>6.3f} {r['best_threshold']:>7.2f} "
              f"{r['iou_at_best']:>6.3f} {r['iou_authors_otsu']:>6.3f}")
    print("\n  IoU, CI, P, R   at the India threshold; CI bootstrapped over chips")
    print("  best t, IoU     the best single threshold for that set, in sample")
    print("  Otsu            the dataset authors' per-chip Otsu labels, same chips")
    for r in rows:
        if r.get("chips_at_search_edge"):
            print(f"  {r['event']}: {r['chips_at_search_edge']} chip(s) aligned at the "
                  f"edge of the search; without them IoU is {r['iou_without_edge_chips']:.3f}")
    india = next((r for r in rows if r["event"] == "India"), None)
    if india and abs(india["iou_at_operating"] - 0.519) > 0.002:
        print(f"\n  CHECK FAILED: India scores {india['iou_at_operating']:.3f} here "
              "against 0.519 in accuracy_ci.csv; something differs from step 10")
    elif india:
        print("\n  check: India reproduces its IoU of 0.519")
    print(f"\n  wrote {OUT / 'transfer_scores.csv'} and transfer_sweep.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["meta", "labels", "rtc", "probe", "align",
                                     "score"])
    ap.add_argument("--event", default="all")
    ap.add_argument("--limit", type=int, default=None,
                    help="rtc only: the first N chips, for a smoke test")
    args = ap.parse_args()
    {"meta": cmd_meta, "labels": cmd_labels, "rtc": cmd_rtc, "probe": cmd_probe,
     "align": cmd_align, "score": cmd_score}[args.step](args)


if __name__ == "__main__":
    main()
