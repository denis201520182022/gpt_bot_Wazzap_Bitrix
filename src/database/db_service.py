# src/database/db_service.py
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from .models import Dialog

def get_or_create_dialog(db: Session, chat_id: str, deal_id: int = None, manager_id: int = None, funnel_id: str = None) -> Dialog:
    """
    Находит диалог по chat_id. Если не находит - создает новый.
    Если находит, может обновить информацию о сделке.
    """
    dialog = db.query(Dialog).filter(Dialog.chat_id == chat_id).first()
    if not dialog:
        dialog = Dialog(
            chat_id=chat_id,
            deal_id=deal_id,
            manager_id=manager_id,
            funnel_id=funnel_id
        )
        db.add(dialog)
        print(f"Создан новый диалог в БД для chat_id: {chat_id} (Сделка: {deal_id})")
    else:
        # Если диалог уже есть, обновляем ID сделки и менеджера, если они переданы
        if deal_id: dialog.deal_id = deal_id
        if manager_id: dialog.manager_id = manager_id
        if funnel_id: dialog.funnel_id = funnel_id
        print(f"Найден существующий диалог для chat_id: {chat_id}. Информация о сделке обновлена.")

    db.commit()
    db.refresh(dialog)
    return dialog

def update_dialog(db: Session, chat_id: str, new_state: str, new_history: list):
    """
    Комплексно обновляет диалог: устанавливает новое состояние и перезаписывает историю.
    """
    dialog = db.query(Dialog).filter(Dialog.chat_id == chat_id).first()
    if dialog:
        dialog.current_state = new_state
        dialog.history = new_history
        flag_modified(dialog, "history")
        db.commit()
        print(f"Диалог {chat_id} обновлен. Новое состояние: '{new_state}'.")
    else:
        print(f"⚠️ Попытка обновить несуществующий диалог: {chat_id}")


def add_message_to_history(db: Session, chat_id: str, role: str, content: str):
    """
    Добавляет одно сообщение в историю диалога.
    ВАЖНО: Эта функция теперь менее предпочтительна, чем update_dialog.
    """
    dialog = get_or_create_dialog(db, chat_id)
    dialog.history.append({"role": role, "content": content})
    flag_modified(dialog, "history")
    db.commit()
    print(f"Сообщение от '{role}' сохранено в историю для chat_id: {chat_id}")

def get_dialog_history(db: Session, chat_id: str) -> list:
    """
    Получает историю диалога для указанного chat_id.
    """
    dialog = get_or_create_dialog(db, chat_id)
    return dialog.history

# --- Функции для работы с очередью остаются без изменений ---
def add_pending_message(db: Session, chat_id: str, content: str, file_url: str = None, file_name: str = None):
    """
    Добавляет входящее сообщение в очередь ожидания.
    Теперь также принимает информацию о файле.
    """
    dialog = get_or_create_dialog(db, chat_id)
    
    # Создаем более богатый объект сообщения
    message_data = {"role": "user", "content": content}
    if file_url:
        message_data["file_url"] = file_url
    if file_name:
        message_data["file_name"] = file_name

    dialog.pending_messages.append(message_data)
    dialog.pending_since = func.now() 
    
    flag_modified(dialog, "pending_messages")
    db.commit()
    print(f"Сообщение для {chat_id} добавлено в очередь.")
    

def get_and_clear_pending_dialogs(db: Session, delay_seconds: int = 10) -> list[dict]:
    """
    Находит диалоги, ожидающие обработки, "забирает" их сообщения и очищает очередь.
    Возвращает список словарей, содержащих объект диалога и его сообщения.
    """
    time_filter = Dialog.pending_since <= (func.now() - timedelta(seconds=delay_seconds))
    
    dialogs_to_process = db.query(Dialog).filter(
        func.jsonb_array_length(Dialog.pending_messages) > 0,
        time_filter
    ).all()

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