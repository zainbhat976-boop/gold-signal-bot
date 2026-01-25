import os
import time
import requests
import pandas as pd
import yfinance as yf

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN or CHAT_ID missing")
        return

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(TELEGRAM_URL, data=payload)


def check_signal():
    data = yf.download("PAXG-USD", interval="5m", period="1d")

    if data.empty:
        return None

    data["EMA20"] = data["Close"].ewm(span=20).mean()
    data["EMA50"] = data["Close"].ewm(span=50).mean()

    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    data["RSI"] = 100 - (100 / (1 + rs))

    last = data.tail(1)

ema20 = float(last["EMA20"].values[0])
ema50 = float(last["EMA50"].values[0])
rsi = float(last["RSI"].values[0])

    if pd.isna(ema20) or pd.isna(ema50) or pd.isna(rsi):
        return None

    if ema20 > ema50 and rsi > 55:
        return "📈 <b>BUY XAUUSD</b>\nEMA bullish + RSI strong"

    if ema20 < ema50 and rsi < 45:
        return "📉 <b>SELL XAUUSD</b>\nEMA bearish + RSI weak"

    return None


def main():
    send_message("🤖 Gold Signal Bot Started Successfully")
    send_message("✅ TEST MESSAGE: Bot connected & running")

    last_signal = None

    while True:
        try:
            signal = check_signal()
            if signal and signal != last_signal:
                send_message(signal)
                last_signal = signal
        except Exception as e:
            print("Error:", e)

        time.sleep(300)  # 5 minutes


if __name__ == "__main__":
    main()
