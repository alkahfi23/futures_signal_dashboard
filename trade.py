import os
from binance.client import Client
from binance.exceptions import BinanceAPIException

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

# ====== Helper ======
def get_quantity_precision(symbol):
    try:
        info = client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        precision = 0
                        while round(step_size * (10 ** precision)) != step_size * (10 ** precision):
                            precision += 1
                        return precision
        return 3
    except:
        return 3

def adjust_quantity(symbol, quantity):
    precision = get_quantity_precision(symbol)
    return round(quantity, precision)

# ====== Check Posisi ======
def position_exists(client, symbol, side):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for p in positions:
            pos_amt = float(p['positionAmt'])
            if (side == "LONG" and pos_amt > 0) or (side == "SHORT" and pos_amt < 0):
                return True
        return False
    except Exception as e:
        print(f"[❌ POSITION CHECK ERROR] {e}")
        return False

# ====== Close Posisi Lawan ======
def close_opposite_position(symbol, current_signal):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for p in positions:
            pos_amt = float(p['positionAmt'])
            if pos_amt == 0:
                continue
            pos_side = "LONG" if pos_amt > 0 else "SHORT"
            if pos_side != current_signal:
                quantity = abs(pos_amt)
                order_side = "SELL" if pos_side == "LONG" else "BUY"
                client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type="MARKET",
                    quantity=adjust_quantity(symbol, quantity),
                    reduceOnly=True
                )
                print(f"[✅ CLOSED OPPOSITE] {symbol} {pos_side} {quantity}")
    except Exception as e:
        print(f"[❌ CLOSE OPPOSITE ERROR] {e}")

# ====== Eksekusi Order dengan SL dan TP ======
def execute_trade(symbol, side, quantity, entry_price, leverage, position_side="BOTH",
                  sl_price=None, tp_price=None, trailing_stop_callback_rate=None):
    try:
        # Auto close posisi lawan
        close_opposite_position(symbol, side)

        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        order_side = "BUY" if side == "LONG" else "SELL"
        opposite_side = "SELL" if side == "LONG" else "BUY"

        # Sesuaikan quantity
        quantity = adjust_quantity(symbol, quantity)

        # Open posisi dengan market order
        order_params = {
            'symbol': symbol,
            'side': order_side,
            'type': 'MARKET',
            'quantity': quantity
        }

        if position_side != "BOTH":
            order_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"

        order = client.futures_create_order(**order_params)

        # Pasang Stop Loss dan Take Profit
        if sl_price:
            sl_params = {
                'symbol': symbol,
                'side': opposite_side,
                'type': 'STOP_MARKET',
                'stopPrice': round(sl_price, 2),
                'closePosition': True,
                'timeInForce': 'GTC'
            }
            if position_side != "BOTH":
                sl_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"
            client.futures_create_order(**sl_params)

        if tp_price:
            tp_params = {
                'symbol': symbol,
                'side': opposite_side,
                'type': 'TAKE_PROFIT_MARKET',
                'stopPrice': round(tp_price, 2),
                'closePosition': True,
                'timeInForce': 'GTC'
            }
            if position_side != "BOTH":
                tp_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"
            client.futures_create_order(**tp_params)

        # Pasang Trailing Stop jika diatur
        if trailing_stop_callback_rate:
            ts_params = {
                'symbol': symbol,
                'side': opposite_side,
                'type': 'TRAILING_STOP_MARKET',
                'callbackRate': trailing_stop_callback_rate,
                'reduceOnly': True
            }
            if position_side != "BOTH":
                ts_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"
            client.futures_create_order(**ts_params)

        return order

    except BinanceAPIException as e:
        print(f"[❌ EXECUTION FAILED] {e}")
        return None
