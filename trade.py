# trade.py

import os
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from utils import get_symbol_filters, get_position_info
from notifikasi import kirim_notifikasi_order, kirim_notifikasi_penutupan

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

def position_exists(symbol, side):
    try:
        pos = client.futures_position_information(symbol=symbol)
        for p in pos:
            amt = float(p['positionAmt'])
            if (side == "LONG" and amt > 0) or (side == "SHORT" and amt < 0):
                return True
        return False
    except BinanceAPIException as e:
        print(f"[ERROR] position_exists: {e}")
        return False

def close_opposite_position(symbol, side):
    try:
        pos = client.futures_position_information(symbol=symbol)
        for p in pos:
            amt = float(p['positionAmt'])
            if (side == "LONG" and amt < 0) or (side == "SHORT" and amt > 0):
                close_side = SIDE_BUY if amt < 0 else SIDE_SELL
                qty = abs(amt)
                mark_price = float(p['markPrice'])
                pnl = float(p['unrealizedProfit'])
                entry_price = float(p['entryPrice'])

                client.futures_create_order(
                    symbol=symbol,
                    side=close_side,
                    type=FUTURE_ORDER_TYPE_MARKET,
                    quantity=qty,
                    reduceOnly=True
                )

                percentage = (pnl / (abs(qty) * entry_price)) * 100 if entry_price > 0 else 0
                kirim_notifikasi_penutupan(symbol, pnl, percentage)

                print(f"[CLOSED] {symbol} {side} Posisi ditutup.")
    except BinanceAPIException as e:
        print(f"[ERROR] close_opposite_position: {e}")

def adjust_quantity(symbol, qty):
    try:
        filters = get_symbol_filters(symbol)
        step_size = float(filters['LOT_SIZE']['stepSize'])
        precision = str(step_size)[::-1].find('1')
        return round(qty, precision)
    except Exception as e:
        print(f"[ERROR] adjust_quantity: {e}")
        return qty

def set_leverage(symbol, leverage):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"✅ Leverage {symbol} di-set ke {leverage}")
    except BinanceAPIException as e:
        print(f"[ERROR] set_leverage: {e}")

def execute_trade(symbol, side, quantity, entry_price, leverage, position_side, sl_price, tp_price, trailing_stop_callback_rate=1.0):
    try:
        set_leverage(symbol, leverage)

        order_side = SIDE_BUY if side == "LONG" else SIDE_SELL
        client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type=FUTURE_ORDER_TYPE_MARKET,
            quantity=quantity,
            newClientOrderId=f"{symbol}_{side}_entry"
        )

        # Set TP/SL via reduce-only orders
        close_side = SIDE_SELL if side == "LONG" else SIDE_BUY

        client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=round(sl_price, 2),
            closePosition=True,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True,
            newClientOrderId=f"{symbol}_{side}_sl"
        )

        client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
            stopPrice=round(tp_price, 2),
            closePosition=True,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True,
            newClientOrderId=f"{symbol}_{side}_tp"
        )

        # Optional: trailing stop
        if trailing_stop_callback_rate:
            client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type="TRAILING_STOP_MARKET",
                callbackRate=trailing_stop_callback_rate,
                activationPrice=round(entry_price * (1.01 if side == "LONG" else 0.99), 2),
                quantity=quantity,
                reduceOnly=True,
                newClientOrderId=f"{symbol}_{side}_trail"
            )

        kirim_notifikasi_order(symbol, side, leverage, quantity)
        return True

    except BinanceAPIException as e:
        print(f"[ERROR] execute_trade: {e}")
        return False
