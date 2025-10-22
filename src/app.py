# src/app.py
import os
from dotenv import load_dotenv
load_dotenv()
import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session

from database import db_service
from database.db import SessionLocal
from services import bitrix_service, wazzup_service, llm_service, prompt_service
from utils import parse_form_data, normalize_phone

# --- ЗАГРУЗКА НАСТРОЕК ИЗ .ENV ---
# ID воронки "Постоянные" (согласно вашему .env)
TARGET_FUNNEL_ID = os.getenv("TARGET_FUNNEL_ID") 
# Первая стадия в этой воронке, которая будет триггером
WELCOME_STAGE_ID = f"C{TARGET_FUNNEL_ID}:NEW" 
NEW_LOT_STAGE_ID = os.getenv("NEW_LOT_STAGE_ID")
TOUCH_TODAY_STAGE_ID = os.getenv("TOUCH_TODAY_STAGE_ID")

async def process_pending_messages_worker():
    print("🚀 Воркер-ДИСПЕТЧЕР запущен!")
    while True:
        try:
            db = SessionLocal()
            # Забираем из БД диалоги, которые ждут обработки
            dialog_batches = db_service.get_and_clear_pending_dialogs(db, delay_seconds=10)
            
            for batch in dialog_batches:
                dialog = batch['dialog']
                pending_messages = batch['pending']
                
                # Проверяем, не находится ли диалог в "замороженном" состоянии
                if dialog.current_state == 'escalated':
                    print(f"Диалог {dialog.chat_id} находится в состоянии 'escalated'. Обработка прекращена.")
                    continue

                print(f"Обработка {len(pending_messages)} сообщений для chat_id: {dialog.chat_id} в состоянии '{dialog.current_state}'")

                # --- 1. ПОДГОТОВКА КОНТЕКСТА ---
                # Получаем текущую историю и добавляем к ней новые сообщения от клиента
                current_history = db_service.get_dialog_history(db, dialog.chat_id)
                for msg in pending_messages:
                    current_history.append({"role": "user", "content": msg['content']})

                # --- 2. ПОЛУЧЕНИЕ РЕШЕНИЯ ОТ LLM ---
                prompt_library = prompt_service.get_prompt_library()
                # --- ИЗМЕНЕНИЕ: Склеиваем все значения из библиотеки в один большой текст ---
                all_prompts_text = "\n\n".join(prompt_library.values())
                
                # Отправляем весь контекст "мозгу" с полным промптом
                llm_decision = await llm_service.get_bot_decision(current_history, all_prompts_text)


                if not llm_decision:
                    print(f"❌ LLM не вернул решение для диалога {dialog.chat_id}. Пропускаем.")
                    continue

                # --- 3. РАЗБОР И ИСПОЛНЕНИЕ КОМАНД ---
                response_text = llm_decision.get("response_text")
                action = llm_decision.get("action")
                action_params = llm_decision.get("action_params", {})
                new_state = llm_decision.get("new_state", dialog.current_state)

                # Получаем ID сделки и менеджера, сохраненные в диалоге
                deal_id = dialog.deal_id
                manager_id = dialog.manager_id

                if not deal_id or not manager_id:
                    print(f"КРИТИЧЕСКАЯ ОШИБКА: В диалоге {dialog.chat_id} отсутствуют deal_id или manager_id. Невозможно выполнить CRM-действие.")
                    continue

                # --- ШАГ 3.1: ОТПРАВКА СООБЩЕНИЯ КЛИЕНТУ ---
                if response_text:
                    success = wazzup_service.send_message(dialog.chat_id, response_text)
                    if success:
                        # Добавляем ответ бота в историю для следующего шага
                        current_history.append({"role": "assistant", "content": response_text})

                # --- ШАГ 3.2: ВЫПОЛНЕНИЕ ДЕЙСТВИЙ В CRM ---
                comment = action_params.get("comment_text")
                task_subject = action_params.get("task_subject")
                task_desc = action_params.get("task_description")

                print(f"  - Действие для CRM: {action}")

                if action == "LOG_COMMENT" and comment:
                    bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот]: {comment}")
                
                elif action == "CREATE_TASK_AND_LOG":
                    if comment: bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот]: {comment}")
                    if task_desc and task_subject: 
                        bitrix_service.create_activity_for_deal(deal_id, manager_id, task_subject, task_desc)

                elif action == "ESCALATE_TO_MANAGER":
                    reason = comment or "Причина эскалации не указана."
                    bitrix_service.escalate_deal_to_manager(deal_id, manager_id, reason)

                # --- 4. ОБНОВЛЕНИЕ ДИАЛОГА В БД ---
                # Сохраняем новое состояние и всю обновленную историю
                db_service.update_dialog(db, dialog.chat_id, new_state, current_history)
                print(f"  - Диалог {dialog.chat_id} переведен в состояние '{new_state}'.")
            
            db.close() # Закрываем сессию после обработки всей пачки
        except Exception as e:
            # Используем traceback для более детального логгирования ошибки
            import traceback
            print(f"❌❌❌ КРИТИЧЕСКАЯ ОШИБКА В ВОРКЕРЕ: {e}")
            traceback.print_exc()
        
        # Пауза перед следующей проверкой очереди
        await asyncio.sleep(5)

# --- УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ ПРИЛОЖЕНИЯ ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Приложение запускается...")
    worker_task = asyncio.create_task(process_pending_messages_worker())
    yield
    print("Приложение останавливается...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        print("Воркер успешно остановлен.")

app = FastAPI(title="Bitrix Wazzup Bot", lifespan=lifespan)

# --- ЗАВИСИМОСТЬ ДЛЯ ПОЛУЧЕНИЯ СЕССИИ БД ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Bot is running"}



# --- ОБНОВЛЕННЫЙ ОБРАБОТЧИК ВЕБХУКОВ BITRIX24 ---
@app.post("/webhook/bitrix")
async def handle_bitrix_webhook(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    data = parse_form_data(form_data)
    
    if data.get("event") != "ONCRMDEALUPDATE":
        return {"status": "ok", "message": "Event ignored"}

    deal_id = int(data.get("data", {}).get("FIELDS", {}).get("ID"))
    if not deal_id: return {"status": "error", "message": "No deal ID"}
    
    deal_details = bitrix_service.get_deal_details(deal_id)
    if not deal_details: return {"status": "error", "message": "Failed to get deal details"}

    current_funnel_id = str(deal_details.get("CATEGORY_ID"))
    current_stage = deal_details.get("STAGE_ID")
    
    # --- Сценарий №1: Приветствие на стадии NEW ---
    if current_funnel_id == TARGET_FUNNEL_ID and current_stage == WELCOME_STAGE_ID:
        print(f"✅✅✅ ТРИГГЕР СЦЕНАРИЯ №1 СРАБОТАЛ: Сделка {deal_id} перешла на стадию '{WELCOME_STAGE_ID}'.")

        # --- Сбор данных ---
        contact_id = int(deal_details.get("CONTACT_ID"))
        manager_id = int(deal_details.get("ASSIGNED_BY_ID"))
        
        contact_details = bitrix_service.get_contact_details(contact_id)
        if not (contact_details and contact_details.get("PHONE")):
            print(f"⚠️ ОСТАНОВКА: У контакта {contact_id} для сделки {deal_id} нет номера телефона.")
            return {"status": "ok", "message": "Contact has no phone number"}
        
        client_name = contact_details.get("NAME", "Уважаемый клиент")
        client_phone = normalize_phone(contact_details["PHONE"][0].get("VALUE"))
        manager = bitrix_service.get_user_details(manager_id)
        manager_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip() if manager else "Ваш менеджер"
        
        print(f"  - Клиент: {client_name} ({client_phone})")
        print(f"  - Менеджер: {manager_name} ({manager_id})")

        # --- Запуск LLM ---
        initial_instruction = {
            "role": "system",
            "content": f"initiate_dialog. ИМЯ_КЛИЕНТА: {client_name}. ИМЯ_МЕНЕДЖЕРА: {manager_name}."
        }
        prompt_library = prompt_service.get_prompt_library()
        all_prompts_text = "\n\n".join(prompt_library.values())
        llm_decision = await llm_service.get_bot_decision([initial_instruction], all_prompts_text)

        if not llm_decision:
            print(f"❌ ОСТАНОВКА: LLM не вернул решение для инициации диалога по сделке {deal_id}.")
            return {"status": "error", "message": "LLM failed to provide initial decision"}
        
        # --- Исполнение и сохранение (общий блок) ---
        response_text = llm_decision.get("response_text")
        action = llm_decision.get("action")
        action_params = llm_decision.get("action_params", {})
        new_state = llm_decision.get("new_state")
        
        if response_text:
            success = wazzup_service.send_message(client_phone, response_text)
            if not success:
                bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот] Ошибка! Не удалось отправить сообщение на номер {client_phone}.")
                return {"status": "ok", "message": "Wazzup send failed"}
        
        if action == "LOG_COMMENT" and action_params.get("comment_text"):
            bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот]: {action_params['comment_text']}")

        dialog = db_service.get_or_create_dialog(db, client_phone, deal_id, manager_id, current_funnel_id)
        # Загружаем существующую историю и ДОБАВЛЯЕМ в нее новое сообщение
        current_history = db_service.get_dialog_history(db, client_phone)
        if response_text:
            current_history.append({"role": "assistant", "content": response_text})
        db_service.update_dialog(db, client_phone, new_state, current_history)
        print(f"✅ Сценарий №1 для сделки {deal_id} успешно запущен.")

    # --- Сценарий №2: Уведомление о новом лоте ---
    elif current_funnel_id == TARGET_FUNNEL_ID and current_stage == NEW_LOT_STAGE_ID:
        print(f"✅✅✅ ТРИГГЕР СЦЕНАРИЯ №2 СРАБОТАЛ: Сделка {deal_id} перешла на стадию 'Новый лот' ({NEW_LOT_STAGE_ID}).")
        
        # --- Сбор данных ---
        contact_id = int(deal_details.get("CONTACT_ID"))
        manager_id = int(deal_details.get("ASSIGNED_BY_ID"))
        contact_details = bitrix_service.get_contact_details(contact_id)
        
        if not (contact_details and contact_details.get("PHONE")):
            print(f"⚠️ ОСТАНОВКА: У контакта {contact_id} нет номера телефона.")
            return {"status": "ok", "message": "Contact has no phone number"}
        
        client_name = contact_details.get("NAME", "Уважаемый клиент")
        client_phone = normalize_phone(contact_details["PHONE"][0].get("VALUE"))
        manager = bitrix_service.get_user_details(manager_id)
        manager_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip() if manager else "Ваш менеджер"
        
        latest_activity = bitrix_service.get_latest_activity_for_deal(deal_id)
        if not latest_activity or not latest_activity.get("DESCRIPTION"):
            print(f"⚠️ ОСТАНОВКА: Не найдено дело с описанием для сделки {deal_id}.")
            bitrix_service.add_comment_to_deal(deal_id, "[Чат-бот] Ошибка: не удалось запустить сценарий 'Новый лот', т.к. к сделке не привязано дело с описанием.")
            return {"status": "ok", "message": "No activity with description"}
        
        debtor_name_info = latest_activity["DESCRIPTION"]
        
        print(f"  - Клиент: {client_name} ({client_phone})")
        print(f"  - Менеджер: {manager_name} ({manager_id})")
        print(f"  - Инфо о лоте: {debtor_name_info}")

        # --- Запуск LLM ---
        initial_instruction = {
            "role": "system",
            "content": f"initiate_new_lot_dialog. ИМЯ_КЛИЕНТА: {client_name}. ИМЯ_МЕНЕДЖЕРА: {manager_name}. НАЗВАНИЕ_ДОЛЖНИКА: {debtor_name_info}."
        }
        prompt_library = prompt_service.get_prompt_library()
        all_prompts_text = "\n\n".join(prompt_library.values())
        llm_decision = await llm_service.get_bot_decision([initial_instruction], all_prompts_text)
        
        if not llm_decision:
            print(f"❌ ОСТАНОВКА: LLM не вернул решение для сценария 'Новый лот' по сделке {deal_id}.")
            return {"status": "error", "message": "LLM failed"}

        # --- Исполнение и сохранение (общий блок) ---
        response_text = llm_decision.get("response_text")
        action = llm_decision.get("action")
        action_params = llm_decision.get("action_params", {})
        new_state = llm_decision.get("new_state")
        
        if response_text:
            success = wazzup_service.send_message(client_phone, response_text)
            if not success:
                bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот] Ошибка! Не удалось отправить сообщение на номер {client_phone}.")
                return {"status": "ok", "message": "Wazzup send failed"}
        
        if action == "LOG_COMMENT" and action_params.get("comment_text"):
            bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот]: {action_params['comment_text']}")

        dialog = db_service.get_or_create_dialog(db, client_phone, deal_id, manager_id, current_funnel_id)
        # Загружаем существующую историю и ДОБАВЛЯЕМ в нее новое сообщение
        current_history = db_service.get_dialog_history(db, client_phone)
        if response_text:
            current_history.append({"role": "assistant", "content": response_text})
        db_service.update_dialog(db, client_phone, new_state, current_history)
        print(f"✅ Сценарий 'Новый лот' для сделки {deal_id} успешно запущен.")

    # --- Сценарий №3: Касание сегодня ---
    elif current_funnel_id == TARGET_FUNNEL_ID and current_stage == TOUCH_TODAY_STAGE_ID:
        print(f"✅✅✅ ТРИГГЕР СЦЕНАРИЯ №3 СРАБОТАЛ: Сделка {deal_id} перешла на стадию 'Касание сегодня' ({TOUCH_TODAY_STAGE_ID}).")
        
        # --- Сбор данных ---
        contact_id = int(deal_details.get("CONTACT_ID"))
        manager_id = int(deal_details.get("ASSIGNED_BY_ID"))
        contact_details = bitrix_service.get_contact_details(contact_id)
        
        if not (contact_details and contact_details.get("PHONE")):
            print(f"⚠️ ОСТАНОВКА: У контакта {contact_id} нет номера телефона.")
            return {"status": "ok", "message": "Contact has no phone number"}
        
        client_name = contact_details.get("NAME", "Уважаемый клиент")
        client_phone = normalize_phone(contact_details["PHONE"][0].get("VALUE"))
        manager = bitrix_service.get_user_details(manager_id)
        manager_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip() if manager else "Ваш менеджер"
        
        print(f"  - Клиент: {client_name} ({client_phone})")
        print(f"  - Менеджер: {manager_name} ({manager_id})")

        # --- Запуск LLM ---
        initial_instruction = {
            "role": "system",
            "content": f"initiate_touch_today_dialog. ИМЯ_КЛИЕНТА: {client_name}. ИМЯ_МЕНЕДЖЕРА: {manager_name}."
        }
        prompt_library = prompt_service.get_prompt_library()
        all_prompts_text = "\n\n".join(prompt_library.values())
        llm_decision = await llm_service.get_bot_decision([initial_instruction], all_prompts_text)
        
        if not llm_decision:
            print(f"❌ ОСТАНОВКА: LLM не вернул решение для сценария 'Касание сегодня' по сделке {deal_id}.")
            return {"status": "error", "message": "LLM failed"}

        # --- Исполнение и сохранение (общий блок) ---
        response_text = llm_decision.get("response_text")
        action = llm_decision.get("action")
        action_params = llm_decision.get("action_params", {})
        new_state = llm_decision.get("new_state")
        
        if response_text:
            success = wazzup_service.send_message(client_phone, response_text)
            if not success:
                bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот] Ошибка! Не удалось отправить сообщение на номер {client_phone}.")
                return {"status": "ok", "message": "Wazzup send failed"}
        
        if action == "LOG_COMMENT" and action_params.get("comment_text"):
            bitrix_service.add_comment_to_deal(deal_id, f"[Чат-бот]: {action_params['comment_text']}")

        dialog = db_service.get_or_create_dialog(db, client_phone, deal_id, manager_id, current_funnel_id)
        # Загружаем существующую историю и ДОБАВЛЯЕМ в нее новое сообщение
        current_history = db_service.get_dialog_history(db, client_phone)
        if response_text:
            current_history.append({"role": "assistant", "content": response_text})
        db_service.update_dialog(db, client_phone, new_state, current_history)
        print(f"✅ Сценарий 'Касание сегодня' для сделки {deal_id} успешно запущен.")

    return {"status": "ok", "message": "Webhook processed"}


# --- ОБРАБОТЧИК WAZZUP (без изменений) ---
@app.post("/webhook/wazzup")
async def handle_wazzup_webhook(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    if data.get("test") is True: return {"status": "ok"}
    if "messages" not in data or not data["messages"]: return {"status": "ok"}
    
    message = data["messages"][0]
    if message.get("isEcho"): return {"status": "ok"}

    text = message.get("text")
    chat_id = message.get("chatId")
    
    if text and chat_id:
        normalized_phone = normalize_phone(chat_id)
        db_service.add_pending_message(db, normalized_phone, text)
        print(f">>> Сообщение от {normalized_phone} добавлено в очередь.")
    
    return {"status": "ok"}