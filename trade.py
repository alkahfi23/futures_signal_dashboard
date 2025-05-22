# trade.py
import os
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = Client(API_KEY, API_SECRET)

def execute_trade(symbol, direction, quantity, sl_price=None, tp_price=None, leverage=10):
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        # Tentukan arah posisi
        side = SIDE_BUY if direction.upper() == "LONG" else SIDE_SELL
        close_side = SIDE_SELL if direction.upper() == "LONG" else SIDE_BUY

        # Eksekusi entry market
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=round(quantity, 3)  # presisi 3 desimal (umum untuk BTC/ETH)
        )

        # Set Stop Loss
        if sl_price:
            client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type=ORDER_TYPE_STOP_MARKET,
                stopPrice=round(sl_price, 2),
                closePosition=True,
                timeInForce=TIME_IN_FORCE_GTC,
                workingType='CONTRACT_PRICE'
            )

        # Set Take Profit
        if tp_price:
            client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type=ORDER_TYPE_TAKE_PROFIT_MARKET,
                stopPrice=round(tp_price, 2),
                closePosition=True,
                timeInForce=TIME_IN_FORCE_GTC,
                workingType='CONTRACT_PRICE'
            )

        print(f"✅ TRADE {symbol} {direction} sukses @ qty {quantity:.3f}")
        return order

    except Exception as e:
        print(f"[ERROR] Eksekusi trade gagal: {e}")
        return None

def calculate_quantity(balance_usdt, risk_pct, entry_price, sl_price, leverage):
    try:
        risk_amount = balance_usdt * (risk_pct / 100)
        stop_loss = abs(entry_price - sl_price)
        qty = (risk_amount / stop_loss) * leverage
        return round(qty, 3)
    except ZeroDivisionError:
        return 0
