from binance.client import Client
import os
from binance.exceptions import BinanceAPIException

client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))
client.FUTURES_URL = 'https://fapi.binance.com/fapi'

# Fungsi untuk mengambil precision quantity (stepSize) dari exchange info
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

# Fungsi untuk menyesuaikan quantity ke precision yang benar
def adjust_quantity(symbol, quantity):
    precision = get_quantity_precision(symbol)
    return round(quantity, precision)

# Fungsi utama untuk eksekusi trade
def execute_trade(symbol, side, quantity, entry_price, leverage, risk_pct, position_side="BOTH"):
    try:
        # Cek saldo USDT terlebih dahulu
        balance = client.futures_account_balance()
        usdt_balance = float([b for b in balance if b['asset'] == 'USDT'][0]['balance'])

        # Set leverage dulu
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

        # Hitung nilai posisi maksimum berdasarkan risiko dan leverage
        max_position_value = usdt_balance * (risk_pct / 100) * leverage
        max_quantity = max_position_value / entry_price

        # Gunakan quantity minimum antara input dan yang dihitung
        quantity = min(quantity, max_quantity)

        # Atur posisi long/short berdasarkan hedge mode
        order_side = "BUY" if side == "LONG" else "SELL"

        # Sesuaikan quantity dengan precision
        quantity = adjust_quantity(symbol, quantity)

        params = {
            'symbol': symbol,
            'side': order_side,
            'type': 'MARKET',
            'quantity': quantity,
        }

        # Tambahkan positionSide jika pakai hedge mode
        if position_side != "BOTH":
            params['positionSide'] = "LONG" if side == "LONG" else "SHORT"

        # Eksekusi order
        order = client.futures_create_order(**params)
        return order

    except BinanceAPIException as e:
        print(f"[❌ EXECUTION FAILED] {e}")
        return None
