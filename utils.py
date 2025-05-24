import os
from binance.client import Client
from binance.exceptions import BinanceAPIException

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

def get_futures_balance(asset='USDT'):
    try:
        balance_info = client.futures_account_balance()
        for b in balance_info:
            if b['asset'] == asset:
                return float(b['balance'])
    except BinanceAPIException as e:
        print(f"Error fetching balance: {e}")
    return 0.0

def set_leverage(symbol, leverage):
    try:
        leverage = int(leverage)
        if leverage < 1:
            leverage = 1
        if leverage > 125:  # Binance max leverage for most coins is 125
            leverage = 125
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage for {symbol} set to {leverage}")
        return True
    except BinanceAPIException as e:
        print(f"Failed to set leverage: {e}")
        return False

def get_dynamic_leverage(balance):
    # Simple logic, max 10x for low balance, max 3x for high balance
    if balance < 100:
        return 10
    elif balance < 500:
        return 5
    else:
        return 3

def get_dynamic_risk_pct(balance):
    # Risk % based on balance tiers
    if balance < 100:
        return 1
    elif balance < 500:
        return 0.7
    else:
        return 0.5

def get_position_info(symbol):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for p in positions:
            if float(p['positionAmt']) != 0:
                return {
                    'entryPrice': float(p['entryPrice']),
                    'positionAmt': float(p['positionAmt']),
                    'unRealizedProfit': float(p['unRealizedProfit']),
                    'markPrice': float(p['markPrice']),
                    'symbol': symbol
                }
    except BinanceAPIException as e:
        print(f"Error getting position info: {e}")
    return None

def calculate_profit_pct(entry_price, mark_price, position_side):
    try:
        if position_side == "LONG":
            return ((mark_price - entry_price) / entry_price) * 100
        elif position_side == "SHORT":
            return ((entry_price - mark_price) / entry_price) * 100
    except Exception as e:
        print(f"Error calculating profit %: {e}")
    return 0.0
