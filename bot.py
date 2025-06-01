import json, os, asyncio
from datetime import datetime, time as dt_time
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters

# Вставьте ваш токен вручную
TOKEN ="BOT_TOKEN"

(ADD_CHANNEL, SELECT_CHANNEL, GET_TEXT, GET_MEDIA, GET_BUTTONS, GET_TIME, GET_FREQUENCY, CONFIRM) = range(8)
db_file = "db.json"

if not os.path.exists(db_file):
    with open(db_file, "w") as f:
        json.dump({"channels": [], "posts": []}, f)

def load_db():
    with open(db_file, "r") as f:
        return json.load(f)

def save_db(data):
    with open(db_file, "w") as f:
        json.dump(data, f, indent=2)

scheduler = BackgroundScheduler()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Команды:
/addchannel — добавить канал
/newpost — создать пост
/cancelpost — отменить все публикации")

async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Используй: /addchannel @channel или chat_id")
        return
    db = load_db()
    channel = context.args[0]
    if channel.startswith("@"):
        db["channels"].append(channel)
    else:
        try:
            db["channels"].append(int(channel))
        except:
            await update.message.reply_text("Неверный формат.")
            return
    save_db(db)
    await update.message.reply_text(f"Канал {channel} добавлен.")

async def newpost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not db["channels"]:
        await update.message.reply_text("Сначала добавь канал.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(str(c), callback_data=str(c))] for c in db["channels"]]
    await update.message.reply_text("Выбери канал:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_CHANNEL

async def select_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    channel = update.callback_query.data
    context.user_data["channel"] = channel
    await update.callback_query.edit_message_text(f"Канал выбран: {channel}
Теперь пришли текст поста:")
    return GET_TEXT

async def get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["text"] = update.message.text
    await update.message.reply_text("Пришли фото или видео, или напиши 'пропустить':")
    return GET_MEDIA

async def get_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.lower() == "пропустить":
        context.user_data["media"] = None
    elif update.message.photo:
        context.user_data["media"] = {"type": "photo", "file_id": update.message.photo[-1].file_id}
    elif update.message.video:
        context.user_data["media"] = {"type": "video", "file_id": update.message.video.file_id}
    else:
        await update.message.reply_text("Пришли фото/видео или 'пропустить':")
        return GET_MEDIA
    await update.message.reply_text("Хочешь кнопки? Напиши:
Текст - ссылка
Или 'нет'")
    return GET_BUTTONS

async def get_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text
    buttons = []
    if raw.lower() != "нет":
        for line in raw.splitlines():
            if " - " in line:
                text, url = line.split(" - ", 1)
                buttons.append(InlineKeyboardButton(text.strip(), url=url.strip()))
    context.user_data["buttons"] = buttons
    await update.message.reply_text("Во сколько публиковать? (формат ЧЧ:ММ, МСК)")
    return GET_TIME

async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        t = datetime.strptime(update.message.text, "%H:%M").time()
        context.user_data["time"] = t
        await update.message.reply_text("Как публиковать?
1 — разово
2 — ежедневно")
        return GET_FREQUENCY
    except:
        await update.message.reply_text("Неверный формат. Пример: 14:30")
        return GET_TIME

async def get_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    freq = update.message.text.strip()
    if freq not in ["1", "2"]:
        await update.message.reply_text("Введи 1 или 2")
        return GET_FREQUENCY
    context.user_data["freq"] = "once" if freq == "1" else "daily"
    preview = f"Канал: {context.user_data['channel']}
Текст: {context.user_data['text']}
Публикация: {context.user_data['freq']}
Время: {context.user_data['time']}"
    await update.message.reply_text("Предпросмотр:
" + preview + "

Отправить? (да/нет)")
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() != "да":
        await update.message.reply_text("Отменено.")
        return ConversationHandler.END

    db = load_db()
    post = {
        "channel": context.user_data["channel"],
        "text": context.user_data["text"],
        "media": context.user_data["media"],
        "buttons": [[btn.text, btn.url] for btn in context.user_data["buttons"]],
        "time": context.user_data["time"].strftime("%H:%M"),
        "freq": context.user_data["freq"]
    }
    db["posts"].append(post)
    save_db(db)

    schedule_post(post)
    await update.message.reply_text("Пост запланирован.")
    return ConversationHandler.END

def schedule_post(post):
    hour, minute = map(int, post["time"].split(":"))

    def send():
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(t, url=u)] for t, u in post["buttons"]]) if post["buttons"] else None
        try:
            if post["media"]:
                if post["media"]["type"] == "photo":
                    app.bot.send_photo(post["channel"], post["media"]["file_id"], caption=post["text"], reply_markup=markup)
                elif post["media"]["type"] == "video":
                    app.bot.send_video(post["channel"], post["media"]["file_id"], caption=post["text"], reply_markup=markup)
            else:
                app.bot.send_message(post["channel"], post["text"], reply_markup=markup)
        except Exception as e:
            print(f"Ошибка при отправке: {e}")

        if post["freq"] == "once":
            db = load_db()
            db["posts"] = [p for p in db["posts"] if p != post]
            save_db(db)

    if post["freq"] == "daily":
        scheduler.add_job(send, "cron", hour=hour, minute=minute)
    else:
        scheduler.add_job(send, "cron", hour=hour, minute=minute, id=f"once-{len(scheduler.get_jobs())}", max_instances=1)

async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    db["posts"] = []
    save_db(db)
    scheduler.remove_all_jobs()
    await update.message.reply_text("Все публикации отменены.")

def load_all_schedules():
    db = load_db()
    for post in db["posts"]:
        schedule_post(post)

async def main():
    global app
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("newpost", newpost)],
        states={
            SELECT_CHANNEL: [CallbackQueryHandler(select_channel)],
            GET_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_text)],
            GET_MEDIA: [MessageHandler(filters.ALL, get_media)],
            GET_BUTTONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_buttons)],
            GET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            GET_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_frequency)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", addchannel))
    app.add_handler(CommandHandler("cancelpost", cancel_all))
    app.add_handler(conv)

    load_all_schedules()
    scheduler.start()
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
