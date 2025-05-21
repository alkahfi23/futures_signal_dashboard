# Refactored and Enhanced Futures Signal Dashboard
import os
import streamlit as st
import pandas as pd
import requests
import ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from twilio.rest import Client
from streamlit_autorefresh import st_autorefresh

# === Configuration ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
FROM = "whatsapp:+14155238886"
TO = os.getenv("WHATSAPP_TO")

BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m", "5m"]
LIMIT = 100
REFRESH_INTERVAL = 60
TRAILING_STOP_PERCENT = 0.01

last_signals = {}
positions = {}

@st.cache_data(ttl=55)
def get_klines(symbol, interval="1m", limit=100):
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url)
        data = res.json()
        df = pd.DataFrame(data, columns=[
            'open_time','open','high','low','close','volume',
            'close_time','qav','num_trades','taker_base_vol','taker_quote_vol','ignore'])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        st.error(f"[ERROR] Gagal ambil data {symbol} ({interval}): {e}")
        return pd.DataFrame()

def send_whatsapp_message(message):
    if not (ACCOUNT_SID and AUTH_TOKEN and TO):
        st.warning("⚠️ Twilio credentials or WhatsApp recipient not set in environment variables.")
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

def enhanced_generate_signal(df):
    latest = df.iloc[-1]

    if pd.isna(latest['ema']) or pd.isna(latest['rsi']) or pd.isna(latest['macd']) or pd.isna(latest['macd_signal']):
        return ""

    st.write(f"[DEBUG] Harga: {latest['close']:.2f}, EMA: {latest['ema']:.2f}, RSI: {latest['rsi']:.2f}, "
             f"MACD: {latest['macd']:.4f}, MACD Signal: {latest['macd_signal']:.4f}, "
             f"ADX: {latest['adx']:.2f}, BB Upper: {latest['bb_upper']:.2f}, BB Lower: {latest['bb_lower']:.2f}")

    long_cond = (
        latest['rsi'] < 40 and
        latest['macd'] > latest['macd_signal'] and
        latest['close'] < latest['bb_lower'] * 1.01 and
        latest['close'] > latest['ema'] * 0.98 and
        latest['adx'] > 15
    )

    short_cond = (
        latest['rsi'] > 60 and
        latest['macd'] < latest['macd_signal'] and
        latest['close'] > latest['bb_upper'] * 0.99 and
        latest['close'] < latest['ema'] * 1.02 and
        latest['adx'] > 15
    )

    if long_cond:
        return "LONG"
    elif short_cond:
        return "SHORT"
    return ""

# === Streamlit UI ===
st.set_page_config(page_title="Futures Signal Dashboard", layout="wide")
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="datarefresh")

st.title("🚀 Futures Signal Dashboard")

for symbol in SYMBOLS:
    for interval in INTERVALS:
        df = get_klines(symbol, interval)
        if df.empty or df.shape[0] < 20:
            continue
        df = calculate_indicators(df)
        signal = enhanced_generate_signal(df)

        if interval == "1m":
            latest_price = df['close'].iloc[-1]

            col1, col2 = st.columns([1, 3])
            with col1:
                st.metric(label=f"{symbol} ({interval})", value=latest_price, delta=signal)

            with col2:
                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    row_heights=[0.5, 0.25, 0.25],
                    vertical_spacing=0.02,
                    subplot_titles=("Price with Bollinger Bands & EMA", "RSI", "MACD")
                )

                fig.add_trace(go.Candlestick(
                    x=df['open_time'], open=df['open'], high=df['high'],
                    low=df['low'], close=df['close'], name="Candles"
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=df['open_time'], y=df['bb_upper'], line=dict(color='gray', dash='dot'), name='BB Upper'
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=df['open_time'], y=df['bb_lower'], line=dict(color='gray', dash='dot'), name='BB Lower'
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=df['open_time'], y=df['ema'], line=dict(color='orange'), name='EMA20'
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=df['open_time'], y=df['rsi'], name='RSI', line=dict(color='purple')
                ), row=2, col=1)

                fig.add_hline(y=70, line=dict(dash='dot', color='red'), row=2, col=1)
                fig.add_hline(y=30, line=dict(dash='dot', color='green'), row=2, col=1)

                fig.add_trace(go.Scatter(
                    x=df['open_time'], y=df['macd'], name='MACD', line=dict(color='blue')
                ), row=3, col=1)

                fig.add_trace(go.Scatter(
                    x=df['open_time'], y=df['macd_signal'], name='Signal Line', line=dict(color='red')
                ), row=3, col=1)

                fig.add_trace(go.Bar(
                    x=df['open_time'], y=(df['macd'] - df['macd_signal']), name='MACD Histogram',
                    marker_color=['green' if v > 0 else 'red' for v in (df['macd'] - df['macd_signal'])]
                ), row=3, col=1)

                fig.update_layout(
                    height=800,
                    title=f"{symbol} - {interval} Signals & Indicators",
                    xaxis=dict(rangeslider=dict(visible=False)),
                    showlegend=False
                )

                st.plotly_chart(fig, use_container_width=True)

            # === Signal Handling ===
            signal_key = f"{symbol}_{interval}"
            last_signal = last_signals.get(signal_key)

            if signal and signal != last_signal:
                msg = f"📢 Signal {signal} untuk {symbol} ({interval})"
                st.success(msg)
                send_whatsapp_message(msg)
                last_signals[signal_key] = signal
            elif not signal and last_signal:
                st.info(f"ℹ️ Menunggu sinyal berlawanan untuk {symbol} ({interval})")
