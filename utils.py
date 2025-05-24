# utils.py
import os
from binance.client import Client

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

def get_balance():
    try:
        balance = client.futures_account_balance()
        usdt_balance = [b for b in balance if b['asset'] == 'USDT']
        return float(usdt_balance[0]['balance']) if usdt_balance else 0.0
    except Exception as e:
        print(f"[ERROR get_balance] {e}")
        return 0.0

def get_current_leverage(symbol):
    try:
        pos = client.futures_position_information(symbol=symbol)
        if pos:
            return int(pos[0]['leverage'])
        return 1
    except Exception as e:
        print(f"[ERROR get_current_leverage] {e}")
        return 1

def calculate_dynamic_risk(leverage):
    if leverage >= 100:
        return 2  # risiko sangat kecil
    elif leverage >= 50:
        return 5
    elif leverage >= 20:
        return 8
    else:
        return 10
