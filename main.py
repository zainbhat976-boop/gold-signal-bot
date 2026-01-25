# ===================== LOGGING OFF =====================
import logging
logging.disable(logging.CRITICAL)

# ===================== IMPORTS =========================
import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

# ===================== CONFIG ==========================
BOT_TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = 7140499311   # 🔒 ONLY YOU

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# XM GOLD
SYMBOL = "XAUUSD=X"     # Yahoo
PAIR_NAME = "XAUUSD"   # XM / MT4 / MT5

TF_ENTRY = "5m"
TF_TREND = "15m"

SLEEP_TIME = 300        # 5 min
RR_RATIO = 2

# ===================== GLOBAL STATE ====================
last_signal = None
last_15m_close_time = None
locked_15m_trend = None

daily_trades = []
last_summary_date = None

# ===================== TELEGRAM ========================
def send_message(text):
    if not BOT_TOKEN:
        return
    payload = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(TELEGRAM_URL, data=payload, timeout=10)

# ===================== INDICATORS ======================
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

# ===================== LIQUIDITY =======================
def liquidity_sweep_buy(df):
    support = df["Low"].tail(20).min()
    last = df.iloc[-1]
    return last["Low"] < support and last["Close"] > support

def liquidity_sweep_sell(df):
    resistance = df["High"].tail(20).max()
    last = df.iloc[-1]
    return last["High"] > resistance and last["Close"] < resistance

# ===================== ORDER BLOCK =====================
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

# ===================== DAILY SUMMARY ===================
def send_daily_summary():
    global daily_trades
    if not daily_trades:
        return

    total = len(daily_trades)
    net_rr = sum(t["rr"] for t in daily_trades)

    msg = f"""
📊 <b>DAILY SUMMARY (XM)</b>

Pair: {PAIR_NAME}
TF: 5M | 15M

Total Signals: {total}
Net RR: {net_rr}
"""
    send_message(msg)
    daily_trades = []

# ===================== SIGNAL LOGIC ====================
def check_signal():
    global last_signal, last_15m_close_time, locked_15m_trend, daily_trades

    now = datetime.now(timezone.utc)   # ✅ WARNING FIX
    hour = now.hour

    if hour < 6 or hour > 20:
        return None

    df = yf.download(SYMBOL, interval=TF_ENTRY, period="2d", progress=False)
    htf = yf.download(SYMBOL, interval=TF_TREND, period="4d", progress=False)

    if df.empty or htf.empty or len(df) < 50:
        return None

    # EMA
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    htf["EMA20"] = htf["Close"].ewm(span=20).mean()
    htf["EMA50"] = htf["Close"].ewm(span=50).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))

    delta_h = htf["Close"].diff()
    gain_h = delta_h.where(delta_h > 0, 0).rolling(14).mean()
    loss_h = -delta_h.where(delta_h < 0, 0).rolling(14).mean()
    htf["RSI"] = 100 - (100 / (1 + gain_h / loss_h))

    df["ADX"] = calculate_adx(df)

    # 15M trend lock
    current_15m_close = htf.index[-1]
    if last_15m_close_time != current_15m_close:
        last_15m_close_time = current_15m_close
        last_htf = htf.iloc[-1]

        if last_htf["EMA20"] > last_htf["EMA50"] and last_htf["RSI"] > 50:
            locked_15m_trend = "BULL"
        elif last_htf["EMA20"] < last_htf["EMA50"] and last_htf["RSI"] < 50:
            locked_15m_trend = "BEAR"
        else:
            locked_15m_trend = None

    last = df.iloc[-1]
    price = float(last["Close"])
    rsi = float(last["RSI"])
    adx = float(last["ADX"])

    swing_low = df["Low"].tail(20).min()
    swing_high = df["High"].tail(20).max()

    ob_low_b, ob_high_b = bullish_order_block(df)
    ob_low_s, ob_high_s = bearish_order_block(df)

    # ================= BUY =================
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
        tp = price + (price - swing_low) * RR_RATIO
        daily_trades.append({"rr": RR_RATIO})

        return f"""
🟢 <b>BUY GOLD (XM)</b>

Pair: {PAIR_NAME}
TF: 5M | Trend: 15M

Entry: {price:.2f}
SL: {swing_low:.2f}
TP: {tp:.2f}

RR: 1:{RR_RATIO}
"""

    # ================= SELL =================
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
        tp = price - (swing_high - price) * RR_RATIO
        daily_trades.append({"rr": RR_RATIO})

        return f"""
🔴 <b>SELL GOLD (XM)</b>

Pair: {PAIR_NAME}
TF: 5M | Trend: 15M

Entry: {price:.2f}
SL: {swing_high:.2f}
TP: {tp:.2f}

RR: 1:{RR_RATIO}
"""

    return None

# ===================== MAIN LOOP =======================
send_message("✅ Bot started | Gold signal engine live")

while True:
    now = datetime.now(timezone.utc)   # ✅ WARNING FIX
    today = now.date()

    if now.hour == 18 and now.minute == 30:
        if last_summary_date != today:
            send_daily_summary()
            last_summary_date = today

    signal = check_signal()
    if signal:
        send_message(signal)

    send_message("💓 Heartbeat: bot alive")
    time.sleep(SLEEP_TIME)
