"""
Flooded cropland over the whole scene, not only inside district polygons.

The README pairs a scene-wide flood figure (119,779 ha) with a cropland figure
(43,494 ha) that district_stats.py computes by summing over ADM2 polygons.
Those polygons only account for 110,081 ha of the flood, so the two numbers are
on different footprints. This measures the cropland figure on the same ground
the flood figure uses, so the pair can be quoted together honestly.

Method. WorldCover was fetched as tiles under data/worldcover/. Each tile is
opened, its bounds are turned into a window on the refined water raster, and
the two are counted together. Tile windows are checked for overlap first: if
any two overlap the script stops rather than double-count. Nothing is mosaicked
into memory.

Run from anywhere:

    python 01-sentinel1-flood-extent\\src\\cropland_scene.py

Writes results/cropland_scene.csv and prints a comparison against the district
sums. Changes nothing else.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255
RES_M = 20.0
PX_HA = cfg.pixel_ha(RES_M)
CROP = int(cfg.CROPLAND_CLASS)

SCENE = cfg.RESULTS / "fullscene"
WC_DIR = cfg.DATA / "worldcover"

# (label, refined raster, district csv suffix, stats json tag)
VARIANTS = [
    ("12 Aug, map-optimal", "India_water_20m_refined.tif", "", "20m"),
    ("12 Aug, area-matched", "India_water_20m_areamatched_refined.tif",
     "_areamatched", "20m_areamatched"),
    ("7 Aug, map-optimal", "India_water_20m_20160807_refined.tif",
     "_20160807", "20m_20160807"),
    ("7 Aug, area-matched", "India_water_20m_20160807am_refined.tif",
     "_20160807am", "20m_20160807am"),
    ("31 Aug, map-optimal", "India_water_20m_20160831_refined.tif",
     "_20160831", "20m_20160831"),
    ("31 Aug, area-matched", "India_water_20m_20160831am_refined.tif",
     "_20160831am", "20m_20160831am"),
]


def district_sums(suffix):
    p = cfg.RESULTS / f"district_flood_stats{suffix}.csv"
    if not p.exists():
        return None, None
    flood = crop = 0.0
    with open(p, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                flood += float(r["flood_ha"])
                crop += float(r["flooded_cropland_ha"])
            except (KeyError, ValueError):
                pass
    return flood, crop


def recorded(tag):
    p = cfg.RESULTS / f"fullscene_stats_{tag}.json"
    if not p.exists():
        return None
    j = json.load(open(p, encoding="utf-8"))
    try:
        return float(j["refined"]["flood_ha_after"])
    except (KeyError, TypeError, ValueError):
        return None


def build_plan(water_path):
    """One window per WorldCover tile, on the water raster's grid. Returns the
    plan, or exits if any two windows overlap."""
    tiles = sorted(WC_DIR.glob("*.tif"))
    if not tiles:
        sys.exit(f"no WorldCover tiles under {WC_DIR}. Nothing written.")

    with rasterio.open(water_path) as w:
        wcrs, wtr = w.crs, w.transform
        H, W = w.height, w.width

    plan = []
    for t in tiles:
        with rasterio.open(t) as s:
            if str(s.crs) != str(wcrs):
                sys.exit(f"{t.name} is {s.crs}, water raster is {wcrs}. "
                         f"Nothing written.")
            b = s.bounds
        win = from_bounds(b.left, b.bottom, b.right, b.top, transform=wtr)
        c0 = int(round(win.col_off))
        r0 = int(round(win.row_off))
        c1 = c0 + int(round(win.width))
        r1 = r0 + int(round(win.height))
        c0, r0 = max(0, c0), max(0, r0)
        c1, r1 = min(W, c1), min(H, r1)
        if c1 <= c0 or r1 <= r0:
            continue
        plan.append((t, r0, r1, c0, c1))

    for i in range(len(plan)):
        _, ar0, ar1, ac0, ac1 = plan[i]
        for j in range(i + 1, len(plan)):
            _, br0, br1, bc0, bc1 = plan[j]
            if ar0 < br1 and br0 < ar1 and ac0 < bc1 and bc0 < ac1:
                sys.exit(
                    f"tiles {plan[i][0].name} and {plan[j][0].name} overlap on "
                    f"the water grid. Counting them would double-count "
                    f"pixels. Nothing written.")

    covered = sum((r1 - r0) * (c1 - c0) for _, r0, r1, c0, c1 in plan)
    print(f"  {len(plan)} WorldCover tiles cover {covered:,} of "
          f"{H * W:,} pixels ({covered / (H * W) * 100:.1f}%)")
    if covered < H * W:
        print(f"  {H * W - covered:,} pixels have no WorldCover tile and are "
              f"counted as not cropland")
    return plan


def measure(water_path, plan):
    flood_crop = crop_imaged = flood_all = imaged = 0
    with rasterio.open(water_path) as w:
        for t, r0, r1, c0, c1 in plan:
            win = Window(c0, r0, c1 - c0, r1 - r0)
            wat = w.read(1, window=win)
            with rasterio.open(t) as s:
                wc = s.read(1, out_shape=(wat.shape[0], wat.shape[1]))
            if wc.shape != wat.shape:
                sys.exit(f"{t.name}: shape {wc.shape} against water "
                         f"{wat.shape}. Nothing written.")
            is_crop = wc == CROP
            seen = wat != NODATA
            flood_crop += int(np.count_nonzero((wat == FLOOD) & is_crop))
            crop_imaged += int(np.count_nonzero(is_crop & seen))
        # totals over the whole raster, not only tiled ground
        for i in range(0, w.height, 2048):
            for j in range(0, w.width, 2048):
                win = Window(j, i, min(2048, w.width - j),
                             min(2048, w.height - i))
                a = w.read(1, window=win)
                flood_all += int(np.count_nonzero(a == FLOOD))
                imaged += int(np.count_nonzero(a != NODATA))
    return (flood_crop * PX_HA, crop_imaged * PX_HA,
            flood_all * PX_HA, imaged * PX_HA)


def main() -> None:
    out = []
    plan = None
    for label, fname, suffix, tag in VARIANTS:
        p = SCENE / fname
        if not p.exists():
            print(f"\n{label}: {fname} not found, skipped")
            continue
        print(f"\n{label}")
        if plan is None:
            plan = build_plan(p)

        fc, ci, fa, im = measure(p, plan)
        d_flood, d_crop = district_sums(suffix)
        rec = recorded(tag)

        if rec is not None and abs(fa - rec) / rec > 0.005:
            sys.exit(f"  counted {fa:,.0f} ha of flood but "
                     f"fullscene_stats_{tag}.json records {rec:,.0f} ha. "
                     f"One is stale. Nothing written.")

        print(f"    flood, scene-wide          {fa:>12,.0f} ha")
        print(f"    flooded cropland, scene    {fc:>12,.0f} ha")
        print(f"    cropland imaged, scene     {ci:>12,.0f} ha")
        print(f"    imaged, scene              {im:>12,.0f} ha")
        if d_flood is not None:
            print(f"    flood, districts only      {d_flood:>12,.0f} ha  "
                  f"({d_flood / fa * 100:.1f}% of scene)")
            print(f"    cropland, districts only   {d_crop:>12,.0f} ha  "
                  f"({d_crop / fc * 100:.1f}% of scene)")
            print(f"    cropland outside districts {fc - d_crop:>12,.0f} ha")
        print(f"    share of scene flood on cropland "
              f"{fc / fa * 100:>6.1f}%")
        if d_flood:
            print(f"    same share, districts only       "
                  f"{d_crop / d_flood * 100:>6.1f}%")

        out.append(dict(
            variant=label,
            flood_scene_ha=round(fa, 1),
            flooded_cropland_scene_ha=round(fc, 1),
            cropland_imaged_scene_ha=round(ci, 1),
            imaged_scene_ha=round(im, 1),
            flood_districts_ha=round(d_flood, 1) if d_flood else "",
            flooded_cropland_districts_ha=round(d_crop, 1) if d_crop else "",
            cropland_outside_districts_ha=(round(fc - d_crop, 1)
                                           if d_crop else ""),
            pct_of_flood_on_cropland_scene=round(fc / fa * 100, 2),
        ))

    if out:
        p = cfg.RESULTS / "cropland_scene.csv"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(out[0]))
            wr.writeheader()
            wr.writerows(out)
        print(f"\nwrote {p.relative_to(cfg.PROJECT)}")

    print("\nRead the two cropland columns against each other. If the gap is "
          "small the\nREADME can keep the district figures with their scope "
          "stated. If it is large\nthe scene-wide figures should replace them "
          "throughout.")


if __name__ == "__main__":
    main()
