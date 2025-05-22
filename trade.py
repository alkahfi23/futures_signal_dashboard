# trade.py

import os
from binance.client import Client
from binance.enums import *
import time

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

def place_trade(symbol, signal, quantity, entry_price, sl, tp, leverage):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        qty_precision, step_size = get_symbol_precision(symbol)
        quantity = round_step_size(quantity, step_size)

        side = SIDE_BUY if signal == "LONG" else SIDE_SELL
        opposite = SIDE_SELL if signal == "LONG" else SIDE_BUY

        # Entry
        client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )

        # TP
        client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type=ORDER_TYPE_LIMIT,
            price=str(round(tp, 2)),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )

        # SL
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

def execute_trade(symbol, signal, quantity, sl, tp, leverage, auto_switch=True, atr=None):
    success = place_trade(symbol, signal, quantity, entry_price=tp if signal=="LONG" else sl, sl=sl, tp=tp, leverage=leverage)
    if not success:
        return False

    if not auto_switch or atr is None:
        return True

    # Monitor for SL trigger (simple polling)
    try:
        print("🔄 Monitoring for SL trigger...")
        while True:
            price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
            if (signal == "LONG" and price <= sl) or (signal == "SHORT" and price >= sl):
                print(f"⚠️ SL Triggered. Switching to {'SHORT' if signal=='LONG' else 'LONG'}")

                new_signal = "SHORT" if signal == "LONG" else "LONG"
                new_entry = price
                new_sl = new_entry + atr * 1.5 if new_signal == "SHORT" else new_entry - atr * 1.5
                new_tp = new_entry - atr * 2.5 if new_signal == "SHORT" else new_entry + atr * 2.5

                place_trade(symbol, new_signal, quantity, entry_price=new_entry, sl=new_sl, tp=new_tp, leverage=leverage)
                break
            time.sleep(2)  # check every 2 sec
    except Exception as e:
        print(f"[ERROR] Monitor SL: {e}")
        return False

    return True
