# test_llm.py
import asyncio
from dotenv import load_dotenv

# Загружаем .env ПЕРЕД импортом наших сервисов
print("Запуск теста LLM сервиса...")
load_dotenv()

from src.services import llm_service

async def run_llm_test():
    """
    Асинхронная функция для вызова LLM и вывода результата.
    """
    # Промпт для теста. Вы можете написать здесь что угодно.
    test_prompt = "Напиши короткий, забавный стих о роботе-помощнике"
    
    response = await llm_service.get_llm_response(test_prompt)

    print("\n" + "="*50)
    if response:
        print("✅ Тест успешно пройден! Ответ от LLM:")
        print(response)
    else:
        print("❌ Тест провалился. Проверьте ошибки в консоли выше.")
    print("="*50)


# src/services/llm_service.py
# ... (весь существующий код до этого места остается без изменений)

async def generate_manager_response(client_message: str, manager_name: str) -> str | None:
    """
    Генерирует осмысленный ответ на сообщение клиента от лица менеджера.
    """
    if not client:
        return None

    # Промпт, который задает роль и контекст для LLM
    system_prompt = (
        "Ты — Алексей, менеджер по сопровождению арбитражных управляющих. "
        "Ты ведешь переписку с клиентом в WhatsApp. Твоя задача — вежливо, "
        "кратко и по делу отвечать на его вопросы. "
        "Если ты не знаешь ответ или вопрос сложный (просит скидки, юридическая консультация), "
        "вежливо скажи, что сейчас уточнишь у коллег и вернешься с ответом. "
        "Не придумывай детали, которых не знаешь. "
        "Твой стиль общения — профессиональный, но дружелюбный."
    )

    # Мы можем имитировать диалог, чтобы дать модели больше контекста
    # (пока для простоты будем использовать только последнее сообщение)
    dialog_history = [
        {"role": "system", "content": system_prompt},
        # Здесь в будущем можно будет добавить предыдущие сообщения
        {"role": "user", "content": client_message}
    ]

    try:
        print(f"Генерация ответа LLM на сообщение: '{client_message[:50]}...'")
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=dialog_history,
            temperature=0.7 # Средний уровень "креативности" для живого общения
        )
        
        ai_response = response.choices[0].message.content.strip()
        print(f"✅ LLM сгенерировал ответ: '{ai_response[:50]}...'")
        return ai_response

    except Exception as e:
        print(f"❌ Ошибка при генерации ответа LLM: {e}")
        return "К сожалению, в данный момент я не могу ответить. Пожалуйста, попробуйте позже."


if __name__ == "__main__":
    # Так как наша функция асинхронная, мы должны запускать ее через asyncio.run()
    asyncio.run(run_llm_test())