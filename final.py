import os
import time
import threading
from flask import Flask, request
import telebot
from telebot import types
from openai import OpenAI

# --- Configuration & Environment Variables ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_TOKEN = os.environ.get('HF_TOKEN')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Hugging Face OpenAI Client
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN
)

# --- Mock Database & State Management ---
# In a real app, use a database like PostgreSQL or Redis
APPROVED_USERS = set()  # Store user IDs of KYC-approved users
ESCROW_ORDERS = {}      # {order_id: {"user_id": 123, "status": "pending", "timer": object}}

# --- AI Helper Function ---
def get_ai_response(prompt):
    try:
        chat_completion = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-R1:novita",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"

# --- Utility: KYC Check ---
def is_approved(user_id):
    return user_id in APPROVED_USERS or user_id == 123456789 # Add your Admin ID here

# --- Keyboards ---
def main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Buy Crypto", callback_data="buy"),
        types.InlineKeyboardButton("📉 Sell Crypto", callback_data="sell"),
        types.InlineKeyboardButton("📊 Today's Price", callback_data="price"),
        types.InlineKeyboardButton("🔐 KYC Services", callback_data="kyc_tab"),
        types.InlineKeyboardButton("👤 Admin", callback_data="admin"),
        types.InlineKeyboardButton("❓ Help", callback_data="help")
    )
    return markup

# --- Bot Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    welcome_text = "Welcome to the Crypto P2P Bot! 🚀\nChoose an option below:"
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    if call.data == "buy":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Enter amount to buy (Simulated):")
        # Logic to initiate P2P order...
        start_escrow_order(call.message.chat.id, user_id, "BUY")

    elif call.data == "sell":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Enter amount to sell (Simulated):")
        start_escrow_order(call.message.chat.id, user_id, "SELL")

    elif call.data == "price":
        bot.answer_callback_query(call.id)
        price_info = "BTC: $65,432\nETH: $3,456\n(Prices synced via AI)"
        bot.send_message(call.message.chat.id, price_info)

    elif call.data == "kyc_tab":
        if is_approved(user_id):
            bot.edit_message_text("✅ Welcome to the KYC Approved Services Page.\nYou have access to exclusive P2P tools.", 
                                 call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "❌ Access Denied. Complete KYC first.", show_alert=True)

    elif call.data == "admin":
        bot.send_message(call.message.chat.id, "Admin Panel: /approve [user_id] to grant access.")

    elif call.data == "help":
        help_prompt = "Explain how a crypto P2P escrow works briefly."
        ai_help = get_ai_response(help_prompt)
        bot.send_message(call.message.chat.id, f"🤖 AI Support:\n\n{ai_help}")

# --- Escrow & P2P Logic ---

def start_escrow_order(chat_id, user_id, side):
    order_id = f"ORD-{int(time.time())}"
    bot.send_message(chat_id, f"📝 Order {order_id} Created ({side}).\nStatus: Waiting for Payment.\n⏳ Timer: 15 minutes to complete.")
    
    # Auto-release/Cancel Timer (Simulated)
    timer = threading.Timer(900, expire_order, [chat_id, order_id])
    ESCROW_ORDERS[order_id] = {"user_id": user_id, "status": "pending", "timer": timer}
    timer.start()

def expire_order(chat_id, order_id):
    if order_id in ESCROW_ORDERS and ESCROW_ORDERS[order_id]["status"] == "pending":
        bot.send_message(chat_id, f"⚠️ Order {order_id} Expired. Crypto returned to escrow.")
        del ESCROW_ORDERS[order_id]

@bot.message_handler(commands=['complete'])
def complete_order(message):
    # Simulated completion: In reality, you'd check Cwallet API Webhook here
    bot.reply_to(message, "✅ Payment Verified. Releasing Crypto from Escrow...")
    time.sleep(2)
    bot.send_message(message.chat.id, "🎉 Success! Crypto has been released to your Cwallet.")

# --- Admin Commands ---

@bot.message_handler(commands=['approve'])
def approve_user(message):
    try:
        target_id = int(message.text.split()[1])
        APPROVED_USERS.add(target_id)
        bot.reply_to(message, f"User {target_id} is now KYC Approved!")
    except:
        bot.reply_to(message, "Usage: /approve [user_id]")

# --- Flask Server for Render ---

@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    # Replace with your actual Render URL after deployment
    # bot.set_webhook(url='https://your-app-name.onrender.com/' + BOT_TOKEN)
    return "Bot is running", 200

if __name__ == "__main__":
    # For local testing, use bot.polling(). 
    # For Render production, the Flask app keeps the service alive.
    if os.environ.get('RENDER'):
        # In production on Render
        bot.remove_webhook()
        # You would set webhook here, but for simplicity, many users use polling 
        # with a background thread or a simple loop.
        threading.Thread(target=bot.infinity_polling).start()
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    else:
        # Local development
        bot.infinity_polling()
