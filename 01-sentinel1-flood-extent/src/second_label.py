"""
RS-01 / validation. Set up a second, independent labelling of part of the
sample, to measure how much the results depend on who makes the calls.

Every label so far came from one interpreter. This script picks two sets of
points for a second reader:

  uncertain   every point the first reader marked as a guess, confidence 3,
              outside permanent water and leaving out C. These are the calls
              most likely to swing the open-water figure.
  random      40 more drawn at random from the rest, so that agreement can be
              measured fairly. Agreement on hard points alone would understate
              it.

The two sets are mixed and renumbered R001 onward in random order, so a reader
cannot tell which set a point came from, and the first reader's labels are not
in anything the second reader sees.

Outputs
-------
Under results/validation/second/, committed:
  relabel_key.csv        R number, original point and set; keep it from the
                         second reader until they finish
  sheet_person.csv       the sheet for a second person
  sheet_claude.csv       the sheet for Claude, labelled separately
Under data/validation/second_chips/, not committed:
  R001.png onward        the same chips under their new numbers
data/validation/second_labeller_pack.zip, not committed:
  the chips, an empty sheet and LABELLING.txt, for a person labelling on
  another computer

Usage
-----
    python src\\second_label.py

Run once; it refuses if the key exists. Then label with
    python src\\label_tool.py --sheet second\\sheet_person.csv --chips second_chips
and compare with compare_labels.py once both sheets are full.
"""

from __future__ import annotations

import csv
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, RESULTS                                  # noqa: E402

SEED = 20261016
N_RANDOM = 40
SAMPLE = RESULTS / "validation" / "sample"
SECOND = RESULTS / "validation" / "second"
CHIPS = DATA / "validation" / "chips"
SECOND_CHIPS = DATA / "validation" / "second_chips"
PACK = DATA / "validation" / "second_labeller_pack.zip"

HOWTO = """\
Second labelling, RS-01 flood check

Thank you for helping. Each image shows one point. Label the 20 m cell inside
the small yellow square, following LABELLING.txt, and write your answer in
sheet.csv: a letter in the label column and a number in the confidence column.

  W  open water        V  water seen through vegetation
  N  not water         C  cannot tell
  1  sure              2  fairly sure          3  a guess

Please label from the images alone, without looking up the place on a map, and
send sheet.csv back when every row is filled.
"""


def main():
    SECOND.mkdir(parents=True, exist_ok=True)
    key_path = SECOND / "relabel_key.csv"
    if key_path.exists():
        sys.exit(f"{key_path} exists; a second labelling is already set up")

    with open(SAMPLE / "points_key.csv", encoding="utf-8") as fh:
        key = {r["point_id"]: r for r in csv.DictReader(fh)}
    with open(SAMPLE / "labels.csv", encoding="utf-8") as fh:
        labels = {r["point_id"]: r for r in csv.DictReader(fh)}

    uncertain = sorted(pid for pid, r in labels.items()
                       if r["confidence"] == "3" and r["label"] in ("W", "V", "N")
                       and key[pid]["stratum"] != "permanent water")
    rest = sorted(pid for pid in labels if pid not in set(uncertain))
    rng = np.random.default_rng(SEED)
    random_pick = sorted(rng.choice(rest, size=N_RANDOM, replace=False).tolist())

    chosen = [(pid, "uncertain") for pid in uncertain] + \
             [(pid, "random") for pid in random_pick]
    order = rng.permutation(len(chosen))
    chosen = [chosen[i] for i in order]

    SECOND_CHIPS.mkdir(parents=True, exist_ok=True)
    rows_key, rows_sheet, missing = [], [], []
    for n, (pid, which) in enumerate(chosen, 1):
        rid = f"R{n:03d}"
        src = CHIPS / f"{pid}.png"
        if src.exists():
            shutil.copyfile(src, SECOND_CHIPS / f"{rid}.png")
        else:
            missing.append(pid)
        rows_key.append(dict(relabel_id=rid, point_id=pid, set=which))
        rows_sheet.append(dict(point_id=rid, lon=key[pid]["lon"], lat=key[pid]["lat"],
                               label="", confidence="", note=""))

    with open(key_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["relabel_id", "point_id", "set"])
        w.writeheader()
        w.writerows(rows_key)
    for name in ("sheet_person.csv", "sheet_claude.csv"):
        with open(SECOND / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_sheet[0]))
            w.writeheader()
            w.writerows(rows_sheet)

    with zipfile.ZipFile(PACK, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows_sheet:
            p = SECOND_CHIPS / f"{r['point_id']}.png"
            if p.exists():
                z.write(p, f"chips/{p.name}")
        z.write(SECOND / "sheet_person.csv", "sheet.csv")
        z.write(SAMPLE / "LABELLING.txt", "LABELLING.txt")
        z.writestr("HOW_TO.txt", HOWTO)

    print(f"  {len(uncertain)} uncertain and {len(random_pick)} random points, "
          f"{len(chosen)} in all, numbered R001 to R{len(chosen):03d}")
    if missing:
        print(f"  no chip for {', '.join(missing)}; run draw_sample.py --chips-only")
    print(f"  wrote {key_path}")
    print(f"  wrote {SECOND / 'sheet_person.csv'} and {SECOND / 'sheet_claude.csv'}")
    print(f"  wrote {PACK}")


if __name__ == "__main__":
    main()
