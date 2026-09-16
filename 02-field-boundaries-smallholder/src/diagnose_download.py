"""
Why 'ftw data download' returned 403, and which fix applies.

The message was 'HTTP Error 403: Forbidden', which is urllib's wording rather
than requests'. So ftw-tools is fetching over urllib. Two very different
things produce a 403 there, and they need opposite fixes:

  1. The HOST refuses the client. Python's urllib announces itself as
     'Python-urllib/3.11'. Object stores behind a CDN frequently refuse that
     while serving the identical URL to a browser. Fix: send a User-Agent.

  2. The NETWORK refuses the request. A corporate proxy answers 403 for a host
     it does not allow, and no header changes that. Fix: proxy settings, or
     fetch the data from somewhere the network permits.

The same URL returns content when fetched from outside this network, so the
file exists and the path ftw-tools uses is right. This script decides which of
the two is in the way, by asking the same question four ways.

Nothing is downloaded beyond a few kilobytes. Nothing is written to disk
unless --save is passed.

    python src\\diagnose_download.py
    python src\\diagnose_download.py --save
"""

from __future__ import annotations

import argparse
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

HOST = "data.source.coop"
BASE = f"https://{HOST}/kerner-lab/fields-of-the-world-archive"
TARGET = f"{BASE}/checksum.md5"

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")

RULE = "=" * 78


def env_report():
    print(RULE)
    print("A. WHAT THIS MACHINE THINKS ABOUT PROXIES")
    print(RULE)
    keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"]
    found = False
    for k in keys:
        v = os.environ.get(k)
        if v:
            print(f"  {k:<20}{v}")
            found = True
    if not found:
        print("  none set in this shell")

    try:
        got = urllib.request.getproxies()
    except Exception as exc:                                  # noqa: BLE001
        got = f"could not read: {exc}"
    print(f"\n  urllib.request.getproxies() -> {got}")
    print("  (on Windows this also reads the system proxy from the registry,")
    print("   so it can be non-empty even with no environment variables)")


def dns_and_tcp():
    print("\n" + RULE)
    print("B. CAN THIS MACHINE EVEN REACH THE HOST")
    print(RULE)
    try:
        infos = socket.getaddrinfo(HOST, 443, proto=socket.IPPROTO_TCP)
        addrs = sorted({i[4][0] for i in infos})
        print(f"  DNS  {HOST} -> {', '.join(addrs[:4])}")
    except Exception as exc:                                  # noqa: BLE001
        print(f"  DNS  failed: {exc}")
        print("\n  A DNS failure means the name never resolved, which is a")
        print("  network or filtering problem rather than a header problem.")
        return

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((HOST, 443), timeout=20) as sock:
            with ctx.wrap_socket(sock, server_hostname=HOST) as tls:
                cert = tls.getpeercert()
                issuer = dict(x[0] for x in cert.get("issuer", []))
                subject = dict(x[0] for x in cert.get("subject", []))
                print(f"  TLS  connected, protocol {tls.version()}")
                print(f"       certificate subject  "
                      f"{subject.get('commonName', '?')}")
                print(f"       certificate issuer   "
                      f"{issuer.get('organizationName', '?')} / "
                      f"{issuer.get('commonName', '?')}")
                print("\n  If that issuer is your employer rather than a public")
                print("  certificate authority, the connection is being opened")
                print("  and re-signed by an inspecting proxy. That proxy is")
                print("  then the thing deciding whether a 403 comes back.")
    except Exception as exc:                                  # noqa: BLE001
        print(f"  TLS  failed: {exc}")


def attempt(label, opener, headers):
    req = urllib.request.Request(TARGET, headers=headers)
    try:
        with opener.open(req, timeout=40) as resp:
            body = resp.read()
            print(f"  {label:<34}{resp.status}  {len(body):,} bytes")
            return body
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read()[:160].decode("utf-8", "replace").strip()
        except Exception:                                     # noqa: BLE001
            pass
        print(f"  {label:<34}{exc.code} {exc.reason}")
        if detail:
            print(f"  {'':<34}server said: {detail!r}")
        server = exc.headers.get("Server") if exc.headers else None
        via = exc.headers.get("Via") if exc.headers else None
        if server:
            print(f"  {'':<34}Server: {server}")
        if via:
            print(f"  {'':<34}Via: {via}")
    except Exception as exc:                                  # noqa: BLE001
        print(f"  {label:<34}failed: {type(exc).__name__}: {exc}")
    return None


def http_attempts():
    print("\n" + RULE)
    print("C. THE SAME URL, ASKED FOUR WAYS")
    print(RULE)
    print(f"  {TARGET}\n")

    results = {}

    plain = urllib.request.build_opener()
    results["urllib default"] = attempt(
        "urllib, default User-Agent", plain, {})

    results["urllib browser UA"] = attempt(
        "urllib, browser User-Agent", plain,
        {"User-Agent": BROWSER_UA, "Accept": "*/*"})

    noproxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results["urllib no proxy"] = attempt(
        "urllib, browser UA, proxy off", noproxy,
        {"User-Agent": BROWSER_UA, "Accept": "*/*"})

    try:
        import requests
        try:
            r = requests.get(TARGET, timeout=40,
                             headers={"User-Agent": BROWSER_UA})
            print(f"  {'requests, browser User-Agent':<34}"
                  f"{r.status_code}  {len(r.content):,} bytes")
            if r.ok:
                results["requests"] = r.content
            else:
                snippet = r.text[:160].strip()
                if snippet:
                    print(f"  {'':<34}server said: {snippet!r}")
        except Exception as exc:                              # noqa: BLE001
            print(f"  {'requests, browser User-Agent':<34}"
                  f"failed: {type(exc).__name__}: {exc}")
    except ImportError:
        print(f"  {'requests':<34}not installed")

    return {k: v for k, v in results.items() if v}


def interpret(ok):
    print("\n" + RULE)
    print("D. WHAT THIS MEANS")
    print(RULE)
    if not ok:
        print("  Nothing got through. The host is not the problem, since the")
        print("  same URL serves content from other networks, so the block is")
        print("  between this machine and source.coop.")
        print()
        print("  Next options, in the order I would try them:")
        print("    1. Open the URL in a browser on this machine. If the browser")
        print("       downloads it, the browser is using a proxy that Python is")
        print("       not, and section A will usually name it.")
        print("    2. If the browser is also refused, the host is blocked for")
        print("       this network. We then fetch the data on a machine that")
        print("       can reach it and bring the files over.")
        return

    if "urllib default" in ok:
        print("  The default urllib request succeeded, which means the 403")
        print("  ftw-tools hit was not reproducible here. Worth re-running")
        print("  'ftw data download --countries india' before anything else,")
        print("  since it may have been a transient refusal.")
    else:
        which = ", ".join(sorted(ok))
        print(f"  Refused with the default User-Agent, served with: {which}.")
        print()
        print("  So the host is refusing the client rather than the network")
        print("  refusing the host. ftw-tools does not expose a User-Agent")
        print("  setting, so the fix is to install a urllib opener that carries")
        print("  one before calling the download. I will write that wrapper.")


def save(body):
    out = PROJECT / "data" / "checksum.md5"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    print(f"\n  saved {out.relative_to(PROJECT)}  ({len(body):,} bytes)")
    text = body.decode("utf-8", "replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print(f"  it lists {len(lines)} files. The ones matching india:")
    hits = [ln for ln in lines if "india" in ln.lower()]
    for ln in hits[:10]:
        print(f"    {ln}")
    if not hits:
        print("    none, so the archive names its files some other way")
        for ln in lines[:6]:
            print(f"    {ln}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true",
                    help="write checksum.md5 into data/ if any attempt worked")
    args = ap.parse_args()

    print("Diagnosing the 403 from 'ftw data download'.\n")
    env_report()
    dns_and_tcp()
    ok = http_attempts()
    interpret(ok)

    if args.save and ok:
        save(next(iter(ok.values())))

    print("\n" + RULE)
    print("Paste all of this. Section C is the part that decides the fix.")
    print(RULE)


if __name__ == "__main__":
    main()
