import aiohttp
import asyncio
import base64
from datetime import datetime

SYSTEM_PROMPT = """Ты — личный AI-ассистент пользователя в Telegram.

Твои задачи:
- Отвечать на вопросы чётко и по делу
- Помогать с планированием и задачами
- Анализировать документы и голосовые сообщения
- Извлекать задачи из пересланных сообщений
- Давать советы с учётом контекста пользователя

Правила:
- Отвечай на том же языке, на котором пишет пользователь
- Будь дружелюбным и конкретным
- Если есть контекст о пользователе — учитывай его
- Используй эмодзи умеренно
- Отвечай лаконично, без лишней воды

Специальные инструкции:
- Если тебя просят запомнить что-то о пользователе — ответь в формате:
  MEMORY_SAVE: ключ=значение
  (например: MEMORY_SAVE: работа=владелец лаунж-бара Liwan)
- Если в сообщении есть задача для извлечения — укажи её в формате:
  TASK_FOUND: текст задачи | приоритет (high/medium/low) | дедлайн или none
"""


class GeminiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"

    async def _call(self, messages: list, system_extra: str = "") -> str:
        system = SYSTEM_PROMPT + system_extra

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": 0.7,
            "max_tokens": 1500,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.base_url, json=payload, headers=headers) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(5 * (attempt + 1))
                            continue
                        if resp.status != 200:
                            error = await resp.text()
                            return f"❌ Ошибка AI: {resp.status}"
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt == 2:
                    return f"❌ Ошибка соединения: {str(e)}"
                await asyncio.sleep(3)
        return "❌ AI не отвечает, попробуй чуть позже."

    async def chat(self, history: list, context: str = "") -> str:
        messages = []
        for role, content in history:
            messages.append({"role": role, "content": content})
        system_extra = f"\n\nКонтекст о пользователе:{context}" if context else ""
        return await self._call(messages, system_extra)

    async def transcribe_voice(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        # Groq поддерживает Whisper через отдельный endpoint
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = aiohttp.FormData()
        data.add_field("file", audio_bytes, filename="voice.ogg", content_type="audio/ogg")
        data.add_field("model", "whisper-large-v3")
        data.add_field("language", "ru")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    data=data, headers=headers
                ) as resp:
                    if resp.status != 200:
                        return f"❌ Ошибка транскрипции: {resp.status}"
                    result = await resp.json()
                    return result.get("text", "Не удалось распознать речь")
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"

    async def analyze_document(self, file_bytes: bytes, mime_type: str, question: str = "") -> str:
        text_content = file_bytes.decode("utf-8", errors="ignore")[:8000]
        prompt = question if question else "Проанализируй этот документ: кратко опиши содержание, выдели ключевые моменты и возможные задачи."
        messages = [{"role": "user", "content": f"{prompt}\n\nСодержимое документа:\n{text_content}"}]
        return await self._call(messages)

    async def extract_tasks_from_message(self, forwarded_text: str) -> str:
        messages = [{
            "role": "user",
            "content": f"""Проанализируй это сообщение и извлеки из него задачи, дедлайны и важные действия.

Сообщение:
{forwarded_text}

Ответь в формате:
📋 Найденные задачи:
1. [задача] — приоритет: высокий/средний/низкий, дедлайн: [дата или нет]

Если задач нет — напиши "Задач не найдено."
"""
        }]
        return await self._call(messages)

    async def parse_reminder_time(self, text: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        messages = [{
            "role": "user",
            "content": f"""Текущее время: {now}

Из этого текста извлеки время напоминания и верни ТОЛЬКО дату и время в формате ISO: YYYY-MM-DDTHH:MM:00
Ничего больше — только строку с датой. Никаких пояснений.

Текст: {text}"""
        }]
        result = await self._call(messages)
        return result.strip()

    async def morning_briefing(self, tasks: list, notes: list, memory: dict) -> str:
        tasks_text = "\n".join([f"- {t[1]} (приоритет: {t[3]}, дедлайн: {t[4] or 'нет'})" for t in tasks if not t[2]]) or "нет активных задач"
        notes_text = "\n".join([f"- {n[1]}" for n in notes[:5]]) or "нет заметок"
        memory_text = "\n".join([f"- {k}: {v}" for k, v in memory.items()]) or "нет данных"

        messages = [{
            "role": "user",
            "content": f"""Составь краткий утренний брифинг для пользователя.

Активные задачи:
{tasks_text}

Последние заметки:
{notes_text}

Контекст о пользователе:
{memory_text}

Формат: приветствие, топ-3 приоритета на сегодня, мотивирующее завершение. Кратко и по делу."""
        }]
        return await self._call(messages)
