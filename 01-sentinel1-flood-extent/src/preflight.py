"""
RS-01 / pre-commit check.

Everything that should be true before this repository becomes public, verified
rather than assumed. Nine groups of checks: syntax, configuration consistency,
required files, leftover scratch files, secrets and machine-specific paths,
number traceability from the README back to generated artefacts, file sizes,
manifest freshness, and unfilled placeholders.

Number traceability is the one that matters most. Every headline figure in the
README is recomputed here from the CSV or JSON that produced it and compared
against the text. A README that has drifted from its own results is the most
likely failure and the least visible one.

Exit code is 0 only if nothing FAILED. Warnings do not block.

Usage:
    python src\\preflight.py
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 01-sentinel1-flood-extent
REPO = ROOT.parent                                     # geospatial-portfolio
SRC, RESULTS, DATA, DOCS = ROOT / "src", ROOT / "results", ROOT / "data", ROOT / "docs"

fails: list[str] = []
warns: list[str] = []
oks = 0


def ok(msg):
    global oks
    oks += 1
    print(f"  PASS  {msg}")


def fail(msg):
    fails.append(msg)
    print(f"  FAIL  {msg}")


def warn(msg):
    warns.append(msg)
    print(f"  warn  {msg}")


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def money(x) -> str:
    return f"{round(float(x)):,}"


# ------------------------------------------------------------------ 1 syntax
head("1. Every script parses")
bad = 0
for f in sorted(SRC.glob("*.py")):
    try:
        ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError as e:
        fail(f"{f.name} line {e.lineno}: {e.msg}")
        bad += 1
if not bad:
    ok(f"{len(list(SRC.glob('*.py')))} files parse")

# ----------------------------------------------------------- 2 config values
head("2. config.py matches what the documents claim")
cfg = {}
try:
    tree = ast.parse((SRC / "config.py").read_text(encoding="utf-8"))
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            try:
                cfg[n.targets[0].id] = ast.literal_eval(n.value)
            except Exception:
                pass
except Exception as e:                                  # noqa: BLE001
    fail(f"could not read config.py: {e}")

for k, want in (("SLOPE_MAX_DEG", 8.0), ("GSW_PERMANENT_MIN", 50),
                ("EDGE_BUFFER_PX", 30), ("MIN_OBJECT_PX_SCENE", 10),
                ("TARGET_CRS", "EPSG:32646")):
    got = cfg.get(k, "<missing>")
    (ok if got == want else fail)(f"{k} = {got!r} (expected {want!r})")

if isinstance(cfg.get("RESAMPLING"), dict):
    missing = {"sar", "dem", "occurrence", "landcover"} - set(cfg["RESAMPLING"])
    (ok if not missing else fail)(
        f"RESAMPLING declares all four variables"
        + (f", missing {sorted(missing)}" if missing else ""))
else:
    fail("RESAMPLING table missing from config.py")

# --------------------------------------------------------- 3 required files
head("3. Required files present")
required = [
    (ROOT / "README.md", "README"),
    (ROOT / "CHANGELOG.md", "changelog"),
    (ROOT / "REVIEW.md", "audit findings"),
    (ROOT / "MANIFEST.csv", "manifest"),
    (ROOT / "MANIFEST_files.csv", "manifest digests"),
    (DOCS / "index.html", "interactive map"),
    (RESULTS / "figures" / "flood_extent_map.png", "publication map, raster"),
    (RESULTS / "figures" / "flood_extent_map.pdf", "publication map, vector"),
    (RESULTS / "final_method.json", "settled method"),
    (REPO / "LICENSE", "licence"),
    (REPO / "requirements.txt", "minimal requirements"),
    (REPO / "requirements-lock.txt", "environment lock"),
]
for p, what in required:
    (ok if p.exists() else fail)(f"{what}: {p.relative_to(REPO)}")

# --------------------------------------------------------------- 4 leftovers
head("4. No scratch files left behind")
for p in (SRC / "apply_threedate_update.py", REPO / "commit_msg.txt",
          SRC / "preflight.py"):
    if p.exists():
        warn(f"still present, delete before or after committing: "
             f"{p.relative_to(REPO)}")
for p in ROOT.rglob("*"):
    if p.is_file() and p.suffix in {".tmp", ".bak", ".orig"}:
        warn(f"temporary file: {p.relative_to(REPO)}")
if not warns:
    ok("nothing stray found")

# ------------------------------------------------- 5 secrets and local paths
head("5. No secrets, tokens or machine-specific paths in text files")
patterns = [
    (r"[A-Za-z0-9+/]{40,}={0,2}\s*$", "long base64-looking string"),
    (r"\bsig=[A-Za-z0-9%]{20,}", "SAS signature"),
    (r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY", "private key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)"
     r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address"),
    (r"[A-Za-z]:\\\\?Users\\\\?", "Windows user path"),
    (r"/mnt/user-data", "sandbox path"),
    (r"D:\\\\geospatial-portfolio", "absolute local path"),
]
scanned = 0
hits = 0
SELF = Path(__file__).resolve()
for p in list(SRC.glob("*.py")) + list(ROOT.glob("*.md")) + [DOCS / "index.html"]:
    if not p.exists() or p.resolve() == SELF:
        continue          # this file carries the patterns it searches for
    scanned += 1
    txt = p.read_text(encoding="utf-8", errors="ignore")
    for line_no, line in enumerate(txt.splitlines(), 1):
        if len(line) > 400:          # embedded data, not prose
            continue
        for rx, what in patterns:
            if re.search(rx, line):
                fail(f"{what} in {p.relative_to(REPO)}:{line_no}")
                hits += 1
if not hits:
    ok(f"{scanned} text files clean")

# --------------------------------------------------- 6 number traceability
head("6. Every headline number traces to a generated artefact")
readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""


def check_in_readme(value, label, source):
    s = money(value)
    (ok if s in readme else fail)(f"{label} {s} ha  <- {source}")


def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# full_scene.py writes its stats BEFORE refine_scene.py runs, so "flood_ha" in
# these files is the RAW threshold output and "refined.flood_ha_after" is the
# reported figure. An earlier version of this script compared the raw number
# and passed, because 217,490 does appear in the README, in the subtraction
# chain. Checking the wrong field is exactly the drift this section exists to
# catch, so both are now checked and labelled.
MAPS = [
    ("20m", "12 Aug, map-optimal"),
    ("20m_areamatched", "12 Aug, area-matched"),
    ("20m_20160807", "7 Aug, map-optimal"),
    ("20m_20160807am", "7 Aug, area-matched"),
    ("20m_20160831", "31 Aug, map-optimal"),
    ("20m_20160831am", "31 Aug, area-matched"),
]
for tag, label in MAPS:
    j = load_json(RESULTS / f"fullscene_stats_{tag}.json")
    if j is None:
        fail(f"fullscene_stats_{tag}.json missing")
        continue
    if "refined" not in j:
        fail(f"{tag}: no 'refined' block; refine_scene.py has not been run "
             f"with --apply on this variant")
        continue
    check_in_readme(j["refined"]["flood_ha_after"],
                    f"flood after refinement, {label}",
                    f"fullscene_stats_{tag}.json refined.flood_ha_after")

raw = load_json(RESULTS / "fullscene_stats_20m.json")
if raw:
    check_in_readme(raw["flood_ha"], "raw threshold output before refinement",
                    "fullscene_stats_20m.json flood_ha")


def crop_total(name):
    p = RESULTS / name
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return sum(float(r["flooded_cropland_ha"]) for r in csv.DictReader(fh))


for suffix, label in (("", "12 Aug, map-optimal"),
                      ("_areamatched", "12 Aug, area-matched"),
                      ("_20160807", "7 Aug, map-optimal"),
                      ("_20160807am", "7 Aug, area-matched"),
                      ("_20160831", "31 Aug, map-optimal"),
                      ("_20160831am", "31 Aug, area-matched")):
    name = f"district_flood_stats{suffix}.csv"
    t = crop_total(name)
    if t is None:
        fail(f"{name} missing")
    else:
        check_in_readme(t, f"flooded cropland, {label}", name)

acc = RESULTS / "accuracy_ci.csv"
if acc.exists():
    rows = {r["split"]: r for r in csv.DictReader(acc.read_text().splitlines())}
    a = rows.get("all")
    if a:
        for v, what in ((a["iou"], "IoU"), (a["iou_ci_lo"], "CI low"),
                        (a["iou_ci_hi"], "CI high")):
            s = f"{float(v):.3f}"
            (ok if s in readme else fail)(f"accuracy {what} {s} <- accuracy_ci.csv")
    else:
        fail("accuracy_ci.csv has no 'all' row")
else:
    fail("accuracy_ci.csv missing")

sg = RESULTS / "sensitivity_grid.csv"
if sg.exists():
    pub = [r for r in csv.DictReader(sg.read_text().splitlines())
           if r["is_published"] == "1"]
    if pub:
        check_in_readme(pub[0]["flood_ha"], "sensitivity published cell",
                        "sensitivity_grid.csv")
    else:
        warn("sensitivity_grid.csv has no row flagged as published")
else:
    warn("sensitivity_grid.csv missing")

fm = load_json(RESULTS / "final_method.json")
if fm:
    thr = fm["operating_points"]["max_iou"]["threshold"]
    (ok if f"{thr:.2f}" in readme or f"{abs(thr):.2f}" in readme else fail)(
        f"operating threshold {thr:.2f} dB <- final_method.json")

# ---------------------------------------------------------------- 7 sizes
head("7. Nothing too large to commit")
gi = (REPO / ".gitignore").read_text(encoding="utf-8") if (REPO / ".gitignore").exists() else ""
(ok if re.search(r"^data/", gi, re.M) else fail)(".gitignore excludes data/")
(ok if "results/**/*.tif" in gi else warn)(".gitignore excludes result rasters")

big = []
for p in ROOT.rglob("*"):
    if not p.is_file() or "__pycache__" in p.parts:
        continue
    rel = p.relative_to(ROOT).as_posix()
    if rel.startswith("data/") or p.suffix in {".tif", ".tiff"}:
        continue
    mb = p.stat().st_size / 1e6
    if mb > 45:
        big.append((mb, rel))
if big:
    for mb, rel in sorted(big, reverse=True):
        fail(f"{mb:.0f} MB and not ignored: {rel}")
else:
    ok("no committable file over 45 MB")

# ------------------------------------------------------- 8 manifest current
head("8. Manifest matches the files on disk")
mf = ROOT / "MANIFEST_files.csv"
if not mf.exists():
    fail("MANIFEST_files.csv missing, run make_manifest.py")
else:
    stale = missing = 0
    for r in csv.DictReader(mf.read_text(encoding="utf-8").splitlines()):
        p = ROOT / r["path"]
        if not p.exists():
            missing += 1
            continue
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest() != r["sha256"]:
            stale += 1
    if missing:
        fail(f"{missing} manifest entries no longer exist")
    if stale:
        fail(f"{stale} files changed since the manifest was written, "
             f"re-run make_manifest.py")
    if not missing and not stale:
        ok("every digested artefact matches")

# ------------------------------------------------------------ 9 placeholders
head("9. Placeholders")
ph = []
for p in list(ROOT.glob("*.md")) + list(SRC.glob("*.py")) + [DOCS / "index.html"]:
    if not p.exists() or p.resolve() == SELF:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8",
                                         errors="ignore").splitlines(), 1):
        if "<user>" in line or "YOURNAME" in line or "YOUR-ID" in line:
            ph.append(f"{p.relative_to(REPO)}:{i}")
if ph:
    for x in ph:
        warn(f"unfilled placeholder at {x}")
else:
    ok("no placeholders left")

# ------------------------------------------------------------------ verdict
print("\n" + "=" * 62)
print(f"{oks} passed, {len(warns)} warnings, {len(fails)} failures")
if fails:
    print("\nFAILURES, fix before committing:")
    for f_ in fails:
        print(f"  - {f_}")
if warns:
    print("\nWarnings, judgement calls:")
    for w in warns:
        print(f"  - {w}")
if not fails:
    print("\nNothing blocking. The warnings above are yours to decide on.")
sys.exit(1 if fails else 0)
