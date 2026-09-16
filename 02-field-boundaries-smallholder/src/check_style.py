"""
Find the writing patterns we agreed to keep out of this repo.

Mechanical tells can be matched exactly: em dashes, curly quotes, a word list,
a set of stock phrases. Those are reported as hits. Rule of three and inflated
framing need a person to judge, so triples are reported only with --triples and
are marked for review rather than counted as faults.

Markdown is read outside fenced code blocks. Python is read inside comments and
string literals that look like writing, which covers docstrings and the
guidance these scripts print to the console.

Exit code is 1 when anything is found, so this can become a pre-commit hook.

    python src\\check_style.py
    python src\\check_style.py --triples
    python src\\check_style.py --path FINDINGS.md
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tokenize
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "data", "models",
             "results", "figures", ".idea", ".vscode", ".pytest_cache"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass


# Characters. Reported by codepoint so a cp1252 console cannot mangle them.
CHAR_CHECKS = [
    ("em dash", re.compile("\u2014")),
    ("en dash", re.compile("\u2013")),
    ("double hyphen as dash", re.compile(r"(?<=\s)--(?=\s)")),
    ("curly quote", re.compile("[\u2018\u2019\u201c\u201d]")),
    ("emoji", re.compile("[\U0001F000-\U0001FAFF]")),
]

# Vocabulary that reads as machine-written. Domain words that are literal here
# stay out of this list on purpose: landscape, ecosystem and spectral are real
# things in remote sensing and flagging them would be wrong.
AI_WORDS = [
    "delve", "delves", "delving", "tapestry", "testament", "underscore",
    "underscores", "underscored", "underscoring", "showcase", "showcases",
    "showcasing", "pivotal", "crucial", "crucially", "intricate",
    "intricacies", "garner", "garners", "garnered", "foster", "fosters",
    "fostering", "vibrant", "seamless", "seamlessly", "leverage",
    "leverages", "leveraging", "interplay", "nuanced", "holistic", "myriad",
    "plethora", "embark", "embarks", "unlock", "unlocks", "unlocking",
    "empower", "empowers", "empowering", "elevate", "elevates", "harness",
    "harnesses", "harnessing", "streamline", "streamlines", "streamlining",
    "cutting-edge", "groundbreaking", "game-changer", "game-changing",
    "revolutionize", "revolutionizes", "revolutionary", "transformative",
    "paradigm", "synergy", "actionable", "world-class", "state-of-the-art",
    "meticulous", "meticulously", "profound", "profoundly", "renowned",
    "boasts", "nestled", "indelible", "vital", "compelling", "robustly",
    "invaluable", "pave", "paves", "realm", "multifaceted", "comprehensive",
]
WORD_CHECK = ("ai vocabulary",
              re.compile(r"\b(" + "|".join(AI_WORDS) + r")\b", re.I))

PHRASE_CHECKS = [
    ("negative parallelism",
     re.compile(r"\bnot (just|only|merely|simply)\b", re.I)),
    ("negative parallelism",
     re.compile(r"\b(is|it'?s|that'?s|was) not (a|an|the)\b.{0,40}?,\s*(it|it'?s|but)\b", re.I)),
    ("tailing negation",
     re.compile(r",\s*no [a-z]+(\.|$)", re.I)),
    ("copula avoidance",
     re.compile(r"\b(serves as|stands as|represents a|marks a|acts as)\b", re.I)),
    ("significance puffery",
     re.compile(r"\b(a testament to|plays? a (key|crucial|vital|pivotal|significant) role|"
                r"highlights? the importance|underscores? the importance|"
                r"key (role|moment|turning point|insight|takeaway)|"
                r"sets? the stage|paves? the way|marks? a shift)\b", re.I)),
    ("filler",
     re.compile(r"\b(in order to|due to the fact that|at this point in time|"
                r"it is important to note|it'?s worth noting|"
                r"in the event that|has the ability to|a wide range of)\b", re.I)),
    ("hedging",
     re.compile(r"\b(could potentially|might possibly|may potentially|"
                r"it could be argued)\b", re.I)),
    ("signposting",
     re.compile(r"\b(let'?s (dive|explore|break this down|take a look)|"
                r"here'?s what you need to know|without further ado|"
                r"now let'?s)\b", re.I)),
    ("authority trope",
     re.compile(r"\b(at its core|the real question is|what really matters|"
                r"the heart of the matter|the deeper issue|fundamentally,)\b", re.I)),
    ("chat artifact",
     re.compile(r"\b(i hope this helps|let me know if|would you like me to|"
                r"want me to|great question|certainly!|of course!)\b", re.I)),
    ("cutoff disclaimer",
     re.compile(r"\b(as of my last|up to my last training|"
                r"based on available information|"
                r"while specific details are (limited|scarce))\b", re.I)),
]

TRIPLE = re.compile(r"\b[\w'-]+(?: [\w'-]+){0,2}, [\w'-]+(?: [\w'-]+){0,2},"
                    r" and [\w'-]+", re.I)

QUOTE_START = re.compile(r"^([A-Za-z]*)('''|\"\"\"|'|\")")
FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)


def markdown_prose(path: Path):
    """Every line outside a fenced code block, with its line number."""
    out, fenced = [], False
    text = path.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if not fenced:
            out.append((i, line))
    return out


def is_prose(literal: str) -> bool:
    """Does this string literal read as writing rather than as machinery?

    Raw strings are patterns, and a literal with no space is a word list entry
    or a path. Anything under four words is a format fragment. Excluding those
    lets this file survive its own check despite holding a lexicon of the very
    words it hunts.
    """
    m = QUOTE_START.match(literal)
    if m and "r" in m.group(1).lower():
        return False
    if " " not in literal:
        return False
    return len(re.findall(r"[A-Za-z]{2,}", literal)) >= 4


def python_prose(path: Path):
    """Comments and prose-shaped string literals, with exact line numbers.

    Every string token is a candidate. Docstrings are one source of prose here
    and the guidance these scripts print to the console is another.
    """
    out = []
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
                continue
            if FSTRING_MIDDLE is not None and tok.type == FSTRING_MIDDLE:
                if is_prose('"' + tok.string + '"'):
                    out.append((tok.start[0], tok.string))
                continue
            if tok.type != tokenize.STRING or not is_prose(tok.string):
                continue
            for i, line in enumerate(tok.string.splitlines()):
                out.append((tok.start[0] + i, line))
    except (tokenize.TokenError, IndentationError) as exc:
        print(f"  could not tokenize {path.name}: {exc}")
    return out


def scan(pairs, want_triples):
    hits = []
    for lineno, text in pairs:
        for name, rx in CHAR_CHECKS:
            for m in rx.finditer(text):
                hits.append((name, lineno, ascii(m.group(0)), text.strip()))
        name, rx = WORD_CHECK
        for m in rx.finditer(text):
            hits.append((name, lineno, m.group(0), text.strip()))
        for name, rx in PHRASE_CHECKS:
            for m in rx.finditer(text):
                hits.append((name, lineno, m.group(0), text.strip()))
        if want_triples:
            for m in TRIPLE.finditer(text):
                hits.append(("triple, review by eye", lineno, m.group(0),
                             text.strip()))
    return hits


def files_to_check(one: str):
    if one:
        p = (PROJECT / one).resolve()
        if not p.exists():
            sys.exit(f"{p} not found")
        return [p]
    out = []
    for p in sorted(PROJECT.rglob("*")):
        if p.is_dir() or p.suffix.lower() not in (".md", ".py"):
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="", help="one file, relative to project")
    ap.add_argument("--triples", action="store_true",
                    help="also report comma-and-comma triples for review")
    ap.add_argument("--quiet", action="store_true",
                    help="counts only, without the per-hit lines")
    args = ap.parse_args()

    paths = files_to_check(args.path)
    print(f"Checking {len(paths)} files under {PROJECT.name}\n")

    totals, faults, reviews = {}, 0, 0
    for p in paths:
        pairs = markdown_prose(p) if p.suffix.lower() == ".md" \
            else python_prose(p)
        hits = scan(pairs, args.triples)
        if not hits:
            continue
        rel = p.relative_to(PROJECT).as_posix()
        print(f"{rel}")
        for name, lineno, match, line in hits:
            totals[name] = totals.get(name, 0) + 1
            if name.startswith("triple"):
                reviews += 1
            else:
                faults += 1
            if not args.quiet:
                trimmed = line if len(line) <= 96 else line[:93] + "..."
                print(f"  {lineno:>5}  {name:<24} {match}")
                print(f"         {trimmed}")
        print()

    print("=" * 70)
    if not totals:
        print("Nothing found.")
        sys.exit(0)
    for name in sorted(totals, key=lambda k: -totals[k]):
        print(f"  {totals[name]:>4}  {name}")
    print(f"\n  {faults} to fix, {reviews} to read by eye")
    print("=" * 70)
    sys.exit(1 if faults else 0)


if __name__ == "__main__":
    main()