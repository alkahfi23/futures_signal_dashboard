# trade.py

import os
from binance.client import Client
from binance.enums import *

# Load API keys from environment
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
    return 3, 0.001  # default

def execute_trade(symbol, signal, quantity, sl, tp, leverage):
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        # Round quantity
        qty_precision, step_size = get_symbol_precision(symbol)
        quantity = round_step_size(quantity, step_size)

        # Position Side
        side = SIDE_BUY if signal == "LONG" else SIDE_SELL
        opposite_side = SIDE_SELL if signal == "LONG" else SIDE_BUY

        # Entry Order (Market)
        client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )

        # TP Order
        client.futures_create_order(
            symbol=symbol,
            side=opposite_side,
            type=ORDER_TYPE_LIMIT,
            price=str(round(tp, 2)),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )

        # SL Order
        client.futures_create_order(
            symbol=symbol,
            side=opposite_side,
            type=ORDER_TYPE_STOP_MARKET,
            stopPrice=str(round(sl, 2)),
            quantity=quantity,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )

        return True

    except Exception as e:
        print(f"[ERROR] Failed to execute trade: {e}")
        return False
