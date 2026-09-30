/**
 * Keder Duct Scan  -  Apps Script backend
 *
 * Same framework as the Enviro-USA/GEI Production Scan app: a web app that
 * runs as the deployer and writes straight into a Google Form's response sheet
 * ("Form Responses 1"), under a script lock, with every rule enforced here on
 * the server rather than only on the phone.
 *
 * What is different: the phone page is NOT served from here. Apps Script puts
 * its pages in a sandbox iframe whose allow= list has no "camera", so
 * getUserMedia can never open the camera from an HtmlService page. The
 * scanner is a small static PWA (../web) that calls this script as a JSON API:
 *
 *   GET  /exec?code=DCT-1234                -> record it, or report the dup
 *   GET  /exec?codes=1                      -> every code already recorded
 *   POST /exec   body {"code":"DCT-1234"}   -> same as ?code= (kept for old copies of the page)
 *
 * The phone records with GET, not POST: Apps Script answers every call with a
 * 302 to script.googleusercontent.com, and home-screen web apps (iOS standalone
 * above all) were dropping the POST-then-redirect while the same page in a
 * browser tab was fine. A GET redirect is the plain case every browser handles.
 *
 * THE LABELS (Abraham, 2026-09-29): 3"x1" Zebra stickers, Code 128 or QR,
 * printed as ALIAS-NUMBER, e.g. DCT-1. The alias is a 3-letter code for the
 * finisher; the number after the dash grows, so the barcode length varies.
 * One sticker = one duct. A sticker may be recorded exactly once, ever.
 */

const FORM_TITLE = 'Duct Finishing Scans';
const RESPONSES_TAB = 'Form Responses 1';

// Abraham's aliases for the finishers, 2026-09-29. A new finisher is one more
// entry here (then push + redeploy).
const FINISHERS = ['DCT', 'PLM', 'CTR', 'STR'];

// Response sheet columns, in the order the form's questions create them.
const COL = { at: 1, finisher: 2, item: 3, code: 4 };

/* ===================== one-time setup ===================== */

/**
 * Run once from the editor (Run > setup). Creates the Google Form and its
 * linked response spreadsheet, and remembers both IDs. Safe to run again: if
 * they already exist it only prints where they are.
 */
function setup() {
  const ids = _ensure();
  const form = FormApp.openById(ids.form);
  const ss = SpreadsheetApp.openById(ids.sheet);
  Logger.log('Form:   ' + form.getEditUrl());
  Logger.log('Sheet:  ' + ss.getUrl());
  return { form: form.getEditUrl(), sheet: ss.getUrl() };
}

function _ensure() {
  const props = PropertiesService.getScriptProperties();
  let formId = props.getProperty('FORM_ID');
  let sheetId = props.getProperty('SHEET_ID');
  if (formId && sheetId) return { form: formId, sheet: sheetId };

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    formId = props.getProperty('FORM_ID');
    sheetId = props.getProperty('SHEET_ID');
    if (formId && sheetId) return { form: formId, sheet: sheetId };

    const form = FormApp.create(FORM_TITLE)
      .setDescription('One row per duct sticker. Filled by the Duct Scan app; ' +
                      'the form also works by hand if the app is down.');
    form.addListItem().setTitle('Finisher').setChoiceValues(FINISHERS).setRequired(true);
    form.addTextItem().setTitle('Item #').setRequired(true);
    form.addTextItem().setTitle('Barcode').setRequired(true);

    const ss = SpreadsheetApp.create(FORM_TITLE + ' (Responses)');
    form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
    SpreadsheetApp.flush();
    // the linked tab appears asynchronously; drop the blank Sheet1 once it has
    for (let i = 0; i < 10 && !ss.getSheetByName(RESPONSES_TAB); i++) Utilities.sleep(500);
    const blank = ss.getSheetByName('Sheet1');
    if (blank && ss.getSheets().length > 1) ss.deleteSheet(blank);

    props.setProperties({ FORM_ID: form.getId(), SHEET_ID: ss.getId() });
    return { form: form.getId(), sheet: ss.getId() };
  } finally {
    lock.releaseLock();
  }
}

function _sheet() {
  return SpreadsheetApp.openById(_ensure().sheet).getSheetByName(RESPONSES_TAB);
}

/* ===================== the API ===================== */

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.code) return _json(submitScan(p.code));
  if (p.codes) return _json({ ok: true, codes: _allCodes() });
  return _json({ ok: true, app: 'keder-duct-scan', finishers: FINISHERS });
}

function doPost(e) {
  let body = {};
  try { body = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (x) {}
  return _json(submitScan(body.code));
}

function _json(o) {
  return ContentService.createTextOutput(JSON.stringify(o))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * "DCT-1234" -> {finisher:'DCT', item:'1234', code:'DCT-1234'}; null if the
 * scan is not one of our stickers. Leading zeros are dropped so DCT-01 and
 * DCT-1 are the same duct and cannot both get in.
 */
function parseCode(raw) {
  const s = String(raw || '').toUpperCase().replace(/\s+/g, '');
  const m = /^([A-Z]{3})-?0*(\d+)$/.exec(s);
  if (!m) return null;
  return { finisher: m[1], item: m[2], code: m[1] + '-' + m[2] };
}

function submitScan(raw) {
  const p = parseCode(raw);
  if (!p) return { ok: false, error: 'Not a duct label: ' + String(raw || '').slice(0, 40) };
  if (FINISHERS.indexOf(p.finisher) < 0) {
    return { ok: false, error: 'Unknown finisher ' + p.finisher + ' (' + p.code + ')' };
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = _sheet();
    const prior = _find(sh, p.code);
    if (prior) {
      return { ok: true, dup: true, finisher: p.finisher, item: p.item, code: p.code,
               at: _fmt(prior) };
    }
    const now = new Date();
    sh.appendRow([now, p.finisher, p.item, p.code]);
    SpreadsheetApp.flush();
    return { ok: true, dup: false, finisher: p.finisher, item: p.item, code: p.code,
             at: _fmt(now) };
  } catch (err) {
    return { ok: false, error: String(err) };
  } finally {
    lock.releaseLock();
  }
}

/** Timestamp of the row already holding this code, or null. */
function _find(sh, code) {
  const last = sh.getLastRow();
  if (last < 2) return null;
  const hit = sh.getRange(2, COL.code, last - 1, 1)
    .createTextFinder(code).matchEntireCell(true).matchCase(false).findNext();
  if (!hit) return null;
  const at = sh.getRange(hit.getRow(), COL.at).getValue();
  return at instanceof Date ? at : new Date();
}

/** [[code, 'h:mm:ss a'], ...] so the phone can call a dup instantly, time included. */
function _allCodes() {
  const sh = _sheet();
  const last = sh.getLastRow();
  if (last < 2) return [];
  return sh.getRange(2, 1, last - 1, COL.code).getValues()
    .filter(function (r) { return String(r[COL.code - 1]).trim(); })
    .map(function (r) {
      const at = r[COL.at - 1];
      return [String(r[COL.code - 1]).trim().toUpperCase(), at instanceof Date ? _fmt(at) : ''];
    });
}

function _fmt(d) {
  return Utilities.formatDate(d, Session.getScriptTimeZone(), 'h:mm:ss a');
}
