"""
Telegram-бот для изучения английских слов (aiogram 3.x).
pip install aiogram deep-translator
"""
 
import asyncio
import json
import os
import random
 
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from deep_translator import GoogleTranslator
 
TELEGRAM_TOKEN = os.environ.get(TELEGRAM_TOKEN, YOUR_TOKEN_HERE)
 
WORDS_FILE = "words.json"
 
 
# ── Хранилище ──────────────────────────────────────────────────────────────────
 
def load_words() -> dict:
    if os.path.exists(WORDS_FILE):
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
 
 
def save_words(data: dict):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
 
 
def get_user_words(user_id: int) -> list:
    return load_words().get(str(user_id), [])
 
 
def add_word(user_id: int, english: str, russian: str) -> bool:
    data = load_words()
    uid = str(user_id)
    if uid not in data:
        data[uid] = []
    if any(w["en"].lower() == english.lower() for w in data[uid]):
        return False
    data[uid].append({"en": english, "ru": russian})
    save_words(data)
    return True
 
 
# ── Перевод ────────────────────────────────────────────────────────────────────
 
def translate(word: str) -> str:
    try:
        return GoogleTranslator(source="en", target="ru").translate(word.strip())
    except Exception as e:
        return f"[ошибка: {e}]"
 
 
# ── Клавиатура ─────────────────────────────────────────────────────────────────
 
def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Мои слова", callback_data="list")],
        [InlineKeyboardButton(text="🎯 Повторять слова", callback_data="quiz_start")],
    ])
 
 
# ── Состояние викторины (в памяти) ─────────────────────────────────────────────
 
quiz_state: dict = {}  # user_id -> dict
 
 
# ── Handlers ───────────────────────────────────────────────────────────────────
 
dp = Dispatcher()
 
 
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я помогу учить английские слова.\n\n"
        "✏️ *Просто напиши любое английское слово* — переведу и сохраню.\n\n"
        "Используй кнопки ниже для просмотра и повторения.",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )
 
 
@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    uid = message.from_user.id
    if uid in quiz_state:
        s = quiz_state.pop(uid)
        await message.answer(
            f"⏹ Повторение остановлено.\nРезультат: *{s['score']}/{s['answered']}* ✅",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer("Нет активного повторения.", reply_markup=main_kb())
 
 
@dp.callback_query(F.data == "list")
async def cb_list(call: CallbackQuery):
    words = get_user_words(call.from_user.id)
    if not words:
        await call.message.answer("📭 Словарь пуст. Напиши английское слово, чтобы добавить!", reply_markup=main_kb())
        await call.answer()
        return
 
    lines = [f"{i+1}. *{w['en']}* — {w['ru']}" for i, w in enumerate(words)]
    # разбиваем по 20
    chunks = [lines[i:i+20] for i in range(0, len(lines), 20)]
    for chunk in chunks:
        await call.message.answer("\n".join(chunk), parse_mode="Markdown")
 
    await call.message.answer(f"📚 Всего слов: {len(words)}", reply_markup=main_kb())
    await call.answer()
 
 
@dp.callback_query(F.data == "quiz_start")
async def cb_quiz_start(call: CallbackQuery):
    uid = call.from_user.id
    words = get_user_words(uid)
    if not words:
        await call.message.answer("📭 Нечего повторять — сначала добавь слова!", reply_markup=main_kb())
        await call.answer()
        return
 
    shuffled = words.copy()
    random.shuffle(shuffled)
 
    quiz_state[uid] = {
        "queue": shuffled,
        "score": 0,
        "answered": 0,
    }
 
    await call.message.answer(
        f"🎯 Начинаем! {len(shuffled)} слов.\n"
        "Я показываю английское слово — пиши перевод на русском.\n"
        "/stop чтобы остановить."
    )
    await call.answer()
    await send_next_question(call.message, uid)
 
 
async def send_next_question(message: Message, uid: int):
    state = quiz_state.get(uid)
    if not state or not state["queue"]:
        s = quiz_state.pop(uid, {"score": 0, "answered": 0})
        await message.answer(
            f"🏁 Готово! Результат: *{s['score']}/{s['answered']}* 🎉",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
        return
 
    word = state["queue"].pop(0)
    state["current_word"] = word["en"]
    state["current_answer"] = word["ru"]
 
    await message.answer(f"❓ Переведи на русский:\n\n*{word['en']}*", parse_mode="Markdown")
 
 
@dp.message(F.text)
async def handle_text(message: Message):
    uid = message.from_user.id
    text = message.text.strip()
 
    # режим викторины
    if uid in quiz_state and "current_answer" in quiz_state[uid]:
        state = quiz_state[uid]
        correct = state.pop("current_answer")
        word = state.pop("current_word")
        state["answered"] += 1
 
        if text.strip().lower() == correct.lower():
            state["score"] += 1
            await message.answer(f"✅ Правильно! *{word}* = *{correct}*", parse_mode="Markdown")
        else:
            await message.answer(f"❌ *{word}* = *{correct}* (ты написал: {text})", parse_mode="Markdown")
 
        await send_next_question(message, uid)
        return
 
    # обычный режим — перевод слова
    if not all(c.isalpha() or c.isspace() or c in "'-" for c in text):
        await message.answer("🔤 Пожалуйста, вводи английские слова (только латинские буквы).")
        return
 
    translation = translate(text)
    added = add_word(uid, text, translation)
    words = get_user_words(uid)
 
    if added:
        msg = f"📖 *{text}* → *{translation}*\n\n✅ Сохранено! Всего в словаре: {len(words)} сл."
    else:
        msg = f"📖 *{text}* → *{translation}*\n\nℹ️ Это слово уже есть в словаре."
 
    await message.answer(msg, parse_mode="Markdown", reply_markup=main_kb())
 
 
# ── Запуск ─────────────────────────────────────────────────────────────────────
 
async def main():
    bot = Bot(token=TELEGRAM_TOKEN)
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())
