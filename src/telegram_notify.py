#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telegram_notify.py
Small helper to send scan results to Telegram: a text summary message, and
chart images (.jpg) as photos. Reads the bot token and target chat id from
the environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
"""
import os
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _get_credentials():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID environment variables are not set"
        )
    return token, chat_id


def send_text(message, parse_mode='HTML'):
    token, chat_id = _get_credentials()
    url = TELEGRAM_API.format(token=token, method='sendMessage')
    # Telegram caps messages at 4096 characters - split long summaries
    for i in range(0, len(message), 4000):
        chunk = message[i:i + 4000]
        resp = requests.post(url, data={
            'chat_id': chat_id,
            'text': chunk,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True,
        }, timeout=30)
        if resp.status_code != 200:
            print("Telegram sendMessage failed:", resp.text)


def send_photo(photo_path, caption=None):
    token, chat_id = _get_credentials()
    url = TELEGRAM_API.format(token=token, method='sendPhoto')
    with open(photo_path, 'rb') as f:
        files = {'photo': f}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption[:1024]
        resp = requests.post(url, data=data, files=files, timeout=60)
    if resp.status_code != 200:
        print(f"Telegram sendPhoto failed for {photo_path}:", resp.text)


def send_photos(photo_paths, captions=None):
    captions = captions or {}
    for p in photo_paths:
        send_photo(p, caption=captions.get(p))
