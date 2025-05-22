# trade.py
import os
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv

# === Load API Key ===
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET)

# === Eksekusi Order ===
def execute_trade(symbol, direction, quantity, sl_price=None, tp_price=None, leverage=10):
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        side = SIDE_BUY if direction.upper() == "LONG" else SIDE_SELL

        # Order pasar untuk entry
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )

        # SL dan TP pakai order OCO (jika mau pakai manual bisa juga)
        if sl_price and tp_price:
            stop_side = SIDE_SELL if direction.upper() == "LONG" else SIDE_BUY
            client.futures_create_order(
                symbol=symbol,
                side=stop_side,
                type=ORDER_TYPE_STOP_MARKET,
                stopPrice=round(sl_price, 2),
                closePosition=True,
                timeInForce=TIME_IN_FORCE_GTC
            )
            client.futures_create_order(
                symbol=symbol,
                side=stop_side,
                type=ORDER_TYPE_TAKE_PROFIT_MARKET,
                stopPrice=round(tp_price, 2),
                closePosition=True,
                timeInForce=TIME_IN_FORCE_GTC
            )

        print(f"✅ Order {direction.upper()} {symbol} sukses!")
        return order

    except Exception as e:
        print(f"[ERROR] Gagal eksekusi order: {e}")
        return None


# === Cek Posisi Terbuka ===
def check_position(symbol):
    positions = client.futures_position_information(symbol=symbol)
    for p in positions:
        if float(p["positionAmt"]) != 0:
            print(f"📊 Posisi aktif: {p['symbol']} {p['positionSide']} {p['positionAmt']} @ {p['entryPrice']}")
            return p
    return None


# === Kalkulasi Ukuran Posisi ===
def calculate_quantity(balance_usdt, risk_pct, entry_price, sl_price, leverage):
    risk_amount = balance_usdt * (risk_pct / 100)
    stop_loss_amount = abs(entry_price - sl_price)
    qty = (risk_amount / stop_loss_amount) * leverage
    return round(qty, 3)
