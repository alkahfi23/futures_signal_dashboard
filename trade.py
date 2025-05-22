# modules/trade.py

import os
import time
from binance.client import Client
from binance.enums import *

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

def round_step_size(quantity, step_size):
    return round(quantity - (quantity % step_size), 8)

def get_symbol_precision(symbol):
    try:
        info = client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                qty_precision = int(s['quantityPrecision'])
                step_size = float([f for f in s['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])
                return qty_precision, step_size
    except Exception as e:
        print(f"[ERROR] Precision fetch: {e}")
    return 3, 0.001

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
        pos = next(p for p in positions if p['symbol'] == symbol)
        return float(pos['positionAmt']) != 0
    except:
        return False

def place_trade(symbol, signal, quantity, sl, tp, leverage):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        qty_precision, step_size = get_symbol_precision(symbol)
        quantity = round_step_size(quantity, step_size)

        side = SIDE_BUY if signal == "LONG" else SIDE_SELL
        opposite = SIDE_SELL if signal == "LONG" else SIDE_BUY

        print(f"\n[ENTRY] {signal} {symbol} Qty: {quantity} @ Lev {leverage}")

        client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )

        client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type=ORDER_TYPE_LIMIT,
            price=str(round(tp, 2)),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )

        client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type=ORDER_TYPE_STOP_MARKET,
            stopPrice=str(round(sl, 2)),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )

        return True

    except Exception as e:
        print(f"[ERROR] Trade Error: {e}")
        return False

def execute_trade(symbol, signal, quantity, entry, leverage, atr=None, auto_switch=True, timeout=300):
    sl, tp = calculate_sl_tp(entry, atr, signal) if atr else (entry * 0.98, entry * 1.02)

    if position_exists(symbol):
        print(f"⚠️ Posisi aktif di {symbol}, tidak entry ulang.")
        return False

    success = place_trade(symbol, signal, quantity, sl, tp, leverage)
    if not success or not auto_switch or atr is None:
        return success

    try:
        print("🔄 Monitoring for SL trigger...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
            if (signal == "LONG" and price <= sl) or (signal == "SHORT" and price >= sl):
                print(f"⚠️ SL Triggered. Switching to {'SHORT' if signal=='LONG' else 'LONG'}")

                new_signal = "SHORT" if signal == "LONG" else "LONG"
                new_entry = price
                new_sl, new_tp = calculate_sl_tp(new_entry, atr, new_signal)

                place_trade(symbol, new_signal, quantity, new_sl, new_tp, leverage)
                break

            time.sleep(2)

    except Exception as e:
        print(f"[ERROR] Monitor SL: {e}")
        return False

    return True
