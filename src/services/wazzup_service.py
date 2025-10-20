# src/services/wazzup_service.py
import os
import requests

# Загружаем URL, ключ и ID канала из .env
API_URL = os.getenv("WAZZUP_API_URL")
API_KEY = os.getenv("WAZZUP_API_KEY")
CHANNEL_ID = os.getenv("WAZZUP_CHANNEL_ID") # <-- Новая переменная

def send_message(phone_number: str, text: str) -> bool:
    """
    Универсальная функция для отправки текстового сообщения через Wazzup.
    """
    if not all([API_URL, API_KEY, CHANNEL_ID]):
        print("❌ Ошибка Wazzup: API_URL, API_KEY или CHANNEL_ID не заданы в .env")
        return False

    endpoint = "/message"
    url = f"{API_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # ОБНОВЛЕННОЕ тело запроса с обязательным полем channelId
    payload = {
        "channelId": CHANNEL_ID, # <-- ДОБАВЛЕНО
        "chatType": "whatsapp",
        "chatId": phone_number,
        "text": text
    }

    try:
        print(f"Отправка сообщения на номер {phone_number} через канал {CHANNEL_ID}...")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        print("✅ Сообщение успешно отправлено через Wazzup.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при отправке сообщения через Wazzup: {e}")
        if e.response:
            print(f"   Ответ сервера Wazzup: {e.response.text}")
        return False