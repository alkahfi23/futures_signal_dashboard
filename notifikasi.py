# notifikasi.py

import os
from twilio.rest import Client as TwilioClient

# Konfigurasi Twilio
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM")  # ex: 'whatsapp:+14155238886'
TWILIO_TO = os.getenv("TWILIO_WHATSAPP_TO")      # ex: 'whatsapp:+628XXXXXXXXX'

twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

def kirim_pesan_wa(pesan):
    try:
        message = twilio_client.messages.create(
            body=pesan,
            from_=TWILIO_FROM,
            to=TWILIO_TO
        )
        print(f"📤 WhatsApp terkirim: SID {message.sid}")
    except Exception as e:
        print(f"[ERROR] Gagal kirim WA: {e}")

def kirim_notifikasi_order(symbol, posisi, leverage, qty):
    pesan = (
        f"🚀 *Trade Eksekusi Berhasil!*\n"
        f"• Coin: {symbol}\n"
        f"• Posisi: {posisi}\n"
        f"• Leverage: {leverage}x\n"
        f"• Ukuran: {qty}\n"
        f"✅ Order telah dikirim ke Binance Futures."
    )
    kirim_pesan_wa(pesan)

def kirim_notifikasi_penutupan(symbol, profit_usdt, profit_pct):
    emoji = "📈" if profit_usdt > 0 else "📉"
    pesan = (
        f"{emoji} *Posisi Ditutup*\n"
        f"• Coin: {symbol}\n"
        f"• Hasil: {profit_usdt:.2f} USDT ({profit_pct:.2f}%)\n"
        f"🏁 Posisi telah ditutup otomatis."
    )
    kirim_pesan_wa(pesan)
