"""
Telegram-бот для изучения английских слов.
Переводит слова с английского на русский и помогает их повторять.

Зависимости:
    pip install python-telegram-bot deep-translator

Запуск:
    1. Создай бота через @BotFather в Telegram → получи TOKEN
    2. Вставь токен в TELEGRAM_TOKEN ниже
    3. python vocab_bot.py
"""

import json
import os
import random
from deep_translator import GoogleTranslator
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ──────────────────────────────────────────
#  🔑  ВСТАВЬ СЮДА СВОЙ ТОКЕН ОТ @BotFather
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TOKEN_HERE")
# ──────────────────────────────────────────

WORDS_FILE = "words.json"  # файл, где хранятся слова каждого пользователя


# ── Хранилище слов ─────────────────────────────────────────────────────────────

def load_words() -> dict:
    if os.path.exists(WORDS_FILE):
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_words(data: dict):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_words(user_id: int) -> list[dict]:
    data = load_words()
    return data.get(str(user_id), [])


def add_word(user_id: int, english: str, russian: str):
    data = load_words()
    uid = str(user_id)
    if uid not in data:
        data[uid] = []
    # не добавляем дубликаты
    if not any(w["en"].lower() == english.lower() for w in data[uid]):
        data[uid].append({"en": english, "ru": russian})
        save_words(data)
        return True
    return False  # уже есть


def delete_word(user_id: int, english: str):
    data = load_words()
    uid = str(user_id)
    if uid in data:
        data[uid] = [w for w in data[uid] if w["en"].lower() != english.lower()]
        save_words(data)


# ── Перевод ────────────────────────────────────────────────────────────────────

def translate_en_to_ru(word: str) -> str:
    try:
        result = GoogleTranslator(source="en", target="ru").translate(word.strip())
        return result
    except Exception as e:
        return f"[ошибка перевода: {e}]"


# ── Клавиатуры ─────────────────────────────────────────────────────────────────

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Мои слова", callback_data="list")],
        [InlineKeyboardButton("🎯 Повторять слова", callback_data="quiz_start")],
    ])


# ── Handlers ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я помогу учить английские слова.\n\n"
        "✏️ *Просто напиши любое английское слово* — я переведу его и сохраню.\n\n"
        "Используй кнопки ниже для просмотра и повторения слов.",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def handle_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # если в режиме викторины — обрабатываем как ответ
    if context.user_data.get("quiz_mode"):
        await handle_quiz_answer(update, context, text)
        return

    # проверяем, что это английское слово/фраза (только латиница + пробелы)
    if not all(c.isalpha() or c.isspace() or c in "'-" for c in text):
        await update.message.reply_text(
            "🔤 Пожалуйста, вводи английские слова (только латинские буквы)."
        )
        return

    translation = translate_en_to_ru(text)
    added = add_word(user_id, text, translation)

    words = get_user_words(user_id)
    count = len(words)

    if added:
        msg = (
            f"📖 *{text}* → *{translation}*\n\n"
            f"✅ Слово сохранено! Всего в словаре: {count} сл."
        )
    else:
        msg = (
            f"📖 *{text}* → *{translation}*\n\n"
            f"ℹ️ Это слово уже есть в твоём словаре."
        )

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())


async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Проверяем ответ в режиме викторины."""
    correct = context.user_data.get("quiz_answer", "")
    question_word = context.user_data.get("quiz_word", "")

    user_answer = text.strip().lower()
    correct_lower = correct.lower()

    if user_answer == correct_lower:
        result = f"✅ Правильно! *{question_word}* = *{correct}*"
    else:
        result = f"❌ Не совсем. *{question_word}* = *{correct}* (ты написал: {text})"

    context.user_data["quiz_score"] = context.user_data.get("quiz_score", 0) + (
        1 if user_answer == correct_lower else 0
    )
    context.user_data["quiz_answered"] = context.user_data.get("quiz_answered", 0) + 1

    await update.message.reply_text(result, parse_mode="Markdown")
    await send_next_quiz(update, context)


async def send_next_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляем следующий вопрос викторины."""
    queue: list = context.user_data.get("quiz_queue", [])

    if not queue:
        score = context.user_data.get("quiz_score", 0)
        total = context.user_data.get("quiz_answered", 0)
        context.user_data["quiz_mode"] = False
        await update.message.reply_text(
            f"🏁 Повторение завершено!\n\n"
            f"Результат: *{score}/{total}* правильных ответов 🎉",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
        return

    word = queue.pop(0)
    context.user_data["quiz_queue"] = queue
    context.user_data["quiz_word"] = word["en"]
    context.user_data["quiz_answer"] = word["ru"]

    await update.message.reply_text(
        f"❓ Переведи на русский:\n\n*{word['en']}*",
        parse_mode="Markdown",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    words = get_user_words(user_id)

    if query.data == "list":
        if not words:
            await query.message.reply_text(
                "📭 Твой словарь пуст. Напиши любое английское слово, чтобы добавить его!",
                reply_markup=main_keyboard(),
            )
            return

        lines = [f"{i+1}. *{w['en']}* — {w['ru']}" for i, w in enumerate(words)]
        # разбиваем на страницы по 20 слов
        page_size = 20
        pages = [lines[i:i+page_size] for i in range(0, len(lines), page_size)]
        page = context.user_data.get("list_page", 0)
        page = min(page, len(pages) - 1)

        text = f"📚 Твой словарь ({len(words)} слов):\n\n" + "\n".join(pages[page])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️", callback_data="list_prev"))
        if page < len(pages) - 1:
            nav_buttons.append(InlineKeyboardButton("▶️", callback_data="list_next"))

        keyboard = []
        if nav_buttons:
            keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])

        await query.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data in ("list_prev", "list_next"):
        page = context.user_data.get("list_page", 0)
        context.user_data["list_page"] = page - 1 if query.data == "list_prev" else page + 1
        # перезапускаем list
        query.data = "list"
        await button_handler(update, context)

    elif query.data == "quiz_start":
        if not words:
            await query.message.reply_text(
                "📭 Нечего повторять — сначала добавь слова!",
                reply_markup=main_keyboard(),
            )
            return

        shuffled = words.copy()
        random.shuffle(shuffled)

        context.user_data["quiz_mode"] = True
        context.user_data["quiz_queue"] = shuffled
        context.user_data["quiz_score"] = 0
        context.user_data["quiz_answered"] = 0

        await query.message.reply_text(
            f"🎯 Начинаем повторение! {len(shuffled)} слов.\n"
            "Я показываю английское слово — ты пишешь перевод на русский.\n\n"
            "Отправь /stop чтобы остановить.",
        )

        # отправляем первый вопрос через reply на сообщение с кнопкой
        word = shuffled.pop(0)
        context.user_data["quiz_queue"] = shuffled
        context.user_data["quiz_word"] = word["en"]
        context.user_data["quiz_answer"] = word["ru"]

        await query.message.reply_text(
            f"❓ Переведи на русский:\n\n*{word['en']}*",
            parse_mode="Markdown",
        )

    elif query.data == "back":
        await query.message.reply_text(
            "Главное меню:", reply_markup=main_keyboard()
        )


async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("quiz_mode"):
        score = context.user_data.get("quiz_score", 0)
        total = context.user_data.get("quiz_answered", 0)
        context.user_data["quiz_mode"] = False
        await update.message.reply_text(
            f"⏹ Повторение остановлено.\nРезультат: *{score}/{total}* ✅",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
    else:
        await update.message.reply_text("Нет активного повторения.", reply_markup=main_keyboard())


# ── Запуск ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_quiz))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word))

    print("🤖 Бот запущен. Нажми Ctrl+C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    main()
