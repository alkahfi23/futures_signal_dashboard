import os
import time
import math
from binance.client import Client
from binance.enums import *

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

def get_symbol_info(symbol):
    try:
        info = client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                return s
    except Exception as e:
        print(f"[ERROR] Fetch symbol info: {e}")
    return None

def get_step_size(symbol):
    s = get_symbol_info(symbol)
    if s:
        try:
            step_size = float([f for f in s['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])
            return step_size
        except Exception as e:
            print(f"[ERROR] Get step size: {e}")
    return 0.001

def get_min_qty(symbol):
    s = get_symbol_info(symbol)
    if s:
        try:
            min_qty = float([f for f in s['filters'] if f['filterType'] == 'LOT_SIZE'][0]['minQty'])
            return min_qty
        except Exception as e:
            print(f"[ERROR] Get min qty: {e}")
    return 0.001

def get_tick_size(symbol):
    s = get_symbol_info(symbol)
    if s:
        try:
            tick_size = float([f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER'][0]['tickSize'])
            return tick_size
        except Exception as e:
            print(f"[ERROR] Get tick size: {e}")
    return 0.01

def round_step_size(quantity, step_size):
    rounded = math.floor(quantity / step_size) * step_size
    return round(rounded, 8)

def round_price(price, tick_size):
    rounded = math.floor(price / tick_size) * tick_size
    return round(rounded, 8)

def calculate_sl_tp(entry, atr, signal, risk_ratio=2.5):
    if signal == "LONG":
        sl = entry - atr * 1.5
        tp = entry + atr * risk_ratio
    else:
        sl = entry + atr * 1.5
        tp = entry - atr * risk_ratio
    return sl, tp

def position_exists(symbol):
    try:
        positions = client.futures_position_information(symbol=symbol)
        # pos_amt = posisi terbuka (bisa + untuk long, - untuk short)
        pos = next(p for p in positions if p['symbol'] == symbol)
        pos_amt = float(pos['positionAmt'])
        print(f"[DEBUG] Position amount for {symbol}: {pos_amt}")
        return pos_amt != 0
    except Exception as e:
        print(f"[ERROR] position_exists: {e}")
        return False

def place_trade(symbol, signal, quantity, sl, tp, leverage):
    try:
        print(f"[DEBUG] Setting leverage {leverage} for {symbol}")
        resp_lev = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"[DEBUG] Leverage response: {resp_lev}")

        step_size = get_step_size(symbol)
        min_qty = get_min_qty(symbol)
        tick_size = get_tick_size(symbol)

        quantity = round_step_size(quantity, step_size)
        if quantity < min_qty:
            print(f"[ERROR] Quantity {quantity} less than minimum {min_qty}, aborting trade.")
            return False

        sl = round_price(sl, tick_size)
        tp = round_price(tp, tick_size)

        side = SIDE_BUY if signal == "LONG" else SIDE_SELL
        opposite = SIDE_SELL if signal == "LONG" else SIDE_BUY

        print(f"\n[ENTRY] {signal} {symbol} Qty: {quantity} @ Lev {leverage}")
        print(f"[ENTRY] SL: {sl} TP: {tp}")

        order_market = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        print(f"[DEBUG] Market order response: {order_market}")

        order_tp = client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type=ORDER_TYPE_LIMIT,
            price=str(tp),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )
        print(f"[DEBUG] TP order response: {order_tp}")

        order_sl = client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type=ORDER_TYPE_STOP_MARKET,
            stopPrice=str(sl),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )
        print(f"[DEBUG] SL order response: {order_sl}")

        return True

    except Exception as e:
        print(f"[ERROR] Trade Error: {e}")
        return False

def execute_trade(symbol, signal, entry, atr, account_balance, risk_pct, max_leverage=100):
    try:
        # Perhitungan dinamis posisi dan leverage agar tidak margin call
        risk_amount = account_balance * (risk_pct / 100)
        sl_distance = atr * 1.5  # SL jarak default (sama dgn rumus utama)
        raw_position = risk_amount / sl_distance

        # Coba leverage dari tinggi ke rendah sampai tidak terlalu berisiko
        for leverage in range(max_leverage, 1, -1):
            pos_size = raw_position * leverage
            used_margin = (pos_size * entry) / leverage
            if used_margin <= account_balance * 0.9:  # Sisakan margin 10%
                break  # leverage aman ditemukan

        # Set leverage dan margin type CROSS
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        try:
            client.futures_change_margin_type(symbol=symbol, marginType='CROSSED')
        except Exception as e:
            if "No need to change margin type" not in str(e):
                raise

        # Buat order
        order = client.futures_create_order(
            symbol=symbol,
            side='BUY' if signal == "LONG" else 'SELL',
            type='MARKET',
            quantity=round(pos_size, 4)
        )

        print(f"[✅ ORDER SUCCESS] {order}")
        return True
    except Exception as e:
        print(f"[❌ EXECUTION FAILED] {e}")
        return False
