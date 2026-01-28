# ================= LOGGING OFF =================
import logging
logging.disable(logging.CRITICAL)

# ================= IMPORTS =================
import os
import time
import requests
import pandas as pd
import yfinance as yf
import re
from datetime import datetime, timedelta, timezone

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 7140499311  # ONLY YOU

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

SYMBOL = "XAUUSD=X"
PAIR_NAME = "XAUUSD"

TF_ENTRY = "5m"
SLEEP_TIME = 60
RR_RATIO = 2

# ================= DAILY SIGNAL LIMIT =================
MAX_SIGNALS_PER_DAY = 10
signals_today = 0
signals_date = None

# ================= GLOBAL STATES =================
last_signal = None
daily_trades = []
last_summary_date = None

# ================= MANUAL SIGNAL STATE =================
last_update_id = 0

# ================= SEND MESSAGE =================
def send_message(text):
    if not BOT_TOKEN:
        return
    payload = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(TELEGRAM_URL, data=payload)

print("🚀 BOT STARTED SUCCESSFULLY ON RAILWAY")
send_message("✅ Bot online & running on Railway")

# ================= VALUE EXTRACTOR (FIX) =================
def extract_value(text, key):
    match = re.search(rf"{key}\s*:\s*([\d\.]+)", text.lower())
    if match:
        return float(match.group(1))
    return None

# ================= MANUAL TEXT SIGNAL (WITH DECISION) =================
def fetch_manual_text_signal():
    global last_update_id
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        r = requests.get(url, timeout=10).json()
        if not r.get("ok"):
            return

        for update in r["result"]:
            update_id = update["update_id"]
            if update_id <= last_update_id:
                continue
            last_update_id = update_id

            if "message" not in update:
                continue

            msg = update["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            text_lower = text.lower()

            if chat_id != OWNER_ID:
                continue

            if not text_upper := text.upper().startswith(("BUY", "SELL")):
                continue

            price = extract_value(text_lower, "price")
            entry = extract_value(text_lower, "entry")

            recommendation = ""
            if price is not None and entry is not None:
                if price > entry:
                    recommendation = "⏳ WAIT (price above entry)"
                else:
                    recommendation = "✅ TRADE"
            else:
                recommendation = "⚠️ INVALID FORMAT"

            send_message(f"""
📊 <b>MANUAL SIGNAL</b>

{text}

<b>Recommendation:</b> {recommendation}
⚠️ Risk: 1–2%
""")

    except Exception:
        pass

# ================= ADX =================
def calculate_adx(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)

    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    return dx.rolling(period).mean().fillna(0)

# ================= AUTO SIGNAL LOGIC (UNCHANGED) =================
def check_signal():
    global last_signal, signals_today, signals_date, daily_trades

    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    weekday = now_ist.weekday()
    hour = now_ist.hour
    minute = now_ist.minute

    if weekday == 6:
        return None
    if weekday == 5 and (hour > 5 or (hour == 5 and minute >= 30)):
        return None
    if weekday == 0 and (hour < 5 or (hour == 5 and minute < 30)):
        return None

    today = now_ist.date()
    if signals_date != today:
        signals_date = today
        signals_today = 0

    if signals_today >= MAX_SIGNALS_PER_DAY:
        return None

    df = yf.download(SYMBOL, interval=TF_ENTRY, period="2d")
    if df.empty or len(df) < 50:
        return None

    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))

    df["ADX"] = calculate_adx(df)

    last = df.iloc[-1]
    price = float(last["Close"])
    rsi = float(last["RSI"])
    adx = float(last["ADX"])

    swing_low = df["Low"].tail(20).min()
    swing_high = df["High"].tail(20).max()

    if (
        last["EMA20"] > last["EMA50"]
        and price > last["EMA20"]
        and 45 < rsi < 70
        and adx > 12
        and last_signal != "BUY"
    ):
        last_signal = "BUY"
        signals_today += 1
        tp = price + (price - swing_low) * RR_RATIO
        return f"""
🟢 <b>BUY GOLD (AUTO)</b>

Entry: {price:.2f}
SL: {swing_low:.2f}
TP: {tp:.2f}
RR: 1:{RR_RATIO}
"""

    if (
        last["EMA20"] < last["EMA50"]
        and price < last["EMA20"]
        and 30 < rsi < 55
        and adx > 12
        and last_signal != "SELL"
    ):
        last_signal = "SELL"
        signals_today += 1
        tp = price - (swing_high - price) * RR_RATIO
        return f"""
🔴 <b>SELL GOLD (AUTO)</b>

Entry: {price:.2f}
SL: {swing_high:.2f}
TP: {tp:.2f}
RR: 1:{RR_RATIO}
"""

    return None

# ================= MAIN LOOP =================
while True:
    fetch_manual_text_signal()

    signal = check_signal()
    if signal:
        send_message(signal)

    time.sleep(SLEEP_TIME)
