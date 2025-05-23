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
from trade import execute_trade  # Import dari modul trade.py

# ====== Initialize Binance Client ======
client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

# ====== Config ======
BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT"]
INTERVAL = "1m"
LIMIT = 100
REFRESH_INTERVAL = 55  # seconds
account_balance = 20  # USD
risk_pct = 10
leverage = 50
MIN_QTY = 0.001

# ====== Helper Functions ======
@st.cache_data(ttl=55)
def get_klines(symbol, interval="1m", limit=100):
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
        st.error(f"[ERROR] Gagal ambil data {symbol} ({interval}): {e}")
        return pd.DataFrame()

def calculate_indicators(df):
    df['ema'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['rsi'] = RSIIndicator(df['close'], window=14).rsi()
    df['adx'] = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    macd = MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    df['volume_spike'] = df['volume'] > df['volume_ma20'] * 2
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['atr'] = atr.average_true_range()
    return df

def enhanced_signal(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    macd_cross_up = prev["macd"] < prev["macd_signal"] and latest["macd"] > latest["macd_signal"]
    macd_cross_down = prev["macd"] > prev["macd_signal"] and latest["macd"] < latest["macd_signal"]
    ema_up = latest["close"] > latest["ema"]
    ema_down = latest["close"] < latest["ema"]
    rsi_bullish = latest["rsi"] > 48
    rsi_bearish = latest["rsi"] < 52
    bb_upper_break = latest["close"] > latest["bb_upper"]
    bb_lower_break = latest["close"] < latest["bb_lower"]
    adx_strong = latest["adx"] > 15
    vol_spike = latest["volume_spike"]

    score_long = sum([macd_cross_up, ema_up, rsi_bullish, bb_upper_break, vol_spike, adx_strong])
    score_short = sum([macd_cross_down, ema_down, rsi_bearish, bb_lower_break, vol_spike, adx_strong])

    if score_long >= 3:
        return "LONG"
    elif score_short >= 3:
        return "SHORT"
    return ""

def load_last_trade(symbol, interval):
    try:
        with open(f"last_trade_{symbol}_{interval}.txt", "r") as f:
            return f.read().strip().split(",")
    except:
        return ["", ""]

def save_last_trade(symbol, interval, signal, candle_time):
    with open(f"last_trade_{symbol}_{interval}.txt", "w") as f:
        f.write(f"{signal},{candle_time}")

def calculate_position_size(account_balance, risk_pct, entry, sl, leverage):
    risk_amount = account_balance * (risk_pct / 100)
    stop_loss_distance = abs(entry - sl)
    if stop_loss_distance == 0:
        return 0
    raw_pos_size = risk_amount / stop_loss_distance
    pos_size = raw_pos_size * leverage
    return round(pos_size, 3)  # disesuaikan untuk precision USDT/BTC

def calculate_risk_reward(entry, sl, tp):
    rr = abs(tp - entry) / abs(entry - sl)
    return round(rr, 2)

def margin_call_warning(account_balance, pos_size, entry, leverage):
    used_margin = (pos_size * entry) / leverage
    margin_threshold = account_balance * 0.1
    if used_margin > margin_threshold:
        return True, "⚠️ Margin call risk tinggi!"
    else:
        return False, ""

# ====== Streamlit UI ======
st.set_page_config(page_title="Futures Signal Dashboard", layout="wide")
st.title("🚀 Futures Signal Dashboard - 1 Minute")
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="refresh")

for symbol in SYMBOLS:
    df = get_klines(symbol, INTERVAL)
    if df.empty or df.shape[0] < 20:
        st.warning(f"Data kurang untuk {symbol}")
        continue

    df = calculate_indicators(df)
    signal = enhanced_signal(df)
    latest = df.iloc[-1]
    candle_time = str(latest['open_time'])

    if signal:
        last_trade_signal, last_trade_time = load_last_trade(symbol, INTERVAL)
        if signal == last_trade_signal and candle_time == last_trade_time:
            st.warning(f"⛔ Duplikat trade {signal} {symbol} - dilewati")
            continue

        entry = latest['close']
        if signal == "LONG":
            sl = entry - latest['atr'] * 1.5
            tp = entry + latest['atr'] * 2.5
        elif signal == "SHORT":
            sl = entry + latest['atr'] * 1.5
            tp = entry - latest['atr'] * 2.5

        pos_size = calculate_position_size(account_balance, risk_pct, entry, sl, leverage)
        if pos_size < MIN_QTY:
            st.warning(f"⛔ Ukuran posisi terlalu kecil (min {MIN_QTY})")
            continue

        rrr = calculate_risk_reward(entry, sl, tp)
        is_margin_risk, margin_note = margin_call_warning(account_balance, pos_size, entry, leverage)

        st.info(f"Symbol: {symbol} | Signal: {signal}\nEntry: {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f}\nPos Size: {pos_size} | RR: {rrr}\n{margin_note}")

        try:
            entry_realtime = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        except Exception as e:
            st.warning(f"⚠️ Gagal ambil harga realtime: {e}")
            entry_realtime = entry

        try:
            # Pemanggilan fungsi trade sudah disesuaikan
            result = execute_trade(
            symbol=symbol,
            side=signal,
            quantity=pos_size,
            entry_price=entry_realtime,
            leverage=leverage,
            position_side=signal,
            sl_price=sl,
            tp_price=tp
          )
            if result:
                st.success(f"✅ Trade berhasil: {symbol} ({signal})")
                save_last_trade(symbol, INTERVAL, signal, candle_time)
            else:
                st.error(f"❌ Trade gagal untuk {symbol}")
        except Exception as e:
            st.error(f"❌ Error saat eksekusi trade: {e}")

    st.subheader(f"📊 {symbol} - Latest Candle")
    st.write(latest[['close', 'volume', 'volume_spike', 'rsi', 'adx', 'macd', 'macd_signal', 'ema']])
    st.write(f"Signal Detected: {signal if signal else 'Tidak ada'}")

# Sidebar info
st.sidebar.write("⏱ Waktu sekarang:", datetime.datetime.now().strftime("%H:%M:%S"))
