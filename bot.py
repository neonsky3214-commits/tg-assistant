import asyncio
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

from database import Database
from gemini import GeminiClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()
gemini = GeminiClient(GROQ_API_KEY)

PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


# ── START / HELP ───────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    db.save_user(user_id, name)
    await message.answer(
        f"Привет, {name}! 👋 Я твой личный AI-ассистент.\n\n"
        "📌 *Основные команды:*\n"
        "/note — заметки\n"
        "/task — задачи\n"
        "/remind — напоминания\n"
        "/memory — моя память о тебе\n"
        "/briefing — утренний брифинг\n"
        "/clear — сбросить диалог\n\n"
        "💡 *Также умею:*\n"
        "🎙 Расшифровывать голосовые сообщения\n"
        "📎 Анализировать документы и PDF\n"
        "📋 Извлекать задачи из пересланных сообщений\n\n"
        "Просто напиши что-нибудь — начнём!",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 *Команды ассистента:*\n\n"
        "📝 *Заметки:*\n"
        "`/note текст` — сохранить\n"
        "`/notes` — все заметки\n\n"
        "✅ *Задачи:*\n"
        "`/task текст` — добавить (средний приоритет)\n"
        "`/task! текст` — высокий приоритет 🔴\n"
        "`/task текст | пятница` — с дедлайном\n"
        "`/tasks` — список задач\n"
        "`/done N` — выполнить задачу\n\n"
        "⏰ *Напоминания:*\n"
        "`/remind через 2 часа позвонить` — любой текст\n"
        "`/reminders` — список\n\n"
        "🧠 *Память:*\n"
        "`/memory` — что я знаю о тебе\n"
        "`/remember ключ=значение` — запомнить факт\n\n"
        "📊 *Прочее:*\n"
        "`/briefing` — утренний брифинг\n"
        "`/clear` — сбросить историю\n\n"
        "🎙 Отправь голосовое — расшифрую\n"
        "📎 Отправь документ — проанализирую\n"
        "↩️ Перешли сообщение — найду задачи",
        parse_mode="Markdown"
    )


# ── NOTES ──────────────────────────────────────────────────────────────────────

@dp.message(Command("note"))
async def cmd_note(message: Message):
    text = message.text.replace("/note", "").strip()
    if not text:
        await message.answer("✏️ Напиши заметку:\n`/note текст заметки`", parse_mode="Markdown")
        return
    db.add_note(message.from_user.id, text)
    await message.answer(f"✅ Заметка сохранена:\n_{text}_", parse_mode="Markdown")


@dp.message(Command("notes"))
async def cmd_notes(message: Message):
    notes = db.get_notes(message.from_user.id)
    if not notes:
        await message.answer("📭 Заметок пока нет.\n`/note текст` — добавить", parse_mode="Markdown")
        return
    text = "📝 *Твои заметки:*\n\n"
    for note_id, content, created_at in notes:
        date = created_at[:10] if created_at else ""
        text += f"• `#{note_id}` {content} _{date}_\n"
    await message.answer(text, parse_mode="Markdown")


# ── TASKS ──────────────────────────────────────────────────────────────────────

@dp.message(Command("task"))
async def cmd_task(message: Message):
    raw = message.text.replace("/task", "").strip()
    if not raw:
        await message.answer(
            "✏️ Добавь задачу:\n"
            "`/task текст` — средний приоритет\n"
            "`/task! текст` — высокий 🔴\n"
            "`/task текст | пятница` — с дедлайном",
            parse_mode="Markdown"
        )
        return

    # Определяем приоритет
    priority = "medium"
    if raw.startswith("!"):
        priority = "high"
        raw = raw[1:].strip()

    # Дедлайн через |
    deadline = None
    if "|" in raw:
        parts = raw.split("|", 1)
        raw = parts[0].strip()
        deadline = parts[1].strip()

    db.add_task(message.from_user.id, raw, priority, deadline)
    emoji = PRIORITY_EMOJI[priority]
    deadline_text = f" 📅 _{deadline}_" if deadline else ""
    await message.answer(
        f"{emoji} Задача добавлена:\n_{raw}_{deadline_text}",
        parse_mode="Markdown"
    )


@dp.message(Command("tasks"))
async def cmd_tasks(message: Message):
    tasks = db.get_tasks(message.from_user.id)
    if not tasks:
        await message.answer("📭 Задач нет.\n`/task текст` — добавить", parse_mode="Markdown")
        return

    active = [t for t in tasks if not t[2]]
    done = [t for t in tasks if t[2]]

    text = "✅ *Твои задачи:*\n\n"
    if active:
        text += "*Активные:*\n"
        for task_id, content, _, priority, deadline, _ in active:
            emoji = PRIORITY_EMOJI.get(priority, "🟡")
            dl = f" 📅 {deadline}" if deadline else ""
            text += f"{emoji} `#{task_id}` {content}{dl}\n"
    if done:
        text += f"\n*Выполнено: {len(done)}*\n"

    text += "\n`/done N` — выполнить"
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("done"))
async def cmd_done(message: Message):
    text = message.text.replace("/done", "").strip()
    if not text or not text.isdigit():
        await message.answer("Укажи номер: `/done 1`", parse_mode="Markdown")
        return
    success = db.complete_task(message.from_user.id, int(text))
    if success:
        await message.answer(f"✅ Задача #{text} выполнена!")
    else:
        await message.answer(f"❌ Задача #{text} не найдена.")


# ── REMINDERS ──────────────────────────────────────────────────────────────────

@dp.message(Command("remind"))
async def cmd_remind(message: Message):
    text = message.text.replace("/remind", "").strip()
    if not text:
        await message.answer(
            "⏰ Примеры напоминаний:\n"
            "`/remind через 30 минут позвонить Ивану`\n"
            "`/remind завтра в 9 утра встреча`\n"
            "`/remind в пятницу в 18:00 сдать отчёт`",
            parse_mode="Markdown"
        )
        return

    await bot.send_chat_action(message.chat.id, "typing")
    remind_at = await gemini.parse_reminder_time(text)

    # Валидация формата
    try:
        datetime.fromisoformat(remind_at[:19])
    except Exception:
        await message.answer("❌ Не смог распознать время. Попробуй: `/remind через 2 часа текст`", parse_mode="Markdown")
        return

    db.add_reminder(message.from_user.id, text, remind_at[:19])
    dt = datetime.fromisoformat(remind_at[:19])
    human_time = dt.strftime("%d.%m.%Y в %H:%M")
    await message.answer(f"⏰ Напомню: *{text}*\n📅 {human_time}", parse_mode="Markdown")


@dp.message(Command("reminders"))
async def cmd_reminders(message: Message):
    reminders = db.get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer("📭 Нет активных напоминаний.\n`/remind текст` — добавить", parse_mode="Markdown")
        return
    text = "⏰ *Твои напоминания:*\n\n"
    for r_id, r_text, remind_at in reminders:
        dt = datetime.fromisoformat(remind_at)
        human = dt.strftime("%d.%m в %H:%M")
        text += f"• `#{r_id}` {r_text} — _{human}_\n"
    await message.answer(text, parse_mode="Markdown")


# ── MEMORY ─────────────────────────────────────────────────────────────────────

@dp.message(Command("memory"))
async def cmd_memory(message: Message):
    memory = db.get_memory(message.from_user.id)
    if not memory:
        await message.answer(
            "🧠 Пока ничего не знаю о тебе.\n\n"
            "Скажи мне что-нибудь, например:\n"
            "_«Запомни, я работаю в сфере HoReCa»_\n"
            "или используй `/remember работа=владелец ресторана`",
            parse_mode="Markdown"
        )
        return
    text = "🧠 *Что я знаю о тебе:*\n\n"
    for key, value in memory.items():
        text += f"• *{key}:* {value}\n"
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("remember"))
async def cmd_remember(message: Message):
    text = message.text.replace("/remember", "").strip()
    if "=" not in text:
        await message.answer("Формат: `/remember ключ=значение`\nНапример: `/remember город=Одесса`", parse_mode="Markdown")
        return
    key, value = text.split("=", 1)
    db.set_memory(message.from_user.id, key.strip(), value.strip())
    await message.answer(f"🧠 Запомнил: *{key.strip()}* = {value.strip()}", parse_mode="Markdown")


# ── BRIEFING ───────────────────────────────────────────────────────────────────

@dp.message(Command("briefing"))
async def cmd_briefing(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")
    user_id = message.from_user.id
    tasks = db.get_tasks(user_id)
    notes = db.get_notes(user_id)
    memory = db.get_memory(user_id)
    briefing = await gemini.morning_briefing(tasks, notes, memory)
    await message.answer(f"☀️ *Твой брифинг:*\n\n{briefing}", parse_mode="Markdown")


# ── CLEAR ──────────────────────────────────────────────────────────────────────

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    db.clear_history(message.from_user.id)
    await message.answer("🔄 История диалога очищена!")


# ── VOICE MESSAGES ─────────────────────────────────────────────────────────────

@dp.message(F.voice)
async def handle_voice(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")

    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    audio_data = file_bytes.read()

    transcript = await gemini.transcribe_voice(audio_data, "audio/ogg")

    if transcript.startswith("❌"):
        await message.answer(transcript)
        return

    await message.answer(f"🎙 *Транскрипция:*\n_{transcript}_", parse_mode="Markdown")

    # Добавляем транскрипцию в историю и отвечаем
    user_id = message.from_user.id
    db.add_message(user_id, "user", transcript)
    history = db.get_history(user_id)
    memory = db.get_memory(user_id)
    context = _build_context(user_id, memory)
    response = await gemini.chat(history, context)
    db.add_message(user_id, "assistant", response)
    await message.answer(response)


# ── DOCUMENTS ─────────────────────────────────────────────────────────────────

@dp.message(F.document)
async def handle_document(message: Message):
    await bot.send_chat_action(message.chat.id, "typing")

    doc = message.document
    mime = doc.mime_type or "application/octet-stream"

    # Поддерживаемые форматы
    supported = ["application/pdf", "text/plain", "text/csv",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]

    if not any(mime.startswith(m) for m in supported) and not mime.startswith("text/"):
        await message.answer("❌ Поддерживаемые форматы: PDF, TXT, CSV, DOCX")
        return

    file = await bot.get_file(doc.file_id)
    file_bytes = await bot.download_file(file.file_path)
    data = file_bytes.read()

    caption = message.caption or ""
    result = await gemini.analyze_document(data, mime, caption)
    await message.answer(f"📎 *Анализ документа:*\n\n{result}", parse_mode="Markdown")


# ── FORWARDED MESSAGES ─────────────────────────────────────────────────────────

@dp.message(F.forward_from | F.forward_from_chat | F.forward_date)
async def handle_forwarded(message: Message):
    if not message.text and not message.caption:
        await message.answer("❌ В пересланном сообщении нет текста.")
        return

    text = message.text or message.caption
    await bot.send_chat_action(message.chat.id, "typing")

    result = await gemini.extract_tasks_from_message(text)

    # Предлагаем добавить задачи
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Добавить задачи", callback_data=f"add_tasks:{message.message_id}"),
            InlineKeyboardButton(text="❌ Не нужно", callback_data="skip_tasks")
        ]
    ])

    # Сохраняем текст для возможного добавления
    db.add_note(message.from_user.id, f"[из чата] {text[:200]}")

    await message.answer(
        f"📋 *Анализ пересланного сообщения:*\n\n{result}\n\n_Текст сохранён в заметки_",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "skip_tasks")
async def skip_tasks(callback: CallbackQuery):
    await callback.answer("Окей, пропустили!")
    await callback.message.edit_reply_markup(reply_markup=None)


# ── TEXT MESSAGES ──────────────────────────────────────────────────────────────

@dp.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text

    db.add_message(user_id, "user", user_text)
    history = db.get_history(user_id)
    memory = db.get_memory(user_id)
    context = _build_context(user_id, memory)

    await bot.send_chat_action(message.chat.id, "typing")
    response = await gemini.chat(history, context)

    # Проверяем — хочет ли Gemini сохранить факт в память
    if "MEMORY_SAVE:" in response:
        lines = response.split("\n")
        clean_lines = []
        for line in lines:
            if line.startswith("MEMORY_SAVE:"):
                try:
                    kv = line.replace("MEMORY_SAVE:", "").strip()
                    key, value = kv.split("=", 1)
                    db.set_memory(user_id, key.strip(), value.strip())
                except Exception:
                    pass
            else:
                clean_lines.append(line)
        response = "\n".join(clean_lines).strip()

    db.add_message(user_id, "assistant", response)
    await message.answer(response)


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _build_context(user_id: int, memory: dict) -> str:
    context = ""
    if memory:
        context += "\nИзвестно о пользователе:\n"
        context += "\n".join([f"- {k}: {v}" for k, v in memory.items()])

    tasks = db.get_tasks(user_id)
    active = [t for t in tasks if not t[2]]
    if active:
        high = [t[1] for t in active if t[3] == "high"]
        if high:
            context += f"\nВысокоприоритетные задачи: {', '.join(high[:3])}"

    return context


# ── REMINDER SCHEDULER ─────────────────────────────────────────────────────────

async def reminder_scheduler():
    while True:
        try:
            pending = db.get_pending_reminders()
            for reminder_id, user_id, text in pending:
                await bot.send_message(user_id, f"⏰ *Напоминание:*\n{text}", parse_mode="Markdown")
                db.mark_reminder_sent(reminder_id)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(30)


# ── MORNING BRIEFING SCHEDULER ─────────────────────────────────────────────────

async def morning_briefing_scheduler():
    while True:
        try:
            now = datetime.now()
            # Отправляем в 9:00
            if now.hour == 9 and now.minute == 0:
                users = db.get_all_users()
                for user_id, name in users:
                    tasks = db.get_tasks(user_id)
                    notes = db.get_notes(user_id)
                    memory = db.get_memory(user_id)
                    if tasks or notes:
                        briefing = await gemini.morning_briefing(tasks, notes, memory)
                        await bot.send_message(
                            user_id,
                            f"☀️ *Доброе утро, {name}!*\n\n{briefing}",
                            parse_mode="Markdown"
                        )
        except Exception as e:
            logger.error(f"Briefing scheduler error: {e}")
        await asyncio.sleep(60)


# ── MAIN ───────────────────────────────────────────────────────────────────────

async def main():
    db.init()
    logger.info("Бот запущен!")
    asyncio.create_task(reminder_scheduler())
    asyncio.create_task(morning_briefing_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
