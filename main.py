import time
import os
import requests
import yfinance as yf
import pandas as pd

# Railway Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }
    requests.post(url, data=payload)

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

    last = data.iloc[-1]

    if last["EMA20"] > last["EMA50"] and last["RSI"] > 55:
        return "📈 BUY XAUUSD\nEMA bullish + RSI strong"

    elif last["EMA20"] < last["EMA50"] and last["RSI"] < 45:
        return "📉 SELL XAUUSD\nEMA bearish + RSI weak"

    return None

def main():
    send_message("🤖 Gold Signal Bot Started Successfully")

    last_signal = None

    while True:
        signal = check_signal()

        if signal and signal != last_signal:
            send_message(signal)
            last_signal = signal

        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
