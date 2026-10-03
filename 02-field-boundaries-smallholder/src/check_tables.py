"""
RS-02. Check that every number in a write-up's tables exists in the artefacts.

B-06 was three numbers in COMPARISON.md that disagreed with the CSVs they
cited, one of them by a factor of two. It happened because a figure was read
off a table inside the document that had rows missing. Nothing in the workflow
would have caught it; a reviewer did.

This closes that hole. It pulls every number out of every markdown table in a
document, pulls every number out of the generated tables, and reports any
document number that appears nowhere in the generated set.

Matching is by value at the precision the document prints. A document saying
0.107 matches a generated 0.1074, and a document saying 0.100 matches nothing,
which is the case that mattered.

Prose is skipped. A sentence saying a ratio is 5.7 times is arithmetic on two
table numbers rather than a number the CSVs should contain, so only rows
starting with a pipe are read.

A correction that shows what was published beside what is true carries old
numbers on purpose, and those can never trace to the current tables. Mark such
a table with a comment on the line before it, naming the columns that hold the
old values, counted from 1 at the first cell:

    <!-- check_tables: historical columns 3,5 -->

Those columns are then checked against earlier versions of the generated
tables in git history instead of being skipped. Every number in one column has
to trace to a single earlier version, and the script names the commit for each
column, so an old figure is verified as having been published rather than taken
on trust. Different columns may come from different versions, which is what a
table showing two successive corrections needs.

    python src\\check_tables.py
    python src\\check_tables.py --doc COMPARISON.md ^
        --against results\\comparison_tables.md
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

# The lookbehind stops a number being read out of the middle of a token.
# A hyphen has to be blocked as well as a word character, or the S-08 in
# a table cell parses as 08 once the sign itself is refused. A genuine
# negative such as -0.029 is preceded by a space, so it still matches.
NUMBER = re.compile(r"(?<![\w.+-])[-+]?\d[\d,]*(?:\.\d+)?%?")
SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")
HISTORICAL = re.compile(r"<!--\s*check_tables:\s*historical columns\s*"
                        r"([\d,\s]+?)\s*-->")

# Numbers that are structure rather than measurement. A table header saying
# "at 175 objects/chip" repeats a figure that is already in the body, and a
# year or a section number is not a result.
IGNORE = {"0", "1", "2", "3", "4", "5", "10", "20", "30", "50", "500"}


def numbers_in(line: str) -> list:
    """Every numeric token in one table row, normalised."""
    out = []
    for raw in NUMBER.findall(line):
        token = raw.replace(",", "").replace("%", "").lstrip("+")
        if token in IGNORE or token.lstrip("-") in IGNORE:
            continue
        try:
            out.append((token, float(token)))
        except ValueError:
            continue
    return out


def table_rows(text: str) -> list:
    """Markdown table rows as (line number, row, historical columns).

    A historical marker applies to the next table after it, allowing blank
    lines between the two, and ends with that table.
    """
    rows = []
    pending, current, in_table = set(), set(), False
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        m = HISTORICAL.search(s)
        if m:
            pending = {int(c) for c in m.group(1).replace(" ", "").split(",")
                       if c}
            continue
        if not s.startswith("|"):
            if in_table:
                in_table, current = False, set()
            continue
        if not in_table:
            in_table, current, pending = True, pending, set()
        if SEPARATOR.match(s):
            continue
        rows.append((n, s, current))
    return rows


def split_cells(row: str, hist: set) -> tuple:
    """The row's current cells as one string, and its historical cells by column."""
    cells = row.strip().strip("|").split("|")
    now = [c for i, c in enumerate(cells, 1) if i not in hist]
    old = {i: c for i, c in enumerate(cells, 1) if i in hist}
    return " | ".join(now), old


def known_numbers(text: str) -> list:
    out = []
    for _, line, _ in table_rows(text):
        out += [v for _, v in numbers_in(line)]
    return out


def traces(token: str, value: float, known: list) -> bool:
    d = decimals(token)
    return any(round(k, d) == round(value, d) for k in known)


def earlier_versions(gen: Path):
    """Each committed version of the generated tables, newest first."""
    try:
        log = subprocess.run(
            ["git", "-C", str(gen.parent), "log", "--format=%h %ad",
             "--date=short", "--", gen.name],
            capture_output=True, text=True, check=True).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"historical columns need git history and git failed: {e}")
    for entry in filter(None, log):
        commit, date = entry.split(" ", 1)
        shown = subprocess.run(
            ["git", "-C", str(gen.parent), "show", f"{commit}:./{gen.name}"],
            capture_output=True, text=True, encoding="utf-8")
        if shown.returncode == 0:
            yield commit, date, shown.stdout


def decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="COMPARISON.md")
    ap.add_argument("--against", default="results/comparison_tables.md")
    args = ap.parse_args()

    doc = F.PROJECT / args.doc
    gen = F.PROJECT / args.against
    for p in (doc, gen):
        if not p.exists():
            sys.exit(f"{p} not found")

    known = known_numbers(gen.read_text(encoding="utf-8"))

    print(RULE)
    print(f"CHECKING {doc.name} AGAINST {gen.name}")
    print(RULE)
    print(f"  {len(known):,} numbers in the generated tables\n")

    checked = 0
    missing, historical = [], []
    for lineno, line, hist in table_rows(doc.read_text(encoding="utf-8")):
        now, old = split_cells(line, hist) if hist else (line, {})
        for token, value in numbers_in(now):
            checked += 1
            if not traces(token, value, known):
                missing.append((lineno, token, line))
        for col, cell in old.items():
            historical += [(col, lineno, token, value, line)
                           for token, value in numbers_in(cell)]

    if historical:
        versions = [(c, d, known_numbers(t))
                    for c, d, t in earlier_versions(gen)]
        for col in sorted({h[0] for h in historical}):
            group = [h for h in historical if h[0] == col]
            found = next(((c, d) for c, d, k in versions
                          if all(traces(t, v, k) for _, _, t, v, _ in group)),
                         None)
            if found:
                checked += len(group)
                print(f"  historical column {col}: {len(group)} number(s) "
                      f"trace to {gen.name} as committed in {found[0]}, "
                      f"{found[1]}")
            else:
                print(f"  historical column {col}: {len(group)} number(s) do "
                      f"not all trace to any one committed version")
                missing += [(n, t, line) for _, n, t, _, line in group]
        print()

    if missing:
        print(f"  {len(missing)} number(s) appear in no generated table\n")
        for lineno, token, line in missing:
            print(f"    line {lineno:>4}  {token}")
            print(f"              {line[:96]}")
        print("\n" + RULE)
        print("Each of those is either a table that is not generated yet or a")
        print("number the document invented. Regenerate, or fix the text.")
        print(RULE)
        sys.exit(1)

    print(f"  all {checked:,} table numbers trace to a generated table")
    print("\n" + RULE)
    print("This does not check that the right number sits in the right row.")
    print("It checks that no number in the document was made up, which is the")
    print("failure B-06 recorded.")
    print(RULE)


if __name__ == "__main__":
    main()
