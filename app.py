import os
import streamlit as st
import pandas as pd
import requests
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from trade import position_exists

BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT"]
INTERVAL = "1m"
LIMIT = 100
REFRESH_INTERVAL = 60

@st.cache_data(ttl=REFRESH_INTERVAL)
def get_klines(symbol, interval, limit):
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url)
        data = res.json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        st.error(f"❌ Gagal ambil data {symbol}: {e}")
        return pd.DataFrame()

def calculate_indicators(df):
    df['ema'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['rsi'] = RSIIndicator(df['close'], window=14).rsi()
    df['adx'] = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    macd = MACD(df['close'])
    df['macd'], df['macd_signal'] = macd.macd(), macd.macd_signal()
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'], df['bb_lower'] = bb.bollinger_hband(), bb.bollinger_lband()
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    df['volume_spike'] = df['volume'] > df['volume_ma20'] * 2
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['atr'] = atr.average_true_range()
    return df

def enhanced_signal(df):
    latest, prev = df.iloc[-1], df.iloc[-2]
    score_long = sum([
        prev["macd"] < prev["macd_signal"] and latest["macd"] > latest["macd_signal"],
        latest["close"] > latest["ema"],
        latest["rsi"] > 48,
        latest["close"] > latest["bb_upper"],
        latest["volume_spike"],
        latest["adx"] > 15
    ])
    score_short = sum([
        prev["macd"] > prev["macd_signal"] and latest["macd"] < latest["macd_signal"],
        latest["close"] < latest["ema"],
        latest["rsi"] < 52,
        latest["close"] < latest["bb_lower"],
        latest["volume_spike"],
        latest["adx"] > 15
    ])
    if score_long >= 3: return "LONG"
    if score_short >= 3: return "SHORT"
    return ""

st.set_page_config(page_title="Futures Dashboard", layout="wide")
st.title("📈 Binance Futures Dashboard (1-Minute Signal)")

for symbol in SYMBOLS:
    df = get_klines(symbol, INTERVAL, LIMIT)
    if df.empty or df.shape[0] < 20:
        st.warning(f"⚠️ Data tidak cukup untuk {symbol}")
        continue

    df = calculate_indicators(df)
    signal = enhanced_signal(df)
    latest = df.iloc[-1]

    st.subheader(f"{symbol} Latest Candle")
    st.write(latest[['open_time', 'close', 'volume', 'rsi', 'adx', 'macd', 'ema', 'atr']])

    st.subheader(f"Current Signal: {signal if signal else 'No Signal'}")

    # Contoh cek posisi via trade.py function
    from trade import position_exists
    has_pos_long = position_exists(symbol=symbol, side="LONG")
    has_pos_short = position_exists(symbol=symbol, side="SHORT")

    st.write(f"Position LONG open: {has_pos_long}")
    st.write(f"Position SHORT open: {has_pos_short}")
