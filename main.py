import os
import logging
import asyncio
import aiohttp
import json
from datetime import datetime
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8222672482:AAFOqy7ySHmSY_9iA6jl0bkMhugPsSmOeHU"
ADMIN_CHAT_ID = 7617135270
API_ENDPOINT = "https://sacoliofficial.com/api/api/games/check_region"

# Conversation States
SELECT_PLAN, ENTER_GAME_ID, ENTER_SERVER_ID, CONFIRM_ORDER, UPLOAD_RECEIPT = range(5)
ADMIN_MAIN, ADMIN_UPDATE_PRICE, ADMIN_EDIT_PAYMENT, ADMIN_BROADCAST = range(5, 9)

# Simple Mock Database (In-memory for this example, Render will reset this on restart)
# In production, use a real database like SQLite or PostgreSQL
db = {
    "prices": {
        "Weekly Pass": 6400,
        "50 + 50": 3400,
        "150 + 150": 10000,
        "250 + 250": 16300,
        "500 + 500": 33000,
        "Dia 5": 450,
        "Dia 11": 850,
        "Dia 22": 1700,
        "Dia 33": 2900,
        "Dia 55": 3400,
        "Dia 110": 6800,
        "86": 5300,
        "112": 7800,
        "172": 10600,
        "257": 15700,
        "275": 16300,
        "343": 20800,
        "429": 26000,
        "514": 31000,
        "600": 36400,
        "706": 41600,
        "792": 46900,
        "878": 52300,
        "963": 57300,
        "1049": 62600,
        "1135": 68000,
        "1220": 72900,
        "1412": 83200,
        "1669": 98900,
        "1841": 108800,
        "2195": 125000,
    },
    "payment_details": {
        "KBZPay": {"name": "Thar Htoo Aung", "phone": "09894828386"},
        "WavePay": {"name": "Hla Min Aung", "phone": "09894828386"}
    },
    "users": set(),
    "pending_orders": {}
}

# Helper Functions
async def check_account(game_id, server_id):
    params = {"id": game_id, "zone": server_id}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(API_ENDPOINT, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                return None
        except Exception as e:
            logger.error(f"API Error: {e}")
            return None

# --- CUSTOMER HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db["users"].add(user_id)
    
    if user_id == ADMIN_CHAT_ID:
        return await admin_start(update, context)
    
    keyboard = []
    prices = db["prices"]
    for plan, price in prices.items():
        keyboard.append([InlineKeyboardButton(f"{plan} - {price} Ks", callback_data=f"plan_{plan}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to MLBB Diamond Shop! 🎮\nPlease select a diamond plan:",
        reply_markup=reply_markup
    )
    return SELECT_PLAN

async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan = query.data.replace("plan_", "")
    context.user_data["selected_plan"] = plan
    context.user_data["price"] = db["prices"][plan]
    
    await query.edit_message_text(f"Selected: {plan}\nPlease enter your MLBB Game ID:")
    return ENTER_GAME_ID

async def get_game_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_id = update.message.text
    if not game_id.isdigit():
        await update.message.reply_text("Invalid Game ID. Please enter numbers only.")
        return ENTER_GAME_ID
    
    context.user_data["game_id"] = game_id
    await update.message.reply_text("Please enter your Server ID:")
    return ENTER_SERVER_ID

async def get_server_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    server_id = update.message.text
    if not server_id.isdigit():
        await update.message.reply_text("Invalid Server ID. Please enter numbers only.")
        return ENTER_SERVER_ID
    
    context.user_data["server_id"] = server_id
    
    status_msg = await update.message.reply_text("Checking account... 🔄")
    
    account_data = await check_account(context.user_data["game_id"], server_id)
    
    if account_data and account_data.get("status") == 200:
        # Based on typical API response structure, adjust if needed
        data = account_data.get("data", {})
        username = data.get("username", "Unknown")
        country = data.get("country", "Unknown")
        
        context.user_data["username"] = username
        
        response_text = (
            "✅ Success!\n\n"
            "🎮 MLBB Account\n"
            f"👤 Name: {username}\n"
            f"🆔 ID: {context.user_data['game_id']}\n"
            f"🌐 Server: {server_id}\n"
            f"📍 Country: {country}\n\n"
            f"📦 Order: {context.user_data['selected_plan']}"
        )
        
        keyboard = [[InlineKeyboardButton("Proceed to Payment 💳", callback_data="proceed_payment")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text(response_text, reply_markup=reply_markup)
        return CONFIRM_ORDER
    else:
        keyboard = [[InlineKeyboardButton("Retry 🔄", callback_data="retry_check")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text("❌ Failed to verify account. Please check your IDs and try again.", reply_markup=reply_markup)
        return CONFIRM_ORDER # Handle retry in callback

async def payment_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "retry_check":
        await query.edit_message_text("Please enter your MLBB Game ID:")
        return ENTER_GAME_ID

    payment_text = (
        f"Order: {context.user_data['selected_plan']} - {context.user_data['price']} Ks\n\n"
        "Payment Details:\n\n"
    )
    
    for method, details in db["payment_details"].items():
        payment_text += f"{method}\nName - {details['name']}\nPh_No - {details['phone']}\n\n"
    
    payment_text += "Please send payment to the above number and upload your receipt."
    
    keyboard = [[InlineKeyboardButton("Upload Receipt 📤", callback_data="upload_receipt")]]
    await query.edit_message_text(payment_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return UPLOAD_RECEIPT

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This can be triggered by callback or direct message
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Please send the receipt image now.")
        return UPLOAD_RECEIPT

    if not update.message.photo:
        await update.message.reply_text("Please upload an image of your receipt.")
        return UPLOAD_RECEIPT
    
    photo_id = update.message.photo[-1].file_id
    order_id = f"ORD-{int(datetime.now().timestamp())}"
    
    order_data = {
        "user_id": update.effective_user.id,
        "username": context.user_data.get("username"),
        "game_id": context.user_data.get("game_id"),
        "server_id": context.user_data.get("server_id"),
        "plan": context.user_data.get("selected_plan"),
        "price": context.user_data.get("price"),
        "photo_id": photo_id,
        "status": "Pending"
    }
    
    db["pending_orders"][order_id] = order_data
    
    # Notify User
    await update.message.reply_text("✅ Your order has been submitted and is pending approval. We will notify you once it's processed.")
    
    # Notify Admin
    admin_text = (
        "📥 New Order Received!\n\n"
        f"Order ID: {order_id}\n"
        f"User: {context.user_data.get('username')}\n"
        f"Game ID: {context.user_data.get('game_id')}\n"
        f"Server ID: {context.user_data.get('server_id')}\n"
        f"Plan: {context.user_data.get('selected_plan')}\n"
        f"Price: {context.user_data.get('price')} Ks"
    )
    
    keyboard = [
        [InlineKeyboardButton("Approve ✅", callback_data=f"admin_approve_{order_id}")],
        [InlineKeyboardButton("Cancel ❌", callback_data=f"admin_cancel_{order_id}")]
    ]
    
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=photo_id,
        caption=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ConversationHandler.END

# --- ADMIN HANDLERS ---
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Check Orders 📥", "Update Diamond Prices 💎"],
        ["Payment Changes 💳", "Add Announcement 📢"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Welcome Admin. Please select an option:", reply_markup=reply_markup)
    return ADMIN_MAIN

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "Check Orders 📥":
        if not db["pending_orders"]:
            await update.message.reply_text("No pending orders.")
            return ADMIN_MAIN
        
        for order_id, order in list(db["pending_orders"].items()):
            admin_text = (
                f"Order ID: {order_id}\n"
                f"User: {order['username']}\n"
                f"Game ID: {order['game_id']}\n"
                f"Server ID: {order['server_id']}\n"
                f"Plan: {order['plan']}\n"
                f"Price: {order['price']} Ks"
            )
            keyboard = [
                [InlineKeyboardButton("Approve ✅", callback_data=f"admin_approve_{order_id}")],
                [InlineKeyboardButton("Cancel ❌", callback_data=f"admin_cancel_{order_id}")]
            ]
            await update.message.reply_photo(order["photo_id"], caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
            
    elif text == "Update Diamond Prices 💎":
        keyboard = []
        for plan, price in db["prices"].items():
            keyboard.append([InlineKeyboardButton(f"{plan} - {price} Ks", callback_data=f"edit_price_{plan}")])
        
        await update.message.reply_text("Select a plan to edit price:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif text == "Payment Changes 💳":
        keyboard = [
            [InlineKeyboardButton("Edit KBZPay", callback_data="edit_pay_KBZPay")],
            [InlineKeyboardButton("Edit WavePay", callback_data="edit_pay_WavePay")]
        ]
        await update.message.reply_text("Current Payment Details:\n" + str(db["payment_details"]), reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "Add Announcement 📢":
        await update.message.reply_text("Please send the announcement message to broadcast to all users:")
        return ADMIN_BROADCAST
        
    return ADMIN_MAIN

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    
    if data.startswith("admin_approve_"):
        order_id = data.replace("admin_approve_", "")
        order = db["pending_orders"].pop(order_id, None)
        if order:
            await context.bot.send_message(order["user_id"], "Your order has been approved. Thank you for your purchase. ✅")
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ APPROVED")
            
    elif data.startswith("admin_cancel_"):
        order_id = data.replace("admin_cancel_", "")
        order = db["pending_orders"].pop(order_id, None)
        if order:
            await context.bot.send_message(order["user_id"], "Your order has been cancelled. Please contact support if you have questions. ❌")
            await query.edit_message_caption(caption=query.message.caption + "\n\n❌ CANCELLED")

    elif data.startswith("edit_price_"):
        plan = data.replace("edit_price_", "")
        context.user_data["editing_plan"] = plan
        await query.message.reply_text(f"Enter new price for {plan}:")
        return ADMIN_UPDATE_PRICE

    elif data.startswith("edit_pay_"):
        method = data.replace("edit_pay_", "")
        context.user_data["editing_pay"] = method
        await query.message.reply_text(f"Enter new details for {method} (Format: Name - Phone):")
        return ADMIN_EDIT_PAYMENT

async def update_price_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_price = update.message.text
    if not new_price.isdigit():
        await update.message.reply_text("Please enter a valid number.")
        return ADMIN_UPDATE_PRICE
    
    plan = context.user_data["editing_plan"]
    db["prices"][plan] = int(new_price)
    await update.message.reply_text(f"Price updated for {plan} to {new_price} Ks.")
    return ADMIN_MAIN

async def update_payment_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    if " - " not in val:
        await update.message.reply_text("Invalid format. Use: Name - Phone")
        return ADMIN_EDIT_PAYMENT
    
    name, phone = val.split(" - ", 1)
    method = context.user_data["editing_pay"]
    db["payment_details"][method] = {"name": name, "phone": phone}
    await update.message.reply_text(f"Payment details updated for {method}.")
    return ADMIN_MAIN

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    count = 0
    for user_id in db["users"]:
        try:
            await context.bot.send_message(user_id, f"📢 ANNOUNCEMENT:\n\n{msg}")
            count += 1
        except:
            pass
    await update.message.reply_text(f"Broadcast sent to {count} users.")
    return ADMIN_MAIN

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def run_health_check():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def main():
    # Start health check server in a separate thread for Render
    threading.Thread(target=run_health_check, daemon=True).start()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Customer Conversation
    customer_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_PLAN: [CallbackQueryHandler(plan_selected, pattern="^plan_")],
            ENTER_GAME_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_game_id)],
            ENTER_SERVER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_server_id)],
            CONFIRM_ORDER: [
                CallbackQueryHandler(payment_step, pattern="^proceed_payment$"),
                CallbackQueryHandler(payment_step, pattern="^retry_check$")
            ],
            UPLOAD_RECEIPT: [
                MessageHandler(filters.PHOTO, handle_receipt),
                CallbackQueryHandler(handle_receipt, pattern="^upload_receipt$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Admin Conversation
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Chat(ADMIN_CHAT_ID) & filters.Regex("^(Check Orders|Update Diamond Prices|Payment Changes|Add Announcement)"), admin_menu_handler)],
        states={
            ADMIN_MAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            ADMIN_UPDATE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_price_value)],
            ADMIN_EDIT_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_payment_value)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(customer_conv)
    application.add_handler(admin_conv)
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    
    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
