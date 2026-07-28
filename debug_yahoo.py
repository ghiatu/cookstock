import sys
sys.path.insert(0, 'src')

import datetime as dt
from yahoofinancials import YahooFinancials

date = dt.date.today()

print("=== TEST 1: ช่วง 365 วัน แบบเดียวกับใน cookFinancials.__init__ ===")
yf = YahooFinancials('AAPL')
data = yf.get_historical_price_data(str(date - dt.timedelta(days=365)), str(date), 'daily')
print("มี key 'prices' ไหม:", 'prices' in data['AAPL'])
if 'prices' not in data['AAPL']:
    print("เนื้อหาที่ได้จริง:", data)

print()
print("=== TEST 2: เรียกผ่านคลาส cookFinancials โดยตรง ===")
from cookStock import cookFinancials
x = cookFinancials('AAPL')
print("สร้าง cookFinancials สำเร็จ, current price:", x.current_stickerPrice)