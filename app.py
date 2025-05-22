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
risk_pct = 20
leverage = 100

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
        st.warning("⚠️ Stop loss distance = 0. Posisi tidak valid.")
        return 0
    raw_pos_size = risk_amount / stop_loss_distance
    pos_size = raw_pos_size * leverage
    return round(pos_size, 4)

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

def format_risk_message(symbol, interval, entry, sl, tp, pos_size, rr, note):
    return (
        f"Signal: {symbol} {interval}\n"
        f"Entry: {entry:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\n"
        f"Position Size: {pos_size:.4f}\nRR: {rr}\n{note}"
    )

def execute_trade(symbol, signal, quantity, entry, leverage, atr=None, auto_switch=True, timeout=300):
    print(f"[EXECUTE TRADE] {signal} {symbol} Qty: {quantity} Entry: {entry} Leverage: {leverage}")
    return True  # Simulasi berhasil

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
        rrr = calculate_risk_reward(entry, sl, tp)
        is_margin_risk, margin_note = margin_call_warning(account_balance, pos_size, entry, leverage)
        risk_msg = format_risk_message(symbol, INTERVAL, entry, sl, tp, pos_size, rrr, margin_note)
        st.info(risk_msg)

        try:
            entry_realtime = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        except Exception as e:
            st.warning(f"⚠️ Gagal ambil harga realtime Binance: {e}")
            entry_realtime = entry

        def safe_execute_trade_and_notify():
            try:
                trade_result = execute_trade(
                    symbol=symbol,
                    signal=signal,
                    quantity=pos_size,
                    entry=entry_realtime,
                    leverage=leverage,
                    atr=latest['atr'],
                    auto_switch=True
                )
                if trade_result:
                    message = (
                        f"✅ TRADE EXECUTED:\n"
                        f"Pair: {symbol}\n"
                        f"Posisi: {signal}\n"
                        f"Entry: {entry_realtime:.2f}\n"
                        f"SL: {sl:.2f}\n"
                        f"TP: {tp:.2f}\n"
                        f"Qty: {pos_size:.4f}"
                    )
                    st.success(message.replace("\n", " | "))
                    save_last_trade(symbol, INTERVAL, signal, candle_time)
                    with open("log_trading.txt", "a") as f:
                        f.write(f"{datetime.datetime.now()} | SUCCESS | {message}\n")
                else:
                    raise Exception("Trade execution returned False")
            except Exception as e:
                error_message = f"[ERROR] Gagal eksekusi trade untuk {symbol}: {e}"
                st.error(error_message)
                with open("log_trading.txt", "a") as f:
                    f.write(f"{datetime.datetime.now()} | ERROR | {error_message}\n")

        if st.button(f"🚨 Eksekusi Trade {symbol} ({signal})"):
            safe_execute_trade_and_notify()

    st.subheader(f"📊 {symbol} - Latest Candle")
    st.write(latest[['close', 'volume', 'volume_spike', 'rsi', 'adx', 'macd', 'macd_signal', 'ema']])
    st.write(f"Signal Detected: {signal if signal else 'Tidak ada'}")

# Sidebar info
st.sidebar.write("⏱ Waktu sekarang:", datetime.datetime.now().strftime("%H:%M:%S"))
debug = st.sidebar.checkbox("🔍 Debug Mode", value=False)
if debug:
    st.write("====== DEBUG: ENHANCED SIGNAL CHECK ======")
    st.write(f"CLOSE: {latest['close']}, OPEN: {latest['open']}")
    st.write(client.futures_account_balance())
