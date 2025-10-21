# test_prompt.py
import os
import json
from dotenv import load_dotenv

def run_prompt_test():
    """
    Загружает все части промпта (системная роль, база знаний, история)
    и выводит в консоль финальный список сообщений, который уходит в LLM.
    """
    print("Запуск теста сборки полного промпта...")
    load_dotenv()

    # Импортируем наши сервисы ПОСЛЕ загрузки .env
    from src.services import prompt_service
    
    # --- 1. ИМИТАЦИЯ ДАННЫХ ---
    # Эти данные обычно приходят из реального диалога
    manager_name = "Алексей"
    
    # Имитируем историю переписки, как будто она пришла из БД
    fake_conversation_history = [
        {"role": "assistant", "content": f"Здравствуйте! Это {manager_name}, ваш менеджер. Чем могу помочь?"},
        {"role": "user", "content": "Расскажите про тарифы"},
        {"role": "assistant", "content": "Конечно! У нас есть несколько тарифов. Вас интересует что-то конкретное?"},
        {"role": "user", "content": "Да, сколько стоит ежемесячное обслуживание?"}
    ]

    # --- 2. СБОРКА ПРОМПТА (повторяем логику из llm_service.py) ---

    # 2.1. Получаем динамические промпты из Google Docs (включая таблицы)
    prompt_library = prompt_service.get_prompt_library()
    
    # 2.2. Получаем и персонализируем системный промпт
    system_prompt_template = prompt_library.get(
        "#ROLE_AND_STYLE#", 
        "Ты — {manager_name}, менеджер. Отвечай вежливо." # Аварийный промпт
    )
    system_prompt = system_prompt_template.format(manager_name=manager_name)

    # 2.3. Добавляем в системный промпт всю остальную базу знаний
    knowledge_base_text = ""
    for key, value in prompt_library.items():
        if key != "#ROLE_AND_STYLE#":
            knowledge_base_text += f"\n--- ИНФОРМАЦИЯ ПО ТЕМЕ '{key}' ---\n{value}\n"
    
    full_system_prompt = f"{system_prompt}\n\nНиже предоставлена дополнительная информация (база знаний), которую ты должен использовать для ответа на вопросы клиента. Не упоминай базу знаний напрямую, просто используй факты из нее.\n{knowledge_base_text}"

    # 2.4. Собираем финальный список сообщений
    final_messages_for_llm = [
        {"role": "system", "content": full_system_prompt}
    ] + fake_conversation_history

    # --- 3. ВЫВОД РЕЗУЛЬТАТА ---
    print("\n" + "="*80)
    print("             РЕЗУЛЬТИРУЮЩИЙ ПРОМПТ ДЛЯ ОТПРАВКИ В LLM")
    print("="*80)
    
    # Используем json.dumps для красивого вывода с отступами и поддержкой кириллицы
    print(json.dumps(final_messages_for_llm, indent=2, ensure_ascii=False))
    
    print("\n" + "="*80)
    print("             КОНЕЦ ПРОМПТА")
    print("="*80)


if __name__ == "__main__":
    run_prompt_test()