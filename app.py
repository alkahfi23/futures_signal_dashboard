import streamlit as st
import pandas as pd
import time
from trade import get_signal, calculate_position_size, margin_warning, execute_trade, position_exists
from worker_bot import close_opposite_position
from binance.client import Client
import os

st.set_page_config(layout="wide")

# ====== Konstanta ======
SYMBOLS = ["BTCUSDT"]
INTERVAL = "1m"
RISK_PER_TRADE = 0.01
LEVERAGE = 20
MIN_QTY = 0.001

# ====== Inisialisasi Client Binance ======
client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

# ====== App UI ======
st.title("⚡ Futures Signal Dashboard - 1 Minute")

risk_pct = st.sidebar.slider("Risk % per Trade", min_value=0.5, max_value=5.0, value=1.0) / 100
leverage = st.sidebar.slider("Leverage", min_value=1, max_value=50, value=LEVERAGE)

# ====== Dashboard Loop ======
if st.button("🔄 Jalankan Analisis Sinyal"):
    for symbol in SYMBOLS:
        st.subheader(f"📈 {symbol} - Timeframe: {INTERVAL}")
        try:
            df = get_signal(symbol, interval=INTERVAL)
            if df is None or df.empty:
                st.warning(f"⛔ Tidak ada data untuk {symbol}")
                continue

            latest = df.iloc[-1]
            signal = latest['signal']
            entry = latest['close']

            balance_info = client.futures_account_balance()
            usdt_balance = next(float(b['balance']) for b in balance_info if b['asset'] == 'USDT')
            account_balance = usdt_balance

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

                # ✅ Auto-reverse: tutup posisi berlawanan sebelum buka
                close_opposite_position(client, symbol, signal)

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

        except Exception as e:
            st.error(f"❌ Gagal proses {symbol}: {e}")
