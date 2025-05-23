from binance.client import Client
import os
from binance.exceptions import BinanceAPIException

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

# Ambil presisi quantity (step size) untuk setiap symbol
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

# Fungsi eksekusi trade dan pasang SL + TP
def execute_trade(symbol, side, quantity, entry_price, leverage, position_side="BOTH", sl_price=None, tp_price=None):
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        order_side = "BUY" if side == "LONG" else "SELL"
        opposite_side = "SELL" if side == "LONG" else "BUY"

        # Sesuaikan quantity ke precision
        quantity = adjust_quantity(symbol, quantity)

        # Market order untuk open posisi
        order_params = {
            'symbol': symbol,
            'side': order_side,
            'type': 'MARKET',
            'quantity': quantity
        }

        if position_side != "BOTH":
            order_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"

        # Eksekusi market order
        order = client.futures_create_order(**order_params)

        # Pasang SL (stop market) dan TP (take profit market)
        if sl_price and tp_price:
            sl_params = {
                'symbol': symbol,
                'side': opposite_side,
                'type': 'STOP_MARKET',
                'stopPrice': round(sl_price, 2),
                'closePosition': True,
                'timeInForce': 'GTC'
            }

            tp_params = {
                'symbol': symbol,
                'side': opposite_side,
                'type': 'TAKE_PROFIT_MARKET',
                'stopPrice': round(tp_price, 2),
                'closePosition': True,
                'timeInForce': 'GTC'
            }

            if position_side != "BOTH":
                sl_params['positionSide'] = tp_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"

            client.futures_create_order(**sl_params)
            client.futures_create_order(**tp_params)

        return order

    except BinanceAPIException as e:
        print(f"[❌ EXECUTION FAILED] {e}")
        return None
