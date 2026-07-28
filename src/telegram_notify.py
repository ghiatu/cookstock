import os
import sys
import glob
import json
import datetime as dt
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def find_path():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    resp.raise_for_status()


def send_photo(photo_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": f},
        )
    resp.raise_for_status()


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ไม่พบ TELEGRAM_BOT_TOKEN หรือ TELEGRAM_CHAT_ID ใน environment variables")
        sys.exit(1)

    basePath = find_path()
    current_date = dt.date.today().strftime("%Y-%m-%d")
    resultsPath = os.path.join(basePath, "results", current_date)

    if not os.path.isdir(resultsPath):
        send_message(f"CookStock {current_date}: วันนี้ไม่พบโฟลเดอร์ผลลัพธ์")
        return

    json_files = glob.glob(os.path.join(resultsPath, "*.json"))
    passed = []
    for jf in json_files:
        with open(jf) as f:
            data = json.load(f)
        for item in data.get("data", []):
            if isinstance(item, dict):
                for ticker, info in item.items():
                    if isinstance(info, dict) and "fig" in info:
                        passed.append((ticker, info))

    if not passed:
        send_message(f"📊 CookStock scan {current_date}\nไม่มีหุ้นผ่านเกณฑ์ VCP วันนี้")
        return

    tickers_line = ", ".join(t for t, _ in passed)
    send_message(f"📊 CookStock scan {current_date}\nพบหุ้นผ่านเกณฑ์ {len(passed)} ตัว: {tickers_line}")

    for ticker, info in passed:
        caption = (
            f"{ticker}\n"
            f"ราคาปัจจุบัน: {info.get('current price')}\n"
            f"แนวรับ: {info.get('support price')}\n"
            f"แนวต้าน: {info.get('pressure price')}"
        )
        fig_path = info.get("fig")
        if fig_path and os.path.exists(fig_path):
            send_photo(fig_path, caption=caption)
        else:
            send_message(caption)


if __name__ == "__main__":
    main()