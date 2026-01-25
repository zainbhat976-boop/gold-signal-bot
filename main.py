# ================= LOGGING OFF =================
import logging
logging.disable(logging.CRITICAL)

# ================= IMPORTS =================
import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = 7140499311  # 🔒 HARD-CODED TELEGRAM USER ID (ONLY YOU)

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

SYMBOL = "PAXG-USD"
TF_ENTRY = "5m"
TF_TREND = "15m"
SLEEP_TIME = 300
RR_RATIO = 2

# ================= GLOBAL STATES =================
last_signal = None
last_15m_close_time = None
locked_15m_trend = None  # "BULL" / "BEAR"

daily_trades = []
last_summary_date = None

# ================= SEND MESSAGE (HARD LOCK) =================
def send_message(text):
    if not BOT_TOKEN:
        return

    payload = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(TELEGRAM_URL, data=payload)

# ================= ADX (FIXED – NO ERROR) =================
def calculate_adx(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

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
    adx = dx.rolling(period).mean()

    return adx.fillna(0)   # 🔥 THIS LINE FIXES RAILWAY ERROR

# ================= LIQUIDITY SWEEP =================
def liquidity_sweep_buy(df):
    support = df["Low"].tail(20).min()
    last = df.iloc[-1]
    return last["Low"] < support and last["Close"] > support

def liquidity_sweep_sell(df):
    resistance = df["High"].tail(20).max()
    last = df.iloc[-1]
    return last["High"] > resistance and last["Close"] < resistance

# ================= ORDER BLOCK =================
def bullish_order_block(df):
    for i in range(len(df) - 3, 1, -1):
        c1 = df.iloc[i]
        c2 = df.iloc[i + 1]
        if c1["Close"] < c1["Open"] and c2["Close"] > c2["Open"]:
            return c1["Low"], c1["High"]
    return None, None

def bearish_order_block(df):
    for i in range(len(df) - 3, 1, -1):
        c1 = df.iloc[i]
        c2 = df.iloc[i + 1]
        if c1["Close"] > c1["Open"] and c2["Close"] < c2["Open"]:
            return c1["Low"], c1["High"]
    return None, None

# ================= DAILY SUMMARY =================
def send_daily_summary():
    global daily_trades

    if not daily_trades:
        return

    total = len(daily_trades)
    net_rr = sum(t["rr"] for t in daily_trades)

    msg = (
        f"📊 <b>DAILY TRADING SUMMARY</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📅 Date: {datetime.utcnow().strftime('%d %b %Y')}\n\n"
        f"📈 Total Signals: {total}\n"
        f"⚖ Net RR (Approx): +{net_rr}R\n\n"
        f"💼 Pair: GOLD\n"
        f"⏱ TF: 5M | 15M\n"
        f"━━━━━━━━━━━━━━━━"
    )

    send_message(msg)
    daily_trades = []

# ================= SIGNAL LOGIC =================
def check_signal():
    global last_signal, last_15m_close_time, locked_15m_trend, daily_trades

    # ---- Session filter ----
    hour = datetime.utcnow().hour
    if hour < 6 or hour > 20:
        return None

    df = yf.download(SYMBOL, interval=TF_ENTRY, period="2d", progress=False)
    htf = yf.download(SYMBOL, interval=TF_TREND, period="4d", progress=False)

    if df.empty or htf.empty or len(df) < 50:
        return None

    # ---- EMA ----
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    htf["EMA20"] = htf["Close"].ewm(span=20).mean()
    htf["EMA50"] = htf["Close"].ewm(span=50).mean()

    # ---- RSI ----
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    delta_h = htf["Close"].diff()
    gain_h = delta_h.where(delta_h > 0, 0).rolling(14).mean()
    loss_h = -delta_h.where(delta_h < 0, 0).rolling(14).mean()
    rs_h = gain_h / loss_h
    htf["RSI"] = 100 - (100 / (1 + rs_h))

    # ---- ADX (FIXED) ----
    df["ADX"] = calculate_adx(df)

    # ---- 15M candle close lock ----
    current_15m_close = htf.index[-1]
    if last_15m_close_time != current_15m_close:
        last_15m_close_time = current_15m_close
        htf_last = htf.iloc[-1]

        if htf_last["EMA20"] > htf_last["EMA50"] and htf_last["RSI"] > 50:
            locked_15m_trend = "BULL"
        elif htf_last["EMA20"] < htf_last["EMA50"] and htf_last["RSI"] < 50:
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

        return f"🟢 BUY GOLD\nEntry: {price:.2f}\nSL: {swing_low:.2f}\nTP: {tp:.2f}"

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

        return f"🔴 SELL GOLD\nEntry: {price:.2f}\nSL: {swing_high:.2f}\nTP: {tp:.2f}"

    return None

# ================= MAIN LOOP =================
while True:
    now = datetime.utcnow()
    today = now.date()

    # ---- Daily summary at 18:30 UTC ----
    if now.hour == 18 and now.minute == 30:
        if last_summary_date != today:
            send_daily_summary()
            last_summary_date = today

    signal = check_signal()
    if signal:
        send_message(signal)

    time.sleep(SLEEP_TIME)
