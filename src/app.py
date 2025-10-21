# src/app.py
import os
from dotenv import load_dotenv
load_dotenv()
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session

from database import db_service
from database.db import SessionLocal
from services import bitrix_service, wazzup_service, llm_service
from utils import parse_form_data, normalize_phone

# --- ЗАГРУЗКА НАСТРОЕК ИЗ .ENV ---
TARGET_FUNNEL_ID = os.getenv("TARGET_FUNNEL_ID")
WELCOME_STAGE_ID = f"C{TARGET_FUNNEL_ID}:NEW"
TOUCH_TODAY_STAGE_ID = os.getenv("TOUCH_TODAY_STAGE_ID")
NEW_LOT_STAGE_ID = os.getenv("NEW_LOT_STAGE_ID")
NOMINALS_STAGE_ID = os.getenv("NOMINALS_STAGE_ID")
TEST_ACTIVITY_STAGE_ID = os.getenv("TEST_ACTIVITY_STAGE_ID")
TEST_FULL_ACTION_STAGE_ID = os.getenv("TEST_FULL_ACTION_STAGE_ID")

# --- ФОНОВЫЙ ПРОЦЕСС (WORKER) ---
async def process_pending_messages_worker():
    print("🚀 Воркер обработки сообщений запущен!")
    while True:
        try:
            db = SessionLocal()
            dialog_batches = db_service.get_and_clear_pending_dialogs(db, delay_seconds=10)
            for batch in dialog_batches:
                dialog = batch['dialog']
                pending = batch['pending']
                print(f"Обработка {len(pending)} сообщений для chat_id: {dialog.chat_id}")
                
                # Сохраняем все сообщения из пачки в основную историю
                for msg in pending:
                    db_service.add_message_to_history(db, dialog.chat_id, "user", msg['content'])

                # Получаем всю историю для контекста
                full_history = db_service.get_dialog_history(db, dialog.chat_id)

                # Генерируем ответ LLM
                ai_response = await llm_service.generate_manager_response(full_history, manager_name="Алексей")

                # Отправляем ответ и сохраняем его в историю
                if ai_response:
                    success = wazzup_service.send_message(dialog.chat_id, ai_response)
                    if success:
                        db_service.add_message_to_history(db, dialog.chat_id, "assistant", ai_response)
            db.close()
        except Exception as e:
            print(f"❌ ОШИБКА В ВОРКЕРЕ: {e}")
        await asyncio.sleep(5)

# --- УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ ПРИЛОЖЕНИЯ ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(process_pending_messages_worker())
    yield

# --- ИСПРАВЛЕНИЕ ЗДЕСЬ: СНАЧАЛА СОЗДАЕМ APP, ПОТОМ ПЕРЕДАЕМ LIFESPAN ---
app = FastAPI(title="Bitrix Wazzup Bot", lifespan=lifespan)
# --------------------------------------------------------------------

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

    current_funnel_id = deal_details.get("CATEGORY_ID")
    current_stage = deal_details.get("STAGE_ID")
    
    if current_funnel_id == TARGET_FUNNEL_ID:
        print(f"Сделка {deal_id} в нужной воронке. Стадия: {current_stage}")

        if current_stage == NOMINALS_STAGE_ID:
            print(f"⚠️ Сделка {deal_id} на стадии 'Номиналы'. Обработка прекращена.")
            return {"status": "ok", "message": "Ignored due to Nominals stage"}

        contact_id = int(deal_details.get("CONTACT_ID"))
        manager_id = int(deal_details.get("ASSIGNED_BY_ID"))
        client_name, manager_name = "Уважаемый клиент", "Ваш менеджер"
        contact_details = None

        if contact_id:
            contact_details = bitrix_service.get_contact_details(contact_id)
            if contact_details and contact_details.get("NAME"):
                client_name = contact_details.get("NAME")

        if manager_id:
            manager = bitrix_service.get_user_details(manager_id)
            if manager:
                full_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
                if full_name: manager_name = full_name
        
        message_to_send = None
        scenario_name = "Неизвестный"

        # --- РОУТЕР СЦЕНАРИЕВ ---
        if current_stage == WELCOME_STAGE_ID:
            scenario_name = "ПРИВЕТСТВИЕ"
            message_to_send = (f"Здравствуйте, {client_name}! Это {manager_name}, ваш менеджер по сопровождению...")
        elif current_stage == TOUCH_TODAY_STAGE_ID:
            scenario_name = "КАСАНИЕ СЕГОДНЯ"
            message_to_send = (f"Здравствуйте, {client_name}! Это {manager_name}. Как проходит работа по вашим текущим делам? ...")
        elif current_stage == NEW_LOT_STAGE_ID:
            scenario_name = "НОВЫЙ ЛОТ"
            latest_activity = bitrix_service.get_latest_activity_for_deal(deal_id)
            if latest_activity and latest_activity.get("DESCRIPTION"):
                lot_description = latest_activity.get("DESCRIPTION")
                message_to_send = (f"Здравствуйте, {client_name}! Это {manager_name}. У нас появились новые лоты по должнику: '{lot_description}'. ...")
            else:
                print(f"ОШИБКА СЦЕНАРИЯ: Сделка {deal_id} на стадии 'Новый лот', но нет дела с описанием.")
        elif current_stage == TEST_ACTIVITY_STAGE_ID:
            print(f"Тестовый триггер: Сделка {deal_id} перешла на стадию 'В ожидании'. Создаем дело...")
            if manager_id:
                subject = f"Тестовая задача от бота для сделки №{deal_id}"
                description = "Это тестовое дело, созданное автоматически для проверки функции эскалации."
                bitrix_service.create_activity_for_deal(deal_id=deal_id, responsible_id=manager_id, subject=subject, description=description)
        elif current_stage == TEST_FULL_ACTION_STAGE_ID:
            scenario_name = "КОМПЛЕКСНЫЙ ТЕСТ"
            reason_for_escalation = "Клиент задал сложный вопрос о юридических аспектах."
            print_formatted_message(scenario_name, deal_id, client_name, manager_name, "Запускаем проверку всех новых функций...")
            bitrix_service.add_comment_to_deal(deal_id, f"Тестовый комментарий от бота. Триггер: {scenario_name}.")
            if manager_id:
                bitrix_service.escalate_deal_to_manager(deal_id, manager_id, reason_for_escalation)

        # --- ЕДИНЫЙ БЛОК ОТПРАВКИ СООБЩЕНИЯ И СОХРАНЕНИЯ В БД ---
        if message_to_send:
            print_formatted_message(scenario_name, deal_id, client_name, manager_name, message_to_send)
            
            if contact_details and contact_details.get("PHONE"):
                phone_info = contact_details["PHONE"][0]
                raw_phone_number = phone_info.get("VALUE")
                phone_number = normalize_phone(raw_phone_number)
                print(f"Найден и нормализован номер клиента: {phone_number}. Попытка отправки...")
                success = wazzup_service.send_message(phone_number, message_to_send)
                if success:
                    db_service.add_message_to_history(db, phone_number, "assistant", message_to_send)
            else:
                print(f"⚠️ Не удалось отправить сообщение: у контакта для сделки {deal_id} не найден номер телефона.")

    return {"status": "ok", "message": "Webhook processed"}

# --- ОБЛЕГЧЕННЫЙ ОБРАБОТЧИК ВЕБХУКОВ WAZZUP ---
@app.post("/webhook/wazzup")
async def handle_wazzup_webhook(request: Request, db: Session = Depends(get_db)):
    print(">>> Получен вебхук от Wazzup, добавляю в очередь...")
    data = await request.json()
    
    if data.get("test") is True: return {"status": "ok"}
    if "messages" not in data or not data["messages"]: return {"status": "ok"}
    
    first_message = data["messages"][0]
    if first_message.get("isEcho") is True: 
        print("   Это наше собственное 'эхо'-сообщение. Игнорируем.")
        return {"status": "ok", "message": "Echo message ignored"}

    client_text = first_message.get("text")
    raw_client_phone = first_message.get("chatId")
    
    if client_text and raw_client_phone:
        client_phone = normalize_phone(raw_client_phone)
        db_service.add_pending_message(db, client_phone, client_text)
    
    return {"status": "ok"}

def print_formatted_message(scenario: str, deal_id, client_name, manager_name, message: str):
    print("="*50)
    print(f"✅ СЦЕНАРИЙ '{scenario}' ДЛЯ СДЕЛКИ {deal_id}")
    print(f"  - Клиент: {client_name}")
    print(f"  - Менеджер: {manager_name}")
    print("\n--- ГОТОВЫЙ ТЕКСТ ДЛЯ WAZZUP ---")
    print(message)
    print("="*50)