"""Produce the deployable copy of the phone app in docs/ (what GitHub Pages serves).

web/index.html carries an __API__ placeholder so the Apps Script /exec URL is
set in one place. This fills it in and draws the home-screen icons.

Run:  python build.py https://script.google.com/macros/s/<id>/exec
Then commit + push docs/. It cannot be served from Apps Script - see the
note at the top of backend/Code.js.
"""
import pathlib, re, shutil, sys
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).parent
WEB, DIST = HERE / "web", HERE / "docs"

# no URL: the page is built but shows "Not configured" until the backend exists
api = sys.argv[1] if len(sys.argv) > 1 else None
if api and not re.match(r"^https://script\.google\.com/macros/s/[\w-]+/exec$", api):
    raise SystemExit("usage: python build.py [https://script.google.com/macros/s/<id>/exec]")

shutil.rmtree(DIST, ignore_errors=True)
shutil.copytree(WEB, DIST)
html = (WEB / "index.html").read_text(encoding="utf-8")
if html.count("'__API__'") != 1:
    raise SystemExit("index.html has no single '__API__' placeholder - refusing to guess")
if api:
    (DIST / "index.html").write_text(html.replace("'__API__'", repr(api), 1), encoding="utf-8")


def icon(size):
    """Dark tile with a green-lit barcode: reads as 'scanner' at 40 px."""
    im = Image.new("RGB", (size, size), "#0b0f14")
    d = ImageDraw.Draw(im)
    u = size / 32
    x = 7 * u
    for w in (1, 2, 1, 1, 3, 1, 2, 1, 1, 2, 1, 3, 1):
        d.rectangle([x, 9 * u, x + w * u - 1, 23 * u], fill="#ffffff")
        x += (w + 0.6) * u
    d.rectangle([5 * u, 15.4 * u, 27 * u, 16.6 * u], fill="#22c55e")
    im.save(DIST / f"icon-{size}.png")


for s in (192, 512):
    icon(s)

for f in sorted(DIST.iterdir()):
    print("  %-22s %8d bytes" % (f.name, f.stat().st_size))
print("docs/ is ready ->", api)
