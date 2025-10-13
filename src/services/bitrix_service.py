# src/services/bitrix_service.py
import requests
import os

# Получаем базовый URL вебхука из переменных окружения
BASE_URL = os.getenv("BITRIX_WEBHOOK_URL")

def get_deals(limit: int = 5):
    """
    Получает 'limit' последних сделок из Битрикс24.
    """
    if not BASE_URL:
        print("❌ Ошибка: URL вебхука для Битрикс24 не задан в .env")
        return None

    # Формируем полный URL для метода crm.deal.list
    method_url = f"{BASE_URL}crm.deal.list.json"
    
    # Параметры для запроса: сортируем по ID по убыванию, чтобы получить самые новые
    params = {
        'order': {"ID": "DESC"},
        'select': ["ID", "TITLE", "STAGE_ID"], # Запрашиваем только нужные поля
    }

    try:
        # Отправляем POST-запрос
        response = requests.post(method_url, json=params)
        response.raise_for_status()  # Вызовет ошибку, если HTTP-статус не 2xx

        data = response.json()
        
        if 'result' in data and data['result']:
             # API вернет страницу результатов, мы берем нужное количество
            return data['result'][:limit]
        else:
            print("⚠️ В ответе от Битрикс24 нет данных о сделках. Возможно, их просто нет?")
            print("Ответ API:", data)
            return []

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при запросе к API Битрикс24: {e}")
        return None
    

# src/services/bitrix_service.py
# ... (оставьте функцию get_deals как есть)

def get_deal_details(deal_id: int):
    """
    Получает детальную информацию о сделке по ее ID.
    """
    if not BASE_URL:
        print("❌ Ошибка: URL вебхука для Битрикс24 не задан в .env")
        return None

    method_url = f"{BASE_URL}crm.deal.get.json"
    params = {'id': deal_id}

    try:
        response = requests.post(method_url, json=params)
        response.raise_for_status()
        data = response.json()
        
        if 'result' in data:
            return data['result']
        else:
            print(f"Ошибка при получении деталей сделки {deal_id}:", data)
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе деталей сделки {deal_id}: {e}")
        return None
    

# src/services/bitrix_service.py
# ... (вставьте этот код после функции get_deal_details)

def get_contact_details(contact_id: int):
    """
    Получает детальную информацию о контакте по его ID.
    """
    if not BASE_URL: return None
    method_url = f"{BASE_URL}crm.contact.get.json"
    params = {'id': contact_id}
    try:
        response = requests.post(method_url, json=params)
        response.raise_for_status()
        data = response.json()
        return data.get('result')
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе контакта {contact_id}: {e}")
        return None
# src/services/bitrix_service.py

def get_user_details(user_id: int):
    """
    Получает информацию о пользователе (менеджере) по его ID.
    """
    if not BASE_URL: return None
    method_url = f"{BASE_URL}user.get.json"
    params = {'ID': user_id}
    try:
        response = requests.post(method_url, json=params)
        response.raise_for_status()
        data = response.json()

        # Метод user.get возвращает массив, даже если пользователь один
        if 'result' in data and len(data['result']) > 0:
            return data['result'][0]
        else:
            # Более информативное сообщение, если пользователь не найден
            print(f"ПРЕДУПРЕЖДЕНИЕ: Ответ от Битрикс24 не содержит данных для пользователя {user_id}.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе пользователя {user_id}: {e}")
        return None