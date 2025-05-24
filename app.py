import streamlit as st
import time
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Inisialisasi Binance Client
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = Client(API_KEY, API_SECRET)

st.set_page_config("🟢 Binance Futures Status", layout="wide")
st.title("📊 Real-Time Binance Futures Status")

# Auto refresh setiap 1 menit
st_autorefresh = st.empty()
if st_autorefresh.button("🔁 Refresh Manual"):
    st.experimental_rerun()

st.markdown("⏱️ **Auto-refresh setiap 60 detik**")
time.sleep(1)

# Fungsi ambil saldo USDT futures
def get_futures_balance():
    try:
        balances = client.futures_account_balance()
        for b in balances:
            if b['asset'] == 'USDT':
                return float(b['balance']), float(b['availableBalance'])
        return 0.0, 0.0
    except BinanceAPIException as e:
        st.error(f"Gagal ambil saldo: {e}")
        return 0.0, 0.0

# Fungsi ambil total unrealized PnL dan posisi berjalan
def get_positions():
    try:
        positions = client.futures_account()['positions']
        running_positions = []
        total_upnl = 0.0
        total_loss = 0.0
        total_gain = 0.0

        for p in positions:
            amt = float(p['positionAmt'])
            upnl = float(p['unrealizedProfit'])
            if amt != 0:
                symbol = p['symbol']
                entry = float(p['entryPrice'])
                mark = float(p['markPrice'])
                side = "LONG" if amt > 0 else "SHORT"
                running_positions.append({
                    'symbol': symbol,
                    'side': side,
                    'qty': amt,
                    'entry': entry,
                    'mark': mark,
                    'pnl': upnl
                })
                total_upnl += upnl
                if upnl > 0:
                    total_gain += upnl
                else:
                    total_loss += abs(upnl)

        return running_positions, total_upnl, total_gain, total_loss
    except BinanceAPIException as e:
        st.error(f"Gagal ambil posisi: {e}")
        return [], 0.0, 0.0, 0.0

# Tampilkan Saldo
balance, available = get_futures_balance()
st.metric("💰 Futures Balance (USDT)", f"{balance:.2f} USDT")
st.metric("🟢 Available Balance", f"{available:.2f} USDT")

# Tampilkan Profit dan Loss
positions, total_upnl, total_gain, total_loss = get_positions()
st.metric("📈 Total Gain", f"{total_gain:.2f} USDT", delta=f"{total_gain:.2f}")
st.metric("📉 Total Loss", f"{total_loss:.2f} USDT", delta=f"-{total_loss:.2f}")
st.metric("📊 Unrealized PnL", f"{total_upnl:.2f} USDT", delta=f"{total_upnl:.2f}")

# Tampilkan Posisi Berjalan
st.subheader("🚀 Running Positions")
if positions:
    st.dataframe(positions)
else:
    st.info("Tidak ada posisi yang sedang berjalan.")

# Auto-refresh tiap 60 detik
st_autorefresh.empty()
st.experimental_rerun()
