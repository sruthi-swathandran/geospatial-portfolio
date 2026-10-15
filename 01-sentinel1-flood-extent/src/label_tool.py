"""
RS-01 / validation. A small window for labelling the accuracy sample, one chip
at a time, with the keyboard.

It shows each chip from data/validation/chips and writes your answer to
results/validation/sample/labels.csv after every point, so you can stop at any time and pick up where
you left off. It never opens points_key.csv, so it cannot show the stratum or
the map class.

Keys
----
  W  open water        V  water through vegetation
  N  not water         C  cannot tell
  then 1, 2 or 3 for confidence: sure, fairly sure, a guess
  M  type a note in the terminal window, then press Enter there
  B  back to the previous point, to change it
  Q  save and quit

The rules for choosing a label are in LABELLING.txt beside labels.csv.

Simple mode
-----------
If the window does not open or ignores the keys, --simple works without it.
Each chip opens in the Windows image viewer, and you type the answer in the
command window: a letter and a number together, such as W1 or n2, then Enter.
Add a note after a space, such as "V2 edge of a paddy". B goes back, Q quits.

Usage
-----
    python src\\label_tool.py              # starts at the first unlabelled point
    python src\\label_tool.py --at P0120   # starts at a given point
    python src\\label_tool.py --simple     # no window; type answers instead
    python src\\label_tool.py --sheet second\\sheet_person.csv --chips second_chips
                                          # a second labelling, see second_label.py
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, RESULTS                 # noqa: E402

SAMPLE = RESULTS / "validation" / "sample"
SHEET = SAMPLE / "labels.csv"
CHIPS = DATA / "validation" / "chips"

LABELS = {"w": "W", "v": "V", "n": "N", "c": "C"}
NAMES = {"W": "open water", "V": "water through vegetation",
         "N": "not water", "C": "cannot tell"}
CONF = {"1": "sure", "2": "fairly sure", "3": "a guess"}

# matplotlib binds many single letters (c, v, q, ...) to its own actions
for key in [k for k in plt.rcParams if k.startswith("keymap.")]:
    plt.rcParams[key] = []


class Labeller:
    def __init__(self, rows, fields, start):
        self.rows, self.fields, self.i = rows, fields, start
        self.pending = None
        self.fig = plt.figure(figsize=(14, 6.2))
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.show()

    # ------------------------------------------------------------ display
    def done(self):
        return sum(1 for r in self.rows if r["label"].strip())

    def show(self):
        self.fig.clf()
        r = self.rows[self.i]
        chip = CHIPS / f"{r['point_id']}.png"
        ax = self.fig.add_axes([0, 0.12, 1, 0.88])
        ax.axis("off")
        if chip.exists():
            ax.imshow(plt.imread(chip))
        else:
            ax.text(0.5, 0.5, f"no chip for {r['point_id']}; label it C",
                    ha="center", va="center", fontsize=14)
        now = (f"current: {r['label']} {NAMES.get(r['label'], '')}, "
               f"confidence {r['confidence'] or '-'}" if r["label"] else
               "not labelled yet")
        step = (f"pressed {self.pending}: now 1, 2 or 3 for confidence"
                if self.pending else "W  V  N  C, then 1  2  3")
        self.fig.text(0.01, 0.065, f"{r['point_id']}   point {self.i + 1} of "
                      f"{len(self.rows)}   {self.done()} labelled   |   {now}",
                      fontsize=11)
        self.fig.text(0.01, 0.02, f"{step}     M note   B back   Q quit"
                      + (f"     note: {r['note']}" if r["note"] else ""),
                      fontsize=11, color="#1f4e79")
        if self.pending:
            self.fig.text(0.80, 0.05, f"{self.pending}  {NAMES[self.pending]}:"
                          "  now press 1, 2 or 3", ha="center", va="center",
                          fontsize=15, color="white", weight="bold",
                          bbox=dict(facecolor="#1f4e79", alpha=0.9,
                                    boxstyle="round,pad=0.6"))
        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------- input
    def on_key(self, event):
        k = (event.key or "").lower()
        print(f"  key {k or '?'} on {self.rows[self.i]['point_id']}", flush=True)
        if k in LABELS:
            self.pending = LABELS[k]
        elif k in CONF and self.pending:
            r = self.rows[self.i]
            r["label"], r["confidence"] = self.pending, k
            self.pending = None
            self.save()
            if self.i < len(self.rows) - 1:
                self.i += 1
            else:
                print("That was the last point.")
        elif k == "b" and self.i > 0:
            self.pending = None
            self.i -= 1
        elif k == "m":
            r = self.rows[self.i]
            print(f"\nNote for {r['point_id']} (Enter to keep "
                  f"'{r['note']}'): ", end="", flush=True)
            text = sys.stdin.readline().strip()
            if text:
                r["note"] = text.replace(",", ";")
                self.save()
        elif k == "q":
            self.save()
            plt.close(self.fig)
            return
        self.show()

    def save(self):
        save_rows(self.rows, self.fields)


def save_rows(rows, fields):
    tmp = SHEET.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, SHEET)


def open_image(path):
    if hasattr(os, "startfile"):
        os.startfile(path)                     # Windows: the default viewer
    else:
        print(f"  open {path} to see the chip")


def simple(rows, fields, start):
    """Type each answer in the command window; no matplotlib window."""
    print("\nType a letter and a number, such as W1, then Enter. "
          "B back, Q quit.\n")
    i = start
    while 0 <= i < len(rows):
        r = rows[i]
        chip = CHIPS / f"{r['point_id']}.png"
        if chip.exists():
            open_image(chip)
        now = f" (now {r['label']}{r['confidence']})" if r["label"] else ""
        done = sum(1 for x in rows if x["label"].strip())
        ans = input(f"{r['point_id']}  {i + 1} of {len(rows)}, {done} labelled"
                    f"{now}: ").strip()
        if not ans:
            continue
        head, _, note = ans.partition(" ")
        head = head.upper()
        if head == "Q":
            break
        if head == "B":
            i = max(0, i - 1)
            continue
        if len(head) != 2 or head[0] not in "WVNC" or head[1] not in "123":
            print("  type a letter W, V, N or C and a number 1, 2 or 3, "
                  "such as W1")
            continue
        r["label"], r["confidence"] = head[0], head[1]
        if note:
            r["note"] = note.replace(",", ";")
        save_rows(rows, fields)
        i += 1
    if i >= len(rows):
        print("That was the last point.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", help="point id to start at, such as P0120")
    ap.add_argument("--sheet", help="sheet under results/validation, "
                    "default sample/labels.csv")
    ap.add_argument("--chips", help="chip folder under data/validation, "
                    "default chips")
    ap.add_argument("--simple", action="store_true",
                    help="no window; type each answer in the command window")
    args = ap.parse_args()
    global SHEET, CHIPS
    if args.sheet:
        SHEET = RESULTS / "validation" / Path(args.sheet)
    if args.chips:
        CHIPS = DATA / "validation" / args.chips

    if not SHEET.exists():
        sys.exit(f"missing {SHEET}; run draw_sample.py first")
    with open(SHEET, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)
    for r in rows:
        for f in ("label", "confidence", "note"):
            r[f] = r.get(f) or ""

    if args.at:
        ids = [r["point_id"] for r in rows]
        if args.at not in ids:
            sys.exit(f"{args.at} is not in labels.csv")
        start = ids.index(args.at)
    else:
        start = next((i for i, r in enumerate(rows) if not r["label"].strip()),
                     len(rows) - 1)

    print(f"{sum(1 for r in rows if r['label'].strip())} of {len(rows)} "
          f"labelled; starting at {rows[start]['point_id']}.")
    backend = matplotlib.get_backend().lower()
    if args.simple or "agg" == backend or backend.endswith("inline"):
        if not args.simple:
            print(f"matplotlib cannot open a window here (backend {backend}); "
                  "switching to simple mode.")
        simple(rows, fields, start)
        print(f"Saved to {SHEET}.")
        return
    print(f"matplotlib backend {backend}. Click the image window once so it "
          "receives the keys.")
    Labeller(rows, fields, start)
    plt.show()
    print(f"Saved to {SHEET}.")


if __name__ == "__main__":
    main()
