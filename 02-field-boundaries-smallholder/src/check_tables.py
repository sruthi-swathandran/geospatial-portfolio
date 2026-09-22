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

    python src\\check_tables.py
    python src\\check_tables.py --doc COMPARISON.md ^
        --against results\\comparison_tables.md
"""

from __future__ import annotations

import argparse
import re
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


def table_rows(path: Path) -> list:
    """Markdown table rows, with separators and blank cells dropped."""
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s.startswith("|") or SEPARATOR.match(s):
            continue
        rows.append((n, s))
    return rows


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

    known = []
    for _, line in table_rows(gen):
        known += [v for _, v in numbers_in(line)]

    print(RULE)
    print(f"CHECKING {doc.name} AGAINST {gen.name}")
    print(RULE)
    print(f"  {len(known):,} numbers in the generated tables\n")

    checked = 0
    missing = []
    for lineno, line in table_rows(doc):
        for token, value in numbers_in(line):
            checked += 1
            d = decimals(token)
            if not any(round(k, d) == round(value, d) for k in known):
                missing.append((lineno, token, line))

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
