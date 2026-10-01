"""Build the Dashboard / Shift Log / Cycles / Shifts tabs of the Duct Finishing Scans sheet.

Everything is a live formula over 'Form Responses 1', which is never written
(the raw log stays raw). Re-running rebuilds the formula tabs in place, keeping
their sheet IDs so bookmarked links survive. Shifts!B4:D6 + B9:B11 are the
settings people edit; a re-run leaves an existing Shifts tab alone.

TWO RATES, because finishers sometimes save their scans for the end of the shift:
  SHIFT RATE  (headline) = paid shift minutes / ducts scanned in that shift.
              Immune to when the scans happen, as long as they happen in the shift.
  LIVE CYCLE  = minutes between back-to-back scans, but only gaps between two
              scans that were each made live. A scan within `fastest real
              cycle` of its neighbour is a BATCH scan; its gaps are not counted.
  SCANNED LIVE % = share of a finisher's scans that were not batch scans - says
              how far to trust their live cycle.

A scan belongs to the shift whose window [start, end + late grace] holds it;
overnight shifts (end < start) belong to the day they started. A scan outside
every window counts nowhere and is reported on the dashboard.

    python sheet/build_dashboard.py
"""
import sys
sys.path.insert(0, r"C:\Users\Evan\Downloads\GEI-Scan-PWA\tests")
import gs  # Keder-account Sheets REST client (same token as the sheets MCP)

SID = "1wZLOyNFVtvsP4Y8wpKxYyk7wUxvsGyrU-LFORCI6tWI"
FR = "'Form Responses 1'"
LOG = "'Shift Log'"
ROWS = 15                       # finisher rows on the dashboard
F0, F1 = 8, 8 + ROWS - 1        # finisher rows 8..22
TEAM_ROW = F1 + 1

# ---------------- Shifts (settings) ----------------
SHIFT_NAMES, SHIFT_START, SHIFT_END, SHIFT_BRK = "Shifts!$A$4:$A$6", "Shifts!$B$4:$B$6", "Shifts!$C$4:$C$6", "Shifts!$D$4:$D$6"
GRACE, MAXGAP, MINCYC = "Shifts!$B$9", "Shifts!$B$10", "Shifts!$B$11"
CUR_SH, CUR_DT = "Shifts!$B$14", "Shifts!$B$15"

# the shift (name) whose window holds time-of-day h; "" if none
def in_shift(h):
    return (f'IFERROR(INDEX(FILTER({SHIFT_NAMES}, ({SHIFT_NAMES}<>"")*IF({SHIFT_END}>{SHIFT_START}, '
            f'({h}>={SHIFT_START})*({h}<={SHIFT_END}+{GRACE}/1440), '
            f'(({h}>={SHIFT_START})+({h}<={SHIFT_END}+{GRACE}/1440))>0)), 1), "")')

# the calendar day a shift started, for a timestamp a inside shift x
def shift_day(a, x):
    return (f'INT({a}) - IF(AND(XLOOKUP({x}, {SHIFT_NAMES}, {SHIFT_END}) < XLOOKUP({x}, {SHIFT_NAMES}, {SHIFT_START}), '
            f'MOD({a}, 1) < XLOOKUP({x}, {SHIFT_NAMES}, {SHIFT_START})), 1, 0)')

SHIFTS = [
    ["Shifts — edit the yellow cells; every number on the dashboard follows them"],
    [],
    ["Shift", "Start", "End", "Unpaid break (min)"],
    ["Day", "7:00 AM", "3:30 PM", 30],
    ["", "", "", ""],
    ["", "", "", ""],
    [],
    ["Settings", "Minutes"],
    ["Late-scan grace after shift end", 60],
    ["Longest gap that still counts as work", 60],
    ["Fastest real cycle (quicker = batch scan)", 1],
    [],
    ["Current shift (calculated — don't edit)"],
    ["Shift",
     f'=LET(cs, {in_shift("MOD(NOW(),1)")}, IF(cs<>"", cs, IFERROR(INDEX({LOG}!B2:B, 1), "")))'],
    ["Shift date",
     f'=LET(cs, {in_shift("MOD(NOW(),1)")}, IF(cs<>"", {shift_day("NOW()", "cs")}, IFERROR(INDEX({LOG}!A2:A, 1), "")))'],
    ["Room for 3 shifts in rows 4-6. An overnight shift (end earlier than start) belongs to the day it starts."],
]

# ---------------- Cycles: one row per scan ----------------
CYCLES = f"""=IFERROR(LET(
  r, FILTER({{{FR}!A2:A, {FR}!B2:B, {FR}!D2:D}}, ISNUMBER({FR}!A2:A), {FR}!B2:B<>""),
  d, SORT(r, 2, TRUE, 1, TRUE),
  n, ROWS(d), t, INDEX(d, 0, 1), f, INDEX(d, 0, 2),
  mn, {MINCYC}/1440, mx, {MAXGAP},
  pt, IFERROR(VSTACK("", CHOOSEROWS(t, SEQUENCE(n-1))), {{""}}),
  pf, IFERROR(VSTACK("", CHOOSEROWS(f, SEQUENCE(n-1))), {{""}}),
  nt, IFERROR(VSTACK(CHOOSEROWS(t, SEQUENCE(n-1, 1, 2)), ""), {{""}}),
  nf, IFERROR(VSTACK(CHOOSEROWS(f, SEQUENCE(n-1, 1, 2)), ""), {{""}}),
  prev, MAP(f, pt, pf, LAMBDA(b, c, e, IF(b=e, c, ""))),
  nxt, MAP(f, nt, nf, LAMBDA(b, c, e, IF(b=e, c, ""))),
  burst, MAP(t, prev, nxt, LAMBDA(a, p, q, OR(IF(p="", FALSE, a-p<mn), IF(q="", FALSE, q-a<mn)))),
  pburst, IFERROR(VSTACK(FALSE, CHOOSEROWS(burst, SEQUENCE(n-1))), {{FALSE}}),
  gap, MAP(t, prev, LAMBDA(a, p, IF(p="", "", ROUND((a-p)*1440, 2)))),
  st, MAP(gap, burst, pburst, LAMBDA(g, b, pb, IF(g="", "first scan",
        IF(g>mx, "dropped (>"&mx&" min)", IF(OR(b, pb), "batch scan", "counted"))))),
  sh, MAP(t, LAMBDA(a, {in_shift("MOD(a,1)")})),
  sd, MAP(t, sh, LAMBDA(a, x, IF(x="", "", {shift_day("a", "x")}))),
  HSTACK(d, prev, gap, st, MAP(burst, LAMBDA(b, IF(b, "yes", ""))), MAP(sh, LAMBDA(x, IF(x="", "outside shift", x))), sd)), "")"""

# ---------------- Shift Log: one row per finisher per shift ----------------
C_ = lambda col: f"Cycles!{col}2:{col}"
SHIFT_LOG = f"""=IFERROR(LET(
  k, SORT(UNIQUE(FILTER({{{C_('I')}, {C_('H')}, {C_('B')}}}, ISNUMBER({C_('I')}))), 1, FALSE, 2, TRUE, 3, TRUE),
  dt, INDEX(k, 0, 1), sh, INDEX(k, 0, 2), fi, INDEX(k, 0, 3),
  ducts, MAP(dt, sh, fi, LAMBDA(a, b, c, COUNTIFS({C_('I')}, a, {C_('H')}, b, {C_('B')}, c))),
  len, MAP(sh, LAMBDA(b, LET(s, XLOOKUP(b, {SHIFT_NAMES}, {SHIFT_START}), e, XLOOKUP(b, {SHIFT_NAMES}, {SHIFT_END}), (e - s + (e < s)) * 1440))),
  paid, MAP(dt, sh, len, LAMBDA(a, b, L, LET(st, a + XLOOKUP(b, {SHIFT_NAMES}, {SHIFT_START}), brk, XLOOKUP(b, {SHIFT_NAMES}, {SHIFT_BRK}),
        el, MAX(0, MIN(NOW(), st + L/1440) - st) * 1440, ROUND(el - brk * el / L, 0)))),
  mpd, MAP(paid, ducts, LAMBDA(p, c, IF(OR(c=0, p=0), "—", ROUND(p / c, 1)))),
  dph, MAP(paid, ducts, LAMBDA(p, c, IF(p=0, "—", ROUND(c / (p / 60), 1)))),
  live, MAP(dt, sh, fi, LAMBDA(a, b, c, IFERROR(ROUND(AVERAGEIFS({C_('E')}, {C_('I')}, a, {C_('H')}, b, {C_('B')}, c, {C_('F')}, "counted"), 1), "—"))),
  lp, MAP(dt, sh, fi, ducts, LAMBDA(a, b, c, n, COUNTIFS({C_('I')}, a, {C_('H')}, b, {C_('B')}, c, {C_('G')}, "<>yes") / n)),
  state, MAP(dt, sh, len, LAMBDA(a, b, L, IF(NOW() < a + XLOOKUP(b, {SHIFT_NAMES}, {SHIFT_START}) + L/1440, "in progress", "done"))),
  HSTACK(k, ducts, paid, mpd, dph, live, lp, state)), "")"""

# ---------------- Dashboard ----------------
A = f"A{F0}:A{F1}"
cur = f"{LOG}!A2:A, {CUR_DT}, {LOG}!B2:B, {CUR_SH}"


def per(expr):
    return f'=MAP({A}, LAMBDA(a, IF(a="", "", {expr})))'


def ratio(num, den, k=1, digits=1):
    """num/den per finisher row; num & den are expressions of a."""
    return per(f'IFERROR(ROUND({k} * ({num}) / ({den}), {digits}), "—")')


DASH = [
    ["Duct Finishing — Production"],
    [f'=IF({CUR_SH}="", "No shift yet", "This shift: "&{CUR_SH}&" · "&TEXT({CUR_DT}, "ddd m/d")&'
     f'IF(NOW() < {CUR_DT} + XLOOKUP({CUR_SH}, {SHIFT_NAMES}, {SHIFT_START}) + '
     f'(XLOOKUP({CUR_SH}, {SHIFT_NAMES}, {SHIFT_END}) - XLOOKUP({CUR_SH}, {SHIFT_NAMES}, {SHIFT_START}) + '
     f'(XLOOKUP({CUR_SH}, {SHIFT_NAMES}, {SHIFT_END}) < XLOOKUP({CUR_SH}, {SHIFT_NAMES}, {SHIFT_START}))), '
     f'"  (in progress — rates use paid time so far)", "  (finished)")&"   ·   last scan "&'
     f'IFERROR(TEXT(MAX({FR}!A2:A), "m/d h:mm AM/PM"), "none"))'],
    ['="Min / duct = paid shift minutes ÷ ducts (breaks taken out) — fair even if scans are saved for the end. '
     'Live cycle = time between scans made as each duct is finished; batch scans are left out. Shift hours: Shifts tab."'],
    [f'=LET(o, COUNTIF(Cycles!H2:H, "outside shift"), IF(o=0, "", "⚠ "&o&" scan(s) fall outside every shift and are not counted — '
     f'check the hours on the Shifts tab (list: Cycles tab, column H)."))'],
    [],
    ["", "THIS SHIFT", "", "", "", "", "ALL TIME"],
    ["Finisher", "Ducts", "Min / duct", "Ducts / hr", "Live cycle (min)", "Scanned live",
     "Ducts", "Shifts", "Min / duct", "Ducts / hr", "Live cycle (min)", "Scanned live"],
]
FIN = [
    f'=IFERROR(SORT(UNIQUE(FILTER({FR}!B2:B, {FR}!B2:B<>""))), "")',
    per(f"SUMIFS({LOG}!D2:D, {cur}, {LOG}!C2:C, a)"),
    ratio(f"SUMIFS({LOG}!E2:E, {cur}, {LOG}!C2:C, a)", f"SUMIFS({LOG}!D2:D, {cur}, {LOG}!C2:C, a)"),
    ratio(f"SUMIFS({LOG}!D2:D, {cur}, {LOG}!C2:C, a)", f"SUMIFS({LOG}!E2:E, {cur}, {LOG}!C2:C, a)", k=60),
    per(f'IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, Cycles!I2:I, {CUR_DT}, Cycles!H2:H, {CUR_SH}, Cycles!B2:B, a, Cycles!F2:F, "counted"), 1), "—")'),
    ratio(f'COUNTIFS(Cycles!I2:I, {CUR_DT}, Cycles!H2:H, {CUR_SH}, Cycles!B2:B, a, Cycles!G2:G, "<>yes")',
          f"COUNTIFS(Cycles!I2:I, {CUR_DT}, Cycles!H2:H, {CUR_SH}, Cycles!B2:B, a)", digits=2),
    per(f"SUMIFS({LOG}!D2:D, {LOG}!C2:C, a)"),
    per(f"COUNTIFS({LOG}!C2:C, a)"),
    ratio(f"SUMIFS({LOG}!E2:E, {LOG}!C2:C, a)", f"SUMIFS({LOG}!D2:D, {LOG}!C2:C, a)"),
    ratio(f"SUMIFS({LOG}!D2:D, {LOG}!C2:C, a)", f"SUMIFS({LOG}!E2:E, {LOG}!C2:C, a)", k=60),
    per(f'IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, Cycles!B2:B, a, Cycles!F2:F, "counted"), 1), "—")'),
    ratio('COUNTIFS(Cycles!B2:B, a, Cycles!G2:G, "<>yes", Cycles!H2:H, "<>outside shift")',
          'COUNTIFS(Cycles!B2:B, a, Cycles!H2:H, "<>outside shift")', digits=2),
]
r = lambda col: f"{col}{F0}:{col}{F1}"
TEAM = [
    "All finishers",
    f"=SUM({r('B')})",
    f'=IFERROR(ROUND(SUMIFS({LOG}!E2:E, {cur}) / SUMIFS({LOG}!D2:D, {cur}), 1), "—")',
    f'=IF(B{TEAM_ROW}=0, "—", IFERROR(ROUND(SUM({r("D")}), 1), "—"))',
    f'=IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, Cycles!I2:I, {CUR_DT}, Cycles!H2:H, {CUR_SH}, Cycles!F2:F, "counted"), 1), "—")',
    f'=IFERROR(ROUND(COUNTIFS(Cycles!I2:I, {CUR_DT}, Cycles!H2:H, {CUR_SH}, Cycles!G2:G, "<>yes") / '
    f'COUNTIFS(Cycles!I2:I, {CUR_DT}, Cycles!H2:H, {CUR_SH}), 2), "—")',
    f"=SUM({r('G')})",
    f"=IFERROR(ROWS(UNIQUE(FILTER({{{LOG}!A2:A, {LOG}!B2:B}}, {LOG}!A2:A<>\"\"))), 0)",
    f'=IFERROR(ROUND(SUM({LOG}!E2:E) / SUM({LOG}!D2:D), 1), "—")',
    f'=IFERROR(ROUND(SUM({r("J")}), 1), "—")',
    f'=IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, Cycles!F2:F, "counted"), 1), "—")',
    f'=IFERROR(ROUND(COUNTIFS(Cycles!G2:G, "<>yes", Cycles!H2:H, "<>outside shift", Cycles!B2:B, "<>") / '
    f'COUNTIFS(Cycles!H2:H, "<>outside shift", Cycles!B2:B, "<>"), 2), "—")',
]

# ---------------- formatting helpers ----------------
NAVY = {"red": .07, "green": .16, "blue": .25}
TINT = {"red": .91, "green": .94, "blue": .97}
YELLOW = {"red": 1, "green": .95, "blue": .7}
GREY = {"red": .35, "green": .4, "blue": .45}
WHITE_B = {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}


def rng(sid, r0, r1, c0, c1):
    return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def fmt(r, cell):
    return {"repeatCell": {"range": r, "cell": {"userEnteredFormat": cell},
                           "fields": "userEnteredFormat(" + ",".join(cell) + ")"}}


def num(p, kind="NUMBER"):
    return {"numberFormat": {"type": kind, "pattern": p}, "horizontalAlignment": "CENTER"}


def width(sid, c0, c1, px):
    return {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": c0, "endIndex": c1},
                                          "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def ensure_tabs():
    """Create missing tabs; wipe the formula tabs in place (same sheetId) so links survive."""
    meta = gs.get_meta(SID, fields="sheets(properties(sheetId,title,index),conditionalFormats,merges)")["sheets"]
    have = {s["properties"]["title"]: s for s in meta}
    spec = {"Dashboard": (0, TEAM_ROW + 2, 12), "Shift Log": (2, 2000, 10), "Cycles": (3, 50000, 9), "Shifts": (4, 20, 6)}
    reqs = []
    for title, (idx, rows, cols) in spec.items():
        s = have.get(title)
        if not s:
            reqs.append({"addSheet": {"properties": {"title": title, "index": idx,
                                                     "gridProperties": {"rowCount": rows, "columnCount": cols}}}})
            continue
        if title == "Shifts":
            continue  # settings: keep whatever people typed
        sid = s["properties"]["sheetId"]
        for _ in s.get("conditionalFormats", []):
            reqs.append({"deleteConditionalFormatRule": {"sheetId": sid, "index": 0}})
        if s.get("merges"):
            reqs.append({"unmergeCells": {"range": {"sheetId": sid}}})
        reqs += [
            {"updateCells": {"range": {"sheetId": sid}, "fields": "*"}},
            {"updateSheetProperties": {"properties": {"sheetId": sid, "index": idx, "gridProperties":
                                                      {"rowCount": rows, "columnCount": cols, "frozenRowCount": 0}},
                                       "fields": "index,gridProperties(rowCount,columnCount,frozenRowCount)"}},
        ]
    if reqs:
        gs.batch_update(SID, reqs)
    return not have.get("Shifts"), gs.sheet_ids(SID)


def main():
    new_shifts, ids = ensure_tabs()
    d, lg, c, sh = ids["Dashboard"], ids["Shift Log"], ids["Cycles"], ids["Shifts"]

    data = [
        {"range": "Cycles!A1", "values": [["Timestamp", "Finisher", "Barcode", "Previous scan (same finisher)",
                                           "Gap (min)", "Gap counted?", "Batch scan?", "Shift", "Shift date"]]},
        {"range": "Cycles!A2", "values": [[CYCLES]]},
        {"range": f"{LOG}!A1", "values": [["Shift date", "Shift", "Finisher", "Ducts", "Paid min", "Min / duct",
                                           "Ducts / hr", "Live cycle (min)", "Scanned live", "Status"]]},
        {"range": f"{LOG}!A2", "values": [[SHIFT_LOG]]},
        {"range": "Dashboard!A1", "values": DASH},
        {"range": f"Dashboard!A{F0}", "values": [FIN]},
        {"range": f"Dashboard!A{TEAM_ROW}", "values": [TEAM]},
    ]
    if new_shifts:
        data.insert(0, {"range": "Shifts!A1", "values": SHIFTS})
    else:  # keep the settings, refresh only the calculated cells
        data.insert(0, {"range": "Shifts!A13", "values": SHIFTS[12:]})
    gs.batch_update_values(SID, data)

    reqs = [
        # Shifts
        fmt(rng(sh, 0, 1, 0, 4), {"textFormat": {"bold": True, "fontSize": 13, "foregroundColor": NAVY}}),
        fmt(rng(sh, 2, 3, 0, 4), {"backgroundColor": NAVY, "textFormat": WHITE_B}),
        fmt(rng(sh, 7, 8, 0, 2), {"backgroundColor": NAVY, "textFormat": WHITE_B}),
        fmt(rng(sh, 12, 13, 0, 2), {"textFormat": {"bold": True, "foregroundColor": GREY}}),
        fmt(rng(sh, 3, 6, 0, 4), {"backgroundColor": YELLOW}),
        fmt(rng(sh, 8, 11, 1, 2), {"backgroundColor": YELLOW, "horizontalAlignment": "CENTER"}),
        fmt(rng(sh, 3, 6, 1, 3), {"numberFormat": {"type": "TIME", "pattern": "h:mm AM/PM"}, "horizontalAlignment": "CENTER"}),
        fmt(rng(sh, 3, 6, 3, 4), {"horizontalAlignment": "CENTER"}),
        fmt(rng(sh, 14, 15, 1, 2), {"numberFormat": {"type": "DATE", "pattern": "ddd m/d/yyyy"}}),
        fmt(rng(sh, 15, 16, 0, 1), {"textFormat": {"italic": True, "foregroundColor": GREY}}),
        width(sh, 0, 1, 290), width(sh, 1, 4, 120),
        # Cycles
        fmt(rng(c, 0, 1, 0, 9), {"backgroundColor": NAVY, "textFormat": WHITE_B}),
        fmt(rng(c, 1, 50000, 0, 1), {"numberFormat": {"type": "DATE_TIME", "pattern": "m/d h:mm:ss AM/PM"}}),
        fmt(rng(c, 1, 50000, 3, 4), {"numberFormat": {"type": "DATE_TIME", "pattern": "m/d h:mm:ss AM/PM"}}),
        fmt(rng(c, 1, 50000, 4, 5), {"numberFormat": {"type": "NUMBER", "pattern": "0.0"}}),
        fmt(rng(c, 1, 50000, 8, 9), {"numberFormat": {"type": "DATE", "pattern": "ddd m/d"}}),
        width(c, 0, 1, 150), width(c, 1, 3, 80), width(c, 3, 4, 200), width(c, 4, 9, 110),
        {"updateSheetProperties": {"properties": {"sheetId": c, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(c, 1, 50000, 4, 7)], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$F2<>"counted"'}]},
            "format": {"textFormat": {"foregroundColor": {"red": .6, "green": .6, "blue": .6}, "italic": True}}}}}},
        {"addConditionalFormatRule": {"index": 1, "rule": {"ranges": [rng(c, 1, 50000, 7, 8)], "booleanRule": {
            "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "outside shift"}]},
            "format": {"textFormat": {"foregroundColor": {"red": .75, "green": .2, "blue": .15}, "bold": True}}}}}},
        # Shift Log
        fmt(rng(lg, 0, 1, 0, 10), {"backgroundColor": NAVY, "textFormat": WHITE_B, "horizontalAlignment": "CENTER"}),
        fmt(rng(lg, 1, 2000, 0, 1), {"numberFormat": {"type": "DATE", "pattern": "ddd m/d/yyyy"}}),
        fmt(rng(lg, 1, 2000, 3, 5), num("0")),
        fmt(rng(lg, 1, 2000, 5, 8), num("0.0")),
        fmt(rng(lg, 1, 2000, 8, 9), num("0%", "PERCENT")),
        fmt(rng(lg, 1, 2000, 9, 10), {"horizontalAlignment": "CENTER"}),
        width(lg, 0, 1, 120), width(lg, 1, 10, 95),
        {"updateSheetProperties": {"properties": {"sheetId": lg, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        # Dashboard
        fmt(rng(d, 0, 1, 0, 12), {"textFormat": {"fontSize": 18, "bold": True, "foregroundColor": NAVY}}),
        fmt(rng(d, 1, 2, 0, 12), {"textFormat": {"fontSize": 11, "bold": True, "foregroundColor": NAVY}}),
        fmt(rng(d, 2, 3, 0, 12), {"textFormat": {"fontSize": 10, "foregroundColor": GREY}}),
        fmt(rng(d, 3, 4, 0, 12), {"textFormat": {"fontSize": 10, "bold": True, "foregroundColor": {"red": .75, "green": .2, "blue": .15}}}),
        {"mergeCells": {"range": rng(d, 5, 6, 1, 6), "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": rng(d, 5, 6, 6, 12), "mergeType": "MERGE_ALL"}},
        fmt(rng(d, 5, 6, 1, 12), {"backgroundColor": NAVY, "textFormat": WHITE_B, "horizontalAlignment": "CENTER"}),
        fmt(rng(d, 6, 7, 0, 12), {"backgroundColor": TINT, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER",
                                  "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}),
        fmt(rng(d, 7, TEAM_ROW, 0, 1), {"textFormat": {"bold": True, "fontSize": 12}}),
        fmt(rng(d, 7, TEAM_ROW, 1, 2), num("0")),
        fmt(rng(d, 7, TEAM_ROW, 2, 5), num("0.0")),
        fmt(rng(d, 7, TEAM_ROW, 5, 6), num("0%", "PERCENT")),
        fmt(rng(d, 7, TEAM_ROW, 6, 8), num("0")),
        fmt(rng(d, 7, TEAM_ROW, 8, 11), num("0.0")),
        fmt(rng(d, 7, TEAM_ROW, 11, 12), num("0%", "PERCENT")),
        fmt(rng(d, 7, TEAM_ROW, 2, 3), {"textFormat": {"bold": True, "fontSize": 12}}),
        fmt(rng(d, 7, TEAM_ROW, 8, 9), {"textFormat": {"bold": True, "fontSize": 12}}),
        fmt(rng(d, TEAM_ROW - 1, TEAM_ROW, 0, 12), {"backgroundColor": TINT, "textFormat": {"bold": True},
                                                    "borders": {"top": {"style": "SOLID_MEDIUM", "color": NAVY}}}),
        {"updateBorders": {"range": rng(d, 5, TEAM_ROW, 6, 7), "left": {"style": "SOLID_MEDIUM", "color": NAVY}}},
        # live % below half: the live cycle for that person can't be trusted
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(d, 7, TEAM_ROW, 5, 6), rng(d, 7, TEAM_ROW, 11, 12)],
            "booleanRule": {"condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0.5"}]},
                            "format": {"backgroundColor": {"red": .99, "green": .89, "blue": .87},
                                       "textFormat": {"foregroundColor": {"red": .7, "green": .15, "blue": .1}, "bold": True}}}}}},
        width(d, 0, 1, 130), width(d, 1, 12, 92),
        {"updateDimensionProperties": {"range": {"sheetId": d, "dimension": "ROWS", "startIndex": 6, "endIndex": 7},
                                       "properties": {"pixelSize": 40}, "fields": "pixelSize"}},
        {"updateSheetProperties": {"properties": {"sheetId": d, "gridProperties": {"frozenRowCount": 7, "hideGridlines": True}},
                                   "fields": "gridProperties(frozenRowCount,hideGridlines)"}},
        # NOW() drives "in progress" paid time: recalc every minute, not only on edit
        {"updateSpreadsheetProperties": {"properties": {"autoRecalc": "MINUTE"}, "fields": "autoRecalc"}},
    ]
    gs.batch_update(SID, reqs)
    print("built Dashboard, Shift Log, Cycles" + (", Shifts (new)" if new_shifts else " (Shifts kept)"))


if __name__ == "__main__":
    main()
