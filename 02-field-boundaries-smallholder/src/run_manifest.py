"""
RS-02. What produced the numbers in results/, recorded where they live.

F-15 in REVIEW.md: no run manifest anywhere, two seeds with no recorded reason,
and nothing tying a results file to the interpreter or package versions that
wrote it. That last part turned out to matter. Python leaves compiled copies of
each module it imports, and `src/__pycache__` shows both 3.11 and 3.14 loading
this code in the same week, because typing `python` outside the project's
.venv runs a system 3.14. Some files written between 21 and 23 September may
have come from either.

This writes results/run_manifest.json, which records:

    the git commit and whether the working tree had uncommitted changes
    the interpreter's path and version
    every package pinned in requirements.txt, with the installed version and
        whether the two match
    the SHA-256 of every checkpoint in models/, which git does not carry
    every seed set in src/, with the script and line it is set on
    every output under results/ and figures/: for a CSV, its row count and a
        hash of each column's text; for anything else, a hash of the file

Hashing columns one at a time is what makes the compare mode useful. Run the
manifest, rerun a script, run it again with --compare, and it says file by
file whether the rerun reproduced the old output exactly, changed a value, or
only added or dropped a column. Comparing text and not parsed numbers is
deliberate: a file that rounds differently is a different file.

    python src\\run_manifest.py
    python src\\run_manifest.py --out ..\\manifest_before.json
    python src\\run_manifest.py --compare ..\\manifest_before.json
    python src\\run_manifest.py --skip-checkpoints

Run it from inside the project's .venv. It records whatever interpreter runs
it, so run from the wrong one it will say so.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

PROJECT = Path(__file__).resolve().parent.parent
RULE = "=" * 78
PIN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#]+)")
SEED = re.compile(r"""(?:"--seed".*default=(\d+))|(?:default_rng\((\d+)\))"""
                  r"""|(?:seed:\s*int\s*=\s*(\d+))|(?:random_state=(\d+))""")
CSV_FIELD_LIMIT = 2 ** 31 - 1


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def git_state() -> dict:
    def run(*args):
        r = subprocess.run(["git", "-C", str(PROJECT), *args],
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    commit = run("rev-parse", "HEAD")
    dirty = run("status", "--porcelain", "--", ".")
    return {"commit": commit,
            "uncommitted_changes": None if dirty is None else bool(dirty)}


def interpreter() -> dict:
    return {"executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "in_project_venv": ".venv" in Path(sys.executable).parts}


def packages() -> list:
    from importlib import metadata
    req = PROJECT / "requirements.txt"
    rows = []
    if not req.exists():
        return rows
    for line in req.read_text(encoding="utf-8").splitlines():
        m = PIN.match(line)
        if not m:
            continue
        name, pinned = m.group(1), m.group(2)
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        # torch ships as 2.14.0+cpu against a pin of 2.14.0
        base = installed.split("+")[0] if installed else None
        rows.append({"name": name, "pinned": pinned, "installed": installed,
                     "match": base == pinned})
    return rows


def checkpoints(skip: bool) -> list:
    rows = []
    for p in sorted((PROJECT / "models").glob("*")):
        if not p.is_file():
            continue
        row = {"file": p.name, "bytes": p.stat().st_size}
        if not skip:
            row["sha256"] = sha256_file(p)
        rows.append(row)
    return rows


def seeds() -> list:
    rows = []
    for p in sorted((PROJECT / "src").glob("*.py")):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for m in SEED.finditer(line):
                value = next(g for g in m.groups() if g)
                rows.append({"script": p.name, "line": n, "value": int(value)})
    return rows


def describe_csv(path: Path) -> dict:
    csv.field_size_limit(CSV_FIELD_LIMIT)
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return {"kind": "csv", "rows": 0, "columns": {}}
        hashes = [hashlib.sha256() for _ in header]
        rows = 0
        for rec in reader:
            rows += 1
            for i, h in enumerate(hashes):
                h.update((rec[i] if i < len(rec) else "").encode("utf-8"))
                h.update(b"\n")
    return {"kind": "csv", "rows": rows,
            "columns": {c: h.hexdigest() for c, h in zip(header, hashes)}}


def outputs() -> dict:
    out = {}
    roots = [PROJECT / "results", PROJECT / "figures"]
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(PROJECT).as_posix()
            if "/pred_" in rel or rel.endswith("run_manifest.json"):
                continue
            if p.suffix.lower() == ".csv":
                out[rel] = describe_csv(p)
            else:
                out[rel] = {"kind": "file", "sha256": sha256_file(p)}
    return out


def build(skip_checkpoints: bool) -> dict:
    return {
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "interpreter": interpreter(),
        "packages": packages(),
        "checkpoints": checkpoints(skip_checkpoints),
        "seeds": seeds(),
        "outputs": outputs(),
    }


def compare(old: dict, new: dict) -> int:
    """Print what changed between two manifests. Returns files that differ."""
    a, b = old["outputs"], new["outputs"]
    same, cols_only, changed = [], [], []
    for name in sorted(set(a) & set(b)):
        x, y = a[name], b[name]
        if x["kind"] != y["kind"]:
            changed.append((name, "kind changed"))
        elif x["kind"] == "file":
            (same if x["sha256"] == y["sha256"] else changed).append(
                (name, "" if x["sha256"] == y["sha256"] else "bytes differ"))
        else:
            common = set(x["columns"]) & set(y["columns"])
            diff = sorted(c for c in common
                          if x["columns"][c] != y["columns"][c])
            gone = sorted(set(x["columns"]) - set(y["columns"]))
            new_c = sorted(set(y["columns"]) - set(x["columns"]))
            if x["rows"] != y["rows"] or diff:
                why = (f"rows {x['rows']} to {y['rows']}"
                       if x["rows"] != y["rows"] else
                       "values differ in " + ", ".join(diff))
                changed.append((name, why))
            elif gone or new_c:
                note = []
                if gone:
                    note.append("dropped " + ", ".join(gone))
                if new_c:
                    note.append("added " + ", ".join(new_c))
                cols_only.append((name, "; ".join(note)))
            else:
                same.append((name, ""))

    print(RULE)
    print("COMPARED WITH THE EARLIER MANIFEST")
    print(RULE)
    oi, ni = old["interpreter"], new["interpreter"]
    print(f"  then  Python {oi['version']}  {oi['executable']}")
    print(f"  now   Python {ni['version']}  {ni['executable']}\n")
    print(f"  {len(same)} output(s) identical")
    print(f"  {len(cols_only)} identical in every shared column, "
          f"with columns added or dropped")
    for n, why in cols_only:
        print(f"      {n}: {why}")
    print(f"  {len(changed)} output(s) changed")
    for n, why in changed:
        print(f"      {n}: {why}")
    only_old = sorted(set(a) - set(b))
    only_new = sorted(set(b) - set(a))
    if only_old:
        print(f"  {len(only_old)} gone since: " + ", ".join(only_old))
    if only_new:
        print(f"  {len(only_new)} new since: " + ", ".join(only_new))
    return len(changed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="",
                    help="where to write, default results/run_manifest.json")
    ap.add_argument("--compare", default="",
                    help="an earlier manifest to compare the outputs against")
    ap.add_argument("--skip-checkpoints", action="store_true",
                    help="list checkpoints without hashing them")
    args = ap.parse_args()

    man = build(args.skip_checkpoints)
    out = Path(args.out) if args.out else PROJECT / "results" / "run_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(man, indent=1), encoding="utf-8")

    print(RULE)
    print("RUN MANIFEST")
    print(RULE)
    it = man["interpreter"]
    print(f"  Python {it['version']}  {it['executable']}")
    if not it["in_project_venv"]:
        print("  NOT the project's .venv. Activate it and run again.")
    g = man["git"]
    print(f"  git {g['commit'] or 'unavailable'}"
          f"{', uncommitted changes' if g['uncommitted_changes'] else ''}")
    bad = [p for p in man["packages"] if not p["match"]]
    print(f"  {len(man['packages'])} pinned packages, "
          f"{len(bad)} not at their pin")
    for p in bad:
        print(f"      {p['name']}: pinned {p['pinned']}, "
              f"installed {p['installed']}")
    for c in man["checkpoints"]:
        tail = c.get("sha256", "not hashed")[:16]
        print(f"  {c['file']:<24} {c['bytes'] / 1e6:>8.0f} MB  {tail}")
    print(f"  {len(man['seeds'])} seed(s) in src: " + ", ".join(
        f"{s['script']} {s['value']}" for s in man["seeds"]))
    print(f"  {len(man['outputs'])} outputs recorded")
    print(f"\n  wrote {out}")

    if args.compare:
        old = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        print()
        n = compare(old, man)
        print("\n" + RULE)
        if n == 0:
            print("Nothing that was rerun changed a value. Those outputs do not")
            print("depend on which interpreter wrote them the first time.")
        else:
            print("Something changed. Each file listed above needs explaining")
            print("before the numbers in it are quoted again.")
        print(RULE)


if __name__ == "__main__":
    main()
