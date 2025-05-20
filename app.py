# --- import dan konfigurasi dasar ---
import os
import streamlit as st
import pandas as pd
import requests
import ta
import plotly.graph_objects as go
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from twilio.rest import Client
from streamlit_autorefresh import st_autorefresh

# === Konstanta dan Variabel Global ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
FROM = "whatsapp:+14155238886"
TO = os.getenv("WHATSAPP_TO")

BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m", "15m"]
PRIMARY_INTERVAL = "1m"
CONFIRMATION_INTERVAL = "15m"

LIMIT = 100
REFRESH_INTERVAL = 60
TRAILING_STOP_PERCENT = 0.01
TP_DYNAMIC_MULTIPLIER = 1.5
SL_DYNAMIC_MULTIPLIER = 1.0

last_signals = {}
positions = {}

# === Fungsi-fungsi utama ===
@st.cache_data(ttl=55)
def get_klines(symbol, interval="1m", limit=100):
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url)
        data = res.json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
        return df
    except Exception as e:
        st.error(f"[ERROR] Gagal ambil data {symbol} ({interval}): {e}")
        return pd.DataFrame()

def send_whatsapp_message(message):
    if not (ACCOUNT_SID and AUTH_TOKEN and TO):
        st.warning("⚠️ Twilio credentials atau nomor WhatsApp belum diset.")
        return
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        client.messages.create(body=message, from_=FROM, to=TO)
    except Exception as e:
        st.error(f"[ERROR] WhatsApp: {e}")

def calculate_indicators(df):
    if df.shape[0] < 20:
        return df
    df['ema'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['rsi'] = RSIIndicator(df['close'], window=14).rsi()
    df['adx'] = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    macd = MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    return df

def generate_signal(df):
    latest = df.iloc[-1]
    if latest['rsi'] < 30 and latest['macd'] > latest['macd_signal'] and latest['close'] < latest['bb_lower']:
        return "LONG"
    elif latest['rsi'] > 70 and latest['macd'] < latest['macd_signal'] and latest['close'] > latest['bb_upper']:
        return "SHORT"
    return ""

def calculate_dynamic_tp_sl(df, signal):
    atr = df['high'].rolling(window=14).max() - df['low'].rolling(window=14).min()
    latest_atr = atr.iloc[-1]
    tp = latest_atr * TP_DYNAMIC_MULTIPLIER
    sl = latest_atr * SL_DYNAMIC_MULTIPLIER
    return tp, sl

def check_trailing_stop(symbol, price, signal, rsi, df, interval):
    symbol_interval = f"{symbol}_{interval}"
    tp_value, sl_value = calculate_dynamic_tp_sl(df, signal)

    if symbol_interval not in positions or signal != positions[symbol_interval]['signal']:
        positions[symbol_interval] = {
            "entry": price,
            "highest": price,
            "lowest": price,
            "signal": signal,
            "tp": price + tp_value if signal == "LONG" else price - tp_value,
            "sl": price - sl_value if signal == "LONG" else price + sl_value
        }
        return

    pos = positions[symbol_interval]
    if signal == "LONG":
        pos['highest'] = max(pos['highest'], price)
        if price < pos['highest'] * (1 - TRAILING_STOP_PERCENT) or price <= pos['sl'] or rsi >= 70:
            send_whatsapp_message(f"🚪 EXIT LONG {symbol} @ {price:.2f}")
            del positions[symbol_interval]
    elif signal == "SHORT":
        pos['lowest'] = min(pos['lowest'], price)
        if price > pos['lowest'] * (1 + TRAILING_STOP_PERCENT) or price >= pos['sl'] or rsi <= 30:
            send_whatsapp_message(f"🚪 EXIT SHORT {symbol} @ {price:.2f}")
            del positions[symbol_interval]

def confirm_with_higher_tf(primary_signal, confirmation_signal):
    return primary_signal == confirmation_signal and primary_signal != ""

# === Streamlit UI ===
st.set_page_config(page_title="Futures Signal Dashboard", layout="wide")
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="datarefresh")
st.title("🚀 Futures Signal Dashboard")

for symbol in SYMBOLS:
    data = {}
    for interval in INTERVALS:
        df = get_klines(symbol, interval)
        if df.empty or df.shape[0] < 20:
            continue
        df = calculate_indicators(df)
        signal = generate_signal(df)
        data[interval] = {"df": df, "signal": signal}

    if PRIMARY_INTERVAL not in data or CONFIRMATION_INTERVAL not in data:
        continue

    primary_df = data[PRIMARY_INTERVAL]['df']
    confirmation_signal = data[CONFIRMATION_INTERVAL]['signal']
    signal = data[PRIMARY_INTERVAL]['signal']
    confirmed = confirm_with_higher_tf(signal, confirmation_signal)

    latest_price = primary_df['close'].iloc[-1]
    col1, col2 = st.columns([1, 3])

    with col1:
        st.metric(label=f"{symbol} ({PRIMARY_INTERVAL})", value=latest_price, delta=signal)
        symbol_key = f"{symbol}_{PRIMARY_INTERVAL}"
        pos = positions.get(symbol_key)
        if pos:
            st.write(f"**Posisi Aktif:** {pos['signal']} | Entry: {pos['entry']:.2f} | TP: {pos['tp']:.2f} | SL: {pos['sl']:.2f}")

    with col2:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=primary_df['open_time'],
            open=primary_df['open'], high=primary_df['high'],
            low=primary_df['low'], close=primary_df['close'],
            name="Candles"))
        fig.add_trace(go.Scatter(x=primary_df['open_time'], y=primary_df['bb_upper'], line=dict(color='gray'), name='BB Upper'))
        fig.add_trace(go.Scatter(x=primary_df['open_time'], y=primary_df['bb_lower'], line=dict(color='gray'), name='BB Lower'))
        fig.update_layout(title=f"{symbol} - {PRIMARY_INTERVAL} Chart", xaxis_title="Time", yaxis_title="Price")
        st.plotly_chart(fig, use_container_width=True)

    # Proses sinyal hanya jika dikonfirmasi
    if confirmed:
        last_signal = last_signals.get(symbol_key)
        check_trailing_stop(symbol, latest_price, signal, primary_df['rsi'].iloc[-1], primary_df, PRIMARY_INTERVAL)

        if last_signal != signal:
            tp, sl = calculate_dynamic_tp_sl(primary_df, signal)
            tp_price = latest_price + tp if signal == "LONG" else latest_price - tp
            sl_price = latest_price - sl if signal == "LONG" else latest_price + sl

            msg = (
                f"📢 Multi-Timeframe Confirmed Signal {signal} untuk {symbol} ({PRIMARY_INTERVAL})\n"
                f"💰 Entry: {latest_price:.2f}\n"
                f"🎯 Take Profit: {tp_price:.2f}\n"
                f"🛡 Stop Loss: {sl_price:.2f}"
            )
            st.success(msg)
            send_whatsapp_message(msg)
            last_signals[symbol_key] = signal
        else:
            st.info(f"ℹ️ Sinyal {signal} untuk {symbol} ({PRIMARY_INTERVAL}) sudah dikirim.")
    else:
        st.warning(f"❌ Belum ada konfirmasi dari {CONFIRMATION_INTERVAL} untuk sinyal {signal} pada {symbol}")
