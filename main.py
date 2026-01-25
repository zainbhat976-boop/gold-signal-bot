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

    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    rsi = float(last["RSI"])

    if pd.isna(ema20) or pd.isna(ema50) or pd.isna(rsi):
        return None

    if ema20 > ema50 and rsi > 55:
        return "📈 BUY XAUUSD\nEMA bullish + RSI strong"

    elif ema20 < ema50 and rsi < 45:
        return "📉 SELL XAUUSD\nEMA bearish + RSI weak"

    return None
