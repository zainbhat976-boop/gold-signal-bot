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
OWNER_ID = 7140499311

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

SYMBOL = "XAUUSD=X"
PAIR_NAME = "XAUUSD"
TF_ENTRY = "5m"
SLEEP_TIME = 60
RR_RATIO = 2

MAX_SIGNALS_PER_DAY = 10
signals_today = 0
signals_date = None

last_signal = None
last_update_id = 0

# ================= SEND MESSAGE =================
def send_message(text):
    payload = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(TELEGRAM_URL, data=payload)

send_message("✅ Bot online & running on Railway")

# =================================================
# ✅ DECISION LOGIC (NEW – ONLY ADDITION)
# =================================================
def trade_decision(current_price, entry_low, entry_high, side):
    if side == "BUY":
        if current_price > entry_high:
            return "WAIT ⏳ (price above entry)"
        elif entry_low <= current_price <= entry_high:
            return "TRADE ✅"
        else:
            return "WAIT ⏳ (wait pullback)"

    if side == "SELL":
        if current_price < entry_low:
            return "WAIT ⏳ (price below entry)"
        elif entry_low <= current_price <= entry_high:
            return "TRADE ✅"
        else:
            return "WAIT ⏳ (wait retrace)"

# =================================================
# ✅ MANUAL SIGNAL WITH DECISION (FIXED)
# =================================================
def fetch_manual_text_signal():
    global last_update_id
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            timeout=10
        ).json()

        for update in r.get("result", []):
            if update["update_id"] <= last_update_id:
                continue
            last_update_id = update["update_id"]

            msg = update.get("message", {})
            if msg.get("chat", {}).get("id") != OWNER_ID:
                continue

            text = msg.get("text", "").upper()
            if not text.startswith(("BUY", "SELL")):
                continue

            side = "BUY" if text.startswith("BUY") else "SELL"

            # Extract numbers
            price_match = re.search(r"CURRENT PRICE[: ]+([\d.]+)", text)
            entry_match = re.search(r"ENTRY[: ]+([\d.]+)[–-]([\d.]+)", text)

            if not price_match or not entry_match:
                send_message("⚠️ Format error: price/entry missing")
                continue

            current_price = float(price_match.group(1))
            entry_high = float(entry_match.group(1))
            entry_low = float(entry_match.group(2))

            decision = trade_decision(
                current_price,
                entry_low,
                entry_high,
                side
            )

            send_message(f"""
📊 <b>MANUAL SIGNAL</b>

{text}

<b>Recommendation:</b> {decision}
⚠️ Risk: 1–2%
""")
    except Exception:
        pass

# =================================================
# AUTO SIGNAL (UNCHANGED)
# =================================================
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

def check_signal():
    global last_signal, signals_today, signals_date

    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
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
    df["ADX"] = calculate_adx(df)

    last = df.iloc[-1]
    price = float(last["Close"])
    adx = float(last["ADX"])

    if last["EMA20"] > last["EMA50"] and adx > 12 and last_signal != "BUY":
        last_signal = "BUY"
        signals_today += 1
        return f"🟢 <b>BUY GOLD (AUTO)</b>\nPrice: {price:.2f}"

    if last["EMA20"] < last["EMA50"] and adx > 12 and last_signal != "SELL":
        last_signal = "SELL"
        signals_today += 1
        return f"🔴 <b>SELL GOLD (AUTO)</b>\nPrice: {price:.2f}"

    return None

# ================= MAIN LOOP =================
while True:
    fetch_manual_text_signal()

    signal = check_signal()
    if signal:
        send_message(signal)

    time.sleep(SLEEP_TIME)
