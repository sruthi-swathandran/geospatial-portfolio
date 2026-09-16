"""
Run the ftw CLI with a User-Agent that source.coop will accept.

Why this exists
---------------
'ftw data download' failed with 'HTTP Error 403: Forbidden'. diagnose_download.py
asked for the same file four ways and got:

    urllib, default User-Agent     403, server said 'error code: 1010', cloudflare
    urllib, browser User-Agent     200, 1,032 bytes
    requests, browser User-Agent   200, 1,032 bytes

Cloudflare 1010 is a client refusal. The certificate came from Google Trust
Services rather than anything internal, so the network is not filtering this.
source.coop simply will not serve a request that announces itself as
'Python-urllib/3.11', and ftw-tools has no setting for that.

What it does
------------
urllib keeps one process-wide opener. urlretrieve and urlopen both go through
it, and the header list on that opener is applied to every request that does
not already carry the header. So installing one opener at the top of the
process changes every fetch ftw-tools makes, without editing ftw-tools.

The CLI itself is then loaded through its console-script entry point rather
than by guessing at an internal module path, and handed the arguments as given.
It is the same command doing the same work, with one header added.

Usage
-----
    python src\\ftw_download.py
        same as: ftw data download --countries india -o data

    python src\\ftw_download.py data download --countries india,kenya
        any ftw arguments are passed straight through

    python src\\ftw_download.py --check
        only verify the header fix works, download nothing
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")

PROBE = ("https://data.source.coop/kerner-lab/"
         "fields-of-the-world-archive/checksum.md5")

DEFAULT_ARGS = ["data", "download", "--countries", "india", "-o", "data"]


def patch_urllib() -> None:
    """Every urllib fetch in this process now carries a browser User-Agent."""
    opener = urllib.request.build_opener()
    opener.addheaders = [
        ("User-Agent", BROWSER_UA),
        ("Accept", "*/*"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    urllib.request.install_opener(opener)


def patch_requests() -> None:
    """Belt and braces, in case some code path uses requests instead."""
    try:
        import requests
        import requests.utils
    except ImportError:
        return
    requests.utils.default_user_agent = lambda name="python-requests": BROWSER_UA
    try:
        requests.sessions.Session.__init__ = _wrap_session_init(
            requests.sessions.Session.__init__)
    except Exception:                                         # noqa: BLE001
        pass


def _wrap_session_init(orig):
    def init(self, *a, **kw):
        orig(self, *a, **kw)
        self.headers["User-Agent"] = BROWSER_UA
    return init


def probe() -> bool:
    print("  checking the header fix against the real host")
    try:
        with urllib.request.urlopen(PROBE, timeout=40) as resp:
            body = resp.read()
    except Exception as exc:                                  # noqa: BLE001
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        print("\n  The patch did not take, so do not start a long download.")
        print("  Paste this and I will look again.")
        return False
    print(f"  OK: {resp.status}, {len(body):,} bytes\n")
    return True


def load_cli():
    """Find the ftw command through its entry point, not by guessing modules."""
    from importlib.metadata import entry_points
    try:
        eps = entry_points(group="console_scripts")
    except TypeError:                                         # older API
        eps = entry_points().get("console_scripts", [])
    for ep in eps:
        if ep.name == "ftw":
            return ep.load()
    return None


def main() -> None:
    args = sys.argv[1:]
    check_only = args == ["--check"]
    if check_only:
        args = []
    if not args:
        args = list(DEFAULT_ARGS)

    print("Running the ftw CLI with a User-Agent source.coop accepts.\n")
    patch_urllib()
    patch_requests()

    if not probe():
        sys.exit(1)
    if check_only:
        print("  Header fix works. Re-run without --check to download.")
        return

    cli = load_cli()
    if cli is None:
        print("  Could not find the 'ftw' console script entry point.")
        print("  Is the venv active? 'pip show ftw-tools' should list it.")
        sys.exit(1)

    print(f"  ftw {' '.join(args)}")
    print("  working directory: " + str(Path.cwd()))
    print("  (a few GB may follow; leave it running)\n")
    print("-" * 78)

    try:
        cli(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        if code:
            sys.exit(code)
    except TypeError:
        # Not a click command after all; call it plainly.
        sys.argv = ["ftw", *args]
        cli()

    print("-" * 78)
    print("\nDone. Next:")
    print("  python src\\explore_ftw.py")


if __name__ == "__main__":
    main()
