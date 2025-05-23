# app.py
import os
import time
import streamlit as st
import pandas as pd
import requests
import datetime
from binance.client import Client
from streamlit_autorefresh import st_autorefresh
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from trade import execute_trade, position_exists

# ====== Initialize Binance Client ======
client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

# ====== Config ======
BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT"]
INTERVAL = "1m"
LIMIT = 100
REFRESH_INTERVAL = 55
account_balance = 18
risk_pct = 20
leverage = 10
MIN_QTY = 1

# ====== Helpers ======
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

def calculate_position_size(balance, risk_pct, entry, sl, leverage):
    risk_amt = balance * (risk_pct / 100)
    sl_distance = abs(entry - sl)
    if sl_distance == 0: return 0
    raw_size = (risk_amt / sl_distance) * leverage
    return round(raw_size, 3)

def margin_warning(balance, pos_size, entry, leverage):
    margin_used = (pos_size * entry) / leverage
    if margin_used > balance:
        return True, "❌ Margin tidak cukup untuk membuka posisi ini."
    elif margin_used > balance * 0.9:
        return True, "⚠️ Margin call risk tinggi!"
    return False, ""


# ====== UI ======
st.set_page_config(page_title="Futures Dashboard", layout="wide")
st.title("📈 Binance Futures Dashboard (1-Minute Signal)")
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="refresh")

# ... (kode impor dan setup sebelumnya tetap sama)

for symbol in SYMBOLS:
    df = get_klines(symbol, INTERVAL, LIMIT)
    if df.empty or df.shape[0] < 20:
        st.warning(f"⚠️ Data tidak cukup untuk {symbol}")
        continue

    df = calculate_indicators(df)
    signal = enhanced_signal(df)
    latest = df.iloc[-1]
    entry = latest["close"]
    candle_time = str(latest["open_time"])

    if signal and not position_exists(client, symbol, signal):
        sl = entry - latest['atr'] * 1.5 if signal == "LONG" else entry + latest['atr'] * 1.5
        tp = entry + latest['atr'] * 2.5 if signal == "LONG" else entry - latest['atr'] * 2.5
        pos_size = calculate_position_size(account_balance, risk_pct, entry, sl, leverage)

        if pos_size < MIN_QTY:
            st.warning(f"⛔ Ukuran posisi terlalu kecil")
            continue
            
        is_margin_risk, note = margin_warning(account_balance, pos_size, entry, leverage)
        if is_margin_risk:
           st.error(f"{note} Margin dibutuhkan: ${(pos_size * entry / leverage):.2f}")
           continue

        is_margin_risk, note = margin_warning(account_balance, pos_size, entry, leverage)
        st.info(f"{symbol} Signal: {signal} | Entry: {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | PosSize: {pos_size} | {note}")

        try:
            trailing_stop_callback_rate = 1.0
            result = execute_trade(
                symbol=symbol,
                side=signal,
                quantity=pos_size,
                entry_price=entry,
                leverage=leverage,
                position_side=signal,
                sl_price=sl,
                tp_price=tp,
                trailing_stop_callback_rate=trailing_stop_callback_rate
            )
            if result:
                st.success(f"✅ Order berhasil {signal} {symbol}")
            else:
                st.error(f"❌ Order gagal {symbol}")
        except Exception as e:
            st.error(f"❌ Error eksekusi trade: {e}")
    else:
        st.write(f"ℹ️ {symbol}: Tidak ada sinyal baru atau posisi sudah terbuka.")

    st.subheader(f"🔍 {symbol} Candle Terakhir")
    st.write(latest[['close', 'volume', 'rsi', 'adx', 'macd', 'ema', 'atr']])
