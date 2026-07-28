import io
import requests
import pandas as pd

def get_sp100_tickers(limit=100):
    """
    ดึงรายชื่อหุ้น S&P100 แบบสดจาก Wikipedia แล้วคืนเป็น list ของ ticker
    limit: จำนวนตัวแรกที่จะเอา (ปรับเป็นตัวเลขน้อยๆ เช่น 10 ตอนทดสอบ เพื่อให้รันเร็ว)
    """
    url = "https://en.wikipedia.org/wiki/S%26P_100"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }

    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    tables = pd.read_html(io.StringIO(resp.text))

    df = None
    for t in tables:
        if "Symbol" in t.columns:
            df = t
            break
    if df is None:
        raise RuntimeError("ไม่พบตารางรายชื่อหุ้นในหน้า Wikipedia (โครงสร้างหน้าอาจเปลี่ยน)")

    tickers = df["Symbol"].astype(str).tolist()
    # yahoofinancials ใช้ '-' แทน '.' เช่น BRK.B -> BRK-B
    tickers = [t.replace(".", "-") for t in tickers]
    return tickers[:limit]

if __name__ == "__main__":
    print(get_sp100_tickers(10))