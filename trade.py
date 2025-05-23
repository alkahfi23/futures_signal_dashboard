from binance.client import Client
from binance.exceptions import BinanceAPIException
import os

# Inisialisasi Client Binance Futures
client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

def get_quantity_precision(symbol: str) -> int:
    """Dapatkan precision quantity untuk simbol tertentu."""
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
    except Exception:
        return 3

def adjust_quantity(symbol: str, quantity: float) -> float:
    """Sesuaikan quantity sesuai precision simbol."""
    precision = get_quantity_precision(symbol)
    return round(quantity, precision)

def position_exists(symbol: str, side: str) -> bool:
    """Cek apakah posisi LONG atau SHORT sudah terbuka di symbol tertentu."""
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

def close_opposite_position(symbol: str, side: str):
    """Tutup posisi lawan sebelum open posisi baru."""
    try:
        opposite_side = "SHORT" if side == "LONG" else "LONG"
        positions = client.futures_position_information(symbol=symbol)
        for p in positions:
            pos_amt = float(p['positionAmt'])
            if (opposite_side == "LONG" and pos_amt > 0) or (opposite_side == "SHORT" and pos_amt < 0):
                quantity = abs(pos_amt)
                quantity = adjust_quantity(symbol, quantity)
                order_side = "SELL" if opposite_side == "LONG" else "BUY"
                client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type='MARKET',
                    quantity=quantity,
                    reduceOnly=True
                )
                print(f"🔄 Closed opposite {opposite_side} position for {symbol}, qty: {quantity}")
    except BinanceAPIException as e:
        print(f"[❌ CLOSE OPPOSITE POSITION ERROR] {e}")

def execute_trade(symbol: str, side: str, quantity: float, entry_price: float, leverage: int,
                  position_side="BOTH", sl_price=None, tp_price=None, trailing_stop_callback_rate=None):
    """
    Eksekusi order market dengan SL, TP, dan trailing stop (opsional).
    position_side: "BOTH", "LONG", atau "SHORT"
    """
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        order_side = "BUY" if side == "LONG" else "SELL"
        opposite_side = "SELL" if side == "LONG" else "BUY"

        # Sesuaikan quantity sesuai precision
        quantity = adjust_quantity(symbol, quantity)

        # Open posisi market
        order_params = {
            'symbol': symbol,
            'side': order_side,
            'type': 'MARKET',
            'quantity': quantity
        }
        if position_side != "BOTH":
            order_params['positionSide'] = "LONG" if side == "LONG" else "SHORT"

        order = client.futures_create_order(**order_params)

        # Pasang SL jika ada
        if sl_price is not None:
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

        # Pasang TP jika ada
        if tp_price is not None:
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

        # Pasang Trailing Stop jika ada
        if trailing_stop_callback_rate is not None:
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
