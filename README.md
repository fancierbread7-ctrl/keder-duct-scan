# Keder Duct Scan

Phone app for the finishers: camera is always on, hover over a duct sticker and
it is recorded into a Google Form's response sheet. No buttons.

- **Green** `✓ CONFIRMED  DCT item 1234  entered at 8:42:15 AM` stays 3 s.
- **Red** `DUPLICATE — NOT ADDED ... already entered at <first time>` if that sticker is already in the sheet. Nothing is written.
- Sticker format (Abraham, 2026-09-29): `ALIAS-NUMBER`, e.g. `DCT-1`, Code 128 or QR, 3"x1" Zebra labels.
  Aliases: `DCT PLM CTR STR` (edit `FINISHERS` in `backend/Code.js`).
- A label has to leave the frame for 1.5 s before the same label counts again, so hovering never
  double-fires. Scan different labels as fast as you like.
- No signal: scans are saved on the phone and sent automatically.

## Layout

| Path | What |
|---|---|
| `backend/Code.js` | Apps Script, same pattern as the GEI Production Scan: runs as you, `LockService` + `appendRow` into `Form Responses 1`. `setup()` creates the form and its sheet. |
| `web/` | The PWA (one HTML file, manifest, service worker). |
| `build.py` | Puts the `/exec` URL into the page and draws the icons into `docs/`, which GitHub Pages serves. |
| `tests/` | `node tests/test_backend_node.js` (8 checks), `python tests/test_e2e.py` (real Chromium, fake camera showing Code 128 labels). |

**Why the page isn't served by Apps Script like GEI's:** Apps Script wraps its pages in a
sandbox iframe whose `allow=` list has no `camera` (checked on the live GEI app 2026-09-30),
so the camera can never open there. Apps Script stays the backend; the one scanner page is a
static file on GitHub Pages (free, no server, nothing to maintain).

## Deploy

```
cd C:\claude\keder-duct-scan
set CLASP=node C:\Users\Evan\Downloads\GEI-Scan-PWA\node_modules\@google\clasp\build\src\index.js
%CLASP% login                      # Evan, in the browser
%CLASP% create-script --type standalone --title "Keder Duct Scan" --rootDir backend
%CLASP% push
```

1. `%CLASP% open-script` -> in the editor run **setup** once and authorize. The log prints the form and sheet URLs.
2. Deploy > New deployment > Web app. Execute as **Me**, access **Anyone**. Copy the `/exec` URL.
3. `python build.py <exec url>` then `git commit -am "point at backend" && git push`.
   GitHub Pages republishes `docs/` in about a minute.
4. On each phone open the Pages URL, allow the camera once, then Share > **Add to Home Screen**.
