
import time
import requests
import yfinance as yf
import pandas as pd

TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_signal(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)

def check_signal():
    data = yf.download("XAUUSD=X", interval="5m", period="2d")

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
    else:
        return None

while True:
    signal = check_signal()
    if signal:
        send_signal(signal)
    time.sleep(300)
