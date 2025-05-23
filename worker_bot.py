import os
import time
import requests
import pandas as pd
from trade import execute_trade, position_exists, close_opposite_position, adjust_quantity
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from binance.client import Client

# Binance config
client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))

# Constants
BASE_URL = "https://api.binance.com"
SYMBOLS = ["BTCUSDT"]
INTERVAL = "1m"
LIMIT = 100

account_balance = 17
risk_pct = 5
leverage = 200
MIN_QTY = 0.001

# Get Klines

def get_klines(symbol, interval, limit):
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    res = requests.get(url)
    data = res.json()
    df = pd.DataFrame(data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return df

# Indicators

def calculate_indicators(df):
    df['ema'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['rsi'] = RSIIndicator(df['close'], window=14).rsi()
    df['adx'] = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    macd = MACD(df['close'])
    df['macd'], df['macd_signal'] = macd.macd(), macd.macd_signal()
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'], df['bb_lower'] = bb.bollinger_hband(), bb.bollinger_lband()
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    df['volume_spike'] = df['volume'] > df['volume_ma20'] * 2
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['atr'] = atr.average_true_range()
    return df

# Signal logic

def enhanced_signal(df):
    latest, prev = df.iloc[-1], df.iloc[-2]
    score_long = sum([
        prev["macd"] < prev["macd_signal"] and latest["macd"] > latest["macd_signal"],
        latest["close"] > latest["ema"],
        latest["rsi"] > 48,
        latest["close"] > latest["bb_upper"],
        latest["volume_spike"],
        latest["adx"] > 15
    ])
    score_short = sum([
        prev["macd"] > prev["macd_signal"] and latest["macd"] < latest["macd_signal"],
        latest["close"] < latest["ema"],
        latest["rsi"] < 52,
        latest["close"] < latest["bb_lower"],
        latest["volume_spike"],
        latest["adx"] > 15
    ])
    if score_long >= 3: return "LONG"
    if score_short >= 3: return "SHORT"
    return ""

# Position Size Calculation

def calculate_position_size(balance, risk_pct, entry, sl, leverage):
    risk_amt = balance * (risk_pct / 100)
    sl_distance = abs(entry - sl)
    if sl_distance == 0: return 0
    raw_size = (risk_amt / sl_distance) * leverage
    return round(raw_size, 6)

# Margin Warning

def margin_warning(balance, pos_size, entry, leverage):
    margin_used = (pos_size * entry) / leverage
    if margin_used > balance:
        return True, "❌ Margin tidak cukup untuk membuka posisi ini."
    elif margin_used > balance * 0.9:
        return True, "⚠️ Margin call risk tinggi!"
    return False, ""

# Notional Check

def get_symbol_filters(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            filters = {}
            for f in s['filters']:
                filters[f['filterType']] = f
            return filters
    return {}

def is_notional_valid(symbol, qty, price):
    filters = get_symbol_filters(symbol)
    min_notional = float(filters.get("MIN_NOTIONAL", {}).get("notional", 5.0))
    notional = qty * price
    return notional >= min_notional

# Main Loop

def main_loop():
    while True:
        try:
            for symbol in SYMBOLS:
                df = get_klines(symbol, INTERVAL, LIMIT)
                if df.empty or df.shape[0] < 20:
                    print(f"⚠️ Data tidak cukup untuk {symbol}")
                    continue

                df = calculate_indicators(df)
                signal = enhanced_signal(df)
                latest = df.iloc[-1]
                entry = latest["close"]

                if signal and not position_exists(symbol, signal):
                    sl = entry - latest['atr'] * 1.5 if signal == "LONG" else entry + latest['atr'] * 1.5
                    tp = entry + latest['atr'] * 2.5 if signal == "LONG" else entry - latest['atr'] * 2.5
                    pos_size = calculate_position_size(account_balance, risk_pct, entry, sl, leverage)
                    pos_size = adjust_quantity(symbol, pos_size)

                    if pos_size < MIN_QTY:
                        print(f"⛔ Ukuran posisi terlalu kecil untuk {symbol} (adjusted: {pos_size})")
                        continue

                    if not is_notional_valid(symbol, pos_size, entry):
                        print(f"⛔ Notional terlalu kecil: {pos_size * entry:.2f} < min")
                        continue

                    is_margin_risk, note = margin_warning(account_balance, pos_size, entry, leverage)
                    if is_margin_risk:
                        print(note)
                        continue

                    close_opposite_position(symbol, signal)

                    result = execute_trade(
                        symbol=symbol,
                        side=signal,
                        quantity=pos_size,
                        entry_price=entry,
                        leverage=leverage,
                        position_side=signal,
                        sl_price=sl,
                        tp_price=tp,
                        trailing_stop_callback_rate=1.0
                    )
                    if result:
                        print(f"✅ Order berhasil: {signal} {symbol} Qty: {pos_size}")
                    else:
                        print(f"❌ Order gagal untuk {symbol}")

                else:
                    print(f"ℹ️ {symbol}: Tidak ada sinyal baru atau posisi sudah terbuka.")

            time.sleep(60)

        except Exception as e:
            print(f"[ERROR MAIN LOOP] {e}")
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
