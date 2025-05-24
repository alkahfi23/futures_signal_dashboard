# utils.py

from binance.client import Client
import os

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

def get_futures_balance(asset="USDT"):
    try:
        balance = client.futures_account_balance()
        for entry in balance:
            if entry['asset'] == asset:
                return float(entry['balance'])
    except Exception as e:
        print(f"[ERROR] Gagal ambil saldo futures: {e}")
    return 0.0

def set_leverage(symbol, leverage):
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        return True
    except Exception as e:
        print(f"[ERROR] Gagal set leverage: {e}")
        return False

def get_dynamic_leverage(balance_usdt):
    """
    Menentukan leverage dinamis agar aman dari margin call.
    """
    if balance_usdt >= 100:
        return 50
    elif balance_usdt >= 50:
        return 75
    elif balance_usdt >= 25:
        return 100
    else:
        return 125

def get_dynamic_risk_pct(balance_usdt):
    """
    Menentukan risk percent berdasarkan balance.
    """
    if balance_usdt >= 100:
        return 3
    elif balance_usdt >= 50:
        return 5
    else:
        return 7

def get_position_info(symbol):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for p in positions:
            if float(p["positionAmt"]) != 0:
                return {
                    "entryPrice": float(p["entryPrice"]),
                    "markPrice": float(p["markPrice"]),
                    "positionAmt": float(p["positionAmt"]),
                    "unRealizedProfit": float(p["unRealizedProfit"]),
                    "leverage": int(p["leverage"])
                }
    except Exception as e:
        print(f"[ERROR] Gagal ambil info posisi: {e}")
    return None

def calculate_profit_pct(entry_price, mark_price, position_side):
    try:
        if position_side == "LONG":
            return ((mark_price - entry_price) / entry_price) * 100
        else:
            return ((entry_price - mark_price) / entry_price) * 100
    except ZeroDivisionError:
        return 0.0
