# manrisk.py

def calculate_position_size(account_balance, risk_per_trade_pct, entry_price, stop_loss_price, leverage=1):
    """
    Menghitung ukuran posisi maksimum berdasarkan modal dan jarak SL.
    """
    risk_amount = account_balance * (risk_per_trade_pct / 100)
    stop_distance = abs(entry_price - stop_loss_price)
    if stop_distance == 0:
        return 0

    position_size = risk_amount / stop_distance
    adjusted_position_size = position_size * leverage
    return adjusted_position_size

def calculate_risk_reward(entry_price, stop_loss, take_profit):
    """
    Menghitung rasio risk to reward.
    """
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)
    if risk == 0:
        return 0
    return reward / risk

def margin_call_warning(account_balance, position_size, entry_price, leverage, maintenance_margin_ratio=0.005):
    """
    Memberikan warning jika potensi margin call terlalu tinggi.
    """
    notional_value = position_size * entry_price / leverage
    maintenance_margin = notional_value * maintenance_margin_ratio
    required_margin = notional_value / leverage

    if account_balance < required_margin + maintenance_margin:
        return True, f"⚠️ Risiko Margin Call Tinggi! Balance kurang dari margin + MM ({account_balance:.2f} < {required_margin + maintenance_margin:.2f})"
    return False, "✅ Aman dari margin call."

def calculate_trailing_stop(entry_price, current_price, atr, direction="long", factor=1.5):
    """
    Menghitung level trailing stop berdasarkan arah dan ATR.
    """
    if direction.lower() == "long":
        trailing_stop = max(entry_price, current_price - atr * factor)
    else:
        trailing_stop = min(entry_price, current_price + atr * factor)
    return trailing_stop
