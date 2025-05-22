import os
import streamlit as st
import pandas as pd
import requests
import ta
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from twilio.rest import Client
from streamlit_autorefresh import st_autorefresh
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from manrisk import calculate_position_size, calculate_risk_reward, margin_call_warning, format_risk_message
from trade import execute_trade


# === Environment Variables ===
ACCOUNT_SID = os.getenv("TWILIO_SID")
AUTH_TOKEN = os.getenv("TWILIO_TOKEN")
FROM = "whatsapp:+14155238886"
TO = os.getenv("WHATSAPP_TO")
BASE_URL = "https://api.binance.com"

# === Configuration ===
SYMBOLS = ["BTCUSDT"]
INTERVAL = "1m"
LIMIT = 100
REFRESH_INTERVAL = 55  # seconds
account_balance = 20   # USD
risk_pct = 50
leverage = 100

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
        st.warning("⚠️ Twilio credentials atau nomor tujuan belum disetel.")
        return
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        client.messages.create(body=message, from_=FROM, to=TO)
    except Exception as e:
        st.error(f"[ERROR] WhatsApp: {e}")

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

def enhanced_generate_signal(df):
    latest = df.iloc[-1]
    if pd.isna(latest['ema']) or pd.isna(latest['rsi']) or pd.isna(latest['macd']) or pd.isna(latest['macd_signal']):
        return ""

    vol_spike = latest['volume'] > latest['volume_ma20'] * 1.5
    strong_candle = abs(latest['close'] - latest['open']) > 0.5 * (latest['high'] - latest['low'])

    early_macd_up = df['macd'].iloc[-2] < df['macd_signal'].iloc[-2] and latest['macd'] > latest['macd_signal']
    early_macd_down = df['macd'].iloc[-2] > df['macd_signal'].iloc[-2] and latest['macd'] < latest['macd_signal']

    above_bb = latest['close'] > latest['bb_upper'] * 1.002
    below_bb = latest['close'] < latest['bb_lower'] * 0.998

    # Filter BB squeeze
    bb_width = latest['bb_upper'] - latest['bb_lower']
    avg_range = df['high'].iloc[-20:].mean() - df['low'].iloc[-20:].mean()
    bb_squeeze = bb_width < avg_range * 0.5

    if bb_squeeze:
        return ""

    long_cond = (
        (early_macd_up or above_bb or strong_candle)
        and latest['rsi'] > 40
        and latest['close'] > latest['ema'] * 1.002
        and vol_spike
        and latest['adx'] > 10
    )
    short_cond = (
        (early_macd_down or below_bb or strong_candle)
        and latest['rsi'] < 60
        and latest['close'] < latest['ema'] * 0.998
        and vol_spike
        and latest['adx'] > 10
    )

    return "LONG" if long_cond else "SHORT" if short_cond else ""


def load_last_signal(symbol, interval):
    try:
        with open(f"last_signal_{symbol}_{interval}.txt", "r") as f:
            return f.read().strip()
    except:
        return ""

def save_last_signal(symbol, interval, signal):
    with open(f"last_signal_{symbol}_{interval}.txt", "w") as f:
        f.write(signal)

def load_last_trade(symbol, interval):
    try:
        with open(f"last_trade_{symbol}_{interval}.txt", "r") as f:
            return f.read().strip().split(",")  # [signal, candle_time]
    except:
        return ["", ""]

def save_last_trade(symbol, interval, signal, candle_time):
    with open(f"last_trade_{symbol}_{interval}.txt", "w") as f:
        f.write(f"{signal},{candle_time}")

# === Streamlit UI ===
st.set_page_config(page_title="Futures Signal Dashboard", layout="wide")
st.title("🚀 Futures Signal Dashboard - 1 Minute")
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="refresh")

for symbol in SYMBOLS:
    df = get_klines(symbol, INTERVAL)
    if df.empty or df.shape[0] < 20:
        continue

    df = calculate_indicators(df)
    signal = enhanced_generate_signal(df)
    latest = df.iloc[-1]
    entry = latest['close']
    candle_time = str(latest['open_time'])

    if signal:
        # Cek apakah trade sudah dilakukan pada candle ini
        last_trade_signal, last_trade_time = load_last_trade(symbol, INTERVAL)
        if signal == last_trade_signal and candle_time == last_trade_time:
            st.warning(f"⛔ Duplikat trade {signal} {symbol} - dilewati")
            continue

        sl = tp = None
        if signal == "LONG":
            sl = entry - latest['atr'] * 1.5
            tp = entry + latest['atr'] * 2.5
        elif signal == "SHORT":
            sl = entry + latest['atr'] * 1.5
            tp = entry - latest['atr'] * 2.5

        if sl and tp:
            pos_size = calculate_position_size(account_balance, risk_pct, entry, sl, leverage)
            rrr = calculate_risk_reward(entry, sl, tp)
            is_margin_risk, margin_note = margin_call_warning(account_balance, pos_size, entry, leverage)
            risk_msg = format_risk_message(symbol, INTERVAL, entry, sl, tp, pos_size, rrr, margin_note)
            send_whatsapp_message(risk_msg)

            trade_result = execute_trade(
                symbol, signal, pos_size, sl, tp, leverage,
                auto_switch=True,
                atr=latest['atr']
            )

            if trade_result:
                message = (
                    f"✅ TRADE EXECUTED:\n"
                    f"Pair: {symbol}\n"
                    f"Posisi: {signal}\n"
                    f"Entry: {entry:.2f}\n"
                    f"SL: {sl:.2f}\n"
                    f"TP: {tp:.2f}\n"
                    f"Qty: {pos_size:.4f}"
                )
                st.success(message.replace("\n", " | "))
                send_whatsapp_message(message)

                # Simpan status trade terakhir
                save_last_trade(symbol, INTERVAL, signal, candle_time)

        last_signal = load_last_signal(symbol, INTERVAL)
        if signal != last_signal:
            st.success(f"📢 New signal {signal} for {symbol}!")
            send_whatsapp_message(f"📢 Signal {signal} untuk {symbol}!")
            save_last_signal(symbol, INTERVAL, signal)
        else:
            st.info(f"✅ No change for {symbol}: {signal}")
    else:
        st.info(f"⏳ Menunggu sinyal {symbol} ({INTERVAL})")

st.subheader(f"📊 {symbol} - Latest Candle")
st.write(latest[['close', 'volume', 'volume_spike', 'rsi', 'adx', 'macd', 'macd_signal', 'ema']])
st.write(f"Signal Detected: {signal}")
st.sidebar.write("⏱ Waktu sekarang:", datetime.datetime.now().strftime("%H:%M:%S"))

