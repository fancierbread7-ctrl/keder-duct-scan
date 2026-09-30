"""Add the Cycles + Dashboard tabs to the Duct Finishing Scans sheet.

Everything is a live formula over 'Form Responses 1', so it updates as scans
land. Re-running rebuilds both tabs from scratch; the responses tab is never
written.

CYCLE TIME = minutes between a finisher's consecutive scans. A gap over 60 min
is a break or a shift change, not work, so it is dropped (Evan, 2026-09-30).
THIS SHIFT = today since midnight, sheet time zone (America/Chicago).

    python sheet/build_dashboard.py
"""
import sys
sys.path.insert(0, r"C:\Users\Evan\Downloads\GEI-Scan-PWA\tests")
import gs  # Keder-account Sheets REST client (same token as the sheets MCP)

SID = "1wZLOyNFVtvsP4Y8wpKxYyk7wUxvsGyrU-LFORCI6tWI"
FR = "'Form Responses 1'"
MAX_GAP = 60
ROWS = 15  # finisher rows reserved on the dashboard

CYCLES = f"""=IFERROR(LET(
  r, FILTER({{{FR}!A2:A, {FR}!B2:B, {FR}!D2:D}}, ISNUMBER({FR}!A2:A), {FR}!B2:B<>""),
  d, SORT(r, 2, TRUE, 1, TRUE),
  n, ROWS(d),
  t, INDEX(d, 0, 1), f, INDEX(d, 0, 2),
  pt, IFERROR(VSTACK("", CHOOSEROWS(t, SEQUENCE(n-1))), {{""}}),
  pf, IFERROR(VSTACK("", CHOOSEROWS(f, SEQUENCE(n-1))), {{""}}),
  prev, MAP(f, pt, pf, LAMBDA(b, c, e, IF(b=e, c, ""))),
  gap, MAP(t, prev, LAMBDA(a, c, IF(c="", "", ROUND((a-c)*1440, 2)))),
  st, MAP(gap, LAMBDA(g, IF(g="", "first scan", IF(g>{MAX_GAP}, "dropped (>1h)", "counted")))),
  HSTACK(d, prev, gap, st)), "")"""

A = f"A7:A{6 + ROWS}"
C = f"C7:C{6 + ROWS}"
F = f"F7:F{6 + ROWS}"
TODAY = f'{FR}!A2:A, ">="&TODAY()'
CTODAY = 'Cycles!A2:A, ">="&TODAY()'
OK = 'Cycles!F2:F, "counted"'


def per(expr):
    return f'=MAP({A}, LAMBDA(a, IF(a="", "", {expr})))'


def rate(col):
    return f'=MAP({A}, {col}, LAMBDA(a, c, IF(a="", "", IF(ISNUMBER(c), IF(c>0, ROUND(60/c, 1), "—"), "—"))))'


DASH = [
    ["Duct Finishing — Production"],
    [f'="This shift = today, "&TEXT(TODAY(), "ddd m/d")&"   ·   last scan "&IFERROR(TEXT(MAX({FR}!A2:A), "m/d h:mm AM/PM"), "none")'],
    [f'="Cycle time = minutes between a finisher\'s back-to-back scans. Gaps over {MAX_GAP} min are breaks or shift changes and are left out."'],
    [],
    ["", "THIS SHIFT", "", "", "ALL TIME"],
    ["Finisher", "Ducts", "Avg cycle (min)", "Ducts / hr", "Ducts", "Avg cycle (min)", "Ducts / hr", "Cycles counted"],
    # row 7 is written below: team row sits at the bottom so the finisher list can spill
]
FIN = [
    f'=IFERROR(SORT(UNIQUE(FILTER({FR}!B2:B, {FR}!B2:B<>""))), "")',
    per(f"COUNTIFS({FR}!B2:B, a, {TODAY})"),
    per(f'IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, Cycles!B2:B, a, {OK}, {CTODAY}), 1), "—")'),
    rate(C),
    per(f"COUNTIFS({FR}!B2:B, a)"),
    per(f'IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, Cycles!B2:B, a, {OK}), 1), "—")'),
    rate(F),
    per(f"COUNTIFS(Cycles!B2:B, a, {OK})"),
]
TEAM_ROW = 7 + ROWS
TEAM = [
    "All finishers",
    f"=COUNTIFS({TODAY})",
    f'=IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, {OK}, {CTODAY}), 1), "—")',
    f'=IFERROR(ROUND(SUM(D7:D{6 + ROWS}), 1), "—")',   # combined floor throughput
    f'=COUNT({FR}!A2:A)',
    f'=IFERROR(ROUND(AVERAGEIFS(Cycles!E2:E, {OK}), 1), "—")',
    f'=IFERROR(ROUND(SUM(G7:G{6 + ROWS}), 1), "—")',
    f'=COUNTIFS({OK})',
]


def main():
    ids = gs.sheet_ids(SID)
    reqs = []
    for title in ("Dashboard", "Cycles"):
        if title in ids:
            reqs.append({"deleteSheet": {"sheetId": ids[title]}})
    reqs += [
        {"addSheet": {"properties": {"title": "Dashboard", "index": 0,
                                     "gridProperties": {"rowCount": TEAM_ROW + 2, "columnCount": 8}}}},
        {"addSheet": {"properties": {"title": "Cycles", "index": 2,
                                     "gridProperties": {"rowCount": 2000, "columnCount": 6, "frozenRowCount": 1}}}},
    ]
    gs.batch_update(SID, reqs)
    ids = gs.sheet_ids(SID)
    d, c = ids["Dashboard"], ids["Cycles"]

    gs.batch_update_values(SID, [
        {"range": "Cycles!A1", "values": [["Timestamp", "Finisher", "Barcode", "Previous scan (same finisher)",
                                           "Cycle (min)", "Counted?"]]},
        {"range": "Cycles!A2", "values": [[CYCLES]]},
        {"range": "Dashboard!A1", "values": DASH},
        {"range": "Dashboard!A7", "values": [FIN]},
        {"range": f"Dashboard!A{TEAM_ROW}", "values": [TEAM]},
    ])

    def rng(sid, r0, r1, c0, c1):
        return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}

    def fmt(r, cell, fields):
        return {"repeatCell": {"range": r, "cell": {"userEnteredFormat": cell}, "fields": "userEnteredFormat(" + fields + ")"}}

    NAVY, TINT, LINE = {"red": .07, "green": .16, "blue": .25}, {"red": .91, "green": .94, "blue": .97}, {"red": .8, "green": .84, "blue": .88}
    white = {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
    num = lambda p: {"numberFormat": {"type": "NUMBER", "pattern": p}, "horizontalAlignment": "CENTER"}
    dt = {"numberFormat": {"type": "DATE_TIME", "pattern": "m/d h:mm:ss AM/PM"}}
    gs.batch_update(SID, [
        # dashboard
        fmt(rng(d, 0, 1, 0, 8), {"textFormat": {"fontSize": 18, "bold": True, "foregroundColor": NAVY}}, "textFormat"),
        fmt(rng(d, 1, 3, 0, 8), {"textFormat": {"fontSize": 10, "foregroundColor": {"red": .35, "green": .4, "blue": .45}}}, "textFormat"),
        {"mergeCells": {"range": rng(d, 4, 5, 1, 4), "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": rng(d, 4, 5, 4, 8), "mergeType": "MERGE_ALL"}},
        fmt(rng(d, 4, 5, 1, 8), {"backgroundColor": NAVY, "textFormat": white, "horizontalAlignment": "CENTER"},
            "backgroundColor,textFormat,horizontalAlignment"),
        fmt(rng(d, 5, 6, 0, 8), {"backgroundColor": TINT, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER",
                                 "wrapStrategy": "WRAP"}, "backgroundColor,textFormat,horizontalAlignment,wrapStrategy"),
        fmt(rng(d, 6, TEAM_ROW, 0, 1), {"textFormat": {"bold": True, "fontSize": 12}}, "textFormat"),
        fmt(rng(d, 6, TEAM_ROW, 1, 2), num("0"), "numberFormat,horizontalAlignment"),
        fmt(rng(d, 6, TEAM_ROW, 2, 4), num("0.0"), "numberFormat,horizontalAlignment"),
        fmt(rng(d, 6, TEAM_ROW, 4, 5), num("0"), "numberFormat,horizontalAlignment"),
        fmt(rng(d, 6, TEAM_ROW, 5, 7), num("0.0"), "numberFormat,horizontalAlignment"),
        fmt(rng(d, 6, TEAM_ROW, 7, 8), num("0"), "numberFormat,horizontalAlignment"),
        fmt(rng(d, 6, TEAM_ROW, 1, 2), {"textFormat": {"bold": True, "fontSize": 12}}, "textFormat"),
        fmt(rng(d, TEAM_ROW - 1, TEAM_ROW, 0, 8), {"backgroundColor": TINT, "textFormat": {"bold": True},
                                                   "borders": {"top": {"style": "SOLID_MEDIUM", "color": NAVY}}},
            "backgroundColor,textFormat,borders"),
        {"updateBorders": {"range": rng(d, 4, TEAM_ROW, 4, 5), "left": {"style": "SOLID", "color": LINE}}},
        {"updateDimensionProperties": {"range": {"sheetId": d, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                                       "properties": {"pixelSize": 130}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": d, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 8},
                                       "properties": {"pixelSize": 105}, "fields": "pixelSize"}},
        {"updateSheetProperties": {"properties": {"sheetId": d, "gridProperties": {"frozenRowCount": 6, "hideGridlines": True}},
                                   "fields": "gridProperties(frozenRowCount,hideGridlines)"}},
        # cycles
        fmt(rng(c, 0, 1, 0, 6), {"backgroundColor": NAVY, "textFormat": white}, "backgroundColor,textFormat"),
        fmt(rng(c, 1, 2000, 0, 1), dt, "numberFormat"),
        fmt(rng(c, 1, 2000, 3, 4), dt, "numberFormat"),
        fmt(rng(c, 1, 2000, 4, 5), {"numberFormat": {"type": "NUMBER", "pattern": "0.0"}}, "numberFormat"),
        {"autoResizeDimensions": {"dimensions": {"sheetId": c, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 6}}},
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(c, 1, 2000, 4, 6)], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$F2="dropped (>1h)"'}]},
            "format": {"textFormat": {"foregroundColor": {"red": .6, "green": .6, "blue": .6}, "italic": True}}}}}},  # the scan still counts as a duct; only its gap is ignored
    ])
    print("built Dashboard + Cycles")


if __name__ == "__main__":
    main()
