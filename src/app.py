# src/app.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()

from services import bitrix_service
from utils import parse_form_data

# --- ЗАГРУЖАЕМ ВСЕ НАШИ НАСТРОЙКИ ИЗ .ENV ---
TARGET_FUNNEL_ID = os.getenv("TARGET_FUNNEL_ID")
# ID стадии для приветствия (первая стадия в воронке)
WELCOME_STAGE_ID = f"C{TARGET_FUNNEL_ID}:NEW" 
# ID для сценария "Касание сегодня"
TOUCH_TODAY_STAGE_ID = os.getenv("TOUCH_TODAY_STAGE_ID")
# ID для сценария "Новый лот"
NEW_LOT_STAGE_ID = os.getenv("NEW_LOT_STAGE_ID")


app = FastAPI(title="Bitrix Wazzup Bot")

@app.get("/")
def read_root(): return {"status": "ok", "message": "Bot is running"}

@app.post("/webhook/bitrix")
async def handle_bitrix_webhook(request: Request):
    form_data = await request.form()
    data = parse_form_data(form_data)
    
    if data.get("event") != "ONCRMDEALUPDATE":
        return {"status": "ok", "message": "Event ignored"}

    deal_id = data.get("data", {}).get("FIELDS", {}).get("ID")
    if not deal_id: return {"status": "error", "message": "No deal ID"}
    
    deal_details = bitrix_service.get_deal_details(deal_id)
    if not deal_details: return {"status": "error", "message": "Failed to get deal details"}

    current_funnel_id = deal_details.get("CATEGORY_ID")
    current_stage = deal_details.get("STAGE_ID")
    
    # --- ГЛАВНАЯ ЛОГИКА: РАБОТАЕМ ТОЛЬКО ВНУТРИ ЦЕЛЕВОЙ ВОРОНКИ ---
    if current_funnel_id == TARGET_FUNNEL_ID:
        print(f"Сделка {deal_id} в нужной воронке. Стадия: {current_stage}")

        # --- Собираем данные для персонализации (они нужны для всех сценариев) ---
        contact_id = deal_details.get("CONTACT_ID")
        manager_id = deal_details.get("ASSIGNED_BY_ID")
        client_name, manager_name = "Уважаемый клиент", "Ваш менеджер"
        if contact_id:
            contact = bitrix_service.get_contact_details(contact_id)
            if contact and contact.get("NAME"): client_name = contact.get("NAME")
        if manager_id:
            manager = bitrix_service.get_user_details(manager_id)
            if manager:
                full_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
                if full_name: manager_name = full_name

        # --- РОУТЕР СЦЕНАРИЕВ: ВЫБИРАЕМ ДЕЙСТВИЕ В ЗАВИСИМОСТИ ОТ СТАДИИ ---

        # Сценарий 1: Приветствие при переходе в воронку
        if current_stage == WELCOME_STAGE_ID:
            message = (f"Здравствуйте, {client_name}! Это {manager_name}, ваш менеджер по сопровождению...") # Сокращено для примера
            print_formatted_message("ПРИВЕТСТВИЕ", deal_id, client_name, manager_name, message)

        # Сценарий 2: "Касание сегодня"
        elif current_stage == TOUCH_TODAY_STAGE_ID:
            message = (f"Здравствуйте, {client_name}! Это {manager_name}. Как проходит работа по вашим текущим делам? "
                       f"Если есть новые должники или вопросы, сообщите. "
                       f"Также напоминаем о возможности привлечения ваших коллег по программе «Приведи друга».")
            print_formatted_message("КАСАНИЕ СЕГОДНЯ", deal_id, client_name, manager_name, message)

        # Сценарий 3: "Новый лот/должник"
        elif current_stage == NEW_LOT_STAGE_ID:
            deal_title = deal_details.get("TITLE", "название должника не указано")
            message = (f"Здравствуйте, {client_name}! Это {manager_name}. У нас появились новые лоты по {deal_title}. "
                       f"Расскажите пожалуйста, можем ли мы поработать по данному должнику? "
                       f"Я могу прямо сейчас оформить заявку на открытие спецсчетов.")
            print_formatted_message("НОВЫЙ ЛОТ", deal_id, client_name, manager_name, message)
            
    return {"status": "ok", "message": "Webhook processed"}


def print_formatted_message(scenario: str, deal_id, client_name, manager_name, message: str):
    """Вспомогательная функция для красивого вывода в консоль"""
    print("="*50)
    print(f"✅ СЦЕНАРИЙ '{scenario}' ДЛЯ СДЕЛКИ {deal_id}")
    print(f"  - Клиент: {client_name}")
    print(f"  - Менеджер: {manager_name}")
    print("\n--- ГОТОВЫЙ ТЕКСТ ДЛЯ WAZZUP ---")
    print(message)
    print("="*50)