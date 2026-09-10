"""
Full verification pass. Read-only. Writes nothing except a report file.

The point of this script is to remove assumption from the project before it
goes public. It does four things:

  A. TRACE EVERY NUMBER IN THE README
     Pulls every numeric claim out of README.md and tries to find it in the
     CSVs and JSONs the pipeline wrote. Anything it cannot find is listed with
     its sentence, so each one can be adjudicated by hand rather than trusted.

  B. INTERNAL CONSISTENCY
     Cross-checks the files against each other where the relationship is
     exact: district totals against scene totals, the sensitivity grid's
     published cell against the reported figure, the slope histogram against
     the before and after counts, config constants against what the stats
     files say was actually run.

  C. HARD-CODED PARAMETERS
     Greps src/ for numeric literals that duplicate a config constant, which
     is how the 80-versus-50 permanent-water discrepancy got in.

  D. FIGURE FRESHNESS
     Compares every figure's timestamp against the CSV it is drawn from and
     the script that draws it, so a stale picture cannot sit beside a
     corrected number.

Run from anywhere:

    python 01-sentinel1-flood-extent\\src\\verify_all.py > verify_report.txt

Then open verify_report.txt. Nothing in the repo is modified.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

# Windows redirects stdout as cp1252, which cannot encode the real minus sign
# (U+2212) or the >= and <= glyphs this report and the README both contain.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

ROOT = cfg.PROJECT
RES = cfg.RESULTS
SRC = ROOT / "src"
README = ROOT / "README.md"

PASS, FAIL, WARN, INFO = "PASS", "FAIL", "WARN", "  · "
n_fail = 0
n_warn = 0


def report(status, msg):
    global n_fail, n_warn
    if status == FAIL:
        n_fail += 1
    if status == WARN:
        n_warn += 1
    print(f"[{status:^4}] {msg}" if status in (PASS, FAIL, WARN)
          else f"{INFO}{msg}")


def head(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def sub(t):
    print(f"\n--- {t} " + "-" * max(0, 72 - len(t)))


# --------------------------------------------------------------------------
# Value index: every number the pipeline actually wrote
# --------------------------------------------------------------------------
def walk_json(obj, prefix, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk_json(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_json(v, f"{prefix}[{i}]", out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append((float(obj), prefix))


def build_index():
    """value -> list of 'file :: where'. Derived sums are added too, because a
    README figure is often a total the CSV holds only as parts."""
    idx = []
    for p in sorted(RES.glob("*.csv")) + sorted((RES / "fullscene").glob("*.csv")):
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except Exception:
            continue
        if not rows:
            continue
        cols = {k: [] for k in rows[0]}
        for r in rows:
            for k, v in r.items():
                if v in (None, ""):
                    continue
                if "_" in str(v):
                    continue
                try:
                    f = float(v)
                except ValueError:
                    continue
                cols[k].append(f)
                idx.append((f, f"{p.name} :: {k}"))
        for k, vals in cols.items():
            if len(vals) > 1:
                idx.append((float(sum(vals)), f"{p.name} :: sum({k})"))
                idx.append((float(max(vals)), f"{p.name} :: max({k})"))
                idx.append((float(min(vals)), f"{p.name} :: min({k})"))
    for p in sorted(RES.glob("*.json")):
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        out = []
        walk_json(j, "", out)
        for v, where in out:
            idx.append((v, f"{p.name} :: {where}"))
    return idx


def find(x, decimals, index, extra_tol=0.0):
    """Does any recorded value round to x at the precision x was written with?
    Also tries the percent and fraction readings of the same number."""
    hits = []
    step = 0.5 * (10 ** -decimals) if decimals > 0 else 0.5
    for cand, scale, note in ((x, 1.0, ""), (x / 100.0, 1.0, " (as a fraction)"),
                              (x * 100.0, 1.0, " (as a percent)")):
        tol = max(step, abs(cand) * extra_tol)
        for v, where in index:
            if abs(v - cand) <= tol:
                hits.append(where + note)
                if len(hits) >= 4:
                    return hits
    return hits


# --------------------------------------------------------------------------
# A. README trace
# --------------------------------------------------------------------------
NUM = re.compile(
    r"(?<![\w.\-])"
    r"([−-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[−-]?\d+\.\d+|[−-]?\d+)"
    r"(?![\w])")

# numbers that are not measurements
IGNORE_EXACT = {
    1984, 2011, 2014, 2016, 2017, 2018, 2021, 2025, 2026,
    32646, 46, 4326, 10, 20, 30, 40, 50, 65, 77, 4, 3, 2, 1, 0,
    5, 8, 12, 14, 31, 7, 25, 100, 1000, 2048, 16, 512, 600,
}
IGNORE_CONTEXT = re.compile(
    r"(EPSG|UTM|zone|orbit|class \d|Sentinel-1|Sentinel-2|ADM2|version|"
    r"Pekel|Pontius|Millones|Olofsson|et al|20\d\d|figure|section|step)",
    re.I)


def trace_readme(index):
    head("A. EVERY NUMBER IN THE README, TRACED TO A FILE")
    if not README.exists():
        report(FAIL, f"{README} not found")
        return
    lines = README.read_text(encoding="utf-8").splitlines()

    traced, untraced, skipped = 0, [], 0
    in_code = False
    for ln, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
        for m in NUM.finditer(line):
            raw = m.group(1)
            txt = raw.replace(",", "").replace("−", "-")
            try:
                x = float(txt)
            except ValueError:
                continue
            dec = len(txt.split(".")[1]) if "." in txt else 0
            if x in IGNORE_EXACT and dec == 0:
                skipped += 1
                continue
            if IGNORE_CONTEXT.search(line) and abs(x) < 2100 and dec == 0:
                skipped += 1
                continue
            hits = find(x, dec, index, extra_tol=0.0005)
            if hits:
                traced += 1
            else:
                untraced.append((ln, raw, line.strip()))

    report(INFO, f"{traced} numbers matched a value in results/")
    report(INFO, f"{skipped} skipped as years, codes or section numbers")
    if untraced:
        report(WARN, f"{len(untraced)} numbers could not be matched to any "
                     f"file. Each needs a human decision: derived, rounded, "
                     f"or wrong.")
        sub("unmatched README numbers")
        seen = set()
        for ln, raw, line in untraced:
            key = (raw, line[:60])
            if key in seen:
                continue
            seen.add(key)
            snippet = line if len(line) <= 150 else line[:147] + "..."
            print(f"  L{ln:<5} {raw:>14}   {snippet}")
    else:
        report(PASS, "every README number traces to a file")


# --------------------------------------------------------------------------
# B. Internal consistency
# --------------------------------------------------------------------------
VARIANTS = [
    ("12 Aug, map-optimal", "20m", ""),
    ("12 Aug, area-matched", "20m_areamatched", "_areamatched"),
    ("7 Aug, map-optimal", "20m_20160807", "_20160807"),
    ("7 Aug, area-matched", "20m_20160807am", "_20160807am"),
    ("31 Aug, map-optimal", "20m_20160831", "_20160831"),
    ("31 Aug, area-matched", "20m_20160831am", "_20160831am"),
]


def load_json(tag):
    p = RES / f"fullscene_stats_{tag}.json"
    if not p.exists():
        return None
    return json.load(open(p, encoding="utf-8"))


def load_csv(name):
    p = RES / name
    if not p.exists():
        return None
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def col_sum(rows, key):
    return sum(float(r[key]) for r in rows if r.get(key) not in (None, ""))


def check_scene_vs_districts():
    sub("scene totals against the sum of district totals")
    for label, tag, suffix in VARIANTS:
        j = load_json(tag)
        rows = load_csv(f"district_flood_stats{suffix}.csv")
        if j is None or rows is None:
            report(WARN, f"{label}: missing stats json or district csv")
            continue
        ref = j.get("refined", {})
        if "flood_ha_after" not in ref:
            report(FAIL, f"{label}: stats json has no refined.flood_ha_after")
            continue
        scene = float(ref["flood_ha_after"])
        dist = col_sum(rows, "flood_ha")
        d = (dist - scene) / scene * 100 if scene else float("nan")
        status = PASS if abs(d) < 3 else (WARN if abs(d) < 12 else FAIL)
        report(status, f"{label}: scene {scene:,.0f} ha, districts sum to "
                       f"{dist:,.0f} ha, {d:+.1f}%")
        report(INFO, "districts clip to ADM2 polygons, so a small shortfall "
                     "is expected; a large one is not")


def check_raw_vs_refined():
    sub("raw threshold output against the refined figure")
    for label, tag, _ in VARIANTS:
        j = load_json(tag)
        if j is None:
            continue
        ref = j.get("refined", {})
        raw_top = j.get("flood_ha")
        before = ref.get("flood_ha_before")
        after = ref.get("flood_ha_after")
        steep = ref.get("removed_steep_ha")
        small = ref.get("removed_small_ha")
        if None in (raw_top, before, after):
            report(WARN, f"{label}: incomplete refined block")
            continue
        # The gap between the top-level count and flood_ha_before is the
        # swath-edge buffer, which refine_scene.py applies before the slope
        # cut and does not record as its own field. Report it as the step it
        # is rather than as a discrepancy.
        edge = float(raw_top) - float(before)
        if edge < -1.0:
            report(FAIL, f"{label}: refined.flood_ha_before "
                         f"{float(before):,.0f} exceeds the raw count "
                         f"{float(raw_top):,.0f}. Refinement cannot add area.")
        elif edge > 1.0:
            report(PASS, f"{label}: edge buffer removed {edge:,.0f} ha, "
                         f"{float(raw_top):,.0f} to {float(before):,.0f}")
        if steep is not None and small is not None:
            expect = float(before) - float(steep) - float(small)
            gap = float(after) - expect
            status = PASS if abs(gap) < max(50.0, 0.005 * float(after)) else FAIL
            report(status, f"{label}: {float(before):,.0f} − steep "
                           f"{float(steep):,.0f} − small {float(small):,.0f} "
                           f"= {expect:,.0f} against reported "
                           f"{float(after):,.0f}, gap {gap:+,.0f} ha")
            if status == FAIL:
                report(INFO, "the edge buffer also removes area and may not "
                             "be in these two fields; check refine_scene.py")


def check_slope_histogram():
    sub("slope histogram against the refined totals")
    for label, tag, _ in VARIANTS:
        rows = load_csv(f"refine_scene_{tag}.csv")
        j = load_json(tag)
        if rows is None or j is None:
            continue
        # This CSV holds the slope bins, then a footer with a different shape
        # (slope_cut,8.0,removed_ha,68436.8 and so on). Keep only the rows
        # whose first field is a number.
        bins, footer = [], {}
        for r in rows:
            try:
                float(r.get("slope_lo", ""))
                bins.append(r)
            except (TypeError, ValueError):
                key = str(r.get("slope_lo", "")).strip()
                if key:
                    footer[key] = r
        if not bins:
            report(WARN, f"{label}: no numeric slope bins in the CSV")
            continue

        tot = col_sum(bins, "flood_ha")
        before = float(j.get("refined", {}).get("flood_ha_before", "nan"))
        d = (tot - before) / before * 100 if before == before else float("nan")
        status = PASS if abs(d) < 1 else FAIL
        report(status, f"{label}: {len(bins)} slope bins sum to {tot:,.0f} ha "
                       f"against flood_ha_before {before:,.0f}, {d:+.2f}%")

        cut = float(j.get("refined", {}).get("slope_cut_deg", cfg.SLOPE_MAX_DEG))
        above = sum(float(r["flood_ha"]) for r in bins
                    if float(r["slope_lo"]) >= cut)
        steep = j.get("refined", {}).get("removed_steep_ha")
        if steep is not None:
            gap = above - float(steep)
            status = PASS if abs(gap) < max(50.0, 0.005 * float(steep)) else FAIL
            report(status, f"{label}: bins at or above {cut:g}° hold "
                           f"{above:,.0f} ha against removed_steep_ha "
                           f"{float(steep):,.0f}, gap {gap:+,.0f} ha")
        if bins and tot:
            report(INFO, f"{label}: {above / tot * 100:.1f}% of mapped flood "
                         f"sits above {cut:g}°")
        pt = col_sum(bins, "permanent_ha")
        pa = sum(float(r["permanent_ha"]) for r in bins
                 if float(r["slope_lo"]) >= cut)
        if pt:
            report(INFO, f"{label}: {pa / pt * 100:.2f}% of permanent water "
                         f"sits above {cut:g}°, so {100 - pa / pt * 100:.1f}% "
                         f"below")
        for key, want in (("kept_ha", j.get("refined", {})
                           .get("flood_ha_after")),):
            if key in footer and want is not None:
                got = float(footer[key].get("slope_hi", "nan"))
                status = PASS if abs(got - float(want)) < 1.0 else FAIL
                report(status, f"{label}: CSV footer {key} {got:,.0f} against "
                               f"stats flood_ha_after {float(want):,.0f}")


def check_sensitivity_published():
    sub("the published cell of the sensitivity grid")
    rows = load_csv("sensitivity_grid.csv")
    j = load_json("20m")
    if rows is None or j is None:
        report(WARN, "sensitivity_grid.csv or fullscene_stats_20m.json missing")
        return
    pub = [r for r in rows if str(r.get("is_published", "0")).strip() in
           ("1", "1.0", "True", "true")]
    if len(pub) != 1:
        report(FAIL, f"{len(pub)} rows flagged is_published, expected exactly 1")
        return
    r = pub[0]
    grid_ha = float(r["flood_ha"])
    report(INFO, f"published cell: slope {r['slope_max_deg']}, occurrence "
                 f"{r['occurrence_permanent_min']}, edge "
                 f"{r.get('edge_buffer_m', r.get('edge_buffer_px'))}")
    for name, want, got in (
            ("slope", float(cfg.SLOPE_MAX_DEG), float(r["slope_max_deg"])),
            ("occurrence", float(cfg.GSW_PERMANENT_MIN),
             float(r["occurrence_permanent_min"])),
            ("edge px", float(cfg.EDGE_BUFFER_PX),
             float(r.get("edge_buffer_px", "nan")))):
        status = PASS if got == want else FAIL
        report(status, f"published {name} {got:g} against config {want:g}")
    # The grid answers 216 combinations from one binning pass over water
    # pixels. A binning pass cannot represent object-size filtering, so every
    # figure in it is BEFORE the minimum mapping unit. Compare like with like.
    ref = j.get("refined", {})
    after = float(ref.get("flood_ha_after", "nan"))
    small = float(ref.get("removed_small_ha", "nan"))
    pre_mmu = after + small
    d = (grid_ha - pre_mmu) / pre_mmu * 100 if pre_mmu == pre_mmu \
        else float("nan")
    status = PASS if abs(d) < 1 else FAIL
    report(status, f"grid says {grid_ha:,.0f} ha at the published settings "
                   f"against {pre_mmu:,.0f} ha pre-MMU "
                   f"({after:,.0f} reported + {small:,.0f} removed by the "
                   f"MMU), {d:+.2f}%")
    report(INFO, "the grid is pre-MMU by construction; CHANGELOG C-08 says "
                 "so, and the README chain table shows the same value at that "
                 "step")


def check_config_vs_run():
    sub("config constants against what the stats files record was run")
    for label, tag, _ in VARIANTS:
        j = load_json(tag)
        if j is None:
            continue
        ref = j.get("refined", {})
        pairs = [
            ("slope cut", ref.get("slope_cut_deg"), float(cfg.SLOPE_MAX_DEG)),
            ("min pixels", ref.get("min_pixels"),
             float(cfg.MIN_OBJECT_PX_SCENE)),
            ("occurrence cut", j.get("occurrence_cut"),
             float(cfg.GSW_PERMANENT_MIN)),
        ]
        for name, got, want in pairs:
            if got is None:
                report(WARN, f"{label}: stats file records no {name}")
                continue
            status = PASS if float(got) == want else FAIL
            report(status, f"{label}: {name} run at {float(got):g}, config "
                           f"declares {want:g}")
        rs = j.get("resampling")
        if rs is not None:
            if rs != cfg.RESAMPLING:
                report(FAIL, f"{label}: resampling recorded {rs} against "
                             f"config {cfg.RESAMPLING}")
            else:
                report(PASS, f"{label}: resampling matches config")


def check_change_arithmetic():
    sub("the 7 to 31 August change figures")
    for suffix, label in (("", "map-optimal"), ("_am", "area-matched")):
        rows = load_csv(f"compare_0807_vs_0831{suffix}.csv")
        if rows is None:
            report(WARN, f"compare_0807_vs_0831{suffix}.csv missing")
            continue
        d = {r["quantity"]: float(r["hectares"]) for r in rows}
        report(INFO, f"{label}: " + ", ".join(f"{k} {v:,.1f}"
                                              for k, v in d.items()))
        keys = list(d)
        drained = next((d[k] for k in keys if "drain" in k.lower()), None)
        new = next((d[k] for k in keys if "new" in k.lower()), None)
        persist = next((d[k] for k in keys if "persist" in k.lower()
                        or "both" in k.lower() and "seen" not in k.lower()),
                       None)
        if None in (drained, new, persist):
            report(WARN, f"{label}: could not identify all three change "
                         f"quantities by name, check the report above by eye")
            continue
        a, b = drained + persist, persist + new
        report(INFO, f"{label}: implied flood 7 Aug {a:,.0f} ha, "
                     f"31 Aug {b:,.0f} ha, fall {(a - b) / a * 100:.1f}%, "
                     f"persistence {persist / a * 100:.1f}%")


def check_accuracy_headline():
    sub("the accuracy headline")
    rows = load_csv("accuracy_ci.csv")
    if rows is None:
        report(WARN, "accuracy_ci.csv missing")
        return
    for r in rows:
        report(INFO, f"{r['split']:>6}  n={r['chips']:>3}  IoU {r['iou']} "
                     f"[{r['iou_ci_lo']}, {r['iou_ci_hi']}]  "
                     f"P {r['precision']}  R {r['recall']}")
    allrow = next((r for r in rows if r["split"] == "all"), None)
    op = load_csv("operating_point.csv")
    fm = RES / "final_method.json"
    if allrow and op and fm.exists():
        j = json.load(open(fm, encoding="utf-8"))
        ops = j.get("operating_points", {})
        report(INFO, f"final_method.json operating_points: "
                     f"{json.dumps(ops, default=str)}")
        thr = None
        for v in (ops.get("max_iou"), ops.get("area_matched")):
            if isinstance(v, dict) and "threshold" in v:
                thr = float(v["threshold"])
                break
            if isinstance(v, (int, float)):
                thr = float(v)
                break
        if thr is not None:
            near = min(op, key=lambda r: abs(float(r["threshold"]) - thr))
            report(INFO, f"operating_point.csv at {near['threshold']} dB: "
                         f"iou_all {near['iou_all']}, iou_valid "
                         f"{near['iou_valid']}, area_err {near['area_err']}")
            d = abs(float(near["iou_all"]) - float(allrow["iou"]))
            status = PASS if d < 0.01 else WARN
            report(status, f"operating_point iou_all {near['iou_all']} "
                           f"against accuracy_ci all {allrow['iou']}, "
                           f"difference {d:.4f}")


def check_change_sweep_peak():
    sub("what the change sweep actually peaks at")
    rows = load_csv("change_sweep.csv")
    if rows is None:
        report(WARN, "change_sweep.csv missing")
        return
    best = max(rows, key=lambda r: float(r["iou_all"]))
    report(INFO, f"overall best: iou_all {best['iou_all']} at threshold "
                 f"{best['threshold']} dB, smooth {best['smooth']}, "
                 f"gate {best['gate']}")
    neg = [r for r in rows if float(r["threshold"]) <= -0.5]
    if neg:
        bn = max(neg, key=lambda r: float(r["iou_all"]))
        report(INFO, f"best where the change test still requires a drop "
                     f"(threshold <= -0.5 dB): iou_all {bn['iou_all']} at "
                     f"{bn['threshold']} dB, smooth {bn['smooth']}, "
                     f"gate {bn['gate']}")
    if float(best["threshold"]) > 0:
        report(WARN, "the sweep peaks at a POSITIVE threshold, meaning the "
                     "change test admits pixels that got brighter and is "
                     "constraining nothing. Any sentence quoting the peak as "
                     "'change detection scores X' is wrong.")
    lo = min(float(r["threshold"]) for r in rows)
    hi = max(float(r["threshold"]) for r in rows)
    if abs(float(best["threshold"]) - lo) < 1e-9 or \
       abs(float(best["threshold"]) - hi) < 1e-9:
        report(WARN, f"peak sits on the edge of the swept range [{lo}, {hi}]")
    else:
        report(PASS, f"peak is interior to the swept range [{lo}, {hi}]")


def check_products():
    sub("the Earth Engine comparison, at each product's own peak")
    rows = load_csv("product_vs_window.csv")
    if rows is None:
        report(WARN, "product_vs_window.csv missing")
        return
    prods = sorted({r["product"] for r in rows})
    peak = {}
    for p in prods:
        sub_rows = [r for r in rows if r["product"] == p]
        b = max(sub_rows, key=lambda r: float(r["iou_all"]))
        peak[p] = b
        report(INFO, f"{p:>10}: best iou_all {b['iou_all']} at "
                     f"{b['threshold']} dB, p_all {b['p_all']}, "
                     f"r_all {b['r_all']}")
    for a, b in (("gee_lee", "rtc_lee"), ("gee_raw", "gee_lee"),
                 ("gee_raw", "rtc_lee")):
        if a in peak and b in peak:
            di = float(peak[b]["iou_all"]) - float(peak[a]["iou_all"])
            dp = float(peak[b]["p_all"]) - float(peak[a]["p_all"])
            report(INFO, f"{a} to {b}: {di:+.4f} IoU, {dp:+.4f} precision")
    report(INFO, "if the README quotes a different pair or a common "
                 "threshold rather than each product's own peak, say which")


def check_orbit():
    sub("cross-orbit agreement")
    rows = load_csv("orbit_offset.csv")
    if rows is None:
        report(WARN, "orbit_offset.csv missing")
        return
    px = [float(r["pixels"]) for r in rows]
    dif = [float(r["median_diff_db"]) for r in rows]
    land = [float(r["median_diff_land_db"]) for r in rows
            if r.get("median_diff_land_db") not in (None, "")]
    w = sum(d * p for d, p in zip(dif, px)) / sum(px)
    report(INFO, f"{len(rows)} tiles, {sum(px) / 1e6:.2f} M pixels")
    report(INFO, f"pixel-weighted median offset, all pixels: {w:+.4f} dB")
    if land:
        wl = sum(d * p for d, p in zip(land, px)) / sum(px)
        report(INFO, f"pixel-weighted median offset, land only: {wl:+.4f} dB")
    report(INFO, f"unweighted median of tile medians: "
                 f"{sorted(dif)[len(dif) // 2]:+.4f} dB")
    report(INFO, f"mean absolute tile median: "
                 f"{sum(abs(d) for d in dif) / len(dif):.4f} dB")
    report(INFO, "the README quotes one of these. Check which, and that the "
                 "wording matches the statistic")


def check_imaged_area():
    sub("imaged area per date, as recorded in the stats files")
    for label, tag, _ in VARIANTS:
        j = load_json(tag)
        if j is None:
            continue
        land = j.get("land_ha")
        flood = j.get("flood_ha")
        perm = j.get("permanent_ha")
        water = j.get("water_ha")
        nodata = j.get("nodata_ha")
        if None in (land, flood, perm):
            report(WARN, f"{label}: stats file missing a class total")
            continue
        raw_imaged = float(land) + float(flood) + float(perm)
        report(INFO, f"{label}: land {float(land):,.0f} + flood "
                     f"{float(flood):,.0f} + permanent {float(perm):,.0f} "
                     f"= {raw_imaged:,.0f} ha BEFORE refinement"
                     + (f", nodata {float(nodata):,.0f}" if nodata else ""))
        report(INFO, "refinement moves the 600 m swath rim to nodata, so the "
                     "imaged area AFTER refinement is smaller. If the README "
                     "table mixes the two, that is the discrepancy.")


# --------------------------------------------------------------------------
# C. Hard-coded parameters in src/
# --------------------------------------------------------------------------
def check_hardcoded():
    head("C. NUMERIC LITERALS IN src/ THAT DUPLICATE A CONFIG CONSTANT")
    consts = {
        "SLOPE_MAX_DEG": cfg.SLOPE_MAX_DEG,
        "GSW_PERMANENT_MIN": cfg.GSW_PERMANENT_MIN,
        "EDGE_BUFFER_PX": cfg.EDGE_BUFFER_PX,
        "MIN_OBJECT_PX_SCENE": cfg.MIN_OBJECT_PX_SCENE,
        "TARGET_RES": cfg.TARGET_RES,
        "SPECKLE_WINDOW": cfg.SPECKLE_WINDOW,
        "EVENT_VH_THRESHOLD": cfg.EVENT_VH_THRESHOLD,
    }
    # things each constant is compared against in code
    patterns = {
        "GSW_PERMANENT_MIN": re.compile(r"occ\w*\s*[<>=]=?\s*(\d+(?:\.\d+)?)"),
        "SLOPE_MAX_DEG": re.compile(r"slope\w*\s*[<>=]=?\s*(\d+(?:\.\d+)?)"),
    }
    # Audit and patch scripts quote the pipeline's own source inside string
    # literals, so scanning them finds the text they exist to fix.
    SKIP = {"config.py", "verify_all.py", "verify_round2.py",
            "apply_corrections.py", "apply_decisions.py",
            "fix_mask_figure.py", "add_figures.py", "peek_results.py",
            "preflight.py", "make_figures.py", "make_date_maps.py"}
    # JRC occurrence uses values above 100 as a nodata sentinel. A comparison
    # against 100 is not a permanent-water cut.
    SENTINEL = re.compile(r"occ\w*\s*[<>]\s*100\b")

    hits = 0
    for p in sorted(SRC.glob("*.py")):
        if p.name in SKIP:
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if line.strip().startswith("#"):
                continue
            if SENTINEL.search(line):
                continue
            for name, rx in patterns.items():
                for m in rx.finditer(line):
                    val = float(m.group(1))
                    want = float(consts[name])
                    if val == want:
                        continue
                    # a sweep over many values is legitimate
                    if "SWEEP" in line or "for " in line or "CUTS" in line:
                        continue
                    hits += 1
                    report(WARN, f"{p.name}:{i} compares against {val:g} "
                                 f"while config.{name} is {want:g}")
                    print(f"        {line.strip()[:110]}")
    if hits == 0:
        report(PASS, "no literal found that contradicts a config constant")
    else:
        report(INFO, "each of these is either a deliberate local choice that "
                     "should be commented, or a drift like the 80 vs 50 one")


# --------------------------------------------------------------------------
# D. Figure freshness
# --------------------------------------------------------------------------
FIG_SOURCE = {
    "operating_point.png": ["operating_point.csv"],
    "accuracy_ci.png": ["accuracy_ci.csv"],
    "change_sweep.png": ["change_sweep.csv"],
    "product_vs_window.png": ["product_vs_window.csv"],
    "orbit_offset.png": ["orbit_offset.csv"],
    "sensitivity_grid.png": ["sensitivity_grid.csv"],
    "flooded_cropland.png": ["district_flood_stats.csv"],
    "mask_terrain_water.png": ["mask_terrain_water.csv"],
    "change_detection.png": ["change_detection.csv"],
    "compare_0812_vs_0807.png": ["compare_0812_vs_0807.csv"],
    "compare_0807_vs_0831.png": ["compare_0807_vs_0831.csv"],
    "compare_0807_vs_0831_am.png": ["compare_0807_vs_0831_am.csv"],
    "flooded_cropland_areamatched.png":
        ["district_flood_stats_areamatched.csv"],
    "flooded_cropland_20160807.png":
        ["district_flood_stats_20160807.csv"],
    "flooded_cropland_20160831.png":
        ["district_flood_stats_20160831.csv"],
    "flood_extent_map.png": ["district_flood_stats.csv"],
    "flood_three_dates.png": ["district_flood_stats.csv"],
    "flood_recession.png": ["district_flood_stats_20160807.csv"],
}


def check_figures():
    head("D. FIGURE FRESHNESS")
    figs = RES / "figures"
    if not figs.exists():
        report(FAIL, "results/figures does not exist")
        return
    stale = 0
    for name, sources in sorted(FIG_SOURCE.items()):
        f = figs / name
        if not f.exists():
            report(WARN, f"{name} does not exist")
            continue
        ft = f.stat().st_mtime
        for s in sources:
            sp = RES / s
            if not sp.exists():
                continue
            if sp.stat().st_mtime > ft:
                stale += 1
                report(FAIL, f"{name} is OLDER than {s}. Redraw it.")
                break
        else:
            report(PASS, f"{name} is newer than its source data")
    if stale == 0:
        report(PASS, "no figure is older than the data behind it")

    sub("figures referenced by README that do not exist")
    if README.exists():
        text = README.read_text(encoding="utf-8")
        refs = set(re.findall(r"(?:!\[[^\]]*\]\(|src=\")([^)\"]+\.(?:png|pdf|svg))",
                              text))
        if not refs:
            report(WARN, "README references no images at all")
        for r in sorted(refs):
            p = (ROOT / r).resolve()
            if p.exists():
                report(PASS, f"{r}")
            else:
                report(FAIL, f"{r} is referenced but not on disk")


# --------------------------------------------------------------------------
def trace_docs(index):
    """The same tracing over docs/index.html.

    That page is hand-written and nothing regenerates it, so a number
    corrected in the README stays wrong there until somebody notices. It is
    what GitHub Pages serves, so it is the first thing a reader sees. Only
    numbers written with thousands separators are traced, which is the class
    that carries hectares and keeps the false-positive rate near zero.
    """
    head("A2. EVERY NUMBER ON docs/index.html, TRACED TO A FILE")
    p = ROOT / "docs" / "index.html"
    if not p.exists():
        report(WARN, "docs/index.html not found")
        return

    s = p.read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"<script\b.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style\b.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)

    traced, untraced = 0, []
    for raw in re.findall(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", s):
        txt = raw.replace(",", "")
        x = float(txt)
        dec = len(txt.split(".")[1]) if "." in txt else 0
        if find(x, dec, index, extra_tol=0.0005):
            traced += 1
        else:
            untraced.append(raw)

    print(f"  \u00b7 {traced} numbers matched a value in results/")
    if untraced:
        report(WARN, f"{len(untraced)} number(s) on the public page match no "
                     f"file: {', '.join(sorted(set(untraced)))}")
        print("        build_docs_page.py generates the figures and the "
              "district table, so")
        print("        an unmatched number is in the prose. Check it against "
              "the analysis")
        print("        it cites, not against whatever else happens to be in "
              "results/.")
    else:
        report(PASS, "every number on the public page traces to results/")
    print("        A match means some file in results/ holds that value, not "
          "that it is")
    print("        the right value. The misses are the strong signal.")


def main() -> None:
    print("VERIFICATION REPORT")
    print(f"project: {ROOT}")
    print("read-only; nothing in the repo is modified\n")

    index = build_index()
    print(f"indexed {len(index)} numeric values from results/\n")

    trace_readme(index)
    trace_docs(index)

    head("B. INTERNAL CONSISTENCY")
    for fn in (check_scene_vs_districts, check_raw_vs_refined,
               check_slope_histogram, check_sensitivity_published,
               check_config_vs_run, check_change_arithmetic,
               check_accuracy_headline, check_change_sweep_peak,
               check_products, check_orbit, check_imaged_area):
        try:
            fn()
        except Exception as e:                                 # noqa: BLE001
            report(FAIL, f"{fn.__name__} crashed: {type(e).__name__}: {e}")

    try:
        check_hardcoded()
    except Exception as e:                                     # noqa: BLE001
        report(FAIL, f"check_hardcoded crashed: {type(e).__name__}: {e}")

    try:
        check_figures()
    except Exception as e:                                     # noqa: BLE001
        report(FAIL, f"check_figures crashed: {type(e).__name__}: {e}")

    head("SUMMARY")
    print(f"  {n_fail} failures")
    print(f"  {n_warn} warnings")
    print("\nA warning is not automatically a problem. It is a place where "
          "this script\ncannot decide on its own and a person has to. A "
          "failure is a contradiction\nbetween two files that both claim to "
          "describe the same thing.")


if __name__ == "__main__":
    main()
