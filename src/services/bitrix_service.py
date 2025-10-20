# src/services/bitrix_service.py
import requests
import os
from datetime import datetime, timedelta

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

# src/services/bitrix_service.py

# src/services/bitrix_service.py

def get_contact_details(contact_id: int):
    """
    Получает детальную информацию о контакте по его ID.
    Целенаправленно запрашивает имя и телефон.
    """
    if not BASE_URL: return None
    method_url = f"{BASE_URL}crm.contact.get.json"
    
    params = {
        'id': contact_id,
        'select': ["NAME", "PHONE"] # Явно запрашиваем только нужные поля
    }
    
    try:
        response = requests.post(method_url, json=params)
        response.raise_for_status()
        data = response.json()
        return data.get('result')
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе контакта {contact_id}: {e}")
        return None

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
    

def get_latest_activity_for_deal(deal_id: int):
    """
    Получает самое последнее дело (активность), связанное со сделкой.
    """
    if not BASE_URL: return None
    method_url = f"{BASE_URL}crm.activity.list.json"
    
    params = {
        'order': { "ID": "DESC" },  # Сортируем по ID по убыванию, чтобы самое новое было первым
        'filter': {
            "OWNER_TYPE_ID": 2,     # 2 - это системный ID для "Сделки"
            "OWNER_ID": deal_id     # Ищем дела, привязанные к нашей сделке
        },
        'select': ["ID", "DESCRIPTION"] # Нам нужно только описание
    }

    try:
        response = requests.post(method_url, json=params)
        response.raise_for_status()
        data = response.json()
        
        # API возвращает список, нам нужен только первый (самый новый) элемент
        if 'result' in data and data['result']:
            return data['result'][0]
        else:
            print(f"ПРЕДУПРЕЖДЕНИЕ: Для сделки {deal_id} не найдено связанных дел/активностей.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе дел для сделки {deal_id}: {e}")
        return None
    
# src/services/bitrix_service.py

def create_activity_for_deal(deal_id: int, responsible_id: int, subject: str, description: str):
    """
    Создает новое универсальное дело (crm.activity.todo.add), привязанное к сделке.
    Возвращает ID созданного дела или None в случае ошибки.
    """
    if not BASE_URL: return None
    method_url = f"{BASE_URL}crm.activity.todo.add.json"
    
    deadline_time = (datetime.now() + timedelta(hours=3)).strftime('%Y-%m-%dT23:59:59')
    
    # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: Убираем вложенность 'fields' ---
    # Все параметры теперь находятся на одном уровне
    params = {
        "ownerTypeId": 2,
        "ownerId": deal_id,
        "responsibleId": responsible_id,
        "deadline": deadline_time,
        "title": subject,
        "description": description,
    }

    try:
        response = requests.post(method_url, json=params)
        data = response.json()
        
        print(f"ОТЛАДКА: Отправлены параметры: {params}")
        print(f"ОТЛАДКА: Получен ответ от todo.add: {data}")

        # Ответ от этого метода немного отличается, ID лежит глубже
        if 'result' in data and data['result'].get('activity'):
            created_id = data['result']['activity']['ID']
            print(f"✅ Успешно создано универсальное дело с ID: {created_id} для сделки {deal_id}")
            return created_id
        else:
            # Пытаемся получить более детальную ошибку
            error_detail = data.get('error_description') or data.get('error')
            print(f"⚠️ Не удалось создать дело. Ошибка: {error_detail}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при создании дела для сделки {deal_id}: {e}")
        return None