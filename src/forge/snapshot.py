"""Record pages once so build, fixes and verify can replay them offline (#52).

Live pages change: in the v7 gold check 14 of 50 test bugs could no longer be rebuilt because
Wikipedia had been edited since the samples were made. A snapshot is a HAR file holding every
response of one page load (HTML, CSS, scripts, images, fonts). `forge.capture.open_page` replays
it with no network, so the page looks the same on every run, on every machine.

One snapshot is recorded per site and viewport, because pages load different images and
styles at different widths:

    python -m forge.snapshot --site wiki=https://en.wikipedia.org/wiki/Web_page
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from forge.build import parse_sites
from forge.capture import VIEWPORTS, settle, snapshot_path

LOAD_TIMEOUT_MS = 60000


def record(url: str, har: Path | str, viewport: str) -> None:
    """Load `url` once at the viewport and save every response into the HAR file `har`."""
    har = Path(har)
    har.parent.mkdir(parents=True, exist_ok=True)
    width, height = VIEWPORTS[viewport]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                reduced_motion="reduce",
                record_har_path=str(har),
                record_har_content="attach",
            )
            page = context.new_page()
            page.goto(url, timeout=LOAD_TIMEOUT_MS)
            settle(page)
            context.close()  # the HAR file is written when the context closes
        finally:
            browser.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record pages once for offline replay.")
    parser.add_argument("--site", action="append", required=True, metavar="NAME=URL")
    parser.add_argument("--viewports", nargs="+", choices=sorted(VIEWPORTS))
    parser.add_argument("--out", default="data/snapshots")
    parser.add_argument("--force", action="store_true", help="record again over old snapshots")
    args = parser.parse_args(argv)

    failed = 0
    for site, url in parse_sites(args.site).items():
        for viewport in args.viewports or list(VIEWPORTS):
            har = snapshot_path(args.out, site, viewport)
            if har.exists() and not args.force:
                print(f"{har.name:<32} kept", flush=True)
                continue
            try:
                record(url, har, viewport)
                print(f"{har.name:<32} {har.stat().st_size / 1e6:.1f} MB", flush=True)
            except PlaywrightError as error:
                failed += 1
                har.unlink(missing_ok=True)
                print(f"{har.name:<32} failed: {str(error).splitlines()[0]}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
