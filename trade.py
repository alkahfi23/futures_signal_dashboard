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

def execute_trade(symbol, signal, quantity, entry, leverage, atr=None, auto_switch=True, timeout=300):
    print(f"[DEBUG] execute_trade called with symbol={symbol}, signal={signal}, quantity={quantity}, entry={entry}, leverage={leverage}, atr={atr}")

    if atr:
        sl, tp = calculate_sl_tp(entry, atr, signal)
    else:
        # fallback SL/TP 2% default
        if signal == "LONG":
            sl = entry * 0.98
            tp = entry * 1.02
        else:
            sl = entry * 1.02
            tp = entry * 0.98

    print(f"[DEBUG] Calculated SL={sl}, TP={tp}")

    if position_exists(symbol):
        print(f"⚠️ Position already active for {symbol}, skipping new trade.")
        return False

    success = place_trade(symbol, signal, quantity, sl, tp, leverage)
    if not success:
        print("[ERROR] Initial trade placement failed.")
        return False

    if not auto_switch or atr is None:
        return True

    try:
        print("🔄 Monitoring SL trigger for possible auto-switch...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
            print(f"[DEBUG] Current price: {price}")
            if (signal == "LONG" and price <= sl) or (signal == "SHORT" and price >= sl):
                print(f"⚠️ SL triggered at price {price}. Switching side.")

                new_signal = "SHORT" if signal == "LONG" else "LONG"
                new_entry = price
                new_sl, new_tp = calculate_sl_tp(new_entry, atr, new_signal)

                place_trade(symbol, new_signal, quantity, new_sl, new_tp, leverage)
                break

            time.sleep(2)

    except Exception as e:
        print(f"[ERROR] SL monitor error: {e}")
        return False

    return True
