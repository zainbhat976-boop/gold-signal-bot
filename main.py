# ================= LOGGING OFF =================
import logging
logging.disable(logging.CRITICAL)

# ================= IMPORTS =====================
import os
import time
import threading
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# ================= CONFIG ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = 7140499311   # 🔒 ONLY YOU
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ================= SYMBOL ======================
SYMBOL = "XAUUSD=X"
PAIR_NAME = "XAUUSD"

TF_ENTRY = "5m"
TF_TREND = "15m"
SLEEP_TIME = 300
RR_RATIO = 2

# ===== NEW: DAILY SIGNAL LIMIT =====
MAX_SIGNALS_PER_DAY = 10
signals_today = 0
signals_date = None

# ================= GLOBAL STATES ===============
bot_enabled = True
last_signal = None
locked_15m_trend = None

# ================= SEND MESSAGE =================
def send_message(text, chat_id=OWNER_ID):
    if not BOT_TOKEN:
        return
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(TELEGRAM_URL, data=payload)

# ================= COMMAND LISTENER (OWNER ONLY) =================
LAST_UPDATE_ID = 0

def listen_commands():
    global LAST_UPDATE_ID, bot_enabled

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        params = {"offset": LAST_UPDATE_ID + 1, "timeout": 100}
        data = requests.get(url, params=params, timeout=120).json()

        for upd in data.get("result", []):
            LAST_UPDATE_ID = upd["update_id"]

            if "message" not in upd:
                continue

            msg = upd["message"]
            text = msg.get("text", "")
            chat_id = msg["chat"]["id"]

            # 🔒 OWNER LOCK
            if chat_id != OWNER_ID:
                continue

            if text == "/start":
                send_message(
                    "🤖 <b>Gold Signal Bot ACTIVE</b>\n\n"
                    "📊 Pair: XAUUSD\n"
                    "⏱ TF: 5M | Trend: 15M\n"
                    "📈 EMA + RSI + ADX + OB + Liquidity Sweep\n"
                    "📌 Max Signals/Day: 10\n\n"
                    "⚠️ Use proper risk management",
                    chat_id
                )

            elif text == "/status":
                state = "ON ✅" if bot_enabled else "OFF ❌"
                send_message(
                    f"📊 <b>BOT STATUS</b>\n\n"
                    f"State: {state}\n"
                    f"Signals Today: {signals_today}/{MAX_SIGNALS_PER_DAY}",
                    chat_id
                )

            elif text == "/on":
                bot_enabled = True
                send_message("✅ Bot ON kar diya gaya hai", chat_id)

            elif text == "/off":
                bot_enabled = False
                send_message("⛔ Bot OFF kar diya gaya hai", chat_id)

    except:
        pass

def command_loop():
    while True:
        listen_commands()
        time.sleep(2)

threading.Thread(target=command_loop, daemon=True).start()

# ================= INDICATORS ==================
def calculate_adx(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    plus_dm = high.diff()
    minus_dm = low.diff().abs()

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    return dx.rolling(period).mean().fillna(0)

def liquidity_sweep_buy(df):
    support = df["Low"].tail(20).min()
    last = df.iloc[-1]
    return last["Low"] < support and last["Close"] > support

def liquidity_sweep_sell(df):
    resistance = df["High"].tail(20).max()
    last = df.iloc[-1]
    return last["High"] > resistance and last["Close"] < resistance

def bullish_order_block(df):
    for i in range(len(df)-3, 0, -1):
        c1, c2 = df.iloc[i], df.iloc[i+1]
        if c1["Close"] < c1["Open"] and c2["Close"] > c2["Open"]:
            return c1["Low"], c1["High"]
    return None, None

def bearish_order_block(df):
    for i in range(len(df)-3, 0, -1):
        c1, c2 = df.iloc[i], df.iloc[i+1]
        if c1["Close"] > c1["Open"] and c2["Close"] < c2["Open"]:
            return c1["Low"], c1["High"]
    return None, None

# ================= SIGNAL LOGIC (UNCHANGED) ==================
def check_signal():
    global last_signal, locked_15m_trend
    global signals_today, signals_date

    if not bot_enabled:
        return None

    # ===== DAILY LIMIT RESET =====
    today = datetime.utcnow().date()
    if signals_date != today:
        signals_date = today
        signals_today = 0

    if signals_today >= MAX_SIGNALS_PER_DAY:
        return None

    hour = datetime.utcnow().hour
    if hour < 6 or hour > 20:
        return None

    df = yf.download(SYMBOL, interval=TF_ENTRY, period="2d", progress=False)
    htf = yf.download(SYMBOL, interval=TF_TREND, period="4d", progress=False)

    if df.empty or htf.empty or len(df) < 50:
        return None

    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    htf["EMA20"] = htf["Close"].ewm(span=20).mean()
    htf["EMA50"] = htf["Close"].ewm(span=50).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))

    df["ADX"] = calculate_adx(df)

    last_htf = htf.iloc[-1]
    if last_htf["EMA20"] > last_htf["EMA50"] and last_htf["RSI"] > 50:
        locked_15m_trend = "BULL"
    elif last_htf["EMA20"] < last_htf["EMA50"] and last_htf["RSI"] < 50:
        locked_15m_trend = "BEAR"
    else:
        return None

    last = df.iloc[-1]
    price = float(last["Close"])
    rsi = float(last["RSI"])
    adx = float(last["ADX"])

    swing_low = df["Low"].tail(20).min()
    swing_high = df["High"].tail(20).max()

    ob_low_b, ob_high_b = bullish_order_block(df)
    ob_low_s, ob_high_s = bearish_order_block(df)

    if (
        locked_15m_trend == "BULL"
        and liquidity_sweep_buy(df)
        and ob_low_b and ob_low_b <= price <= ob_high_b
        and last["EMA20"] > last["EMA50"]
        and price > last["EMA20"]
        and 50 < rsi < 65
        and adx > 20
        and last_signal != "BUY"
    ):
        last_signal = "BUY"
        signals_today += 1
        tp = price + (price - swing_low) * RR_RATIO
        return f"🟢 BUY GOLD\nEntry: {price:.2f}\nSL: {swing_low:.2f}\nTP: {tp:.2f}\nRR 1:{RR_RATIO}"

    if (
        locked_15m_trend == "BEAR"
        and liquidity_sweep_sell(df)
        and ob_low_s and ob_low_s <= price <= ob_high_s
        and last["EMA20"] < last["EMA50"]
        and price < last["EMA20"]
        and 35 < rsi < 50
        and adx > 20
        and last_signal != "SELL"
    ):
        last_signal = "SELL"
        signals_today += 1
        tp = price - (swing_high - price) * RR_RATIO
        return f"🔴 SELL GOLD\nEntry: {price:.2f}\nSL: {swing_high:.2f}\nTP: {tp:.2f}\nRR 1:{RR_RATIO}"

    return None

# ================= MAIN LOOP ====================
print("Bot started")

while True:
    signal = check_signal()
    if signal:
        send_message(signal)
    time.sleep(SLEEP_TIME)
