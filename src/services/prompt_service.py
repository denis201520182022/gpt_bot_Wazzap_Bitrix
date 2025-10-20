# src/services/prompt_service.py
import os
import time
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- Настройки ---
# ID документа можно вынести в .env для гибкости
DOCUMENT_ID = os.getenv("GOOGLE_DOC_ID", "1WAihQAluIf0KXpqM06KgZ7VsFQoKl2uq37X9f2VemDs") 
SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'
CACHE_TTL_SECONDS = 120 # Кэшируем на 2 минуты

# --- Переменные для кэша ---
_cached_prompt_library = None
_cache_timestamp = 0

def get_prompt_library():
    """
    Читает Google Doc, парсит его в библиотеку блоков {marker: text}
    и кэширует результат.
    """
    global _cached_prompt_library, _cache_timestamp

    # Проверяем, актуален ли кэш
    if _cached_prompt_library and (time.time() - _cache_timestamp < CACHE_TTL_SECONDS):
        return _cached_prompt_library

    print("Кэш библиотеки промптов устарел, обновляю из Google Docs...")
    try:
        # --- 1. АУТЕНТИФИКАЦИЯ И ЧТЕНИЕ ДОКУМЕНТА ---
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('docs', 'v1', credentials=creds)

        document = service.documents().get(documentId=DOCUMENT_ID).execute()
        content = document.get('body').get('content')
        
        # Собираем весь текст документа в одну строку
        full_text = ''
        for value in content:
            if 'paragraph' in value:
                elements = value.get('paragraph').get('elements')
                for elem in elements:
                    full_text += elem.get('textRun', {}).get('content', '')

        # --- 2. УПРОЩЕННЫЙ ПАРСИНГ ПО МАРКЕРАМ ---
        prompt_library = {}
        # Находим все маркеры вида #WORD#
        markers = re.findall(r"(#\w+#)", full_text)
        if not markers:
            print("⚠️ В документе не найдено ни одного маркера вида #WORD#")
            return {"error": "No markers found"}

        # Разделяем текст по этим маркерам, но сохраняем и сами маркеры в списке
        parts = re.split(r"(#\w+#)", full_text)

        # Собираем словарь: { "маркер1": "текст до маркера2", "маркер2": "текст до маркера3", ... }
        for i in range(len(parts)):
            # Если текущая часть - это маркер и за ней есть какой-то текст
            if parts[i] in markers and i + 1 < len(parts):
                marker = parts[i]
                text_block = parts[i+1].strip()
                if text_block: # Добавляем, только если текстовый блок не пустой
                    prompt_library[marker] = text_block
        
        print(f"✅ Библиотека промптов успешно загружена. Найдено блоков: {len(prompt_library)}")
        
        # --- 3. ОБНОВЛЕНИЕ КЭША ---
        _cached_prompt_library = prompt_library
        _cache_timestamp = time.time()
        
        return prompt_library

    except Exception as e:
        print(f"❌ ОШИБКА при чтении Google Doc: {e}")
        if _cached_prompt_library:
            print("⚠️ Возвращаю старую версию библиотеки из кэша.")
            return _cached_prompt_library
        
        # Аварийный фолбэк, если кэша нет
        return {"#ROLE_AND_STYLE#": "Ты - вежливый ассистент."}