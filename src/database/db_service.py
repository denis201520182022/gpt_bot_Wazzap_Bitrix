# src/database/db_service.py
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from .models import Dialog

def get_or_create_dialog(db: Session, chat_id: str) -> Dialog:
    """
    Находит диалог по chat_id. Если не находит - создает новый.
    Возвращает объект диалога.
    """
    dialog = db.query(Dialog).filter(Dialog.chat_id == chat_id).first()
    if not dialog:
        dialog = Dialog(chat_id=chat_id)
        db.add(dialog)
        db.commit()
        db.refresh(dialog)
        print(f"Создан новый диалог в БД для chat_id: {chat_id}")
    return dialog

def add_message_to_history(db: Session, chat_id: str, role: str, content: str):
    """
    Добавляет новое сообщение в историю диалога.
    """
    dialog = get_or_create_dialog(db, chat_id)
    
    # SQLAlchemy автоматически отслеживает изменения в JSONB поле
    dialog.history.append({"role": role, "content": content})
    
    # Помечаем объект как "измененный", чтобы SQLAlchemy точно сохранил изменения в JSON
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(dialog, "history")
    
    db.commit()
    print(f"Сообщение от '{role}' сохранено в историю для chat_id: {chat_id}")

def get_dialog_history(db: Session, chat_id: str) -> list:
    """
    Получает историю диалога для указанного chat_id.
    Возвращает список сообщений или пустой список, если диалога нет.
    """
    dialog = get_or_create_dialog(db, chat_id)
    return dialog.history

# --- НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ОЧЕРЕДЬЮ ---

def add_pending_message(db: Session, chat_id: str, content: str):
    """
    Добавляет входящее сообщение в очередь ожидания.
    """
    dialog = get_or_create_dialog(db, chat_id)
    
    dialog.pending_messages.append({"role": "user", "content": content})
    dialog.pending_since = func.now() # Устанавливаем время последнего сообщения
    
    flag_modified(dialog, "pending_messages")
    db.commit()
    print(f"Сообщение для {chat_id} добавлено в очередь.")
# src/database/db_service.py
# ... (все импорты и другие функции остаются без изменений)

def get_and_clear_pending_dialogs(db: Session, delay_seconds: int = 10) -> list[Dialog]:
    """
    Находит диалоги, ожидающие обработки, "забирает" их сообщения и очищает очередь.
    """
    # --- ГЛАВНОЕ ИСПРАВЛЕНИЕ: ПЕРЕНОСИМ ЛОГИКУ ВРЕМЕНИ В SQL ---
    # Мы больше не вычисляем время в Python. Мы говорим SQLAlchemy:
    # "Найди записи, где pending_since СТАРШЕ, чем (ТЕКУЩЕЕ_ВРЕМЯ_БД минус 10 секунд)"
    # SQLAlchemy сама превратит timedelta в правильный SQL-интервал.
    time_filter = Dialog.pending_since <= (func.now() - timedelta(seconds=delay_seconds))
    
    dialogs_to_process = db.query(Dialog).filter(
        func.jsonb_array_length(Dialog.pending_messages) > 0,
        time_filter  # <-- Используем нашу новую переменную-фильтр
    ).all()
    # -----------------------------------------------------------

    if not dialogs_to_process:
        return []

    results = []
    for dialog in dialogs_to_process:
        pending = list(dialog.pending_messages)
        dialog.pending_messages.clear()
        dialog.pending_since = None
        flag_modified(dialog, "pending_messages")
        results.append({'dialog': dialog, 'pending': pending})
    
    db.commit()
    return results