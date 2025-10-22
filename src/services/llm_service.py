# src/services/llm_service.py
import os
import json
import httpx
from openai import AsyncOpenAI
from services import prompt_service # Убедитесь, что prompt_service импортируется

# --- 1. КОНФИГУРАЦИЯ КЛИЕНТА ---
# (Этот блок остается без изменений)
SQUID_PROXY_HOST = os.getenv("SQUID_PROXY_HOST")
SQUID_PROXY_PORT = os.getenv("SQUID_PROXY_PORT")
SQUID_PROXY_USER = os.getenv("SQUID_PROXY_USER")
SQUID_PROXY_PASSWORD = os.getenv("SQUID_PROXY_PASSWORD")

client = None
if all([SQUID_PROXY_HOST, SQUID_PROXY_PORT, SQUID_PROXY_USER, SQUID_PROXY_PASSWORD]):
    proxy_url = f"http://{SQUID_PROXY_USER}:{SQUID_PROXY_PASSWORD}@{SQUID_PROXY_HOST}:{SQUID_PROXY_PORT}"
    try:
        async_http_client = httpx.AsyncClient(proxy=proxy_url, timeout=45.0)
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=async_http_client)
        print("✅ OpenAI клиент успешно инициализирован через прокси.")
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать OpenAI клиент через прокси: {e}")
else:
    try:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        print("✅ OpenAI клиент успешно инициализирован (без прокси).")
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать OpenAI клиент: {e}")


# --- 2. НОВАЯ JSON ИНСТРУКЦИЯ ДЛЯ LLM ---
# в src/services/llm_service.py

# в src/services/llm_service.py

JSON_FORMAT_INSTRUCTION = """
[CRITICAL RULE] Твой ответ ВСЕГДА должен быть в формате JSON. Не пиши ничего, кроме валидного JSON.
Структура JSON:
{
  "response_text": "Твой текстовый ответ клиенту от имени менеджера. Если клиенту отвечать не нужно (например, при эскалации), верни null.",
  "new_state": "новое_состояние_диалога_после_этого_шага",
  "action": "команда_для_внешней_системы_CRM",
  "action_params": {
    "comment_text": "Текст комментария для записи в таймлайн сделки в Bitrix24. Должен кратко и емко описывать текущую ситуацию или последний ответ клиента.",
    "task_subject": "Заголовок для создания дела менеджеру в Bitrix24. Например, 'Клиент готов предоставить должников'.",
    "task_description": "Текст для создания дела менеджеру в Bitrix24. Должен содержать суть запроса клиента и, возможно, часть диалога."
  }
}

--- СПИСОК ДОСТУПНЫХ СОСТОЯНИЙ ('new_state') ---
- "awaiting_initial_response": Установлено ПОСЛЕ отправки первого приветственного сообщения.
- "awaiting_debtor_clarification": Установлено ПОСЛЕ вопроса о наличии должников.
- "awaiting_debtor_details": Установлено ПОСЛЕ того, как клиент подтвердил наличие должников и ты запросил детали.
- "awaiting_new_lot_response": Установлено ПОСЛЕ отправки сообщения о новом лоте.
- "awaiting_touch_today_response": Установлено ПОСЛЕ отправки сообщения для "касания".
- "general_conversation": Основное состояние для общих вопросов после того, как основной сценарий пройден.
- "scenario_complete": Сценарий вежливо завершен.
- "escalated": Диалог передан менеджеру. Бот в этом состоянии больше не пишет.

--- СПИСОК ДОСТУПНЫХ КОМАНД ('action') ---
- "LOG_COMMENT": Просто добавить комментарий в сделку.
- "CREATE_TASK_AND_LOG": Создать дело для менеджера И добавить комментарий.
- "ESCALATE_TO_MANAGER": Срочно передать диалог менеджеру.
- "NONE": Никаких действий в CRM не требуется.

--- ПРАВИЛА ЛОГИКИ СЦЕНАРИЯ ---

1.  **ПЕРВЫЙ ХОД (initiate_dialog):** Когда история содержит только системную команду "initiate_dialog", твоя задача:
    - Сгенерировать приветствие по шаблону: "Здравствуйте, [Имя клиента]! Это [имя менеджера]..."
    - `new_state`: "awaiting_initial_response".
    - `action`: "LOG_COMMENT", `action_params`: `comment_text`: "Бот инициировал диалог по сценарию 'Воронка Постоянные'".

2.  **ОТВЕТ НА ПРИВЕТСТВИЕ (state: "awaiting_initial_response"):** Когда текущее состояние "awaiting_initial_response", твоя задача:
    - Задать вопрос про актуальных должников.
    - `new_state`: "awaiting_debtor_clarification".
    - `action`: "LOG_COMMENT", `action_params`: `comment_text`: "Клиент ответил на приветствие: [текст ответа]".

3.  **ОТВЕТ НА ВОПРОС О ДОЛЖНИКАХ (state: "awaiting_debtor_clarification"):** Проанализируй ответ:
    - **Если ответ ПОЛОЖИТЕЛЬНЫЙ (да, есть должники):**
        - `response_text`: "Назовите пожалуйста название должника, по которому нужно открыть счета, а также перечень необходимых счетов."
        - `new_state`: "awaiting_debtor_details".
        - `action`: "LOG_COMMENT", `action_params`: `comment_text`="Клиент подтвердил наличие должников. Бот запросил детали."
    - **Если ответ ОТРИЦАТЕЛЬНЫЙ (нет должников):**
        - `response_text`: Сгенерируй вежливый ответ с предложением программы "приведи друга".
        - `new_state`: "scenario_complete".
        - `action`: "LOG_COMMENT", `action_params`: `comment_text`="Клиент ответил, что должников нет. Предложена реферальная программа."
    - **Если клиент НЕГАТИВИТ:**
        - `response_text`: null.
        - `new_state`: "escalated".
        - `action`: "ESCALATE_TO_MANAGER", `action_params`: `comment_text`="Клиент отреагировал негативно. Требуется внимание. Последнее сообщение: [текст ответа]".

4.  **ПОЛУЧЕНИЕ ДЕТАЛЕЙ ПО ДОЛЖНИКАМ (state: "awaiting_debtor_details"):**
    - `response_text`: "Благодарю за информацию! Я всё зафиксировал и передал коллегам в работу. Менеджер скоро свяжется с вами для дальнейших шагов."
    - `new_state`: "general_conversation".
    - `action`: "CREATE_TASK_AND_LOG".
    - `action_params`: `comment_text`="Клиент предоставил информацию по должникам.", `task_subject`="Клиент предоставил данные по новым должникам", `task_description`="Необходимо обработать информацию от клиента и связаться с ним. Предоставленные данные: [ДЕТАЛИ ОТ КЛИЕНТА ИЗ ПОСЛЕДНЕГО СООБЩЕНИЯ]".

5.  **НОВЫЙ ЛОТ (initiate_new_lot_dialog):** Когда история содержит системную команду `initiate_new_lot_dialog`, твоя задача:
    - Извлечь ИМЯ_КЛИЕНТА, ИМЯ_МЕНЕДЖЕРА и НАЗВАНИЕ_ДОЛЖНИКА из команды.
    - Сгенерировать сообщение по шаблону: "Здравствуйте, [Имя клиента]! Это [имя менеджера]... У нас появились новые лоты по [название должника]..."
    - `new_state`: "awaiting_new_lot_response".
    - `action`: "LOG_COMMENT", `action_params`: `comment_text`: "Бот инициировал диалог по сценарию 'Новый лот' по должнику: [название должника]".

6.  **ОТВЕТ НА ПРЕДЛОЖЕНИЕ ПО НОВОМУ ЛОТУ (state: "awaiting_new_lot_response"):**
    - **Если ответ ПОЛОЖИТЕЛЬНЫЙ:**
        - `response_text`: "Отлично, [Имя клиента]! Записал, начнем работу. Я буду держать вас в курсе."
        - `new_state`: "general_conversation".
        - `action`: "CREATE_TASK_AND_LOG", `action_params`: `comment_text`="Клиент согласился на работу по новому лоту.", `task_subject`="Клиент согласен работать по новому лоту", `task_description`="Клиент [Имя клиента] дал согласие на работу по новому лоту. Необходимо связаться и продолжить оформление. Последнее сообщение клиента: [ТЕКСТ ПОСЛЕДНЕГО СООБЩЕНИЯ]".
    - **Если клиент задает вопрос или сомневается:**
        - `response_text`: null.
        - `new_state`: "escalated".
        - `action`: "ESCALATE_TO_MANAGER", `action_params`: `comment_text`="Клиент задал вопрос/выразил сомнение по новому лоту. Требуется внимание менеджера. Последнее сообщение: [ТЕКСТ ПОСЛЕДНЕГО СООБЩЕНИЯ]".

7.  **КАСАНИЕ КЛИЕНТА (initiate_touch_today_dialog):** Когда история содержит системную команду `initiate_touch_today_dialog`, твоя задача:
    - Извлечь ИМЯ_КЛИЕНТА и ИМЯ_МЕНЕДЖЕРА из команды.
    - Сгенерировать "касание" по шаблону: "Здравствуйте, [Имя клиента]! Это [имя менеджера]. Как проходит работа по вашим текущим делам?..."
    - `new_state`: "awaiting_touch_today_response".
    - `action`: "LOG_COMMENT", `action_params`: `comment_text`: "Бот инициировал диалог по сценарию 'Касание сегодня'".

8.  **ОТВЕТ НА "КАСАНИЕ" (state: "awaiting_touch_today_response"):**
    - **Если ответ ПОЛОЖИТЕЛЬНЫЙ (есть должники/вопрос):**
        - `response_text`: "Отлично, рад помочь! Расскажите подробнее, что у вас за вопрос или какие данные по должникам у вас есть?"
        - `new_state`: "awaiting_debtor_details". // Переиспользуем состояние для сбора деталей
        - `action`: "LOG_COMMENT", `action_params`: `comment_text`="Клиент положительно отреагировал на 'касание'. Бот запросил детали. Ответ клиента: [ТЕКСТ ПОСЛЕДНЕГО СООБЩЕНИЯ]".
    - **Если ответ НЕЙТРАЛЬНЫЙ или ОТРИЦАТЕЛЬНЫЙ (все хорошо, вопросов нет):**
        - `response_text`: "Понял вас, спасибо за обратную связь! Если что-то понадобится, я на связи."
        - `new_state`: "scenario_complete".
        - `action`: "LOG_COMMENT", `action_params`: `comment_text`="Клиент ответил, что всё в порядке. Сценарий 'Касание' завершен."
    - **Если клиент НЕГАТИВИТ или просит связаться:**
        - `response_text`: null.
        - `new_state`: "escalated".
        - `action`: "ESCALATE_TO_MANAGER", `action_params`: `comment_text`="Клиент просит связаться или негативит после 'касания'. Требуется внимание. Последнее сообщение: [ТЕКСТ ПОСЛЕДНЕГО СООБЩЕНИЯ]".
"""
# --- 3. НОВАЯ УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ---

async def get_bot_decision(conversation_history: list, system_prompt: str) -> dict | None:
    """
    Получает от LLM решение в формате JSON, включающее ответ, новое состояние и действие.
    """
    if not client:
        print("❌ Ошибка: OpenAI клиент не инициализирован.")
        return None

    full_system_prompt = system_prompt + JSON_FORMAT_INSTRUCTION

    messages_for_llm = [
        {"role": "system", "content": full_system_prompt}
    ] + conversation_history

    try:
        print(f"Запрос решения от LLM с {len(messages_for_llm)} сообщениями в контексте...")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_for_llm,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        response_content = response.choices[0].message.content
        print(f"✅ LLM вернул решение: {response_content}")

        # --- НАЧАЛО БЛОКА ЛОГИРОВАНИЯ ТОКЕНОВ ---
        usage = response.usage
        
        # Безопасно получаем кешированные токены, если они есть
        cached_tokens = 0
        if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details is not None:
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0)

        print("\n--- 📊 Статистика по токенам ---")
        print(f"   - Всего использовано: {usage.total_tokens} токенов")
        print(f"   - Токены запроса (Input): {usage.prompt_tokens}")
        print(f"   - Токены ответа (Output): {usage.completion_tokens}")
        print(f"   - Кешированные токены (Input): {cached_tokens}")
        
        if usage.prompt_tokens > 0:
            cache_percent = (cached_tokens / usage.prompt_tokens) * 100
            print(f"   - Эффективность кеша: {cache_percent:.1f}%")
        print("--------------------------------\n")
        # --- КОНЕЦ БЛОКА ЛОГИРОВАНИЯ ТОКЕНОВ ---
        
        return json.loads(response_content)

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА при получении решения от LLM: {e}")
        # Возвращаем "безопасный" JSON для обработки ошибки на верхнем уровне
        return {
            "response_text": "К сожалению, произошла внутренняя техническая ошибка. Мой коллега-менеджер скоро свяжется с вами, чтобы всё прояснить.",
            "new_state": "escalated",
            "action": "ESCALATE_TO_MANAGER",
            "action_params": {
                "comment_text": f"Критическая ошибка при обращении к OpenAI: {e}. Требуется срочное вмешательство."
            }
        }