"""End to end: real Chromium, a fake camera showing printed Code 128 labels,
the Apps Script API stubbed with the same dedupe rule as backend/Code.js.

The camera feed (looped by Chrome): DCT-1234, nothing, DCT-1234 again,
nothing, PLM-7, nothing. Expect green DCT, red DCT, green PLM, and exactly two
rows written. Headless Chromium on Windows has no native BarcodeDetector, so
this also exercises the ZXing/WebAssembly path the iPhones use.

    python tests/test_e2e.py
"""
import io, json, urllib.parse, pathlib, re, subprocess, sys, threading, functools, http.server
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
import barcode
from barcode.writer import ImageWriter
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
API = "https://script.google.com/macros/s/TEST/exec"
TMP = ROOT / "tests" / "_e2e"
TMP.mkdir(exist_ok=True)

subprocess.run([sys.executable, str(ROOT / "build.py"), API], check=True, stdout=subprocess.DEVNULL,
               creationflags=0x08000000)

# ---- fake camera: 3"x1" style label on a bench, 10 fps ----
def frame(code):
    im = Image.new("RGB", (640, 480), (70, 72, 76))
    if code:
        buf = io.BytesIO()
        barcode.get("code128", code, writer=ImageWriter()).write(
            buf, {"module_width": 0.35, "module_height": 12, "font_size": 8, "quiet_zone": 4})
        lab = Image.open(buf).convert("RGB")
        lab.thumbnail((480, 200))
        im.paste(lab, ((640 - lab.width) // 2, (480 - lab.height) // 2))
    out = io.BytesIO(); im.save(out, "JPEG", quality=90); return out.getvalue()

script = [("DCT-1234", 30), (None, 90), ("DCT-1234", 30), (None, 90), ("PLM-7", 30), (None, 90)]  # ~30 fps
mjpeg = TMP / "cam.mjpeg"
with open(mjpeg, "wb") as f:
    for code, n in script:
        jpg = frame(code)
        for _ in range(n): f.write(jpg)

# ---- serve docs/ on localhost (a secure context, so the camera is allowed) ----
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
Handler = functools.partial(Quiet, directory=str(ROOT / "docs"))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/" % srv.server_port

# ---- stub backend, same rule as Code.js ----
rows = []
def api(route):
    req = route.request
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(req.url).query))
    if "code" not in q:
        body = {"ok": True, "codes": [[c, t] for c, t in rows]}
    else:
        m = re.match(r"^([A-Z]{3})-?0*(\d+)$", q["code"].upper())
        code = m.group(1) + "-" + m.group(2)
        prior = [t for c, t in rows if c == code]
        if prior:
            body = {"ok": True, "dup": True, "finisher": m.group(1), "item": m.group(2), "code": code, "at": prior[0]}
        else:
            t = "8:%02d:00 AM" % len(rows)
            rows.append((code, t))
            body = {"ok": True, "dup": False, "finisher": m.group(1), "item": m.group(2), "code": code, "at": t}
    route.fulfill(status=200, body=json.dumps(body), headers={
        "content-type": "application/json", "access-control-allow-origin": "*"})

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                "--use-file-for-fake-video-capture=" + str(mjpeg)])
    ctx = b.new_context(viewport={"width": 390, "height": 844}, permissions=["camera"])
    ctx.route("https://script.google.com/**", api)
    pg = ctx.new_page()
    pg.add_init_script("""
      window.__log = [];
      new MutationObserver(ms => ms.forEach(m => [...m.addedNodes, m.target].forEach(n => {
        if (n.classList && n.classList.contains('toast') && !n.classList.contains('wait'))
          window.__log.push(n.className.replace('toast ', '').trim() + ' | ' + n.innerText.replace(/\\n/g, ' / '));
      }))).observe(document, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
    """)
    msgs = []
    pg.on("console", lambda m: msgs.append("console " + m.type + ": " + m.text))
    pg.on("pageerror", lambda e: msgs.append("pageerror: " + str(e)))
    pg.goto(url)
    try:
        pg.wait_for_function("window.__log.some(l => l.includes('PLM')) && window.__log.some(l => l.startsWith('dup'))", timeout=60000)
    except Exception:
        pg.screenshot(path=str(TMP / "fail.png"))
        print("status:", pg.inner_text("#st"), "| msg:", pg.inner_text("#msg"))
        print("log:", pg.evaluate("window.__log")); print(chr(10).join(msgs[-15:])); print("rows:", rows)
        raise
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(TMP / "phone.png"))
    log = list(dict.fromkeys(l for l in pg.evaluate("window.__log") if not l.startswith("ok out")
                             and not l.startswith("dup out")))
    b.close()
srv.shutdown()

for l in log: print("   ", l)
assert log[0].startswith("ok") and "DCT" in log[0] and "1234" in log[0] and "CONFIRMED" in log[0], log
assert any(l.startswith("dup") and "DCT" in l and "already entered at 8:00:00 AM" in l for l in log), log
assert any(l.startswith("ok") and "PLM" in l and "item 7" in l for l in log), log
assert [c for c, _ in rows] == ["DCT-1234", "PLM-7"], rows
print("e2e passed: green, red dup, green; sheet rows =", [c for c, _ in rows])
