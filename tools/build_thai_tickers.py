#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/build_thai_tickers.py

Builds data/thai_tickers.csv (the FULL SET + mai symbol list) from the
official "List of Listed Companies" file you download from SET's website.

WHY MANUAL DOWNLOAD, NOT AUTO-SCRAPED:
SET's website renders that download link via JavaScript and doesn't expose
a stable public API for the full symbol list (their only ticker-list APIs
are paid data-subscription products). Scraping the page directly is
fragile and itself risks being blocked. Since listings only change a few
times a year, downloading it by hand every quarter and committing the
resulting CSV is far more robust than fighting SET's anti-bot protections
in CI, on top of the ones we already have to manage for Yahoo Finance.

HOW TO USE:
1. Go to: https://www.set.or.th/en/market/index/set/profile
   (or https://www.set.or.th/en/market/index/mai/profile for mai)
   and click "Download List of Listed Companies". This gives you an
   .xlsx file containing BOTH SET and mai symbols (there's a "Market"
   column). Save it anywhere, e.g. ~/Downloads/listedCompanies_th.xlsx

2. Run:
     python tools/build_thai_tickers.py ~/Downloads/listedCompanies_th.xlsx

   This writes data/thai_tickers.csv (one symbol per line, no header,
   already de-duplicated and sorted) - exactly what get_thai_tickers.py
   expects.

3. Commit + push data/thai_tickers.csv. Repeat every few months, or
   whenever you notice IPOs/delistings you want reflected in the scan.

The parser is defensive about SET's export layout (title rows above the
real header, mixed Thai/English column names), since that layout has
changed between exports before.
"""
import sys
import csv
import os

try:
    import pandas as pd
except ImportError:
    print("This tool needs pandas + openpyxl: pip install pandas openpyxl")
    sys.exit(1)

# Column header candidates SET has used for the symbol column, in past
# exports (English and Thai, varying capitalization/spacing).
_SYMBOL_HEADER_CANDIDATES = {
    'symbol', 'securitysymbol', 'ticker', 'securities',
    'หลักทรัพย์', 'ชื่อย่อหลักทรัพย์', 'ชื่อย่อ',
}


def _find_header_row(raw_df):
    """SET's export usually has a few title rows before the real header.
    Scan the first 15 rows for one that contains a recognizable symbol
    column name, and return its row index."""
    for i in range(min(15, len(raw_df))):
        row_values = [str(v).strip().lower() for v in raw_df.iloc[i].tolist()]
        if any(v in _SYMBOL_HEADER_CANDIDATES for v in row_values):
            return i
    return None


def _table_to_raw_grid(df):
    """pd.read_html often promotes the first row to column names (unlike
    read_excel with header=None). Push those names back into row 0 so the
    rest of the pipeline can treat every source the same way: a raw grid
    with no special header row, which _find_header_row() then scans."""
    cols = list(df.columns)
    looks_like_real_header = any(
        isinstance(c, str) and not c.startswith('Unnamed') for c in cols
    )
    if looks_like_real_header:
        body_rows = df.reset_index(drop=True).values.tolist()
        return pd.DataFrame([cols] + body_rows)
    return df.reset_index(drop=True)


def _read_any_excel_like(path):
    """
    Websites (including SET) frequently label their "Export to Excel"
    download as .xls even though the actual file content is one of:
      - a real legacy .xls (BIFF binary format)   -> needs 'xlrd'
      - a real modern .xlsx (zip/OOXML)            -> needs 'openpyxl'
      - a plain HTML table saved with an .xls name -> pandas can't
        read this with read_excel at all; use read_html instead

    We sniff the actual file bytes rather than trusting the extension,
    then use the right reader. Returns a DataFrame with header=None
    (raw grid), same as the old direct read_excel call.
    """
    with open(path, 'rb') as f:
        head = f.read(8)

    if head.startswith(b'PK\x03\x04'):
        # Real .xlsx (zip signature)
        return pd.read_excel(path, header=None, sheet_name=0, engine='openpyxl')

    if head.startswith(b'\xd0\xcf\x11\xe0'):
        # Real legacy .xls (OLE2 compound file signature)
        return pd.read_excel(path, header=None, sheet_name=0, engine='xlrd')

    # Not a real Excel binary - almost certainly HTML (or CSV/TSV) wearing
    # an .xls costume, which is exactly what SET's website exports.
    try:
        tables = pd.read_html(path)
    except Exception as exc:
        raise ValueError(
            f"Couldn't read {path} as .xlsx, legacy .xls, or HTML table. "
            f"Open it in a text editor and check what it actually contains. "
            f"Underlying error: {exc}"
        )
    # Pick the largest table on the page - the symbol list is virtually
    # always the biggest table in these exports.
    tables.sort(key=len, reverse=True)
    return _table_to_raw_grid(tables[0])


def extract_symbols(xlsx_path):
    raw = _read_any_excel_like(xlsx_path)
    header_row = _find_header_row(raw)

    if header_row is None:
        # Fallback: assume the first column already IS the symbol column
        # with no usable header (rare, but don't crash - just try it and
        # let the caller sanity-check the count).
        print("WARNING: couldn't find a recognizable header row - "
              "falling back to column 0 as-is. Please spot-check the output.")
        col = raw.iloc[:, 0]
    else:
        headers = [str(v).strip().lower() for v in raw.iloc[header_row].tolist()]
        col_idx = next(i for i, h in enumerate(headers) if h in _SYMBOL_HEADER_CANDIDATES)
        col = raw.iloc[header_row + 1:, col_idx]

    symbols = []
    seen = set()
    for v in col.tolist():
        if pd.isna(v):
            continue
        s = str(v).strip().upper()
        if not s or s in seen:
            continue
        # sanity filter: real SET symbols are short alnum codes (letters,
        # digits, occasionally '-'), e.g. PTT, AOT, TRUE, WHA, DELTA
        if len(s) > 12 or not all(c.isalnum() or c == '-' for c in s):
            continue
        seen.add(s)
        symbols.append(s)
    return sorted(symbols)


def main():
    if len(sys.argv) != 2:
        print("Usage: python tools/build_thai_tickers.py <path-to-set-export.xlsx>")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    if not os.path.exists(xlsx_path):
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    symbols = extract_symbols(xlsx_path)
    if len(symbols) < 100:
        print(f"WARNING: only extracted {len(symbols)} symbols - that's suspiciously "
              f"low for a full SET+mai export (~850 expected). Open the xlsx and "
              f"check the column layout, the parser's header detection may need "
              f"updating for this export format.")

    out_path = os.path.join('data', 'thai_tickers.csv')
    os.makedirs('data', exist_ok=True)
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for s in symbols:
            writer.writerow([s])

    print(f"Wrote {len(symbols)} symbols to {out_path}")


if __name__ == '__main__':
    main()
