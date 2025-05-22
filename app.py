# === Refactored and Enhanced Futures Signal Dashboard ===
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
from ta.volatility import AverageTrueRange
from manrisk import calculate_position_size, calculate_risk_reward, margin_call_warning, format_risk_message


# === Configuration ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
FROM = "whatsapp:+14155238886"
TO = os.getenv("WHATSAPP_TO")

BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m"]
LIMIT = 100
REFRESH_INTERVAL = 55
TRAILING_STOP_PERCENT = 0.01

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
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    df['volume_spike'] = df['volume'] > df['volume_ma20'] * 2
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['atr'] = atr.average_true_range()

    return df

def is_volume_spike(df):
    latest = df.iloc[-1]
    volume_avg = df['volume'].rolling(window=20).mean().iloc[-1]
    return latest['volume'] > 2 * volume_avg

def is_strong_trend_candle(df):
    latest = df.iloc[-1]
    body_size = abs(latest['close'] - latest['open'])
    candle_range = latest['high'] - latest['low']
    return body_size > 0.6 * candle_range

def enhanced_generate_signal(df):
    latest = df.iloc[-1]

    if pd.isna(latest['ema']) or pd.isna(latest['rsi']) or pd.isna(latest['macd']) or pd.isna(latest['macd_signal']):
        return ""

    vol_spike = is_volume_spike(df)
    strong_candle = is_strong_trend_candle(df)

    price_above_bb_upper = latest['close'] > latest['bb_upper'] * 1.005
    price_below_bb_lower = latest['close'] < latest['bb_lower'] * 0.995
    early_macd_cross_up = (df['macd'].iloc[-2] < df['macd_signal'].iloc[-2]) and (latest['macd'] > latest['macd_signal'])
    early_macd_cross_down = (df['macd'].iloc[-2] > df['macd_signal'].iloc[-2]) and (latest['macd'] < latest['macd_signal'])

    st.write(f"[DEBUG] Harga: {latest['close']:.2f}, EMA: {latest['ema']:.2f}, RSI: {latest['rsi']:.2f}, "
             f"MACD: {latest['macd']:.4f}, MACD Signal: {latest['macd_signal']:.4f}, "
             f"ADX: {latest['adx']:.2f}, BB Upper: {latest['bb_upper']:.2f}, BB Lower: {latest['bb_lower']:.2f}, "
             f"Vol Spike: {vol_spike}, Strong Candle: {strong_candle}, "
             f"MACD Early Up: {early_macd_cross_up}, MACD Early Down: {early_macd_cross_down}")

    long_cond = (
        (early_macd_cross_up or price_above_bb_upper or strong_candle) and
        latest['rsi'] > 45 and
        latest['close'] > latest['ema'] * 1.005 and
        vol_spike and
        latest['adx'] > 15
    )

    short_cond = (
        (early_macd_cross_down or price_below_bb_lower or strong_candle) and
        latest['rsi'] < 55 and
        latest['close'] < latest['ema'] * 0.995 and
        vol_spike and
        latest['adx'] > 15
    )
# === Risk Management Section ===
account_balance = 20 # Ganti sesuai real account balance kamu
risk_pct = 50
leverage = 10

entry = latest['close']
if "LONG" in signal:
    sl = entry - latest['atr'] * 1.5
    tp = entry + latest['atr'] * 2.5
    direction = "long"
elif "SHORT" in signal:
    sl = entry + latest['atr'] * 1.5
    tp = entry - latest['atr'] * 2.5
    direction = "short"
else:
    sl = tp = direction = None

return ""

if sl and tp:
    pos_size = calculate_position_size(account_balance, risk_pct, entry, sl, leverage)
    rrr = calculate_risk_reward(entry, sl, tp)
    is_margin_risk, margin_note = margin_call_warning(account_balance, pos_size, entry, leverage)
    risk_msg = format_risk_message(symbol, interval, entry, sl, tp, pos_size, rrr, margin_note)

    # ✅ Kirim ke WhatsApp
    send_whatsapp_message(risk_msg)

# === Persistent Signal Check ===
def load_last_signal(symbol, interval):
    path = f"last_signal_{symbol}_{interval}.txt"
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def save_last_signal(symbol, interval, signal):
    path = f"last_signal_{symbol}_{interval}.txt"
    with open(path, "w") as f:
        f.write(signal)

# === Streamlit UI ===
st.set_page_config(page_title="Fuures Signal Dashboard", layout="wide")
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
            last_signal = load_last_signal(symbol, interval)

            if signal and signal != last_signal:
                msg = f"📢 Signal {signal} untuk {symbol} ({interval})"
                st.success(msg)
                send_whatsapp_message(msg)
                save_last_signal(symbol, interval, signal)
            elif not signal:
                st.info(f"ℹ️ Menunggu sinyal untuk {symbol} ({interval})")
            else:
                st.info(f"✅ Tidak ada perubahan sinyal {symbol} ({interval}): {signal}")
