from binance.client import Client
from binance.exceptions import BinanceAPIException
import os

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

# ====== Eksekusi Order dengan SL dan TP ======
def execute_trade_with_tp_sl(client, symbol, side, quantity, entry_price, stop_loss_price, take_profit_price, leverage=20):
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        order_side = "BUY" if side == "LONG" else "SELL"
        close_side = "SELL" if side == "LONG" else "BUY"

        # Adjust quantity
        quantity = adjust_quantity(symbol, quantity)

        # Market entry
        market_order = client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type="MARKET",
            quantity=quantity
        )

        # Pasang SL
        client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type="STOP_MARKET",
            stopPrice=round(stop_loss_price, 2),
            closePosition=True,
            timeInForce="GTC"
        )

        # Pasang TP
        client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=round(take_profit_price, 2),
            closePosition=True,
            timeInForce="GTC"
        )

        print(f"[✅ ORDER EXECUTED] {symbol} {side} qty={quantity} entry={entry_price} SL={stop_loss_price} TP={take_profit_price}")
        return market_order

    except BinanceAPIException as e:
        print(f"[❌ TRADE FAILED] {e.message}")
        return None
