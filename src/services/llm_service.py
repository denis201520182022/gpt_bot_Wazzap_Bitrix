# src/services/llm_service.py
import os
import httpx
from openai import AsyncOpenAI
from services import prompt_service

# --- 1. ЗАГРУЗКА КОНФИГУРАЦИИ ---
# Загружаем настройки прокси из .env
SQUID_PROXY_HOST = os.getenv("SQUID_PROXY_HOST", "38.180.203.212")
SQUID_PROXY_PORT = os.getenv("SQUID_PROXY_PORT", "8787")
SQUID_PROXY_USER = os.getenv("SQUID_PROXY_USER", "zabota")
SQUID_PROXY_PASSWORD = os.getenv("SQUID_PROXY_PASSWORD", "zabota2000")

# Формируем URL прокси с аутентификацией
proxy_url = (
    f"http://{SQUID_PROXY_USER}:{SQUID_PROXY_PASSWORD}@"
    f"{SQUID_PROXY_HOST}:{SQUID_PROXY_PORT}"
)

# --- 2. ИНИЦИАЛИЗАЦИЯ КЛИЕНТА (ваш код) ---
# Этот блок кода выполняется один раз при запуске приложения.
# Клиент создается заранее и готов к использованию.
try:
    async_http_client = httpx.AsyncClient(
        proxy=proxy_url,
        timeout=30.0
    )

    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        http_client=async_http_client
    )
    print("✅ OpenAI клиент успешно инициализирован через прокси.")
except Exception as e:
    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать OpenAI клиент: {e}")
    client = None


# --- 3. УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ---
async def get_llm_response(prompt: str) -> str | None:
    """
    Отправляет промпт в OpenAI и возвращает текстовый ответ.
    Это асинхронная функция.
    """
    if not client:
        print("❌ Ошибка: OpenAI клиент не инициализирован.")
        return None

    try:
        print(f"Отправка промпта в OpenAI: '{prompt[:50]}...'")
        response = await client.chat.completions.create(
            model="gpt-4-mini", # Или любая другая модель, например, gpt-4
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        
        # Извлекаем и возвращаем текстовое содержимое ответа
        content = response.choices[0].message.content
        print("✅ Ответ от OpenAI получен.")
        return content.strip()

    except Exception as e:
        print(f"❌ Ошибка при обращении к OpenAI API: {e}")
        return None
    
async def generate_manager_response(client_message: str, manager_name: str) -> str | None:
    """
    Генерирует осмысленный ответ на сообщение клиента от лица менеджера,
    используя промпты из Google Docs.
    """
    if not client:
        return None

    # --- ИНТЕГРАЦИЯ: ПОЛУЧАЕМ ДИНАМИЧЕСКИЙ ПРОМПТ ---
    prompt_library = prompt_service.get_prompt_library()
    # Получаем "роль" из библиотеки. Если ее там нет, используем безопасное значение по умолчанию.
    system_prompt_template = prompt_library.get(
        "#ROLE_AND_STYLE#", 
        "Ты — {manager_name}, менеджер по сопровождению. Отвечай вежливо и по делу."
    )
    # Персонализируем промпт, подставляя реальное имя менеджера
    system_prompt = system_prompt_template.format(manager_name=manager_name)
    # --------------------------------------------------

    dialog_history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": client_message}
    ]

    try:
        print(f"Генерация ответа LLM на сообщение: '{client_message[:50]}...'")
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=dialog_history,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content.strip()
        print(f"✅ LLM сгенерировал ответ: '{ai_response[:50]}...'")
        return ai_response

    except Exception as e:
        print(f"❌ Ошибка при генерации ответа LLM: {e}")
        return "К сожалению, произошла техническая ошибка. Я уже уведомил коллег."