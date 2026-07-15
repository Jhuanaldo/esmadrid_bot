import logging
import os
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import xml_utils
from config import (
    load_user_config,
    save_user_config,
    FILTERED_XML,
    TIME_RANGES,
    FREQUENCIES,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ["ESMADRID_BOT_TOKEN"]
MADRID_TZ = ZoneInfo("Europe/Madrid")

async def fetch_and_filter_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Fetching XML...")
    try:
        content = xml_utils.fetch_xml()
        xml_utils.filter_and_save(content, FILTERED_XML)
        logger.info("XML filtered and saved.")
    except Exception as e:
        logger.error(f"Error fetching/filtering XML: {e}")


def get_events_for_user(config: dict) -> list[dict]:
    all_events = xml_utils.load_filtered_data()
    selected = config.get("categorias", [])

    def match(event):
        for cat, subcat in event["categorias"]:
            if [cat, subcat] in selected:
                return True
        return False

    filtered = [e for e in all_events if match(e)]

    range_days = TIME_RANGES.get(config.get("rango", "1"))
    if range_days:
        days = range_days[1]
        today = date.today()
        end_date = today + timedelta(days=days)
        result = []
        for ev in filtered:
            ev_start = xml_utils.parse_date_es(ev["inicio"])
            if ev_start and today <= ev_start <= end_date:
                result.append(ev)
        return result
    return filtered


def format_config_summary(config: dict) -> str:
    cats = config.get("categorias", [])
    range_label = TIME_RANGES.get(config.get("rango", "1"), [""])[0]
    freq_label = FREQUENCIES.get(config.get("frecuencia", "1"), ["", ""])[0]
    lines = [
        "📋 **Tu configuración:**",
        f"  • Categorías: {len(cats)} seleccionadas",
        f"  • Rango: {range_label}",
        f"  • Frecuencia: {freq_label}",
    ]
    return "\n".join(lines)


def should_send_today(config: dict) -> bool:
    freq = FREQUENCIES.get(config.get("frecuencia", "1"))
    if freq is None:
        return False
    freq_key = freq[1]
    today = datetime.now(MADRID_TZ).weekday()
    if freq_key == "daily":
        return True
    if freq_key == "mwf":
        return today in (0, 2, 4)
    if freq_key == "mondays":
        return today == 0
    return False


MAX_LENGTH = 4000


async def send_long_message(chat_id: int, text: str, app: Application):
    if len(text) <= MAX_LENGTH:
        await app.bot.send_message(chat_id=chat_id, text=text)
        return
    for i in range(0, len(text), MAX_LENGTH):
        await app.bot.send_message(chat_id=chat_id, text=text[i:i + MAX_LENGTH])


async def send_report_to_user(app: Application, user_id: int):
    config = load_user_config(user_id)
    if not config:
        return
    events = get_events_for_user(config)
    if not events:
        text = "No hay planes para mostrar."
    else:
        text = xml_utils.format_events(events)
    try:
        await send_long_message(user_id, text, app)
    except Exception as e:
        logger.error(f"Error sending to {user_id}: {e}")


async def scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now(MADRID_TZ).strftime("%Y-%m-%d %A")
    logger.info(f"Running scheduled report for {today_str}")

    app = context.application
    users_dir = __import__("config").USERS_DIR
    for f in users_dir.iterdir():
        if f.suffix == ".json":
            user_id = int(f.stem)
            config = load_user_config(user_id)
            if config and should_send_today(config):
                await send_report_to_user(app, user_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data.clear()
    context.user_data["user_id"] = user_id
    await ask_categories(update, context)


async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = load_user_config(user_id)
    if not config:
        await update.message.reply_text(
            "No tienes configuración. Usa /start para configurar."
        )
        return
    events = get_events_for_user(config)
    if not events:
        text = "No hay planes que coincidan con tus filtros."
    else:
        text = xml_utils.format_events(events)
    await send_long_message(user_id, text, context.application)


async def ask_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = xml_utils.get_categories()
    keyboard = []
    for cat, subs in cats.items():
        display = f"📁 {cat} ({len(subs)} subcategorías)" if subs else f"📁 {cat}"
        keyboard.append([InlineKeyboardButton(display, callback_data=f"cat_{cat}")])
    keyboard.append([InlineKeyboardButton("✅ He terminado", callback_data="done_cats")])
    await update.message.reply_text(
        "Selecciona una categoría para ver sus subcategorías:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "done_cats":
        selected = context.user_data.get("selected_cats", [])
        if not selected:
            await query.edit_message_text(
                "Debes seleccionar al menos una categoría. Usa /start de nuevo."
            )
            return
        await query.edit_message_text(
            f"Categorías seleccionadas: {len(selected)}. Ahora elige el rango de tiempo."
        )
        await ask_time_range(query, context)
        return

    if data.startswith("cat_"):
        cat_name = data[4:]
        context.user_data["current_cat"] = cat_name
        cats = xml_utils.get_categories()
        subs = cats.get(cat_name, [])
        if not subs:
            toggle_cat_selection(context, cat_name, "")
            await query.edit_message_text(
                text=format_selection_summary(context),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Volver", callback_data="back_to_cats")]]
                ),
            )
            return

        keyboard = []
        for sub in subs:
            key = f"{cat_name}|{sub}"
            selected = context.user_data.get("selected_cats", [])
            checked = "✅" if [cat_name, sub] in selected else ""
            keyboard.append(
                [InlineKeyboardButton(f"{checked} {sub}", callback_data=f"sub_{key}")]
            )
        keyboard.append(
            [InlineKeyboardButton("⬅️ Volver", callback_data="back_to_cats")]
        )
        await query.edit_message_text(
            text=f"Categoría: {cat_name}\nSelecciona subcategorías:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("sub_"):
        key = data[4:]
        cat, sub = key.split("|", 1)
        toggle_cat_selection(context, cat, sub)
        cats = xml_utils.get_categories()
        subs_list = cats.get(cat, [])
        keyboard = []
        for s in subs_list:
            k = f"{cat}|{s}"
            selected = context.user_data.get("selected_cats", [])
            checked = "✅" if [cat, s] in selected else ""
            keyboard.append(
                [InlineKeyboardButton(f"{checked} {s}", callback_data=f"sub_{k}")]
            )
        keyboard.append(
            [InlineKeyboardButton("⬅️ Volver", callback_data="back_to_cats")]
        )
        await query.edit_message_text(
            text=f"Categoría: {cat}\nSelecciona subcategorías:\n\n{format_selection_summary(context)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "back_to_cats":
        cats = xml_utils.get_categories()
        keyboard = []
        for cat, subs in cats.items():
            display = f"📁 {cat} ({len(subs)})" if subs else f"📁 {cat}"
            keyboard.append(
                [InlineKeyboardButton(display, callback_data=f"cat_{cat}")]
            )
        keyboard.append(
            [InlineKeyboardButton("✅ He terminado", callback_data="done_cats")]
        )
        await query.edit_message_text(
            text=f"Selecciona una categoría:\n\n{format_selection_summary(context)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def toggle_cat_selection(context, cat: str, sub: str):
    selected = context.user_data.setdefault("selected_cats", [])
    pair = [cat, sub]
    if pair in selected:
        selected.remove(pair)
    else:
        selected.append(pair)


def format_selection_summary(context) -> str:
    selected = context.user_data.get("selected_cats", [])
    if not selected:
        return "Ninguna categoría seleccionada aún."
    return "Seleccionadas:\n" + "\n".join(
        f"  • {c} - {s}" if s else f"  • {c}" for c, s in selected
    )


async def ask_time_range(query_or_update, context):
    keyboard = [
        [InlineKeyboardButton(v[0], callback_data=f"range_{k}")]
        for k, v in TIME_RANGES.items()
    ]
    if hasattr(query_or_update, "edit_message_text"):
        await query_or_update.edit_message_text(
            "¿Qué rango de tiempo te interesa?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await query_or_update.message.reply_text(
            "¿Qué rango de tiempo te interesa?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def range_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("range_"):
        key = data[6:]
        context.user_data["rango"] = key
        await ask_frequency(query, context)


async def ask_frequency(query, context):
    keyboard = [
        [InlineKeyboardButton(v[0], callback_data=f"freq_{k}")]
        for k, v in FREQUENCIES.items()
    ]
    await query.edit_message_text(
        "¿Con qué frecuencia quieres recibir el informe?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def freq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("freq_"):
        key = data[5:]
        context.user_data["frecuencia"] = key

        user_id = context.user_data["user_id"]
        config = {
            "categorias": context.user_data.get("selected_cats", []),
            "rango": context.user_data.get("rango", "1"),
            "frecuencia": key,
        }
        save_user_config(user_id, config)

        summary = format_config_summary(config)
        await query.edit_message_text(
            f"✅ Configuración guardada correctamente.\n\n"
            f"{summary}\n\n"
            f"📬 Recibirás el informe a las **10:00** (hora española).\n"
            f"Usa /config para cambiar tu configuración o /report para consultar ahora."
        )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CallbackQueryHandler(category_callback, pattern="^(cat_|sub_|done_cats|back_to_cats)"))
    app.add_handler(CallbackQueryHandler(range_callback, pattern="^range_"))
    app.add_handler(CallbackQueryHandler(freq_callback, pattern="^freq_"))

    app.job_queue.run_daily(
        fetch_and_filter_job,
        time=time(8, 0, tzinfo=MADRID_TZ),
        days=tuple(range(7)),
    )

    app.job_queue.run_daily(
        scheduled_report,
        time=time(10, 0, tzinfo=MADRID_TZ),
        days=tuple(range(7)),
    )

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
