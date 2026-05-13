import aiohttp
import json
import base64

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
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    async def _call(self, contents: list, system_extra: str = "") -> str:
        system = SYSTEM_PROMPT + system_extra

        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1500,
            }
        }

        url = f"{self.base_url}?key={self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        return f"❌ Ошибка Gemini: {resp.status}"
                    data = await resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            return f"❌ Ошибка соединения: {str(e)}"

    async def chat(self, history: list, context: str = "") -> str:
        contents = []
        for role, content in history:
            gemini_role = "user" if role == "user" else "model"
            contents.append({"role": gemini_role, "parts": [{"text": content}]})

        system_extra = f"\n\nКонтекст о пользователе:{context}" if context else ""
        return await self._call(contents, system_extra)

    async def transcribe_voice(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        contents = [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
                {"text": "Транскрибируй это голосовое сообщение точно, слово в слово. Верни только текст транскрипции без пояснений."}
            ]
        }]
        return await self._call(contents)

    async def analyze_document(self, file_bytes: bytes, mime_type: str, question: str = "") -> str:
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        prompt = question if question else "Проанализируй этот документ: кратко опиши содержание, выдели ключевые моменты и возможные задачи."
        contents = [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": file_b64}},
                {"text": prompt}
            ]
        }]
        return await self._call(contents)

    async def extract_tasks_from_message(self, forwarded_text: str) -> str:
        contents = [{
            "role": "user",
            "parts": [{"text": f"""Проанализируй это сообщение и извлеки из него задачи, дедлайны и важные действия.

Сообщение:
{forwarded_text}

Ответь в формате:
📋 Найденные задачи:
1. [задача] — приоритет: высокий/средний/низкий, дедлайн: [дата или нет]
...

Если задач нет — напиши "Задач не найдено."
"""}]
        }]
        return await self._call(contents)

    async def parse_reminder_time(self, text: str) -> str:
        """Парсим время напоминания из естественного языка, возвращаем ISO datetime"""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        contents = [{
            "role": "user",
            "parts": [{"text": f"""Текущее время: {now}

Из этого текста извлеки время напоминания и верни ТОЛЬКО дату и время в формате ISO: YYYY-MM-DDTHH:MM:00
Ничего больше — только строку с датой.

Текст: {text}

Примеры:
"через 2 часа" → {now[:11]}HH:MM:00 (текущее время + 2 часа)
"завтра в 9 утра" → следующий день, 09:00:00
"в пятницу в 18:00" → ближайшая пятница, 18:00:00
"""}]
        }]
        result = await self._call(contents)
        return result.strip()

    async def morning_briefing(self, tasks: list, notes: list, memory: dict) -> str:
        tasks_text = "\n".join([f"- {t[1]} (приоритет: {t[3]}, дедлайн: {t[4] or 'нет'})" for t in tasks if not t[2]]) or "нет активных задач"
        notes_text = "\n".join([f"- {n[1]}" for n in notes[:5]]) or "нет заметок"
        memory_text = "\n".join([f"- {k}: {v}" for k, v in memory.items()]) or "нет данных"

        contents = [{
            "role": "user",
            "parts": [{"text": f"""Составь краткий утренний брифинг для пользователя.

Активные задачи:
{tasks_text}

Последние заметки:
{notes_text}

Контекст о пользователе:
{memory_text}

Формат: приветствие, топ-3 приоритета на сегодня, мотивирующее завершение. Кратко и по делу.
"""}]
        }]
        return await self._call(contents)
