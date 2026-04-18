import os
import time
import threading
import requests
from flask import Flask, request
import telebot
from telebot import types
from openai import OpenAI

# --- Configuration ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_TOKEN = os.environ.get('HF_TOKEN')
# Your Platform's Cwallet ID where sellers send crypto for Escrow
PLATFORM_CWALLET_ID = "YOUR_PLATFORM_CWALLET_ID" 
CWALLET_API_KEY = os.environ.get('CWALLET_API_KEY') # For automated release

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
client = OpenAI(base_url="https://router.huggingface.co/v1", api_key=HF_TOKEN)

# --- Memory Storage (Use a Database for Production) ---
USER_STATE = {} # {user_id: 'awaiting_buy_amount'}
ACTIVE_TRADES = {} # {trade_id: {data}}
APPROVED_USERS = set()

# --- Cwallet Logic ---
def release_crypto_via_api(target_cwallet_id, amount_crypto):
    """
    Logic to call Cwallet/CCPayment API to transfer crypto.
    We deduct 2% before calling this.
    """
    fee = amount_crypto * 0.02
    final_amount = amount_crypto - fee
    
    # Placeholder for Cwallet API Request
    # payload = {
    #     "to_wallet_id": target_cwallet_id,
    #     "amount": final_amount,
    #     "asset": "USDT"
    # }
    # requests.post("https://api.cwallet.com/v1/transfer", json=payload, headers=headers)
    
    print(f"DEBUG: Released {final_amount} to {target_cwallet_id} after {fee} fee.")
    return True

# --- Keyboards ---
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Buy Crypto", callback_data="buy_init"),
        types.InlineKeyboardButton("📉 Sell Crypto", callback_data="sell_init"),
        types.InlineKeyboardButton("📊 Today's Price", callback_data="price"),
        types.InlineKeyboardButton("🔐 KYC Tab", callback_data="kyc_tab"),
        types.InlineKeyboardButton("👤 Admin", callback_data="admin"),
        types.InlineKeyboardButton("❓ Help", callback_data="help")
    )
    return markup

# --- Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "💎 **Crypto P2P Escrow Bot**\nSecure buying and selling with 2% service fee.", 
                     reply_markup=main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    uid = call.from_user.id
    
    if call.data == "sell_init":
        bot.send_message(call.message.chat.id, "How much crypto do you want to SELL? (Enter amount, e.g. 100)")
        USER_STATE[uid] = "awaiting_sell_amount"

    elif call.data == "buy_init":
        bot.send_message(call.message.chat.id, "How much crypto do you want to BUY? (Enter amount, e.g. 100)")
        USER_STATE[uid] = "awaiting_buy_amount"

    elif call.data == "kyc_tab":
        if uid in APPROVED_USERS:
            bot.send_message(call.message.chat.id, "✅ KYC Approved. Accessing Premium Services...")
        else:
            bot.answer_callback_query(call.id, "❌ KYC Required!", show_alert=True)

    elif "confirm_payment_" in call.data:
        trade_id = call.data.split("_")[2]
        trade = ACTIVE_TRADES.get(trade_id)
        bot.send_message(trade['seller_id'], f"🚨 Buyer claims payment sent for Trade {trade_id}.\nPlease check your bank/UPI. If received, click below to release crypto.",
                         reply_markup=release_markup(trade_id))
        bot.edit_message_text("✅ Notification sent to Seller. Waiting for release.", call.message.chat.id, call.message.message_id)

    elif "release_crypto_" in call.data:
        trade_id = call.data.split("_")[2]
        trade = ACTIVE_TRADES.get(trade_id)
        
        # Trigger actual Cwallet Transfer
        success = release_crypto_via_api(trade['buyer_cwallet'], trade['amount'])
        
        if success:
            bot.send_message(trade['buyer_id'], f"🎉 Crypto Released! {trade['amount'] * 0.98} sent to your Cwallet (2% fee deducted).")
            bot.send_message(trade['seller_id'], "✅ Trade Completed. Crypto released from escrow.")
            del ACTIVE_TRADES[trade_id]

# --- Text Input Handler (Amounts & IDs) ---

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid = message.from_user.id
    state = USER_STATE.get(uid)

    if state == "awaiting_sell_amount":
        amount = message.text
        trade_id = str(int(time.time()))
        ACTIVE_TRADES[trade_id] = {'seller_id': uid, 'amount': float(amount), 'status': 'escrow_pending'}
        
        msg = f"📝 **Sell Order {trade_id}**\n\nTo start escrow, send {amount} crypto to:\n" \
              f"📍 **Cwallet ID:** `{PLATFORM_CWALLET_ID}`\n\n" \
              "After sending, the crypto will be locked in our system."
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        USER_STATE[uid] = None

    elif state == "awaiting_buy_amount":
        amount = message.text
        USER_STATE[uid] = f"awaiting_buyer_cwallet_{amount}"
        bot.send_message(message.chat.id, "Please provide your **Cwallet ID** to receive crypto after payment:")

    elif state and "awaiting_buyer_cwallet_" in state:
        amount = float(state.split("_")[3])
        buyer_cwallet = message.text
        trade_id = str(int(time.time()))
        
        # In a real app, you'd match this with an existing Seller's order. 
        # Here we simulate finding a seller.
        seller_payment_details = "UPI: example@upi | Bank: 1234567890 (IMPS)"
        
        ACTIVE_TRADES[trade_id] = {
            'buyer_id': uid, 
            'buyer_cwallet': buyer_cwallet,
            'amount': amount,
            'seller_id': 12345678, # Hardcoded demo seller ID
            'status': 'payment_pending'
        }
        
        msg = f"🛒 **Buy Order {trade_id}**\n\nAmount: {amount} Crypto\n" \
              f"Please pay the seller here:\n💰 `{seller_payment_details}`\n\n" \
              "Click the button below ONLY after you have transferred the money."
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ I Have Paid", callback_data=f"confirm_payment_{trade_id}"))
        bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")
        USER_STATE[uid] = None

def release_markup(trade_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔓 Release Crypto", callback_data=f"release_crypto_{trade_id}"))
    return markup

# --- Admin & KYC Simulation ---
@bot.message_handler(commands=['approve'])
def approve(message):
    try:
        target = int(message.text.split()[1])
        APPROVED_USERS.add(target)
        bot.reply_to(message, f"User {target} KYC Approved.")
    except:
        bot.reply_to(message, "Usage: /approve [user_id]")

# --- Flask Server ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def webhook():
    return "Bot logic is active", 200

if __name__ == "__main__":
    if os.environ.get('RENDER'):
        threading.Thread(target=bot.infinity_polling).start()
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    else:
        bot.infinity_polling()
