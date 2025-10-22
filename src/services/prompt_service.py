
# src/services/prompt_service.py
import os
import time
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from pathlib import Path

# --- Настройки ---
MAIN_DOC_ID = os.getenv("GOOGLE_DOC_ID", "1b_EfaKe-iqZG4beYI9lVrCwj2tOMDvK5WqaevJopXVM") 
KNOWLEDGE_BASE_DOC_ID = os.getenv("KNOWLEDGE_BASE_DOC_ID", "1TE1PJWGfSFksvcuh1Nyova91BaeegRlUBmVVeBAZ8iw")
SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
SERVICE_ACCOUNT_FILE = Path(__file__).parent.parent.parent / 'credentials.json'
CACHE_TTL_SECONDS = 120

_cached_prompt_library = None
_cache_timestamp = 0

def _get_text_from_element(element):
    """Извлекает чистый текст из элемента Google Doc."""
    text = ''
    if 'textRun' in element and element.get('textRun').get('content'):
        text += element['textRun']['content']
    return text.strip()

def _parse_table_to_markdown(table: dict) -> str:
    """Конвертирует объект таблицы из Google Docs API в Markdown формат."""
    markdown_table = []
    rows = table.get('tableRows', [])
    if not rows:
        return ""

    # Обрабатываем первую строку (заголовок)
    header_row = rows[0]
    header_cells = [_get_text_from_cell(cell) for cell in header_row.get('tableCells', [])]
    markdown_table.append(f"| {' | '.join(header_cells)} |")

    # Создаем разделитель
    separator = ["---"] * len(header_cells)
    markdown_table.append(f"| {' | '.join(separator)} |")

    # Обрабатываем остальные строки
    for row in rows[1:]:
        body_cells = [_get_text_from_cell(cell) for cell in row.get('tableCells', [])]
        markdown_table.append(f"| {' | '.join(body_cells)} |")
    
    return "\n".join(markdown_table)

def _get_text_from_cell(cell: dict) -> str:
    """Извлекает весь текст из ячейки таблицы."""
    cell_text = ''
    for content_element in cell.get('content', []):
        if 'paragraph' in content_element:
            for element in content_element['paragraph'].get('elements', []):
                cell_text += _get_text_from_element(element)
    return cell_text.replace('\n', ' ') # Убираем переносы строк внутри ячейки

def _read_and_parse_doc(document_id: str) -> dict:
    """Читает и парсит ОДИН Google Doc, включая таблицы."""
    if not document_id: return {}
        
    print(f"Читаю Google Doc с ID: ...{document_id[-10:]}")
    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('docs', 'v1', credentials=creds)
        document = service.documents().get(documentId=document_id).execute()
        content = document.get('body').get('content')
        
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: СОБИРАЕМ ТЕКСТ И ТАБЛИЦЫ ---
        full_text = ''
        for value in content:
            if 'paragraph' in value:
                elements = value.get('paragraph').get('elements', [])
                for elem in elements:
                    full_text += _get_text_from_element(elem)
            elif 'table' in value:
                # Если нашли таблицу, конвертируем ее в Markdown и добавляем
                markdown_table_str = _parse_table_to_markdown(value['table'])
                full_text += f"\n{markdown_table_str}\n"
        # --------------------------------------------------------

        doc_library = {}
        markers = re.findall(r"(#\w+#)", full_text)
        parts = re.split(r"(#\w+#)", full_text)

        for i in range(len(parts)):
            if parts[i] in markers and i + 1 < len(parts):
                marker = parts[i]
                text_block = parts[i+1].strip()
                if text_block:
                    doc_library[marker] = text_block
        
        return doc_library
    except Exception as e:
        print(f"❌ ОШИБКА при чтении документа {document_id}: {e}")
        return {}


def get_prompt_library():
    """Читает Основной Промпт и Базу Знаний, объединяет их и кэширует."""
    # ... (Эта функция остается БЕЗ ИЗМЕНЕНИЙ!)
    global _cached_prompt_library, _cache_timestamp
    if _cached_prompt_library and (time.time() - _cache_timestamp < CACHE_TTL_SECONDS):
        return _cached_prompt_library
    print("Кэш библиотеки промптов устарел, обновляю из Google Docs...")
    
    merged_library = {}
    main_prompts = _read_and_parse_doc(MAIN_DOC_ID)
    merged_library.update(main_prompts)
    kb_prompts = _read_and_parse_doc(KNOWLEDGE_BASE_DOC_ID)
    merged_library.update(kb_prompts)

    if not merged_library:
        print("❌ Не удалось загрузить ни одного блока промптов.")
        if _cached_prompt_library:
            print("⚠️ Возвращаю старую версию библиотеки из кэша.")
            return _cached_prompt_library
        return {"#ROLE_AND_STYLE#": "Ты - вежливый ассистент."}

    print(f"✅ Библиотека промптов успешно загружена. Всего найдено блоков: {len(merged_library)}")
    _cached_prompt_library = merged_library
    _cache_timestamp = time.time()
    return merged_library