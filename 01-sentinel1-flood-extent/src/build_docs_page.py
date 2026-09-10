"""
Generate docs/index.html from results/.

The page used to be hand-written. Nothing regenerated it, so when C-12 moved
flooded cropland from the district sum to the scene total, the README, the
publication sheet and the three-date sheet were corrected and the page kept
printing 43,494 ha. It also still quoted IoU 0.147 for the change signal, a
number superseded on 9 September. Both are the same failure: a document with
no producer drifts away from its sources and nobody notices.

This builds the page instead, from the same files everything else reads.

What it writes
--------------
    docs/index.html
    docs/overlay_20160807.png    flood classes, warped to the page grid
    docs/overlay_20160812.png
    docs/overlay_20160831.png
    docs/overlay_change.png      7 to 31 August, drained / still / new

Why three dates and a change layer
----------------------------------
Across the three acquisitions there are 44 distinct districts and only 18 are
seen by all three. Nagaon is fully imaged on 12 August and not imaged at all on
the other two. Golaghat goes from 36% imaged to 97%. A plain date switch would
let a reader watch a district vanish, or watch its number jump, and read
geometry as hydrology. So every figure on this page carries the share of the
district that pass actually saw, districts a pass did not see render as not
imaged rather than as zero, and figures below 50% coverage are marked as a
floor.

The fourth mode is the only cross-date comparison the data supports. 7 and 31
August are both relative orbit 4 and cover the same ground to the hectare, so
each pixel is compared against itself. 12 August is orbit 77 with a different
footprint and stays out of it.

Run:
    python 01-sentinel1-flood-extent\\src\\build_docs_page.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

SCENE = cfg.RESULTS / "fullscene"
DOCS = cfg.PROJECT / "docs"
RES_M = 20.0

LAND, FLOOD, PERM, ND = 0, 1, 2, 255

# The display grid. Plate carree at 0.0018 deg/px over the AOI, which is the
# grid the page's canvas maths already assumes.
B = {"w": 92.12484644575109, "s": 24.844729206912216,
     "e": 94.20024644575109, "n": 28.289929206912216, "W": 1153, "H": 1914}

PAL_DATE = {LAND: (226, 236, 243, 190), FLOOD: (41, 128, 185, 255),
            PERM: (12, 44, 82, 255), ND: (0, 0, 0, 0)}
# dry, still flooded, drained, newly flooded, permanent, not seen by both
PAL_CHANGE = {0: (237, 234, 227, 190), 1: (27, 94, 140, 255),
              2: (224, 164, 88, 255), 3: (142, 69, 133, 255),
              4: (123, 148, 166, 255), 255: (0, 0, 0, 0)}

DATES = [
    # tag          suffix        scene-csv row            label       orbit
    ("20160807", "_20160807", "7 Aug, map-optimal", "7 August 2016", 4),
    ("20160812", "", "12 Aug, map-optimal", "12 August 2016", 77),
    ("20160831", "_20160831", "31 Aug, map-optimal", "31 August 2016", 4),
]
AM_ROW = {"20160807": "7 Aug, area-matched",
          "20160812": "12 Aug, area-matched",
          "20160831": "31 Aug, area-matched"}

SIMPLIFY_DEG = 0.002      # 1.1 display pixels, below what the canvas can show
COORD_DP = 4              # about 11 m, well under one display pixel

# Numbers that live in an analysis rather than in a single column. Each is
# named with the file it came from. verify_all.py section A2 traces every one
# of them against results/, so a drift here is caught rather than shipped.
LIT = {
    "iou_map": "0.519",          # accuracy_ci.csv, micro IoU at -18.75 dB
    "iou_area": "0.522",         # operating_point.csv at -17.75 dB
    "ci_lo": "0.395",            # accuracy_ci.csv percentile bootstrap
    "ci_hi": "0.609",
    "ci_halfwidth": "0.11",
    "change_best": "0.196",      # change_sweep.csv, gate 0, drop 2 dB
    "all_water": "0.130",        # the same configuration with no drop required
    "perm_below_slope": "99.3%",  # flood_by_slope, share of channel under 8 deg
}

# gsw_lo and gsw_hi are read from mask_terrain_water.csv at build time rather
# than typed. The page used to say 11,067 and 23,423, which appear nowhere in
# results/; the measurement is 8,893 and 19,458. verify_all.py section A2 is
# what caught it.


# --------------------------------------------------------------------- data
def warp(tif):
    """The refined raster on the page's grid, nearest neighbour."""
    dst = from_origin(B["w"], B["n"],
                      (B["e"] - B["w"]) / B["W"], (B["n"] - B["s"]) / B["H"])
    out = np.full((B["H"], B["W"]), ND, np.uint8)
    with rasterio.open(tif) as s:
        reproject(rasterio.band(s, 1), out,
                  src_transform=s.transform, src_crs=s.crs,
                  dst_transform=dst, dst_crs="EPSG:4326",
                  resampling=Resampling.nearest, src_nodata=ND, dst_nodata=ND)
    return out


def png(arr, pal, path):
    from PIL import Image
    rgba = np.zeros((*arr.shape, 4), np.uint8)
    for v, c in pal.items():
        rgba[arr == v] = c
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)
    return path.stat().st_size


def refined(sfx):
    p = SCENE / f"{cfg.EVENT}_water_{RES_M:g}m{sfx}_refined.tif"
    if not p.exists():
        sys.exit(f"missing {p}. Nothing written.")
    return p


def write_overlays():
    DOCS.mkdir(parents=True, exist_ok=True)
    grids = {}
    print("overlays")
    for tag, sfx, _row, _lab, _orb in DATES:
        g = warp(refined(sfx))
        grids[tag] = g
        n = png(g, PAL_DATE, DOCS / f"overlay_{tag}.png")
        print(f"  overlay_{tag}.png{'':<4}{n / 1024:>6.0f} KB")

    a, b = grids["20160807"], grids["20160831"]
    both = (a != ND) & (b != ND)
    ch = np.full(a.shape, 255, np.uint8)
    ch[both & (a == LAND) & (b == LAND)] = 0
    ch[both & (a == FLOOD) & (b == FLOOD)] = 1
    ch[both & (a == FLOOD) & (b != FLOOD) & (b != PERM)] = 2
    ch[both & (a != FLOOD) & (a != PERM) & (b == FLOOD)] = 3
    ch[both & ((a == PERM) | (b == PERM))] = 4
    n = png(ch, PAL_CHANGE, DOCS / "overlay_change.png")
    print(f"  overlay_change.png{'':<2}{n / 1024:>6.0f} KB")


def macro_iou():
    """Macro IoU over the 65 chips, from accuracy_ci.csv.

    accuracy_ci.py computed this all along and only printed it, so the 0.280
    the page and the README quoted was a recollection with nothing behind it.
    It writes the column now.
    """
    p = cfg.RESULTS / "accuracy_ci.csv"
    if not p.exists():
        sys.exit(f"missing {p.name}. Nothing written.")
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("split") == "all":
                if "macro_iou" not in r:
                    sys.exit(f"{p.name} has no macro_iou column. Re-run "
                             f"accuracy_ci.py after patching it. "
                             f"Nothing written.")
                return float(r["macro_iou"])
    sys.exit(f"{p.name} has no 'all' row. Nothing written.")


def edge_rates():
    """How often the classifier called flood in the swath rim vs the interior.

    Measured by edge_rate.py. The page and the README used to say 17% against
    1.9%, which appears in no file and is not what the rasters say.
    """
    p = cfg.RESULTS / "edge_rate.csv"
    if not p.exists():
        sys.exit(f"missing {p.name}. Run edge_rate.py first. Nothing written.")
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("variant", "").strip() == "12 Aug, map-optimal":
                # Recomputed from the hectare columns rather than read from
                # the pre-rounded percentage columns. Rounding 3.053 to 3.05
                # in the CSV and then to one decimal for display gives 3.0,
                # while the README and the console both say 3.1.
                b = float(r["buffer_flood_ha"]) / float(r["buffer_ha"]) * 100
                i = (float(r["interior_flood_ha"])
                     / float(r["interior_ha"]) * 100)
                return b, i, b / i
    sys.exit(f"{p.name} has no 12 Aug, map-optimal row. Nothing written.")


def gsw_range():
    """Flood extent when permanent water is defined at 10% and at 90%.

    mask_terrain_water.py measures this on the validation chips and writes it
    as occurrence_10 / occurrence_90 with key flood_only_ha.
    """
    p = cfg.RESULTS / "mask_terrain_water.csv"
    if not p.exists():
        sys.exit(f"missing {p.name}. Run mask_terrain_water.py first. "
                 f"Nothing written.")
    want = {"occurrence_10": None, "occurrence_90": None}
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("section") in want and r.get("key") == "flood_only_ha":
                want[r["section"]] = float(r["value"])
    missing = [k for k, v in want.items() if v is None]
    if missing:
        sys.exit(f"{p.name} has no flood_only_ha row for "
                 f"{', '.join(missing)}. Nothing written.")
    return want["occurrence_10"], want["occurrence_90"]


def scene_rows():
    p = cfg.RESULTS / "cropland_scene.csv"
    if not p.exists():
        sys.exit(f"missing {p.name}. Run cropland_scene.py first. "
                 f"Nothing written.")
    with open(p, encoding="utf-8") as fh:
        return {r["variant"].strip(): r for r in csv.DictReader(fh)}


def headline(rows):
    """The four figures at the top of the page, per date, from results."""
    out = {}
    for tag, sfx, row, label, orbit in DATES:
        m, a = rows[row], rows[AM_ROW[tag]]
        st = json.load(open(cfg.RESULTS / f"fullscene_stats_{RES_M:g}m{sfx}"
                                          f".json", encoding="utf-8"))
        ref = st.get("refined", {})
        out[tag] = {
            "label": label, "orbit": orbit,
            "flood": float(m["flood_scene_ha"]),
            "flood_am": float(a["flood_scene_ha"]),
            "crop": float(m["flooded_cropland_scene_ha"]),
            "crop_am": float(a["flooded_cropland_scene_ha"]),
            "imaged": float(m["imaged_scene_ha"]),
            "outside": float(m["flood_scene_ha"]) - float(m["flood_districts_ha"]),
            "raw": float(st.get("flood_ha", 0)),
            "before": float(ref.get("flood_ha_before", 0)),
            "steep": float(ref.get("removed_steep_ha", 0)),
            "small": float(ref.get("removed_small_ha", 0)),
        }
    return out


def change_totals():
    """7 to 31 August at full raster resolution, not from the preview grid."""
    px_ha = cfg.pixel_ha(RES_M)
    tot = dict(still=0, drained=0, new=0, a=0, b=0)
    with rasterio.open(refined("_20160807")) as A, \
            rasterio.open(refined("_20160831")) as Bx:
        if (A.height, A.width) != (Bx.height, Bx.width):
            sys.exit("the 7 and 31 August grids differ. Nothing written.")
        for i in range(0, A.height, 2048):
            for j in range(0, A.width, 2048):
                w = rasterio.windows.Window(j, i, min(2048, A.width - j),
                                            min(2048, A.height - i))
                x, y = A.read(1, window=w), Bx.read(1, window=w)
                seen = (x != ND) & (y != ND)
                fa, fb = (x == FLOOD) & seen, (y == FLOOD) & seen
                tot["a"] += int(np.count_nonzero(fa))
                tot["b"] += int(np.count_nonzero(fb))
                tot["still"] += int(np.count_nonzero(fa & fb))
                tot["drained"] += int(np.count_nonzero(fa & ~fb))
                tot["new"] += int(np.count_nonzero(~fa & fb))
    return {k: v * px_ha for k, v in tot.items()}


def district_payload():
    """Geometry once for the union, plus one attribute row per date."""
    from shapely.geometry import mapping, shape

    fields = ["flood_ha", "flooded_cropland_ha", "cropland_ha", "imaged_ha",
              "district_ha", "imaged_pct_of_district",
              "pct_of_imaged_cropland_flooded", "permanent_water_ha"]
    geom, attrs = {}, {}
    for tag, sfx, _row, _lab, _orb in DATES:
        p = cfg.RESULTS / f"district_flood_stats{sfx}.geojson"
        if not p.exists():
            sys.exit(f"missing {p.name}. Nothing written.")
        d = json.load(open(p, encoding="utf-8"))
        attrs[tag] = {}
        for f in d["features"]:
            n = f["properties"]["district"]
            geom.setdefault(n, f["geometry"])
            attrs[tag][n] = [round(float(f["properties"][k]), 1)
                             for k in fields]

    def rnd(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], COORD_DP), round(c[1], COORD_DP)]
        return [rnd(x) for x in c]

    names = sorted(geom)
    gs = []
    for n in names:
        g = shape(geom[n]).simplify(SIMPLIFY_DEG, preserve_topology=True)
        m = mapping(g)
        gs.append({"type": m["type"], "coordinates": rnd(m["coordinates"])})

    return names, {
        "fields": fields, "names": names, "geom": gs,
        "attrs": {t: [attrs[t].get(n) for n in names] for t, *_ in DATES},
    }


# --------------------------------------------------------------------- page
CSS = """
:root{
  --ground:#EFF2F4; --surface:#FFFFFF; --surface-2:#F7F9FA;
  --ink:#101A22; --muted:#5C6B76; --line:#D6DEE4; --line-soft:#E7EDF1;
  --water:#2980B9; --deep:#0C2C52; --crop:#B4823C; --flag:#A8562F;
  --sheet:#EDF2F5; --drain:#E0A458; --new:#8E4585; --none:#98A6B0;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --cond:"IBM Plex Sans Condensed",var(--sans);
  --mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0B1218; --surface:#121C24; --surface-2:#17232C;
    --ink:#E4EDF3; --muted:#93A6B4; --line:#25343F; --line-soft:#1B2831;
    --water:#4FA3D8; --deep:#89AFD2; --crop:#D6A459; --flag:#D98A63;
    --sheet:#0F1A22; --none:#6B7C88;
  }
}
:root[data-theme="dark"]{
  --ground:#0B1218; --surface:#121C24; --surface-2:#17232C;
  --ink:#E4EDF3; --muted:#93A6B4; --line:#25343F; --line-soft:#1B2831;
  --water:#4FA3D8; --deep:#89AFD2; --crop:#D6A459; --flag:#D98A63;
  --sheet:#0F1A22; --none:#6B7C88;
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1280px;margin:0 auto;padding:28px 22px 56px}

header.top{display:flex;flex-wrap:wrap;align-items:flex-end;gap:14px 26px;
  padding-bottom:16px;border-bottom:1px solid var(--line)}
h1{font-family:var(--cond);font-weight:700;font-size:clamp(26px,3.4vw,38px);
  letter-spacing:.008em;margin:0;text-wrap:balance}
.sub{font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);margin:0}
.prov{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted);
  text-align:right;line-height:1.7}

.dates{display:flex;flex-wrap:wrap;gap:6px;margin:18px 0 0;align-items:center}
.dates .lbl{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);margin-right:6px}
.dates .gap{flex-basis:100%;height:0}

.figs{display:flex;flex-wrap:wrap;gap:0;margin:14px 0 26px;
  border-top:1px solid var(--line-soft);border-bottom:1px solid var(--line-soft)}
.fig{flex:1 1 180px;padding:14px 20px 13px;border-right:1px solid var(--line-soft)}
.fig:last-child{border-right:0}
.fig .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);display:block;margin-bottom:5px}
.fig .v{font-family:var(--cond);font-weight:600;font-size:27px;
  font-variant-numeric:tabular-nums;line-height:1.1}
.fig .v small{font-family:var(--mono);font-size:12px;font-weight:400;
  color:var(--muted);margin-left:5px}
.fig.-w .v{color:var(--water)} .fig.-c .v{color:var(--crop)}
.fig.-d .v{color:var(--drain)} .fig.-n .v{color:var(--new)}
.fig .rng{font-family:var(--mono);font-size:10px;line-height:1.4;
  color:var(--muted);margin-top:4px;max-width:24ch}

.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(290px,1fr);
  gap:22px;align-items:start}
@media (max-width:900px){.split{grid-template-columns:1fr}}

.mapcard{background:var(--surface);border:1px solid var(--line);
  border-radius:3px;overflow:hidden}
.maphead{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  padding:9px 13px;border-bottom:1px solid var(--line-soft);
  background:var(--surface-2)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-family:var(--mono);
  font-size:10.5px;letter-spacing:.04em;color:var(--muted)}
.legend[hidden]{display:none}
.sw{display:inline-block;width:11px;height:11px;border-radius:2px;
  margin-right:5px;vertical-align:-1px}
.tools{margin-left:auto;display:flex;gap:6px}
button{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;
  text-transform:uppercase;color:var(--ink);background:var(--surface);
  border:1px solid var(--line);border-radius:2px;padding:5px 9px;cursor:pointer}
button:hover{border-color:var(--water);color:var(--water)}
button[aria-pressed="true"]{background:var(--water);border-color:var(--water);
  color:#fff}
button:focus-visible{outline:2px solid var(--water);outline-offset:2px}
#stage{position:relative;background:var(--sheet);touch-action:none;
  cursor:grab;display:flex;justify-content:center}
#stage.drag{cursor:grabbing}
canvas{display:block}
#tip{position:absolute;pointer-events:none;z-index:3;opacity:0;
  transition:opacity .12s;background:var(--surface);color:var(--ink);
  border:1px solid var(--line);border-radius:2px;padding:6px 9px;
  font-family:var(--mono);font-size:11px;line-height:1.5;
  box-shadow:0 4px 14px rgba(8,26,40,.16);white-space:nowrap}
#tip b{font-family:var(--cond);font-size:13px;letter-spacing:.01em}

.rail h2,.notes h2{font-family:var(--cond);font-weight:600;font-size:13px;
  letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  margin:0 0 10px}
.railnote{font-family:var(--mono);font-size:10.5px;line-height:1.6;
  color:var(--muted);margin:-4px 0 10px}
.rows{display:flex;flex-direction:column}
.row{display:grid;grid-template-columns:1fr auto;gap:2px 10px;
  padding:8px 9px;border:0;border-bottom:1px solid var(--line-soft);
  background:none;text-align:left;width:100%;cursor:pointer;border-radius:2px;
  font-family:var(--sans);text-transform:none;letter-spacing:0;font-size:15px}
.row:hover{background:var(--surface-2);border-color:var(--line-soft);
  color:var(--ink)}
.row[aria-current="true"]{background:var(--surface);
  box-shadow:inset 3px 0 0 var(--water)}
.row .nm{font-weight:500}
.row .ha{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:13px;color:var(--muted)}
.row.-unseen .nm,.row.-unseen .ha{color:var(--none);font-style:italic}
.bar{grid-column:1/-1;height:4px;background:var(--line-soft);border-radius:2px;
  overflow:hidden;margin-top:3px}
.bar i{display:block;height:100%;background:var(--water)}
.bar i.-drain{background:var(--drain)}
.chip{font-family:var(--mono);font-size:9.5px;letter-spacing:.07em;
  color:var(--flag);border:1px solid currentColor;border-radius:2px;
  padding:0 4px;margin-left:6px;vertical-align:1px}
.chip.-none{color:var(--none)}

.detail{margin-top:22px;background:var(--surface);border:1px solid var(--line);
  border-radius:3px;padding:15px 16px}
.detail h3{font-family:var(--cond);font-weight:700;font-size:21px;margin:0 0 2px}
.detail .cov{font-family:var(--mono);font-size:11px;color:var(--muted);
  margin:0 0 12px}
.detail .warn{font-family:var(--mono);font-size:10.5px;line-height:1.6;
  color:var(--flag);margin:10px 0 0}
dl{display:grid;grid-template-columns:1fr auto;gap:7px 12px;margin:0;
  font-size:13.5px}
dt{color:var(--muted)}
dd{margin:0;font-family:var(--mono);font-variant-numeric:tabular-nums;
  text-align:right}
dd.hi{color:var(--water);font-weight:500}
dd.crop{color:var(--crop);font-weight:500}
dd.drain{color:var(--drain);font-weight:500}
dd.new{color:var(--new);font-weight:500}

.notes{margin-top:30px;padding-top:20px;border-top:1px solid var(--line);
  display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
  gap:20px 30px}
.notes p{margin:0 0 9px;font-size:13.5px;color:var(--muted);max-width:62ch}
.notes strong{color:var(--ink);font-weight:600}
.notes code{font-family:var(--mono);font-size:12px;color:var(--ink)}
.built{font-family:var(--mono);font-size:10.5px!important;line-height:1.7;
  color:var(--muted);margin-top:16px!important;padding-top:12px;
  border-top:1px solid var(--line-soft)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


BODY = """<title>Brahmaputra Flood Ledger</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">

<style>{css}</style>

<div class="wrap">
  <header class="top">
    <div>
      <h1>Brahmaputra Flood Ledger</h1>
      <p class="sub" id="sub">Assam &middot; three Sentinel-1 acquisitions, August 2016</p>
    </div>
    <div class="prov">
      threshold &minus;18.75 dB &middot; 20 m grid<br>
      slope &gt; 8&deg; removed &middot; EPSG:32646
    </div>
  </header>

  <div class="dates">
    <span class="lbl">Acquisition</span>
    <button class="dbtn" data-m="20160807">7 Aug</button>
    <button class="dbtn" data-m="20160812" aria-pressed="true">12 Aug</button>
    <button class="dbtn" data-m="20160831">31 Aug</button>
    <button class="dbtn" data-m="change">7 &rarr; 31 Aug change</button>
  </div>

  <section class="figs" id="figs"></section>

  <div class="split">
    <div class="mapcard">
      <div class="maphead">
        <div class="legend" id="legDate">
          <span><i class="sw" style="background:#2980B9"></i>flood</span>
          <span><i class="sw" style="background:#0C2C52"></i>permanent water</span>
          <span><i class="sw" style="background:#E2ECF3;border:1px solid #C3D3DE"></i>imaged, dry</span>
        </div>
        <div class="legend" id="legChange" hidden>
          <span><i class="sw" style="background:#E0A458"></i>drained</span>
          <span><i class="sw" style="background:#1B5E8C"></i>still flooded</span>
          <span><i class="sw" style="background:#8E4585"></i>newly flooded</span>
          <span><i class="sw" style="background:#7B94A6"></i>permanent</span>
          <span><i class="sw" style="background:#EDEAE3;border:1px solid #C3D3DE"></i>dry both dates</span>
        </div>
        <div class="tools">
          <button id="tDist" aria-pressed="true">Districts</button>
          <button id="tReset">Reset view</button>
        </div>
      </div>
      <div id="stage"><canvas id="cv"></canvas><div id="tip"></div></div>
    </div>

    <div class="rail">
      <h2 id="railTitle">Flooded cropland by district</h2>
      <p class="railnote" id="railNote"></p>
      <div class="rows" id="rows"></div>
      <div class="detail" id="detail"></div>
    </div>
  </div>

  <section class="notes">
    <div>
      <h2>Why three dates and not one map</h2>
      <p>Across the three acquisitions there are <strong>44</strong> districts
      and only <strong>18</strong> are seen by all three. 12 August is relative
      orbit 77 and images {imaged12} million hectares; 7 and 31 August are orbit
      4 and image {imaged07} and {imaged31} million. Nagaon is fully imaged on
      12 August and not imaged at all on the other two.</p>
      <p>So a district's number can move between dates because the water moved
      or because the satellite saw a different amount of it, and the two look
      identical in a bar chart. Every figure here carries the share of the
      district that pass actually saw. Below 50% it is marked as a floor rather
      than a measurement, and a district a pass did not reach is shown as not
      imaged rather than as zero.</p>
      <p>The change view is the one honest cross-date comparison. 7 and 31
      August share a footprint to the hectare, so each pixel is compared with
      itself. 12 August is a different orbit and stays out of it.</p>
    </div>
    <div>
      <h2>How the extent was made</h2>
      <p>Water is dark to radar because a calm surface reflects the pulse away
      from the sensor. Each pass was speckle filtered with a 5&times;5 Lee
      window and thresholded at <code>&minus;18.75 dB</code> on VH, an operating
      point chosen against the hand-labelled Sen1Floods11 chips for this
      event.</p>
      <p>Change detection against an earlier date was tested and rejected. With
      the change signal alone the sweep reaches <strong>{change_best} IoU</strong>
      at a required drop of 2 dB; relax that requirement and it converges on
      <strong>{all_water}</strong>, which is what labelling the entire scene as
      water scores.</p>
    </div>
    <div>
      <h2>What the numbers depend on</h2>
      <p>Three things are dark to radar without being wet, and each was found by
      looking at the map rather than by any metric. A 600 m buffer inside the
      swath boundary is marked no data, where flood classification ran at
      <strong>{edge_rate}</strong> of area against <strong>{interior_rate}</strong>
      in the interior, {edge_ratio} times the rate. Ground steeper than
      8&deg; becomes land, since
      {perm_below_slope} of the permanent channel sits below that slope.
      Components under 10 pixels are dropped. On 12 August the chain runs
      {raw12} &rarr; {before12} &rarr; {mid12} &rarr; <strong>{flood12} ha</strong>.</p>
      <p>None of those three steps is validated. The hand labels cover 65
      floodplain chips and none of these situations appears in them.</p>
      <p>Permanent water means JRC Global Surface Water occurrence of 50% or
      more. Moving that definition between 10% and 90% moves flood extent
      between <strong>{gsw_lo}</strong> and <strong>{gsw_hi} ha</strong> on the
      validation chips. The definitions move the answer more than the method
      does.</p>
    </div>
    <div>
      <h2>Which number, and how sure</h2>
      <p>The threshold was chosen twice against two defensible criteria. At
      <code>&minus;18.75 dB</code> the map agrees best with hand labels pixel by
      pixel; at <code>&minus;17.75 dB</code> its total area is unbiased against
      them. The two score <strong>{iou_map}</strong> and <strong>{iou_area}</strong>
      IoU, indistinguishable inside a confidence interval of
      &plusmn;{ci_halfwidth}. This page draws the first; the range beside each
      figure gives the second.</p>
      <p>Accuracy on the 65 labelled chips is IoU <strong>{iou_map}</strong>, 95%
      interval <strong>{ci_lo} to {ci_hi}</strong>, bootstrapped over chips. Macro
      IoU is {iou_macro} with a minimum of zero, so the method fails outright on
      some chips. Nothing here has been checked against an independent flood
      map: no contemporaneous district-wise inundation figure for this event was
      retrievable from open archives.</p>
    </div>
    <div>
      <h2>Read this before quoting a figure</h2>
      <p>Cropland comes from ESA WorldCover 2021, four to five years after the
      event, because no open 10 m cropland map exists for India in 2016. Land
      that changed use in between is misattributed, and the fetched tiles cover
      97.8% of the grid, so every cropland figure here is a floor.</p>
      <p>District boundaries are present-day geoBoundaries ADM2, and Assam has
      created districts since 2016, so these will not match a 2016 bulletin one
      for one.</p>
      <p>The headline figures are measured over the whole raster. The district
      rows are sums over ADM2 polygons, which on 12 August account for
      {inside12} ha of the {flood12} ha mapped: {outside12} ha fell outside every
      Indian district polygon, in Bangladesh, Bhutan and the Arunachal border
      strip. The map layer is a preview render; every number comes from the 20 m
      raster.</p>
      <p class="built">Built by <code>build_docs_page.py</code> on {built}.
      The wording here is written; every number in it, and every figure in the
      panel above, is read from <code>results/</code> at build time. The page
      it replaced was maintained by hand and had drifted from its sources.</p>
    </div>
  </section>
</div>

<script id="dpay" type="application/json">{payload}</script>
<script id="dhead" type="application/json">{head}</script>
<script>{js}</script>
"""


JS = r"""
(function () {
const PAY = JSON.parse(document.getElementById("dpay").textContent);
const HEAD = JSON.parse(document.getElementById("dhead").textContent);
const B = __BOUNDS__;
const F = {}; PAY.fields.forEach((k, i) => F[k] = i);
const DATE_MODES = ["20160807", "20160812", "20160831"];

const latMid = (B.n + B.s) / 2, kx = Math.cos(latMid * Math.PI / 180);
const degPerPxY = (B.n - B.s) / B.H;
const baseW = B.W * kx, baseH = B.H;

const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
const stage = document.getElementById("stage"), tip = document.getElementById("tip");
let mode = "20160812", showD = true, hoverI = -1, selI = -1;
let view = {s: 1, x: 0, y: 0};

const imgs = {}; let ready = false;
["20160807", "20160812", "20160831", "change"].forEach(m => {
  const im = new Image();
  im.onload = () => { ready = true; draw(); };
  im.src = "overlay_" + m + ".png";
  imgs[m] = im;
});

const feats = PAY.geom.map((g, i) => {
  const rings = [];
  const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const poly of polys) {
    const pr = [];
    for (const ring of poly) {
      pr.push(ring.map(([lo, la]) => {
        const X = (lo - B.w) / degPerPxY * kx, Y = (B.n - la) / degPerPxY;
        if (X < x0) x0 = X; if (X > x1) x1 = X;
        if (Y < y0) y0 = Y; if (Y > y1) y1 = Y;
        return [X, Y];
      }));
    }
    rings.push(pr);
  }
  return {i, name: PAY.names[i], rings, bb: [x0, y0, x1, y1]};
});

/* Attributes for feature i on a given date, or null if that pass never saw
   the district. Null is the whole point: it is not the same as zero flood. */
function at(i, m) { const r = PAY.attrs[m]; return r ? r[i] : null; }
function val(i, m, k) { const r = at(i, m); return r ? r[F[k]] : null; }
function cov(i, m) { const v = val(i, m, "imaged_pct_of_district"); return v == null ? null : v; }

/* In change mode a district counts only if BOTH orbit-4 passes reached it. */
function chg(i) {
  const a = at(i, "20160807"), b = at(i, "20160831");
  if (!a || !b) return null;
  return {
    fa: a[F.flood_ha], fb: b[F.flood_ha],
    ca: a[F.flooded_cropland_ha], cb: b[F.flooded_cropland_ha],
    cov: Math.min(a[F.imaged_pct_of_district], b[F.imaged_pct_of_district]),
  };
}
function seen(i) { return mode === "change" ? !!chg(i) : !!at(i, mode); }

/* Thousands separators every three digits. toLocaleString("en-IN") groups by
   lakh, so 119779 came out as 1,19,779 while every other document in this
   repository writes 119,779. */
const grp = n => String(Math.abs(Math.round(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
const num = v => (v == null ? "&mdash;" : (v < 0 ? "-" : "") + grp(v));
const sgn = v => (v > 0 ? "+" : v < 0 ? "-" : "") + grp(v);
function flag(c) {
  if (c == null) return {t: "NOT IMAGED", cls: " -none"};
  if (c >= 50) return null;
  return {t: c >= 15 ? "PARTIAL" : "SLIVER", cls: ""};
}

/* ------------------------------------------------------------------ canvas */
function fit() {
  const maxH = Math.max(380, Math.min(700, window.innerHeight - 250));
  const avail = (stage.clientWidth || 700) - 2;
  const s = Math.min(maxH / baseH, avail / baseW);
  const cw = Math.round(baseW * s), ch = Math.round(baseH * s);
  cv.style.width = cw + "px"; cv.style.height = ch + "px";
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr);
  cv.__base = s; cv.__dpr = dpr;
  view = {s: 1, x: 0, y: 0};
  draw();
}
function local(e) { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top, r]; }
function T() { const s = cv.__base * view.s; return {s, x: view.x, y: view.y}; }
function path(f, t) {
  ctx.beginPath();
  for (const poly of f.rings) for (const ring of poly) {
    ring.forEach(([X, Y], k) => {
      const x = X * t.s + t.x, y = Y * t.s + t.y;
      k ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.closePath();
  }
}
function draw() {
  const dpr = cv.__dpr || 1, t = T();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cv.width / dpr, cv.height / dpr);
  const im = imgs[mode];
  if (ready && im && im.complete && im.naturalWidth) {
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
    ctx.drawImage(im, t.x, t.y, baseW * t.s, baseH * t.s);
  }
  if (!showD) return;
  const css = getComputedStyle(document.body);
  const line = css.getPropertyValue("--muted").trim() || "#5C6B76";
  const none = css.getPropertyValue("--none").trim() || "#98A6B0";
  /* A district this pass did not reach is drawn dashed and pale, so it reads
     as absent rather than as dry. */
  for (const f of feats) {
    const ok = seen(f.i);
    ctx.setLineDash(ok ? [] : [3, 3]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = ok ? line : none;
    ctx.globalAlpha = ok ? .5 : .75;
    path(f, t); ctx.stroke();
  }
  ctx.setLineDash([]); ctx.globalAlpha = 1;
  for (const idx of [hoverI, selI]) {
    if (idx < 0) continue;
    const f = feats[idx], ok = seen(idx);
    path(f, t);
    ctx.fillStyle = ok
      ? (idx === selI ? "rgba(41,128,185,.20)" : "rgba(41,128,185,.10)")
      : "rgba(152,166,176,.14)";
    ctx.fill();
    ctx.lineWidth = idx === selI ? 2.2 : 1.6;
    ctx.strokeStyle = ok ? "#2980B9" : none;
    ctx.stroke();
  }
}
function inside(f, X, Y) {
  const [a, b, c, d] = f.bb;
  if (X < a || X > c || Y < b || Y > d) return false;
  let n = 0;
  for (const poly of f.rings) for (const ring of poly)
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > Y) !== (yj > Y) && X < (xj - xi) * (Y - yi) / (yj - yi) + xi) n++;
    }
  return n % 2 === 1;
}
function hit(px, py) {
  const t = T(), X = (px - t.x) / t.s, Y = (py - t.y) / t.s;
  for (const f of feats) if (inside(f, X, Y)) return f.i;
  return -1;
}

/* ------------------------------------------------------------------ panels */
function figs() {
  const el = document.getElementById("figs");
  if (mode === "change") {
    const c = HEAD.change;
    el.innerHTML =
      fig("-w", "Flood, 7 Aug", num(c.a), "ha", "map-optimal, over the shared footprint") +
      fig("-w", "Flood, 31 Aug", num(c.b), "ha", Math.round(100 * c.b / c.a) + "% of the 7 August extent") +
      fig("-d", "Drained", num(c.drained), "ha", "flood on 7 Aug, dry on 31 Aug") +
      fig("-n", "Newly flooded", num(c.new), "ha", "dry on 7 Aug, flood on 31 Aug");
    return;
  }
  const h = HEAD[mode];
  el.innerHTML =
    fig("-w", "Flood water", num(h.flood), "ha", "to " + num(h.flood_am) + " ha at the area-matched threshold") +
    fig("-c", "Flooded cropland", num(h.crop), "ha", "to " + num(h.crop_am) + " ha at the area-matched threshold") +
    fig("", "Permanent channel", num(h.perm), "ha", "JRC occurrence 50% or more") +
    fig("", "Imaged area", (h.imaged / 1e6).toFixed(2), "million ha", "relative orbit " + h.orbit + ", 20 m");
}
function fig(cls, k, v, u, rng) {
  return '<div class="fig ' + cls + '"><span class="k">' + k + '</span>' +
    '<div class="v">' + v + '<small>' + u + '</small></div>' +
    '<div class="rng">' + rng + '</div></div>';
}

function rank() {
  const idx = feats.map(f => f.i).filter(seen);
  if (mode === "change") {
    return idx.sort((a, b) => (chg(a).ca - chg(a).cb) - (chg(b).ca - chg(b).cb)).reverse();
  }
  return idx.sort((a, b) => (val(b, mode, "flooded_cropland_ha") || 0) -
                            (val(a, mode, "flooded_cropland_ha") || 0));
}

function rail() {
  const rowsEl = document.getElementById("rows");
  const order = rank();
  const top = order.slice(0, 12);
  document.getElementById("railTitle").textContent = mode === "change"
    ? "Cropland that drained, by district" : "Flooded cropland by district";
  document.getElementById("railNote").innerHTML = mode === "change"
    ? "Districts both orbit-4 passes reached. " + order.length + " of 44 qualify."
    : order.length + " of 44 districts were imaged by this pass. Percentages are of the cropland imaged, not of all the cropland a district has.";

  const maxv = top.length
    ? (mode === "change" ? Math.max(1, chg(top[0]).ca - chg(top[0]).cb)
                         : Math.max(1, val(top[0], mode, "flooded_cropland_ha") || 1))
    : 1;
  rowsEl.innerHTML = top.map(i => {
    const c = mode === "change" ? chg(i).cov : cov(i, mode);
    const fl = flag(c);
    const v = mode === "change" ? (chg(i).ca - chg(i).cb)
                                : (val(i, mode, "flooded_cropland_ha") || 0);
    return '<button class="row" data-i="' + i + '">' +
      '<span class="nm">' + feats[i].name +
        (fl ? '<span class="chip' + fl.cls + '">' + fl.t + '</span>' : '') + '</span>' +
      '<span class="ha">' + (mode === "change" ? sgn(-v) : num(v)) + ' ha</span>' +
      '<span class="bar"><i class="' + (mode === "change" ? "-drain" : "") +
        '" style="width:' + (100 * Math.abs(v) / maxv).toFixed(1) + '%"></i></span>' +
      '</button>';
  }).join("");
  if (!top.includes(selI)) selI = top.length ? top[0] : -1;
  detail(selI);
  [...document.querySelectorAll(".row")].forEach(r =>
    r.setAttribute("aria-current", String(+r.dataset.i === selI)));
}

function detail(i) {
  const el = document.getElementById("detail");
  if (i < 0) { el.innerHTML = ""; return; }
  const name = feats[i].name;
  if (mode === "change") {
    const c = chg(i);
    if (!c) {
      el.innerHTML = '<h3>' + name + '</h3><p class="cov">One of the two ' +
        'orbit-4 passes did not reach this district, so no change can be ' +
        'measured for it.</p>';
      return;
    }
    el.innerHTML = '<h3>' + name + '</h3>' +
      '<p class="cov">' + Math.round(c.cov) + '% of the district imaged on both dates</p>' +
      '<dl>' +
      '<dt>Flood, 7 Aug</dt><dd class="hi">' + num(c.fa) + ' ha</dd>' +
      '<dt>Flood, 31 Aug</dt><dd class="hi">' + num(c.fb) + ' ha</dd>' +
      '<dt>Change</dt><dd class="drain">' + sgn(c.fb - c.fa) + ' ha</dd>' +
      '<dt>Flooded cropland, 7 Aug</dt><dd class="crop">' + num(c.ca) + ' ha</dd>' +
      '<dt>Flooded cropland, 31 Aug</dt><dd class="crop">' + num(c.cb) + ' ha</dd>' +
      '<dt>Change</dt><dd class="drain">' + sgn(c.cb - c.ca) + ' ha</dd>' +
      '</dl>' + warn(c.cov);
    return;
  }
  const r = at(i, mode);
  if (!r) {
    el.innerHTML = '<h3>' + name + '</h3><p class="cov">This pass did not ' +
      'image this district. That is not the same as no flood: nothing was ' +
      'observed here on ' + HEAD[mode].label + '.</p>';
    return;
  }
  const c = r[F.imaged_pct_of_district];
  el.innerHTML = '<h3>' + name + '</h3>' +
    '<p class="cov">' + Math.round(c) + '% of the district imaged on ' + HEAD[mode].label + '</p>' +
    '<dl>' +
    '<dt>Flood water</dt><dd class="hi">' + num(r[F.flood_ha]) + ' ha</dd>' +
    '<dt>Flooded cropland</dt><dd class="crop">' + num(r[F.flooded_cropland_ha]) + ' ha</dd>' +
    '<dt>Share of imaged cropland</dt><dd>' + r[F.pct_of_imaged_cropland_flooded].toFixed(1) + '%</dd>' +
    '<dt>Cropland imaged</dt><dd>' + num(r[F.cropland_ha]) + ' ha</dd>' +
    '<dt>Permanent water</dt><dd>' + num(r[F.permanent_water_ha]) + ' ha</dd>' +
    '<dt>District area</dt><dd>' + num(r[F.district_ha]) + ' ha</dd>' +
    '</dl>' + warn(c);
}
function warn(c) {
  if (c >= 50) return "";
  return '<p class="warn">The swath covered ' + Math.round(c) + '% of this ' +
    'district, so the hectares above are a floor rather than a measurement, ' +
    'and the share is computed only over the cropland that was imaged.</p>';
}

function select(i) {
  selI = i; detail(i); draw();
  [...document.querySelectorAll(".row")].forEach(r =>
    r.setAttribute("aria-current", String(+r.dataset.i === i)));
}
function setMode(m) {
  mode = m;
  [...document.querySelectorAll(".dbtn")].forEach(b =>
    b.setAttribute("aria-pressed", String(b.dataset.m === m)));
  document.getElementById("legDate").hidden = (m === "change");
  document.getElementById("legChange").hidden = (m !== "change");
  document.getElementById("sub").innerHTML = m === "change"
    ? "Assam &middot; 7 to 31 August 2016 &middot; relative orbit 4, same footprint"
    : "Assam &middot; " + HEAD[m].label + " &middot; relative orbit " + HEAD[m].orbit;
  figs(); rail(); draw();
}

/* ------------------------------------------------------------------ events */
document.getElementById("rows").addEventListener("click", e => {
  const b = e.target.closest(".row"); if (b) select(+b.dataset.i);
});
document.getElementById("rows").addEventListener("mouseover", e => {
  const b = e.target.closest(".row");
  if (b) { hoverI = +b.dataset.i; draw(); }
});
document.getElementById("rows").addEventListener("mouseleave", () => { hoverI = -1; draw(); });
[...document.querySelectorAll(".dbtn")].forEach(b =>
  b.addEventListener("click", () => setMode(b.dataset.m)));

stage.addEventListener("pointermove", e => {
  const [px, py, r] = local(e);
  const i = showD ? hit(px, py) : -1;
  if (i !== hoverI) { hoverI = i; draw(); }
  if (i >= 0) {
    let body;
    if (!seen(i)) body = "not imaged on this date";
    else if (mode === "change") {
      const c = chg(i);
      body = sgn(c.cb - c.ca) + " ha cropland, 7 to 31 Aug";
    } else body = num(val(i, mode, "flooded_cropland_ha")) + " ha cropland flooded";
    tip.innerHTML = "<b>" + feats[i].name + "</b><br>" + body;
    tip.style.opacity = 1;
    const sr = stage.getBoundingClientRect();
    const dx = r.left - sr.left, tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(Math.max(px + dx + 14, 4), sr.width - tw - 4) + "px";
    tip.style.top = Math.max(py - th - 12, 4) + "px";
  } else tip.style.opacity = 0;
});
stage.addEventListener("pointerleave", () => { hoverI = -1; tip.style.opacity = 0; draw(); });
stage.addEventListener("click", e => {
  const [px, py] = local(e); const i = hit(px, py); if (i >= 0) select(i);
});
stage.addEventListener("wheel", e => {
  e.preventDefault();
  const [px, py] = local(e);
  const f = e.deltaY < 0 ? 1.18 : 1 / 1.18;
  const ns = Math.min(Math.max(view.s * f, 1), 14), k = ns / view.s;
  view.x = px - (px - view.x) * k; view.y = py - (py - view.y) * k; view.s = ns;
  clamp(); draw();
}, {passive: false});
let drag = null;
stage.addEventListener("pointerdown", e => {
  drag = {x: e.clientX, y: e.clientY, vx: view.x, vy: view.y};
  stage.classList.add("drag"); stage.setPointerCapture(e.pointerId);
});
stage.addEventListener("pointerup", () => { drag = null; stage.classList.remove("drag"); });
stage.addEventListener("pointermove", e => {
  if (!drag) return;
  view.x = drag.vx + (e.clientX - drag.x); view.y = drag.vy + (e.clientY - drag.y);
  clamp(); draw();
});
function clamp() {
  const t = T(), w = cv.clientWidth, h = cv.clientHeight;
  view.x = Math.min(0, Math.max(view.x, w - baseW * t.s));
  view.y = Math.min(0, Math.max(view.y, h - baseH * t.s));
  if (view.s <= 1) { view.x = 0; view.y = 0; }
}
document.getElementById("tDist").addEventListener("click", e => {
  showD = !showD; e.currentTarget.setAttribute("aria-pressed", String(showD)); draw();
});
document.getElementById("tReset").addEventListener("click", () => {
  view = {s: 1, x: 0, y: 0}; draw();
});
window.addEventListener("resize", fit);
setMode("20160812");
fit();
})();
"""


def perm_ha(sfx):
    """Permanent water for a date, counted on the raster at full resolution."""
    px_ha = cfg.pixel_ha(RES_M)
    n = 0
    with rasterio.open(refined(sfx)) as s:
        for i in range(0, s.height, 2048):
            for j in range(0, s.width, 2048):
                w = rasterio.windows.Window(j, i, min(2048, s.width - j),
                                            min(2048, s.height - i))
                n += int(np.count_nonzero(s.read(1, window=w) == PERM))
    return n * px_ha


def main() -> None:
    print(f"Building docs/index.html from {cfg.RESULTS}\n")

    write_overlays()

    rows = scene_rows()
    head = headline(rows)
    for tag, sfx, *_ in DATES:
        head[tag]["perm"] = perm_ha(sfx)
    ch = change_totals()
    head["change"] = {"a": ch["a"], "b": ch["b"], "still": ch["still"],
                      "drained": ch["drained"], "new": ch["new"]}

    names, payload = district_payload()

    h12 = head["20160812"]
    lo, hi = gsw_range()
    er, ir, ratio = edge_rates()
    fmt = dict(LIT)
    fmt.update(
        gsw_lo=f"{lo:,.0f}", gsw_hi=f"{hi:,.0f}",
        iou_macro=f"{macro_iou():.3f}",
        edge_rate=f"{er:.1f}%", interior_rate=f"{ir:.1f}%",
        edge_ratio=f"{ratio:.0f}",
        css=CSS,
        js=JS.replace("__BOUNDS__", json.dumps(B)),
        payload=json.dumps(payload, separators=(",", ":")),
        head=json.dumps(head, separators=(",", ":")),
        built=__import__("datetime").date.today().strftime("%d %B %Y"),
        imaged07=f'{head["20160807"]["imaged"] / 1e6:.2f}',
        imaged12=f'{h12["imaged"] / 1e6:.2f}',
        imaged31=f'{head["20160831"]["imaged"] / 1e6:.2f}',
        raw12=f'{h12["raw"]:,.0f}',
        before12=f'{h12["before"]:,.0f}',
        mid12=f'{h12["before"] - h12["steep"]:,.0f}',
        flood12=f'{h12["flood"]:,.0f}',
        outside12=f'{h12["outside"]:,.0f}',
        inside12=f'{h12["flood"] - h12["outside"]:,.0f}',
    )
    html = BODY.format(**fmt)

    out = DOCS / "index.html"
    out.write_text(html, encoding="utf-8")

    print("\npage")
    print(f"  index.html{'':<9}{len(html.encode('utf-8')) / 1024:>6.0f} KB")
    print(f"  districts{'':<10}{len(names):>6}   union of the three passes")
    for tag, *_ in DATES:
        n = sum(1 for v in payload["attrs"][tag] if v)
        print(f"    {tag}{'':<12}{n:>6}   imaged by this pass")
    common = sum(1 for i in range(len(names))
                 if all(payload["attrs"][t][i] for t, *_ in DATES))
    print(f"    all three{'':<7}{common:>6}")

    print("\nheadline figures, straight from results/")
    for tag, *_ in DATES:
        h = head[tag]
        print(f"  {h['label']:<16} flood {h['flood']:>9,.0f}   "
              f"cropland {h['crop']:>8,.0f}   imaged {h['imaged'] / 1e6:>5.2f} M ha")
    print(f"  {'7 to 31 Aug':<16} flood {ch['a']:>9,.0f} to {ch['b']:,.0f}   "
          f"drained {ch['drained']:>8,.0f}   new {ch['new']:>6,.0f}")

    print(f"\nwrote {out.relative_to(cfg.PROJECT)} and four overlays.")
    print("Re-run verify_all.py: section A2 traces every number on this page.")


if __name__ == "__main__":
    main()
