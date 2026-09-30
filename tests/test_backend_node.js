// Runs backend/Code.js against in-memory fakes of the Apps Script services.
//   node tests/test_backend_node.js
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');

function load() {
  const rows = [];                       // the response sheet, header excluded
  const props = {};
  const sheet = {
    getLastRow: () => rows.length + 1,
    appendRow: r => rows.push(r),
    getRange: (row, col, n = 1, w = 1) => ({
      getValue: () => rows[row - 2][col - 1],
      getValues: () => rows.slice(row - 2, row - 2 + n).map(r => r.slice(col - 1, col - 1 + w)),
      createTextFinder: text => {
        let mc = false;
        const f = {
          matchEntireCell: () => f, matchCase: v => { mc = v; return f; },
          findNext: () => {
            for (let i = row - 2; i < row - 2 + n; i++) {
              const a = String(rows[i][col - 1]), b = String(text);
              if (mc ? a === b : a.toUpperCase() === b.toUpperCase()) return { getRow: () => i + 2 };
            }
            return null;
          }
        };
        return f;
      }
    })
  };
  const ss = { getId: () => 'SHEET', getUrl: () => 'u', getSheetByName: n => n === 'Form Responses 1' ? sheet : null,
               getSheets: () => [sheet], deleteSheet() {} };
  const item = () => { const o = { setTitle: () => o, setChoiceValues: () => o, setRequired: () => o }; return o; };
  const form = { setDescription: () => form, addListItem: item, addTextItem: item, setDestination() {},
                 getId: () => 'FORM', getEditUrl: () => 'e' };
  const ctx = {
    rows,
    PropertiesService: { getScriptProperties: () => ({
      getProperty: k => props[k] || null, setProperties: o => Object.assign(props, o) }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    FormApp: { create: () => form, openById: () => form, DestinationType: { SPREADSHEET: 1 } },
    SpreadsheetApp: { create: () => ss, openById: () => ss, flush() {} },
    Utilities: { sleep() {}, formatDate: d => d.toISOString().slice(11, 19) },
    Session: { getScriptTimeZone: () => 'America/Chicago' },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: s => ({ setMimeType: () => JSON.parse(s) }) },
    Logger: { log() {} }, Date, JSON, String, Number
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'backend', 'Code.js'), 'utf8'), ctx);
  return ctx;
}

let pass = 0;
const t = (name, fn) => { fn(); pass++; console.log('  ok  ' + name); };
const g = load();
const post = code => g.doPost({ postData: { contents: JSON.stringify({ code }) } });

t('parse: alias + number, dash optional, zeros and case folded', () => {
  assert.deepStrictEqual({ ...g.parseCode('DCT-1234') }, { finisher: 'DCT', item: '1234', code: 'DCT-1234' });
  assert.strictEqual(g.parseCode('dct1').code, 'DCT-1');
  assert.strictEqual(g.parseCode(' PLM-0007 ').code, 'PLM-7');
  assert.strictEqual(g.parseCode('STR-0').code, 'STR-0');
  assert.strictEqual(g.parseCode('DC-12'), null);
  assert.strictEqual(g.parseCode('DCTX-12'), null);
  assert.strictEqual(g.parseCode('https://example.com'), null);
  assert.strictEqual(g.parseCode(''), null);
});

t('first scan is recorded as Timestamp, Finisher, Item #, Barcode', () => {
  const r = post('DCT-1234');
  assert.strictEqual(r.ok, true); assert.strictEqual(r.dup, false);
  assert.strictEqual(r.finisher, 'DCT'); assert.strictEqual(r.item, '1234');
  assert.strictEqual(g.rows.length, 1);
  assert.ok(g.rows[0][0] instanceof Date);
  assert.deepStrictEqual([...g.rows[0].slice(1)], ['DCT', '1234', 'DCT-1234']);
});

t('the same sticker again is a dup, nothing appended, original time returned', () => {
  const r = post('DCT-1234');
  assert.strictEqual(r.dup, true); assert.strictEqual(g.rows.length, 1);
  assert.strictEqual(r.at, g.rows[0][0].toISOString().slice(11, 19));
});

t('dup is caught through zero-padding / lowercase / missing dash', () => {
  for (const c of ['DCT-01234', 'dct-1234', 'DCT1234']) assert.strictEqual(post(c).dup, true, c);
  assert.strictEqual(g.rows.length, 1);
});

t('same number, different finisher is a different duct', () => {
  assert.strictEqual(post('PLM-1234').dup, false); assert.strictEqual(g.rows.length, 2);
});

t('unknown alias and junk are refused, not written', () => {
  const a = post('XYZ-5'); assert.strictEqual(a.ok, false); assert.match(a.error, /Unknown finisher XYZ/);
  const b = post('hello'); assert.strictEqual(b.ok, false); assert.match(b.error, /Not a duct label/);
  assert.strictEqual(g.rows.length, 2);
});

t('GET ?codes lists every code with its time', () => {
  const r = g.doGet({ parameter: { codes: '1' } });
  assert.deepStrictEqual([...r.codes.map(c => c[0])], ['DCT-1234', 'PLM-1234']);
});

t('setup is idempotent', () => {
  g.setup(); g.setup(); assert.strictEqual(g.rows.length, 2);
});

console.log(pass + ' passed');
