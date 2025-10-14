from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import sqlite3, uuid

BOT_TOKEN = "8424318619:AAGG11m7Nr9Jfs2PpdnvLp9_o6AZT4grg6c"
ADMIN_ID = 8363798429  # (07715562538)

conn = sqlite3.connect("orders.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS orders
             (id TEXT, user_id INTEGER, product TEXT, price REAL,
              method TEXT, status TEXT, proof_file_id TEXT)""")
conn.commit()

# 🎁 المنتجات
PRODUCTS = [
    {
        "id": "master_small",
        "name": "بطاقات ماستر 10 (1000–2000$) - 300$",
        "desc": "",
        "price": 300
    },
    {
        "id": "master_big",
        "name": "بطاقات ماستر 10 (3000–5000$) - 450$",
        "desc": "",
        "price": 450
    },
    {
        "id": "visa_small",
        "name": "بطاقات فيزا 5 (1000–2000$) - 150$",
        "desc": "",
        "price": 150
    },
    {
        "id": "mix_cards",
        "name": "بطاقات مختلطة 10 (2000–3000$) - 400$",
        "desc": "",
        "price": 400
    },
]

PAYMENT_DETAILS = {
    "btc": "bc1q86293fs38sfhg0lph8pzdpejvz7kx93fsfg7wl:\n`bc1qexamplebtcaddress`",
    "zain": "  07766437765 ",
    "card": "4071811576",
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton(f"{p['name']} - ${p['price']}", callback_data=f"buy:{p['id']}")]
        for p in PRODUCTS
    ]
    await update.message.reply_text("ملاحظه ان الرصيد هو للبطاقة الواحدة:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("buy:"):
        prod_id = data.split(":")[1]
        prod = next(p for p in PRODUCTS if p["id"] == prod_id)
        kb = [
            [InlineKeyboardButton("💰 بيتكوين", callback_data=f"pay:btc:{prod_id}")],
            [InlineKeyboardButton("📱 زين كاش", callback_data=f"pay:zain:{prod_id}")],
            [InlineKeyboardButton("💳 ماستر كارد", callback_data=f"pay:card:{prod_id}")],
        ]
        await query.message.reply_text(f"اختر طريقة الدفع لشراء {prod['name']}:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("pay:"):
        _, method, prod_id = data.split(":")
        prod = next(p for p in PRODUCTS if p["id"] == prod_id)
        order_id = str(uuid.uuid4())[:8]

        c.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (order_id, query.from_user.id, prod["name"], prod["price"], method, "waiting_proof", None))
        conn.commit()

        pay_info = PAYMENT_DETAILS.get(method, "تفاصيل الدفع غير متوفرة")
        await query.message.reply_text(
            f"رقم الطلب: {order_id}\n"
            f"💵 السعر: ${prod['price']}\n\n{pay_info}\n\n"
            "بعد تحويل المبلغ، أرسل صورة إثبات الدفع هنا 📸"
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    photo = update.message.photo[-1].file_id
    c.execute("SELECT id, product FROM orders WHERE user_id=? AND status='waiting_proof'", (user_id,))
    row = c.fetchone()

    if not row:
        await update.message.reply_text("⚠️ لا يوجد طلب بانتظار إثبات.")
        return

    order_id, product = row
    c.execute("UPDATE orders SET proof_file_id=?, status='pending_review' WHERE id=?", (photo, order_id))
    conn.commit()

    await update.message.reply_text("✅ تم استلام إثبات الدفع. سيتم المراجعة قريباً.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ موافقة وتسليم", callback_data=f"admin:ok:{order_id}")],
        [InlineKeyboardButton("❌ رفض", callback_data=f"admin:no:{order_id}")]
    ])
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo,
        caption=f"طلب جديد قيد المراجعة:\nالمنتج: {product}\nالطلب: {order_id}\nمن المستخدم {user_id}",
        reply_markup=kb)

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action, order_id = query.data.split(":")
    c.execute("SELECT user_id, product FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()

    if not row:
        await query.message.reply_text("❌ الطلب غير موجود.")
        return

    user_id, product = row
    if action == "ok":
        code = "CODE-" + str(uuid.uuid4())[:6]
        await context.bot.send_message(chat_id=user_id,
            text=f"🎉 تمت الموافقة على الدفع.\nكود منتجك ({product}): `{code}`", parse_mode="Markdown")
        c.execute("UPDATE orders SET status='delivered' WHERE id=?", (order_id,))
        await query.message.reply_text(f"✅ تم تسليم الطلب {order_id}")
    else:
        await context.bot.send_message(chat_id=user_id,
            text=f"❌ تم رفض طلبك {order_id}. تواصل مع الدعم.")
        c.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
        await query.message.reply_text(f"تم رفض الطلب {order_id}")
    conn.commit()

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_callback, pattern="^(buy:|pay:)"))
app.add_handler(CallbackQueryHandler(admin_action, pattern="^admin:"))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

if __name__ == "__main__":
    print("✅ Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
