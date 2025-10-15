# get_stages.py (v3 - The Right Way)
import os
import requests
from dotenv import load_dotenv

def fetch_and_print_stages():
    """
    Подключается к Битрикс24 и выводит список стадий для указанной воронки,
    используя правильный метод API crm.dealcategory.stage.list.
    """
    print("Загружаем переменные окружения...")
    load_dotenv()

    BASE_URL = os.getenv("BITRIX_WEBHOOK_URL")
    if not BASE_URL:
        print("❌ Ошибка: не удалось найти BITRIX_WEBHOOK_URL в файле .env")
        return

    # ID нашей целевой воронки "Постоянные"
    FUNNEL_ID = '11'
    
    # --- ИЗМЕНЕНИЕ ---
    # Используем новый, правильный метод API
    method_url = f"{BASE_URL}crm.dealcategory.stage.list.json"
    
    # --- ИЗМЕНЕНИЕ ---
    # Параметры для этого метода гораздо проще: нужен только ID воронки
    params = {
        'id': FUNNEL_ID
    }

    print(f"Отправляем запрос для получения стадий воронки ID {FUNNEL_ID}...")
    
    try:
        response = requests.post(method_url, json=params)
        response.raise_for_status()
        data = response.json()

        if 'result' in data and data['result']:
            print(f"\n--- ✅ СПИСОК СТАДИЙ ДЛЯ ВОРОНКИ 'ПОСТОЯННЫЕ' (ID: {FUNNEL_ID}) ---")
            
            # Этот метод сразу возвращает только нужные стадии, фильтрация не нужна
            for stage in data['result']:
                print(f"Название: {stage.get('NAME', 'Без имени'):<30} | ID: {stage.get('STATUS_ID')}")

            print("--------------------------------------------------")
        else:
            print("⚠️ Не удалось получить стадии. Ответ от Битрикс24:", data)

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при запросе к API Битрикс24: {e}")


if __name__ == "__main__":
    fetch_and_print_stages()