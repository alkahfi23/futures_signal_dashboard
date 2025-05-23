import os
from binance.client import Client
from binance.enums import *

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

# Pastikan leverage di-set sebelum eksekusi order
def set_leverage(symbol, leverage):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except Exception as e:
        print(f"[SET LEVERAGE FAILED] {e}")

# Eksekusi order di Futures Binance dengan dukungan mode hedge
def execute_trade(symbol, side, quantity, entry_price, leverage=50, risk_pct=10):
    try:
        set_leverage(symbol, leverage)

        order_side = SIDE_BUY if side == "LONG" else SIDE_SELL
        position_side = "LONG" if side == "LONG" else "SHORT"

        # Tentukan precision quantity sesuai aturan Binance
        exchange_info = client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        step_size = 0.001
        if symbol_info:
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    break

        precision = abs(round(-1 * (len(str(step_size).split('.')[-1]) - str(step_size).split('.')[-1].find('1'))))
        quantity = round(quantity, precision)

        order = client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity,
            positionSide=position_side,
            newOrderRespType='RESULT'
        )
        print(f"[✅ EXECUTED] {symbol} {side} @ {entry_price} | Qty: {quantity}")
        return order

    except Exception as e:
        print(f"[❌ EXECUTION FAILED] {e}")
        return None
