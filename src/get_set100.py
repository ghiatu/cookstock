import io
import requests
import pandas as pd

def get_set100_tickers(limit=100):
    """
    ดึงรายชื่อหุ้น SET100 แบบสดจาก Wikipedia แล้วคืนเป็น list ของ ticker
    พร้อมต่อท้าย .BK ตามรูปแบบที่ yfinance ใช้กับหุ้นไทย
    """
    url = "https://en.wikipedia.org/wiki/SET50_Index_and_SET100_Index"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    tables = pd.read_html(io.StringIO(resp.text))

    candidate_tables = [t for t in tables if "Symbol" in t.columns]
    if not candidate_tables:
        raise RuntimeError("ไม่พบตารางรายชื่อหุ้นในหน้า Wikipedia (โครงสร้างหน้าอาจเปลี่ยน)")

    df = max(candidate_tables, key=len)  # เอาตารางที่มีแถวเยอะสุด = SET100

    tickers = df["Symbol"].astype(str).str.strip().tolist()
    tickers = [t + ".BK" for t in tickers if t and t.lower() != "nan"]
    return tickers[:limit]

if __name__ == "__main__":
    print(get_set100_tickers(10))