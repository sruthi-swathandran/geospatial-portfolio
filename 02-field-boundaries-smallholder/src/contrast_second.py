"""
RS-02. A second analyst on the contrast panel, and a third panel for the first.

F-14 in REVIEW.md. One analyst, the author, judged two blind panels of 20
Indian parcels, and the contrast measure ranked the edges she could see higher
about two times in three both times, rank scores 0.655 and 0.650, p = 0.16 and
0.14. That is one person's eye. The edge test, finding 20 of COMPARISON.md,
showed the models respond to what the measure reads. Whether the measure reads
what a person sees is still open, so this asks a second person.

What is judged
--------------
  second person  60 parcels: the 20 of panel 20260925, the 20 of panel
                 20261012, and 20 new ones drawn here, five from each quartile
                 of edge_over_interior, from parcels no earlier panel showed.
                 All in natural colour and in one shuffled order, numbered 1
                 to 60 over three images of 20, so the panel a parcel came
                 from cannot be told.
  author         the 20 new parcels, in an order of their own, numbered 1 to
                 20. Her answers on the other 40 are the ones already in
                 contrast_panel_scores.csv. Panel 20260925 was shown to her
                 with red and blue swapped (B-23), so her 40 mix two colour
                 conditions.

Each judge answers y or n per parcel through --part judge, which saves after
every answer and prints nothing about the measure. The author judges first.
--part score refuses until both sheets are full, so neither judgement is made
after seeing a result.

Rules, set before anyone judged
-------------------------------
The score is the rank score of contrast_panel.py: over every pair of one
parcel marked visible and one not, the share where the measure puts the
visible one higher. 0.5 is a coin. Its p value comes from 20,000 shuffles of
the answers.

  The primary reading is the second person's score over all 60.
    0.75 or more with p under 0.05   the measure tracks what a person sees,
                                     and F-14 closes
    0.60 or more otherwise           weak: fine as a country summary, not per
                                     parcel, and F-14 stays scoped
    below 0.60                       not tracking visibility, and the
                                     documents stop calling it contrast
  The author's score over the 20 new parcels, and over all 60 with her earlier
  answers, is reported beside it under the same bars, as secondary.
  Agreement between the two is reported as the share agreeing and Cohen's
  kappa, over all 60 and per source panel. Kappa under 0.40 is read as two
  people not sharing a standard for a visible boundary, which limits what any
  check against one eye can say.

Outputs
-------
  results/india/contrast_second_key.csv        the key, with the values the
                                               judges must not see
  results/india/contrast_second/sheet_second.csv
  results/india/contrast_second/sheet_author.csv
  figures/contrast_second/second_1.png to second_3.png, and author.png
After scoring:
  results/india/contrast_second_answers.csv    the key with both answers
  results/india/contrast_second_scores.csv
  results/india/contrast_second_agreement.csv

Usage
-----
    python src\\contrast_second.py --part draw
    python src\\contrast_second.py --part judge --who author
    python src\\contrast_second.py --part judge --who second
    python src\\contrast_second.py --part score
    python src\\contrast_second.py --part redraw

redraw draws the images again from the key, with the same parcels and numbers.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np

os.environ["FTW_COUNTRY"] = "india"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402
import contrast_panel as CP                                   # noqa: E402

RULE = "=" * 78
OLD_SEEDS = ["20260925", "20261012"]
UNSCORED_KEY = "contrast_panel_key_spent_1.csv"   # seen, never scored
N_PER_QUARTILE = 5
PER_IMAGE = 20
N_PERMUTATIONS = 20000
KAPPA_SHARED = 0.40

KEY = F.RESULTS / "contrast_second_key.csv"
SHEETS = F.RESULTS / "contrast_second"
FIGS = F.PROJECT / "figures" / "contrast_second"
SHEET = {"author": SHEETS / "sheet_author.csv",
         "second": SHEETS / "sheet_second.csv"}
WHO_NO = {"author": "author_no", "second": "second_no"}


def panel_key(seed: str):
    """The key of an earlier panel, found by its seed in any key file."""
    import pandas as pd
    for p in sorted(F.RESULTS.glob("contrast_panel_key*.csv")):
        k = pd.read_csv(p)
        if "seed" in k.columns and (k["seed"].astype(str) == seed).all():
            return k
    sys.exit(f"no contrast panel key with seed {seed} under {F.RESULTS}")


def image_name(who: str, no: int) -> str:
    if who == "author":
        return "author.png"
    return f"second_{(no - 1) // PER_IMAGE + 1}.png"


def render_all(key) -> list:
    FIGS.mkdir(parents=True, exist_ok=True)
    out = []
    s = key.sort_values("second_no")
    for i in range(0, len(s), PER_IMAGE):
        chunk = s.iloc[i:i + PER_IMAGE].assign(panel_no=lambda d: d["second_no"])
        dest = FIGS / image_name("second", int(chunk["second_no"].iloc[0]))
        out.append(CP.render(chunk, CP.NATURAL_BANDS, dest))
    a = key[key["source"] == "new"].sort_values("author_no")
    a = a.assign(panel_no=lambda d: d["author_no"].astype(int))
    out.append(CP.render(a, CP.NATURAL_BANDS, FIGS / "author.png"))
    return out


def write_sheet(path: Path, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["no", "visible"])
        w.writeheader()
        w.writerows(rows)


def read_sheet(path: Path) -> list:
    with open(path, encoding="utf-8") as fh:
        return [dict(no=r["no"], visible=(r["visible"] or "").strip().lower())
                for r in csv.DictReader(fh)]


def draw(seed: int) -> None:
    import pandas as pd
    if KEY.exists():
        sys.exit(f"{KEY.name} exists, so the panel is already drawn. "
                 "--part redraw draws its images again.")
    reg = pd.read_csv(F.RESULTS / "label_registration.csv")
    reg = reg.dropna(subset=["edge_over_interior"])

    old = []
    for s in OLD_SEEDS:
        k = panel_key(s)
        old.append(k.assign(source=s, source_no=k["panel_no"]))
    seen_keys = old + [pd.read_csv(F.RESULTS / UNSCORED_KEY)]
    seen = set()
    for k in seen_keys:
        seen |= set(zip(k["chip"], k["parcel_id"].astype(int)))
    pool = reg[[(c, int(p)) not in seen
                for c, p in zip(reg["chip"], reg["parcel_id"])]]

    rng = np.random.default_rng(seed)
    q = pd.qcut(pool["edge_over_interior"], 4, labels=False, duplicates="drop")
    new = pd.concat([pool[q == lv].sample(N_PER_QUARTILE,
                                          random_state=int(rng.integers(1e6)))
                     for lv in sorted(pd.unique(q.dropna()))])
    new = new.assign(source="new", source_no=0)

    cols = ["source", "source_no", "chip", "parcel_id", "edge_over_interior",
            "width_native_px"]
    key = pd.concat([d[cols] for d in old + [new]], ignore_index=True)
    # measured values come from label_registration.csv for every parcel; for
    # the two earlier panels they equal the values in their keys
    key = key.drop(columns="edge_over_interior").merge(
        reg[["chip", "parcel_id", "edge_over_interior"]],
        on=["chip", "parcel_id"], how="left")
    key = key.iloc[rng.permutation(len(key))].reset_index(drop=True)
    key["second_no"] = np.arange(1, len(key) + 1)
    is_new = (key["source"] == "new").to_numpy()
    author = np.zeros(len(key), dtype=int)
    author[np.flatnonzero(is_new)[rng.permutation(is_new.sum())]] = \
        np.arange(1, is_new.sum() + 1)
    key["author_no"] = pd.Series(author).astype("Int64")
    key.loc[~is_new, "author_no"] = pd.NA
    key["seed"] = seed

    paths = render_all(key)
    SHEETS.mkdir(parents=True, exist_ok=True)
    write_sheet(SHEET["second"], [dict(no=i, visible="")
                                  for i in range(1, len(key) + 1)])
    write_sheet(SHEET["author"], [dict(no=i, visible="")
                                  for i in range(1, int(is_new.sum()) + 1)])
    key[["second_no", "author_no", "source", "source_no", "chip", "parcel_id",
         "edge_over_interior", "width_native_px", "seed"]].to_csv(KEY,
                                                                  index=False)

    print(RULE)
    print(f"SECOND ANALYST PANEL, INDIA, seed {seed}")
    print(RULE)
    print(f"  {len(seen)} parcels from earlier panels left out of the new draw")
    print(f"  {len(key)} parcels for the second person, {int(is_new.sum())} "
          f"for the author")
    for p in paths:
        print(f"  wrote {p.relative_to(F.PROJECT)}")
    print(f"  wrote {SHEET['second'].relative_to(F.PROJECT)}")
    print(f"  wrote {SHEET['author'].relative_to(F.PROJECT)}")
    print(f"  wrote {KEY.relative_to(F.PROJECT)}, the key")
    print(RULE)
    print("Neither judge opens the key. The author judges first, with")
    print("    python src\\contrast_second.py --part judge --who author")
    print(RULE)


def redraw() -> None:
    import pandas as pd
    if not KEY.exists():
        sys.exit(f"{KEY.name} not found. Run --part draw first.")
    for p in render_all(pd.read_csv(KEY)):
        print(f"  wrote {p.relative_to(F.PROJECT)}")
    print("  same parcels, same numbers; the key and the sheets are untouched")


def judge(who: str) -> None:
    path = SHEET[who]
    if not path.exists():
        sys.exit(f"{path} not found. Run --part draw first.")
    rows = read_sheet(path)
    n = len(rows)
    files = sorted({image_name(who, int(r["no"])) for r in rows})

    print(RULE)
    print(f"IS THERE A BOUNDARY YOU CAN SEE? {n} parcels, judged as {who}")
    print(RULE)
    print(f"  Open {', '.join(files)} in figures\\contrast_second.")
    print("  Each parcel appears twice, plain on the left and outlined on the")
    print("  right. Use the outline to know where to look, then judge the")
    print("  plain copy: can you see a field boundary along that line?")
    print("  Answer y or n. Answer from the image alone, and when unsure,")
    print("  give the answer you lean to.")
    print("  b goes back one parcel, q stops; every answer is saved as you go.")
    print(RULE)

    i = next((k for k, r in enumerate(rows) if r["visible"] not in ("y", "n")),
             n)
    if i == n:
        print("  every parcel already has an answer. To change one, open the")
        print(f"  sheet, {path.name}, in Notepad and edit its visible column.")
        return
    while i < n:
        no = int(rows[i]["no"])
        now = rows[i]["visible"]
        hint = f" [now {now}]" if now in ("y", "n") else ""
        try:
            ans = input(f"  {no:>2} of {n}, in {image_name(who, no)}{hint}: "
                        "boundary visible? y, n, b, q: ").strip().lower()
        except EOFError:
            break
        if ans == "q":
            break
        if ans == "b":
            i = max(0, i - 1)
            continue
        if ans not in ("y", "n"):
            print("    please answer y or n")
            continue
        rows[i]["visible"] = ans
        write_sheet(path, rows)
        i += 1

    done = sum(r["visible"] in ("y", "n") for r in rows)
    print(f"\n  {done} of {n} answered, saved in "
          f"{path.relative_to(F.PROJECT)}")
    if done < n:
        print("  run the same command again to carry on where you stopped")
    else:
        print("  all answered. Close the images. Nothing about the measure was")
        print("  shown, and nothing is shown until both judges have finished.")


def kappa(a: np.ndarray, b: np.ndarray) -> tuple:
    po = float((a == b).mean())
    pa, pb = a.mean(), b.mean()
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def reading(auc: float, p: float) -> str:
    if np.isnan(auc):
        return "all marked alike, nothing to rank"
    if auc >= CP.TRACKS_AUC and p < CP.TRACKS_P:
        return "tracks what a person sees"
    if auc >= CP.WEAK_AUC:
        return "weak"
    return "not tracking visibility"


def score(seed: int, force: bool) -> None:
    import pandas as pd
    for who, path in SHEET.items():
        if not path.exists():
            sys.exit(f"{path} not found. Run --part draw first.")
        rows = read_sheet(path)
        left = sum(r["visible"] not in ("y", "n") for r in rows)
        if left:
            sys.exit(f"{who}: {left} of {len(rows)} parcels still unanswered. "
                     "Nothing was scored and nothing was shown.")
    out_scores = F.RESULTS / "contrast_second_scores.csv"
    if out_scores.exists() and not force:
        sys.exit(f"{out_scores.name} exists; this panel is scored and spent.")

    key = pd.read_csv(KEY, dtype={"source": str})
    ans = {who: {int(r["no"]): r["visible"] == "y"
                 for r in read_sheet(path)} for who, path in SHEET.items()}
    done = pd.read_csv(F.RESULTS / "contrast_panel_scores.csv",
                       dtype={"seed": str})
    earlier, recorded = {}, {}
    for s in OLD_SEEDS:
        row = done[done["seed"] == s].iloc[-1]
        earlier[s] = {int(x) for x in str(row["marked_numbers"]).split()}
        recorded[s] = float(row["rank_score"])

    key["second_visible"] = [ans["second"][int(x)] for x in key["second_no"]]
    key["author_visible"] = [
        ans["author"][int(a)] if s == "new" else int(n) in earlier[s]
        for s, n, a in zip(key["source"], key["source_no"], key["author_no"])]
    key.to_csv(F.RESULTS / "contrast_second_answers.csv", index=False)

    subsets = [("all 60", np.ones(len(key), bool))] + [
        (f"panel {s}", (key["source"] == s).to_numpy()) for s in OLD_SEEDS] + [
        ("new 20", (key["source"] == "new").to_numpy())]
    rng = np.random.default_rng(seed)
    values = key["edge_over_interior"].to_numpy(float)

    scores = []
    for who in ("second", "author"):
        marked_all = key[f"{who}_visible"].to_numpy(bool)
        for name, m in subsets:
            v, mk = values[m], marked_all[m]
            if mk.all() or not mk.any():
                auc = p = float("nan")
            else:
                auc = CP.rank_score(v, mk)
                null = np.array([CP.rank_score(v, rng.permutation(mk))
                                 for _ in range(N_PERMUTATIONS)])
                p = float((null >= auc).mean())
            scores.append(dict(judge=who, parcels=name, n=int(m.sum()),
                               marked_visible=int(mk.sum()),
                               rank_score=round(auc, 4),
                               permutation_p=round(p, 4),
                               reading=reading(auc, p)))

    agree = []
    for name, m in subsets:
        a = key["second_visible"].to_numpy(bool)[m]
        b = key["author_visible"].to_numpy(bool)[m]
        po, k = kappa(a, b)
        agree.append(dict(parcels=name, n=int(m.sum()),
                          both_visible=int((a & b).sum()),
                          both_not=int((~a & ~b).sum()),
                          second_only=int((a & ~b).sum()),
                          author_only=int((~a & b).sum()),
                          agree_share=round(po, 3), kappa=round(k, 3)))

    pd.DataFrame(scores).to_csv(out_scores, index=False)
    pd.DataFrame(agree).to_csv(F.RESULTS / "contrast_second_agreement.csv",
                               index=False)

    print(RULE)
    print("CONTRAST MEASURE AGAINST TWO PEOPLE, INDIA")
    print(RULE)
    print(f"  {'judge':<7} {'parcels':<15} {'n':>3} {'marked':>7} "
          f"{'rank':>7} {'p':>7}  reading")
    for r in scores:
        print(f"  {r['judge']:<7} {r['parcels']:<15} {r['n']:>3} "
              f"{r['marked_visible']:>7} {r['rank_score']:>7.3f} "
              f"{r['permutation_p']:>7.4f}  {r['reading']}")
    print("\n  The author's two earlier panels, recomputed here, against the")
    print("  rank scores recorded when she scored them:")
    for s in OLD_SEEDS:
        got = next(r["rank_score"] for r in scores
                   if r["judge"] == "author" and r["parcels"] == f"panel {s}")
        print(f"    panel {s}  {got:.4f}  recorded {recorded[s]:.4f}")

    print(f"\n  {'parcels':<15} {'n':>3} {'both y':>7} {'both n':>7} "
          f"{'2nd only':>9} {'author only':>12} {'agree':>6} {'kappa':>6}")
    for r in agree:
        print(f"  {r['parcels']:<15} {r['n']:>3} {r['both_visible']:>7} "
              f"{r['both_not']:>7} {r['second_only']:>9} "
              f"{r['author_only']:>12} {r['agree_share']:>6.2f} "
              f"{r['kappa']:>6.2f}")
    print("  the author saw panel 20260925 with red and blue swapped and the")
    print("  second person saw it in natural colour")

    main = scores[0]
    k_all = agree[0]["kappa"]
    print("\n" + RULE)
    print(f"Primary, the second person over all 60: {main['reading']}.")
    if main["reading"] == "tracks what a person sees":
        print("F-14 closes.")
    elif main["reading"] == "weak":
        print("Fine as a country summary, not per parcel. F-14 stays scoped.")
    elif main["reading"] == "not tracking visibility":
        print("The documents stop calling the measure contrast.")
    if not np.isnan(k_all) and k_all < KAPPA_SHARED:
        print(f"Kappa {k_all:.2f} is under {KAPPA_SHARED:.2f}: the two judges do "
              "not share a standard for a visible boundary.")
    print(RULE)
    print(f"  wrote {out_scores.relative_to(F.PROJECT)}, "
          "contrast_second_agreement.csv and contrast_second_answers.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True,
                    choices=["draw", "judge", "score", "redraw"])
    ap.add_argument("--who", choices=["author", "second"])
    ap.add_argument("--seed", type=int, default=20261025)
    ap.add_argument("--force", action="store_true",
                    help="score: score again over an existing result")
    args = ap.parse_args()
    if args.part == "draw":
        draw(args.seed)
    elif args.part == "redraw":
        redraw()
    elif args.part == "judge":
        if not args.who:
            sys.exit("--part judge needs --who author or --who second")
        judge(args.who)
    else:
        score(args.seed, args.force)


if __name__ == "__main__":
    main()
